import json
import csv
import sys
from pathlib import Path
from shapely.geometry import shape
from shapely.ops import unary_union
import argparse


def load_geojson(filepath):
    """Load and parse a GeoJSON file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File {filepath} not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from {filepath}: {e}")
        sys.exit(1)


def create_municipal_exclusion_zones(municipalities_data):
    """
    Create a unified geometry of all municipal boundaries except for 
    Anaconda-Deer Lodge and Butte-Silver Bow.
    """
    exclusion_polygons = []
    
    for feature in municipalities_data['features']:
        name = feature['properties'].get('NAME', '')
        
        # skip the two exceptions — unified county/city gov would exclude all roads in the county
        if name in ['Anaconda-Deer Lodge', 'Butte-Silver Bow']:
            print(f"Keeping segments within: {name}")
            continue
            
        # convert geometry to shapely object
        try:
            geom = shape(feature['geometry'])
            if not geom.is_valid:
                print(f"Warning: Invalid geometry for municipality {name}, attempting to fix...")
                # fix invalid geometry using buffer(0) — Billings, Bozeman, Troy, Whitefish etc. broken
                geom = geom.buffer(0)
                if geom.is_valid:
                    print(f"Successfully fixed geometry for municipality {name}")
                else:
                    print(f"Could not fix geometry for municipality {name}, skipping")
                    continue
            
            exclusion_polygons.append(geom)
        except Exception as e:
            print(f"Warning: Could not process geometry for municipality {name}: {e}")
    
    if not exclusion_polygons:
        print("Warning: No valid exclusion zones found")
        return None
    
    try:
        exclusion_zone = unary_union(exclusion_polygons)
        print(f"Created exclusion zone from {len(exclusion_polygons)} municipalities")
        return exclusion_zone
    except Exception as e:
        print(f"Error creating exclusion zone: {e}")
        return None


def segment_intersects_exclusion_zone(segment_geom, exclusion_zone):
    """Check if a road segment intersects with the exclusion zone."""
    if exclusion_zone is None:
        return False
    
    try:
        # convert segment geometry to shapely LineString
        line = shape(segment_geom)
        
        # check if the line intersects with the exclusion zone
        return line.intersects(exclusion_zone)
    except Exception as e:
        print(f"Warning: Error checking intersection: {e}")
        return False


def filter_traffic_segments(traffic_data, exclusion_zone):
    """Filter traffic segments to exclude those within municipal boundaries."""
    filtered_features = []
    excluded_count = 0
    
    for feature in traffic_data['features']:
        segment_key = feature['properties'].get('SEGMENT_KEY', 'Unknown')
        
        intersects = segment_intersects_exclusion_zone(feature['geometry'], exclusion_zone)
        if intersects:
            excluded_count += 1
            print(f"Excluding segment: {segment_key}")
        else:
            filtered_features.append(feature)
    
    print(f"Excluded {excluded_count} segments within municipal boundaries")
    print(f"Kept {len(filtered_features)} segments outside municipal boundaries")
    
    return {
        'type': 'FeatureCollection',
        'features': filtered_features
    }


def calculate_weighted_average(filtered_data):
    """Calculate SEC_LNT_MI weighted average of PER_100M_VMT."""
    total_weighted_vmt = 0.0
    total_length = 0.0
    
    for feature in filtered_data['features']:
        props = feature['properties']
        
        try:
            sec_lnt_mi = float(props.get('SEC_LNT_MI', 0))
            per_100m_vmt = float(props.get('PER_100M_VMT', 0))
            
            if sec_lnt_mi > 0 and per_100m_vmt > 0:
                total_weighted_vmt += sec_lnt_mi * per_100m_vmt
                total_length += sec_lnt_mi
        except (ValueError, TypeError) as e:
            segment_key = props.get('SEGMENT_KEY', 'Unknown')
            print(f"Warning: Invalid numeric data for segment {segment_key}: {e}")
    
    if total_length > 0:
        weighted_average = total_weighted_vmt / total_length
        return weighted_average, total_length
    else:
        return 0.0, 0.0


def calculate_interstate_weighted_average(filtered_data):
    """Calculate weighted average but only for routes with SIGNED_ROUTE starting with 'I-'."""
    total_weighted_vmt = 0.0
    total_length = 0.0

    for feature in filtered_data['features']:
        props = feature['properties']
        route = props.get('SIGNED_ROUTE', '') or ''
        if not str(route).startswith('I-'):
            continue

        try:
            sec_lnt_mi = float(props.get('SEC_LNT_MI', 0))
            per_100m_vmt = float(props.get('PER_100M_VMT', 0))

            if sec_lnt_mi > 0 and per_100m_vmt > 0:
                total_weighted_vmt += sec_lnt_mi * per_100m_vmt
                total_length += sec_lnt_mi
        except (ValueError, TypeError):
            # ignore malformed numeric values for this calculation
            continue

    if total_length > 0:
        return total_weighted_vmt / total_length
    return 0.0


def calculate_noninterstate_weighted_average(filtered_data):
    """Calculate weighted average for routes that do NOT start with 'I-'."""
    total_weighted_vmt = 0.0
    total_length = 0.0

    for feature in filtered_data['features']:
        props = feature['properties']
        route = (props.get('SIGNED_ROUTE', '') or '')
        # treat empty/unknown routes as non-interstate only if they are explicit non-I values
        if str(route).startswith('I-'):
            continue

        try:
            sec_lnt_mi = float(props.get('SEC_LNT_MI', 0))
            per_100m_vmt = float(props.get('PER_100M_VMT', 0))

            if sec_lnt_mi > 0 and per_100m_vmt > 0:
                total_weighted_vmt += sec_lnt_mi * per_100m_vmt
                total_length += sec_lnt_mi
        except (ValueError, TypeError):
            continue

    if total_length > 0:
        return total_weighted_vmt / total_length
    return 0.0


def save_filtered_geojson(filtered_data, output_path):
    """Save filtered data as GeoJSON."""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(filtered_data, f, indent=2)
        print(f"Saved filtered GeoJSON to: {output_path}")
    except Exception as e:
        print(f"Error saving GeoJSON: {e}")


def save_properties_csv(filtered_data, output_path):
    """Save properties (without geometry) as CSV."""
    try:
        if not filtered_data['features']:
            print("Warning: No features to save to CSV")
            return
        
        # get all unique property keys
        all_keys = set()
        for feature in filtered_data['features']:
            all_keys.update(feature['properties'].keys())
        
        fieldnames = sorted(list(all_keys))
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for feature in filtered_data['features']:
                writer.writerow(feature['properties'])
        
        print(f"Saved properties CSV to: {output_path}")
    except Exception as e:
        print(f"Error saving CSV: {e}")


def main():
    parser = argparse.ArgumentParser(description='Filter traffic segments and calculate weighted averages')
    parser.add_argument('--municipalities', default='data/mt-municipalities-1m.geojson',
                       help='Path to municipalities GeoJSON file')
    parser.add_argument('--traffic', default='output/merged_data/merged_traffic_lines.geojson',
                       help='Path to traffic segments GeoJSON file')
    parser.add_argument('--output-dir', default='output/filtered_by_municipality',
                       help='Output directory for results')
    
    args = parser.parse_args()

    # ensure output directory exists - create if needed
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("Loading municipalities data...")
    municipalities_data = load_geojson(args.municipalities)
    
    print("Loading traffic segments data...")
    traffic_data = load_geojson(args.traffic)
    
    print("Creating municipal exclusion zones...")
    exclusion_zone = create_municipal_exclusion_zones(municipalities_data)
    
    print("Filtering traffic segments...")
    filtered_data = filter_traffic_segments(traffic_data, exclusion_zone)
    
    print("Calculating weighted average...")
    weighted_avg, total_length = calculate_weighted_average(filtered_data)
    
    # print results to console
    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    print(f"Total segments after filtering: {len(filtered_data['features'])}")
    print(f"Total road length (miles): {total_length:.2f}")
    print(f"SEC_LNT_MI weighted average PER_100M_VMT: {weighted_avg:.2f}")
    # Interstate-only weighted average
    interstate_avg = calculate_interstate_weighted_average(filtered_data)
    print(f"Interstate Crash rate avg: {interstate_avg:.2f}")
    noninterstate_avg = calculate_noninterstate_weighted_average(filtered_data)
    print(f"Non-Interstate Crash rate avg: {noninterstate_avg:.2f}")
    print("="*60)
    
    # outputs
    geojson_output = output_dir / 'filtered_traffic_segments.geojson'
    csv_output = output_dir / 'filtered_traffic_properties.csv'
    
    save_filtered_geojson(filtered_data, geojson_output)
    save_properties_csv(filtered_data, csv_output)
    
    # save stats
    summary_output = output_dir / 'traffic_analysis_summary.txt'
    try:
        with open(summary_output, 'w', encoding='utf-8') as f:
            f.write("Traffic Segment Analysis Summary\n")
            f.write("="*40 + "\n\n")
            f.write(f"Total segments after filtering: {len(filtered_data['features'])}\n")
            f.write(f"Total road length (miles): {total_length:.2f}\n")
            f.write(f"SEC_LNT_MI weighted average PER_100M_VMT: {weighted_avg:.2f}\n")
            f.write("\nExcluded municipalities (segments within these areas were removed):\n")
            
            excluded_munis = []
            for feature in municipalities_data['features']:
                name = feature['properties'].get('NAME', '')
                if name not in ['Anaconda-Deer Lodge', 'Butte-Silver Bow']:
                    excluded_munis.append(name)
            
            for name in sorted(excluded_munis):
                f.write(f"  - {name}\n")
            
            f.write("\nIncluded municipalities (segments within these areas were kept):\n")
            f.write("  - Anaconda-Deer Lodge\n")
            f.write("  - Butte-Silver Bow\n")
        
        print(f"Saved analysis summary to: {summary_output}")
    except Exception as e:
        print(f"Error saving summary: {e}")


if __name__ == "__main__":
    main()