from __future__ import annotations

import json
import os
import re
from math import floor
from typing import Dict



# single-file candidates
merged_traffic_simplified = os.path.join("output", "simplified-data", "merged_traffic_lines-1m.geojson")
on_system_routes = os.path.join("data", "mt-highways-1m.geojson")

# pick a simplified input from candidates
def find_simplified_input():
    # repository structure is fixed; return the single simplified candidate
    return on_system_routes
# max distance (meters) between sampled simplified point and nearest merged point to consider "close"
MAX_DISTANCE_M = 50.0
# max bearing difference (degrees) to consider same direction
MAX_BEARING_DIFF = 30.0
# fraction of sampled points that must match to consider the simplified line matched
MATCH_FRACTION = 0.25
OUTPUT_DIR = os.path.join("output", "mini_highways")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "mini_mt_highways-1m.json")


def refpt_to_float(ref: str) -> float:
    # convert '663+0.0150' to numeric 663.015 (float).

    if ref is None:
        return 0.0
    # common format: '663+0.0150' or '000+0.0000'
    m = re.match(r"^(\d+)\+(\d*\.?\d*)$", str(ref).strip())
    if m:
        major = int(m.group(1))
        minor = float(m.group(2)) if m.group(2) != "" else 0.0
        return major + minor
    # fallback: try float
    try:
        return float(ref)
    except Exception:
        return 0.0


def route_id_base(route_id: str) -> str:
    # strip trailing letter from ROUTE_ID like 'C000001A' -> 'C000001
    if not route_id:
        return ""
    # remove trailing alpha characters
    return re.sub(r"[A-Za-z]+$", "", route_id)


