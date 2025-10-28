"""
Calculate length-weighted average crash rates (per 100M VMT) for different road categories.

Note: This data uses merged_traffic_lines.geojson that is output from `merge_traffic_accident.py`.
That means this is an analysis of all MT (including secondary), US and Interstate highways in Montana but does NOT include rural/local roads.

Categories:
1. All on system roads (regardless of in/out municipality)
2. All roads outside municipality limits
3. Non-interstates outside municipality limits
4. Interstates outside municipality limits
5. All roads inside municipality limits
6. Non-interstates inside municipality limits
7. Interstates inside municipality limits

Excludes Butte-Silver Bow and Anaconda-Deer Lodge (treated as outside municipalities).
"""

import json
from shapely.geometry import shape, MultiPolygon
from shapely.ops import unary_union
from typing import Dict, List, Tuple


def load_geojson(filepath: str) -> dict:
    """Load a GeoJSON file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def calculate_line_length_miles(coordinates: List[List[float]]) -> float:
    """
    Calculate the length of a LineString in miles using Haversine formula.
    Coordinates are in [lon, lat] format.
    """
    from math import radians, sin, cos, sqrt, atan2

    total_length = 0.0
    for i in range(len(coordinates) - 1):
        lon1, lat1 = coordinates[i]
        lon2, lat2 = coordinates[i + 1]

        # haversine formula
        R = 3958.8  # Earth's radius in miles

        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)
        delta_lat = radians(lat2 - lat1)
        delta_lon = radians(lon2 - lon1)

        a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * \
            cos(lat2_rad) * sin(delta_lon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        total_length += R * c

    return total_length


def is_interstate(segment_key: str) -> bool:
    """Check if a road segment is an interstate (has I- prefix)."""
    dept_id = segment_key.split('_')[-1] if '_' in segment_key else ""
    return dept_id.startswith('I-')


def create_municipality_union(municipalities_geojson: dict) -> MultiPolygon:
    """
    Create a union of all municipality polygons, excluding Butte-Silver Bow and Anaconda-Deer Lodge.
    """
    polygons = []
    excluded_names = ["Butte-Silver Bow", "Anaconda-Deer Lodge"]

    for feature in municipalities_geojson['features']:
        name = feature['properties'].get('NAME', '')
        if name not in excluded_names:
            try:
                geom = shape(feature['geometry'])
                # attempt to fix invalid geometries (some municipal polys are broken)
                if not geom.is_valid:
                    geom = geom.buffer(0)
                if geom.is_valid:
                    polygons.append(geom)
                else:
                    print(
                        f"Warning: Skipping invalid municipality geometry: {name}")
            except Exception as e:
                print(f"Warning: Could not process municipality {name}: {e}")

    print(
        f"Loaded {len(polygons)} municipalities (excluding Butte-Silver Bow and Anaconda-Deer Lodge)")

    # union of all municipality polygons
    if polygons:
        municipality_union = unary_union(polygons)
        return municipality_union
    return None


def categorize_segments(traffic_geojson: dict, municipality_union) -> Dict[str, List[dict]]:
    """
    Categorize road segments based on location (in/out of municipalities) and type (interstate/non-interstate).

    Returns a dictionary with keys:
    - 'all_outside'
    - 'non_interstate_outside'
    - 'interstate_outside'
    - 'all_inside'
    - 'non_interstate_inside'
    - 'interstate_inside'

    Each value is a list of dicts with keys: 'length_miles', 'crash_rate'
    """
    categories = {
        'all_outside': [],
        'non_interstate_outside': [],
        'interstate_outside': [],
        'all_inside': [],
        'non_interstate_inside': [],
        'interstate_inside': []
    }

    total_segments = len(traffic_geojson['features'])
    print(f"\nProcessing {total_segments} road segments...")

    for idx, feature in enumerate(traffic_geojson['features']):
        if idx % 1000 == 0:
            print(f"  Processed {idx}/{total_segments} segments...")

        properties = feature['properties']
        geometry = feature['geometry']

        # skip if missing required data
        if 'PER_100M_VMT' not in properties or properties['PER_100M_VMT'] is None:
            continue

        try:
            crash_rate = float(properties['PER_100M_VMT'])
        except (ValueError, TypeError):
            continue  # skip segments with invalid crash rate data

        segment_key = properties.get('SEGMENT_KEY', '')

        # prefer SEC_LNT_MI (official segment length) when present, otherwise fall back to geometry
        length_miles = None
        sec_lnt_val = None
        try:
            sec_lnt = properties.get('SEC_LNT_MI')
            if sec_lnt is not None and str(sec_lnt).strip() != '':
                sec_lnt_val = float(sec_lnt)
                length_miles = sec_lnt_val
        except (ValueError, TypeError):
            sec_lnt_val = None
            length_miles = None

        # ff no valid SEC_LNT_MI, compute from geometry
        if length_miles is None:
            if geometry['type'] == 'LineString':
                length_miles = calculate_line_length_miles(
                    geometry['coordinates'])
            else:
                continue  # skip non-LineString geometries

        # determine if interstate: prefer SIGNED_ROUTE if available, otherwise fall back to SEGMENT_KEY parsing
        signed_route = (properties.get('SIGNED_ROUTE') or '')
        if signed_route and str(signed_route).startswith('I-'):
            is_i = True
        else:
            is_i = is_interstate(segment_key)

        line_geom = shape(geometry)
        is_inside = False

        if municipality_union:
            try:
                is_inside = line_geom.intersects(municipality_union)
            except Exception as e:
                print(
                    f"Warning: Error checking intersection for segment {segment_key}: {e}")
                is_inside = False

        if crash_rate <= 0:
            continue

        total_crashes = 0
        for crash_key in ('TOTAL_CRASHES', 'TOTAL', 'TOTAL_CRASHES_5YR', 'TOTAL_CRASH'):
            val = properties.get(crash_key)
            if val is None:
                continue
            try:
                total_crashes = int(float(val))
                break
            except (ValueError, TypeError):
                continue

        # find AADT-like value
        aadt = 0.0
        for k in ("TYC_AADT", "AADT", "AVG_AADT", "TYC_AADT_EST", "EST_AADT"):
            v = properties.get(k)
            if v is None:
                continue
            try:
                aadt = float(v)
                if aadt > 0:
                    break
            except (ValueError, TypeError):
                continue

        # use SEC_LNT_MI for VMT calculation when available, otherwise fall back to computed length_miles
        sec_len_for_vmt = sec_lnt_val if sec_lnt_val is not None else length_miles
        daily_vmt = sec_len_for_vmt * \
            aadt if (sec_len_for_vmt is not None and aadt > 0) else 0.0

        # create segment data
        segment_data = {
            'length_miles': length_miles,
            'crash_rate': crash_rate,
            'segment_key': segment_key,
            'total_crashes': total_crashes,
            'daily_vmt': daily_vmt
        }

        # categorize
        if is_inside:
            categories['all_inside'].append(segment_data)
            if is_i:
                categories['interstate_inside'].append(segment_data)
            else:
                categories['non_interstate_inside'].append(segment_data)
        else:
            categories['all_outside'].append(segment_data)
            if is_i:
                categories['interstate_outside'].append(segment_data)
            else:
                categories['non_interstate_outside'].append(segment_data)

    print(f"  Processed {total_segments}/{total_segments} segments.")

    return categories


def calculate_weighted_average(segments: List[dict]) -> Tuple[float, float, float]:
    if not segments:
        return 0.0, 0.0, 0.0

    total_weighted_rate = 0.0
    total_length = 0.0

    for segment in segments:
        length = segment['length_miles']
        rate = segment['crash_rate']

        total_weighted_rate += rate * length
        total_length += length

    if total_length == 0:
        return 0.0, 0.0, 0.0

    weighted_avg = total_weighted_rate / total_length

    miles_per_crash = 100_000_000 / \
        weighted_avg if weighted_avg > 0 else float('inf')

    return weighted_avg, total_length, miles_per_crash


def main():
    # load data
    print("Loading GeoJSON files...")
    traffic_data = load_geojson(
        'output/merged_data/merged_traffic_lines.geojson')
    municipalities_data = load_geojson('data/mt-municipalities-1m.geojson')

    print("\nCreating municipality boundary union...")
    municipality_union = create_municipality_union(municipalities_data)
    categories = categorize_segments(traffic_data, municipality_union)
    print("\n" + "="*80)
    print("LENGTH-WEIGHTED AVERAGE CRASH RATES BY CATEGORY")
    print("="*80)

    category_names = {
        'all_outside': '1. All roads OUTSIDE municipality limits',
        'non_interstate_outside': '2. Non-interstates OUTSIDE municipality limits',
        'interstate_outside': '3. Interstates OUTSIDE municipality limits',
        'all_inside': '4. All roads INSIDE municipality limits',
        'non_interstate_inside': '5. Non-interstates INSIDE municipality limits',
        'interstate_inside': '6. Interstates INSIDE municipality limits'
    }

    results = {}

    for key, name in category_names.items():
        segments = categories[key]
        avg_rate, total_length, miles_per_crash = calculate_weighted_average(
            segments)
        results[key] = (avg_rate, total_length, miles_per_crash)

        print("\n" + name)
        print("  Number of segments: {}".format(len(segments)))
        # compute totals: total accidents and total daily miles
        total_accidents = sum(int(s.get('total_crashes', 0)) for s in segments)
        total_daily_miles = sum(float(s.get('daily_vmt', 0.0))
                                for s in segments)
        print(f"  Total accidents: {total_accidents:,}")
        print(f"  Total daily miles: {total_daily_miles:,.0f}")
        print(f"  Total road miles: {total_length:,.2f}")
        print(f"  Weighted avg crash rate: {avg_rate:.2f} per 100M VMT")
        if miles_per_crash != float('inf'):
            print(f"  Expected miles per crash: {miles_per_crash:,.0f} miles")
        else:
            print("  Expected miles per crash: N/A (no crashes)")

    # ------------------------------------------------------------------
    # Aggregate across ALL roads (ignore municipality split)
    # ------------------------------------------------------------------
    all_segments = categories['all_outside'] + categories['all_inside']
    all_avg_rate, all_total_length, all_miles_per_crash = calculate_weighted_average(
        all_segments)
    all_total_accidents = sum(int(s.get('total_crashes', 0))
                              for s in all_segments)
    all_total_daily_miles = sum(float(s.get('daily_vmt', 0.0))
                                for s in all_segments)

    print("\n" + "="*60)
    print("ALL ROADS (no municipality split)")
    print("="*60)
    print(f"  Number of segments: {len(all_segments)}")
    print(f"  Total accidents: {all_total_accidents:,}")
    print(f"  Total daily miles: {all_total_daily_miles:,.0f}")
    print(f"  Total road miles: {all_total_length:,.2f}")
    print(f"  Weighted avg crash rate: {all_avg_rate:.2f} per 100M VMT")
    if all_miles_per_crash != float('inf'):
        print(f"  Expected miles per crash: {all_miles_per_crash:,.0f} miles")
    else:
        print("  Expected miles per crash: N/A (no crashes)")

    # summary
    print("\n" + "="*80)
    print("SUMMARY COMPARISON")
    print("="*80)

    outside_all = results['all_outside']
    inside_all = results['all_inside']

    print("\nOUTSIDE municipalities:")
    print(f"  Total miles: {outside_all[1]:,.2f}")
    print(f"  Crash rate: {outside_all[0]:.2f} per 100M VMT")
    print(f"  Miles per crash: {outside_all[2]:,.0f}")

    print("\nINSIDE municipalities:")
    print(f"  Total miles: {inside_all[1]:,.2f}")
    print(f"  Crash rate: {inside_all[0]:.2f} per 100M VMT")
    print(f"  Miles per crash: {inside_all[2]:,.0f}")

    if inside_all[0] > 0 and outside_all[0] > 0:
        ratio = inside_all[0] / outside_all[0]
        print(f"\nCrash rate ratio (inside/outside): {ratio:.2f}x")
        if ratio > 1:
            print(
                f"  → Roads inside municipalities have {ratio:.1f}x HIGHER crash rates")
        else:
            print(
                f"  → Roads inside municipalities have {1/ratio:.1f}x LOWER crash rates")

    # Interstate vs Non-Interstate comparison
    print("\n" + "-"*80)
    print("INTERSTATE vs NON-INTERSTATE COMPARISON (Outside municipalities)")
    print("-"*80)

    interstate_out = results['interstate_outside']
    non_interstate_out = results['non_interstate_outside']

    print("\nInterstates:")
    print(f"  Crash rate: {interstate_out[0]:.2f} per 100M VMT")
    print(f"  Miles per crash: {interstate_out[2]:,.0f}")

    print("\nNon-interstates:")
    print(f"  Crash rate: {non_interstate_out[0]:.2f} per 100M VMT")
    print(f"  Miles per crash: {non_interstate_out[2]:,.0f}")

    if non_interstate_out[0] > 0 and interstate_out[0] > 0:
        ratio = non_interstate_out[0] / interstate_out[0]
        print(f"\nCrash rate ratio (non-interstate/interstate): {ratio:.2f}x")


if __name__ == '__main__':
    main()
