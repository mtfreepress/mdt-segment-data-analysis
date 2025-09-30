#!/usr/bin/env python3
"""
Create per-SIGNED_ROUTE GeoJSON files from merged output.

Usage:
  python individual_highways_merge.py --routes US-2,U-8133
  python individual_highways_merge.py --routes-file routes.txt

Output:
  Writes files to output/merged_data/individual_{SIGNED_ROUTE}.geojson

The produced GeoJSON uses the same feature structure and properties as
`output/merged_data/merged_traffic_lines.geojson`.
"""
import argparse
import json
import os
from typing import List


def load_merged_geojson(path='output/merged_data/merged_traffic_lines.geojson'):
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, 'r') as fh:
        return json.load(fh)


def normalize_signed(s):
    if s is None:
        return ''
    return str(s).strip()


# Default list of SIGNED_ROUTE strings so this module can be used directly from
# a REPL or imported by other scripts without passing routes via CLI. Edit this
# list as you like.
DEFAULT_ROUTES = {
    'flathead_area': ['MT-35', 'MT-82','MT-200/US-93' ],
    'helena': ['S-279', 'S-518'],
    'missoula_area': ['US-93', 'US-12'],
    'yellowstone': ['US-89', 'S-540', 'S-571'],
    'bozeman_pass': ['I-90'],
    'red_lodge': ['US-212', 'S-421']
}


def write_geojson_for_route(features, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as fh:
        json.dump({'type': 'FeatureCollection', 'features': features}, fh)


def routes_from_file(path) -> List[str]:
    with open(path, 'r') as fh:
        lines = [ln.strip() for ln in fh if ln.strip()]
    return lines


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--routes', help='Comma-separated list of SIGNED_ROUTE values', default='')
    p.add_argument('--routes-file', help='File with one SIGNED_ROUTE per line')
    p.add_argument('--group', help='Name for a combined output containing all routes passed to --routes')
    p.add_argument('--groups-file', help='JSON file mapping group_name -> [SIGNED_ROUTE, ...]')
    p.add_argument('--in', dest='input', help='Input merged geojson', default='output/merged_data/merged_traffic_lines.geojson')
    p.add_argument('--out-dir', help='Output directory', default='output/individual_roads')
    args = p.parse_args()

    routes = []
    if args.routes:
        routes = [r.strip() for r in args.routes.split(',') if r.strip()]
    if args.routes_file:
        routes.extend(routes_from_file(args.routes_file))
    # fallback to DEFAULT_ROUTES when none provided
    if not routes and not args.groups_file:
        routes = DEFAULT_ROUTES

    geo = load_merged_geojson(args.input)
    all_feats = geo.get('features', [])

    # build index by normalized SIGNED_ROUTE (exact matching)
    idx = {}
    for feat in all_feats:
        props = feat.get('properties', {})
        sr = normalize_signed(props.get('SIGNED_ROUTE'))
        idx.setdefault(sr, []).append(feat)

    # If groups-file provided, produce combined files per group
    if args.groups_file:
        with open(args.groups_file, 'r') as gf:
            groups = json.load(gf)
        for gname, groutes in groups.items():
            combined = []
            for rr in groutes:
                norm = normalize_signed(rr)
                combined.extend(idx.get(norm, []))
            out_name = f'individual_{gname.replace("/","_").replace(" ","_")}.geojson'
            out_path = os.path.join(args.out_dir, out_name)
            write_geojson_for_route(combined, out_path)
            print(f'Wrote {len(combined)} features for group "{gname}" to {out_path}')
        return

    # If DEFAULT_ROUTES is a dict and no CLI args for groups were provided,
    # produce combined files per default group and exit. This supports the
    # common use-case of embedding pre-defined groupings in DEFAULT_ROUTES.
    if not args.routes and not args.routes_file and not args.group and not args.groups_file and isinstance(DEFAULT_ROUTES, dict):
        for gname, groutes in DEFAULT_ROUTES.items():
            combined = []
            for rr in groutes:
                norm = normalize_signed(rr)
                combined.extend(idx.get(norm, []))
            out_name = f'individual_{gname.replace("/","_").replace(" ","_")}.geojson'
            out_path = os.path.join(args.out_dir, out_name)
            write_geojson_for_route(combined, out_path)
            print(f'Wrote {len(combined)} features for default group "{gname}" to {out_path}')
        return

    # If a single group name is supplied, produce one combined file from --routes
    if args.group:
        combined = []
        for r in routes:
            norm = normalize_signed(r)
            combined.extend(idx.get(norm, []))
        out_name = f'individual_{args.group.replace("/","_").replace(" ","_")}.geojson'
        out_path = os.path.join(args.out_dir, out_name)
        write_geojson_for_route(combined, out_path)
        print(f'Wrote {len(combined)} features for group "{args.group}" to {out_path}')
        return

    # default behavior: separate file per route
    for r in routes:
        norm = normalize_signed(r)
        feats = idx.get(norm, [])
        out_name = f'individual_{norm.replace("/","_").replace(" ","_")}.geojson'
        out_path = os.path.join(args.out_dir, out_name)
        write_geojson_for_route(feats, out_path)
        print(f'Wrote {len(feats)} features for route "{r}" to {out_path}')


if __name__ == '__main__':
    main()


def generate_individual_geojsons(routes=None, input_path='output/merged_data/merged_traffic_lines.geojson', out_dir='output/merged_data'):
    """Programmatic entrypoint: generate geojsons for the provided routes list.

    If routes is None, DEFAULT_ROUTES is used. This function mirrors the CLI
    behavior and returns a dict mapping route -> output path.
    """
    if routes is None:
        routes = DEFAULT_ROUTES

    geo = load_merged_geojson(input_path)
    all_feats = geo.get('features', [])
    idx = {}
    for feat in all_feats:
        props = feat.get('properties', {})
        sr = normalize_signed(props.get('SIGNED_ROUTE'))
        idx.setdefault(sr, []).append(feat)

    results = {}
    for r in routes:
        norm = normalize_signed(r)
        feats = idx.get(norm, [])
        out_name = f'individual_{norm.replace("/","_").replace(" ","_")}.geojson'
        out_path = os.path.join(out_dir, out_name)
        write_geojson_for_route(feats, out_path)
        results[r] = out_path
    return results