def load_geojson(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def haversine(lon1, lat1, lon2, lat2):
    # returns meters
    from math import radians, sin, cos, sqrt, atan2

    R = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def bearing(lon1, lat1, lon2, lat2):
    # returns degrees 0-360
    from math import radians, degrees, sin, cos, atan2

    lon1, lat1, lon2, lat2 = map(radians, (lon1, lat1, lon2, lat2))
    dlon = lon2 - lon1
    x = sin(dlon) * cos(lat2)
    y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    br = degrees(atan2(x, y))
    return (br + 360) % 360


def point_along_linestring(coords, fraction: float):
    # coords is list of [lon, lat]; fraction between 0 and 1
    if not coords:
        return None
    if fraction <= 0:
        return coords[0]
    if fraction >= 1:
        return coords[-1]
    # accumulate segment lengths (approx meters)
    seg_lengths = []
    total = 0.0
    for i in range(len(coords) - 1):
        a = coords[i]
        b = coords[i + 1]
        d = haversine(a[0], a[1], b[0], b[1])
        seg_lengths.append(d)
        total += d
    if total == 0:
        return coords[0]
    target = total * fraction
    acc = 0.0
    for i, seg in enumerate(seg_lengths):
        if acc + seg >= target:
            # interpolate
            remain = target - acc
            t = remain / seg if seg != 0 else 0
            a = coords[i]
            b = coords[i + 1]
            lon = a[0] + (b[0] - a[0]) * t
            lat = a[1] + (b[1] - a[1]) * t
            return [lon, lat]
        acc += seg
    return coords[-1]


def sample_points(coords, n=10):
    # return up to n sampled points along linestring (lon, lat)
    if not coords:
        return []
    if len(coords) == 1:
        return [coords[0]]
    pts = []
    for i in range(n):
        frac = i / (n - 1) if n > 1 else 0
        pt = point_along_linestring(coords, frac)
        if pt:
            pts.append(pt)
    return pts


def build_merged_point_index(merged_features):
    # build simple grid index (dict) mapping bin -> list of (lon, lat, bearing)
    # bin size is degrees; small enough to reduce candidates but coarse enough
    # to keep memory low.
    BIN_SIZE_DEG = 0.01  # ~1.1 km latitude
    from math import floor

    def to_bin(lon, lat):
        return (int(floor(lon / BIN_SIZE_DEG)), int(floor(lat / BIN_SIZE_DEG)))

    index = {}
    for f in merged_features:
        geom = f.get("geometry") or {}
        if geom.get("type") != "LineString":
            continue
        coords = geom.get("coordinates", [])
        # reduced sample density for large datasets
        pts = sample_points(coords, n=12)
        for i in range(len(pts) - 1):
            a = pts[i]
            b = pts[i + 1]
            br = bearing(a[0], a[1], b[0], b[1])
            bin_key = to_bin(a[0], a[1])
            index.setdefault(bin_key, []).append((a[0], a[1], br))
        if pts:
            if len(pts) >= 2:
                a = pts[-2]
                b = pts[-1]
                br = bearing(a[0], a[1], b[0], b[1])
            else:
                br = 0.0
            bin_key = to_bin(pts[-1][0], pts[-1][1])
            index.setdefault(bin_key, []).append((pts[-1][0], pts[-1][1], br))
    return {"bins": index, "bin_size": BIN_SIZE_DEG}


def point_matches_index(lon, lat, br, index, max_dist_m=MAX_DISTANCE_M, max_bearing_diff=MAX_BEARING_DIFF):
    # index is a dict with 'bins' and 'bin_size'
    bins = index.get("bins", {})
    bin_size = index.get("bin_size", 0.01)

    bx = int(floor(lon / bin_size))
    by = int(floor(lat / bin_size))

    # check neighboring bins (3x3) to cover small distances
    rng = 1
    for dx in range(-rng, rng + 1):
        for dy in range(-rng, rng + 1):
            key = (bx + dx, by + dy)
            if key not in bins:
                continue
            for ilon, ilat, ibr in bins[key]:
                d = haversine(lon, lat, ilon, ilat)
                if d <= max_dist_m:
                    diff = abs((br - ibr + 180) % 360 - 180)
                    if diff <= max_bearing_diff:
                        return True
    return False


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    merged_path = merged_traffic_simplified
    if not os.path.exists(merged_path):
        merged_path = os.path.join("output", "simplified_data", "merged_traffic_lines-1m.geojson")
         
    if not os.path.exists(merged_path):
        tried = [merged_traffic_simplified, merged_path]
        raise FileNotFoundError(f"Could not find merged traffic file; tried: {tried}")

    merged = load_geojson(merged_path)
    simplified_path = find_simplified_input()
    simplified = load_geojson(simplified_path)

    # Choose matching mode: 'geometry' for spatial matching, 'signed' for route-name
    MODE = "geometry"

    merged_features = merged.get("features", [])
    simplified_features = simplified.get("features", [])

    if MODE == "signed":
        merged_signed_routes = set()
        for f in merged_features:
            p = f.get("properties", {})
            signed = p.get("SIGNED_ROUTE")
            if signed is None:
                continue
            merged_signed_routes.add(str(signed).strip().upper())
    else:
        merged_point_index = build_merged_point_index(merged_features)

    kept = []
    removed_count = 0
    kept_count = 0

    for f in simplified_features:
        p = f.get("properties", {})

        if MODE == "signed":
            sign_route = p.get("SIGN_ROUTE")
            if sign_route is not None and str(sign_route).strip().upper() in merged_signed_routes:
                removed_count += 1
                continue
            kept.append(f)
            kept_count += 1
        else:
            geom = f.get("geometry") or {}
            if geom.get("type") != "LineString":
                # keep non-lines by default
                kept.append(f)
                kept_count += 1
                continue
            coords = geom.get("coordinates", [])
            samples = sample_points(coords, n=12)
            if not samples:
                kept.append(f)
                kept_count += 1
                continue
            match_hits = 0
            for i in range(len(samples) - 1):
                a = samples[i]
                b = samples[i + 1]
                br = bearing(a[0], a[1], b[0], b[1])
                if point_matches_index(a[0], a[1], br, merged_point_index):
                    match_hits += 1
            # also check last point
            if len(samples) >= 2:
                a = samples[-2]
                b = samples[-1]
                br = bearing(a[0], a[1], b[0], b[1])
                if point_matches_index(samples[-1][0], samples[-1][1], br, merged_point_index):
                    match_hits += 1

            frac = match_hits / max(1, len(samples))
            if frac >= MATCH_FRACTION:
                removed_count += 1
            else:
                kept.append(f)
                kept_count += 1

    out = {"type": "FeatureCollection", "features": kept}

    # write compact JSON (no indentation) to reduce file size
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))

    total_simplified = len(simplified_features)
    print(f"Total simplified features: {total_simplified}")
    print(f"Removed (matched) features: {removed_count}")
    print(f"Kept (unmatched) features: {kept_count}")

    # print input/output sizes for debugging
    try:
        in_size = os.path.getsize(simplified_path)
        out_size = os.path.getsize(OUTPUT_FILE)
        print(f"Input simplified file size: {in_size / 1024 / 1024:.2f} MB")
        print(f"Output mini file size: {out_size / 1024 / 1024:.2f} MB")
    except Exception:
        pass


if __name__ == "__main__":
    main()
