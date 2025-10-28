import os
import json
import math
import numpy as np
import pandas as pd
import msgspec


def parse_milepost(mp_str):
    if pd.isna(mp_str):
        return None
    parts = str(mp_str).split('+')
    if len(parts) != 2:
        return None
    try:
        return float(parts[0].lstrip('0') or '0') + float(parts[1])
    except ValueError:
        return None


def load_base_segments_2023(base_csv='data/Traffic_Yearly_Counts_2023/TYC_2023.csv'):
    if not os.path.exists(base_csv):
        raise FileNotFoundError(base_csv)
    df = pd.read_csv(base_csv, dtype=str)
    df['CORR_ID'] = df['CORR_ID'].astype(str).str.strip().str.upper()
    df['DEPT_ID'] = df['DEPT_ID'].astype(str).str.strip().str.upper()
    df['SEGMENT_KEY'] = (df['CORR_ID'] + '_' + df['CORR_MP'] +
                         '_' + df['CORR_ENDMP'] + '_' + df['DEPT_ID'])
    df['CORR_MP_FLOAT'] = df['CORR_MP'].apply(parse_milepost)
    df['CORR_ENDMP_FLOAT'] = df['CORR_ENDMP'].apply(parse_milepost)
    df['TYC_AADT'] = pd.to_numeric(df.get('TYC_AADT', ''), errors='coerce')
    df['YEARS_WITH_DATA'] = 1
    return df


def calculate_averaged_traffic(base_df, years=[2023, 2022, 2021, 2020, 2019]):
    # aggregate TYC_AADT by SEGMENT_KEY across years and compute mean and count
    parts = []
    # include base year from base_df
    parts.append(base_df[['SEGMENT_KEY', 'TYC_AADT']].copy())
    for year in years[1:]:
        csv_path = f'data/Traffic_Yearly_Counts_{year}/TYC_{year}.csv'
        if not os.path.exists(csv_path):
            continue
        ydf = pd.read_csv(csv_path, dtype=str)
        ydf['CORR_ID'] = ydf['CORR_ID'].astype(str).str.strip().str.upper()
        ydf['DEPT_ID'] = ydf['DEPT_ID'].astype(str).str.strip().str.upper()
        ydf['SEGMENT_KEY'] = (ydf['CORR_ID'] + '_' + ydf['CORR_MP'] +
                              '_' + ydf['CORR_ENDMP'] + '_' + ydf['DEPT_ID'])
        ydf['TYC_AADT'] = pd.to_numeric(
            ydf.get('TYC_AADT', ''), errors='coerce')
        parts.append(ydf[['SEGMENT_KEY', 'TYC_AADT']])

    if not parts:
        return base_df

    all_years = pd.concat(parts, ignore_index=True)
    agg = all_years.groupby('SEGMENT_KEY', sort=False)['TYC_AADT'].agg(['mean', 'count']).rename(
        columns={'mean': 'TYC_AADT_MEAN', 'count': 'YEARS_WITH_DATA'}).reset_index()

    merged = base_df.merge(agg, on='SEGMENT_KEY', how='left')
    merged['TYC_AADT'] = merged['TYC_AADT_MEAN'].where(
        merged['TYC_AADT_MEAN'].notna(), merged['TYC_AADT'])
    if 'YEARS_WITH_DATA' in merged.columns:
        merged['YEARS_WITH_DATA'] = merged['YEARS_WITH_DATA'].fillna(
            1).astype(int)
    merged = merged.drop(columns=[c for c in (
        'TYC_AADT_MEAN',) if c in merged.columns])
    return merged


def build_corridor_index(segments_df):
    # build numpy-backed per-corridor interval index for fast lookup
    temp = {}
    for _, r in segments_df.iterrows():
        corr = r['CORR_ID']
        a = r.get('CORR_MP_FLOAT')
        b = r.get('CORR_ENDMP_FLOAT')
        if a is None or b is None:
            continue
        temp.setdefault(corr, []).append(
            (float(a), float(b), r['SEGMENT_KEY']))

    corridor_index = {}
    for corr, intervals in temp.items():
        intervals.sort(key=lambda x: x[0])
        starts = np.array([it[0] for it in intervals], dtype=float)
        ends = np.array([it[1] for it in intervals], dtype=float)
        keys = [it[2] for it in intervals]
        corridor_index[corr] = {'starts': starts, 'ends': ends, 'keys': keys}
    return corridor_index


def match_crash_to_section_vectorized(crashes_df, corridor_index):
    s = pd.Series(index=crashes_df.index, dtype=object)
    # parse REF_POINT to float mileposts
    ref_floats = crashes_df.get('REF_POINT').apply(parse_milepost)
    corridors = crashes_df.get('CORRIDOR').astype(str).str.strip().str.upper()

    # group by corridor to limit search
    for corr, group_idxs in corridors.groupby(corridors).groups.items():
        if corr not in corridor_index:
            s.loc[list(group_idxs)] = None
            continue
        starts = corridor_index[corr]['starts']
        ends = corridor_index[corr]['ends']
        keys = corridor_index[corr]['keys']
        sub_refs = ref_floats.loc[list(group_idxs)].to_numpy(dtype=float)
        nan_mask = np.isnan(sub_refs)
        cand = np.searchsorted(starts, sub_refs, side='right') - 1
        out = [None] * len(sub_refs)
        for i, (ref, ci, is_nan) in enumerate(zip(sub_refs, cand, nan_mask)):
            if is_nan or ci < 0 or ci >= len(starts):
                out[i] = None
            else:
                out[i] = keys[ci] if ref <= ends[ci] else None
        s.loc[list(group_idxs)] = out
    return s


def match_crash_to_section(crash_row, corridor_index):
    corridor = str(crash_row.get('CORRIDOR', '')).strip().upper()
    ref = parse_milepost(crash_row.get('REF_POINT'))
    if pd.isna(ref) or corridor not in corridor_index:
        return None
    for sec in corridor_index[corridor]:
        a = sec.get('CORR_MP_FLOAT')
        b = sec.get('CORR_ENDMP_FLOAT')
        if a is not None and b is not None and a <= ref <= b:
            return sec['SEGMENT_KEY']
    return None


def load_tyc_geojson_map(years, base_dir='data/Traffic_Yearly_Counts', needed_keys=None):
    combined = {}
    for year in years:
        candidates = [
            os.path.join(base_dir, f'TYC_{year}.json'),
            os.path.join(base_dir + f'_{year}', f'TYC_{year}.json'),
            os.path.join(base_dir + f'_{year}', f'TYC_{year}.JSON'),
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    # read as bytes and decode with msgspec for speed
                    with open(path, 'rb') as fh:
                        raw = fh.read()
                    js = msgspec.json.decode(raw)
                except Exception:
                    continue
                for feat in js.get('features', []):
                    p = feat.get('properties', {})
                    corr_id = str(p.get('CORR_ID', '')).strip().upper()
                    dept_id = str(p.get('DEPT_ID', '')).strip().upper()
                    corr_mp = str(p.get('CORR_MP', ''))
                    corr_endmp = str(p.get('CORR_ENDMP', ''))
                    key = f"{corr_id}_{corr_mp}_{corr_endmp}_{dept_id}"
                    if needed_keys is not None and key not in needed_keys:
                        continue
                    if key not in combined:
                        combined[key] = feat
                break
    return combined


def _strip_trailing_letter(s):
    """Strip a single trailing letter from a departmental route string.

    Examples: 'N-1A' -> 'N-1', 'U-8133' -> 'U-8133' (no trailing letter)
    """
    if s is None:
        return None
    s = str(s).strip().upper()
    if not s:
        return s
    # remove trailing letter if the last character is an ASCII letter
    if s[-1].isalpha():
        return s[:-1]
    return s


def load_on_system_routes_map(csv_path='raw-mdt-source-data/Montana_On_System_Routes_OD.csv'):
    """Load the Montana on-system routes file and return a mapping from
    departmental route (stripped of trailing letter) -> SIGNED ROUTE.

    If multiple rows map to the same departmental route, the first non-empty
    SIGNED ROUTE encountered will be used.
    """
    if not os.path.exists(csv_path):
        return {}
    try:
        rdf = pd.read_csv(csv_path, dtype=str)
    except Exception:
        return {}
    mapping = {}
    # column names in the file: 'DEPARTMENTAL ROUTE' and 'SIGNED ROUTE'
    for _, r in rdf.iterrows():
        dep = r.get('DEPARTMENTAL ROUTE') or r.get(
            'DEPARTMENTAL ROUTE'.upper())
        signed = r.get('SIGNED ROUTE') or r.get('SIGNED ROUTE'.upper())
        if pd.isna(dep):
            continue
        key = _strip_trailing_letter(dep)
        if not key:
            continue
        signed_val = '' if pd.isna(signed) else str(signed).strip()
        # prefer the first non-empty signed route
        if key not in mapping or (not mapping[key] and signed_val):
            mapping[key] = signed_val
    return mapping


def point_on_linestring(geometry, prefer='midpoint'):
    if geometry is None:
        return None
    t = geometry.get('type')
    if t == 'LineString':
        coords = geometry.get('coordinates', [])
    elif t == 'MultiLineString':
        parts = geometry.get('coordinates', [])
        if not parts:
            return None
        coords = max(parts, key=lambda p: len(p))
    else:
        return None
    if not coords:
        return None
    if prefer == 'start':
        return coords[0]
    seg_lengths = []
    total = 0.0
    for i in range(1, len(coords)):
        x0, y0 = coords[i-1]
        x1, y1 = coords[i]
        d = math.hypot(x1 - x0, y1 - y0)
        seg_lengths.append(d)
        total += d
    if total == 0:
        return coords[0]
    half = total / 2.0
    cum = 0.0
    for i, d in enumerate(seg_lengths, start=1):
        prev = coords[i-1]
        cur = coords[i]
        if cum + d >= half:
            remain = half - cum
            t = remain / d if d != 0 else 0
            x = prev[0] + (cur[0] - prev[0]) * t
            y = prev[1] + (cur[1] - prev[1]) * t
            return [x, y]
        cum += d
    return coords[-1]


def main(crash_csv='raw-mdt-source-data/2019-2023-crash-data.csv', years=[2023, 2022, 2021, 2020, 2019], out_dir='output/merged_data'):
    os.makedirs(out_dir, exist_ok=True)
    base = load_base_segments_2023()
    averaged = calculate_averaged_traffic(base, years)
    corridor_index = build_corridor_index(averaged)

    # load on-system routes mapping: departmental route (stripped) -> SIGNED ROUTE
    on_system_map = load_on_system_routes_map()

    crashes = pd.read_csv(crash_csv, dtype=str)
    crashes['CORRIDOR'] = crashes['CORRIDOR'].astype(
        str).str.strip().str.upper()

    matched_series = match_crash_to_section_vectorized(crashes, corridor_index)
    crash_counts = matched_series.dropna().value_counts().to_dict()

    # compute metrics
    df = averaged.copy()
    df['SEC_LNT_MI'] = pd.to_numeric(
        df.get('SEC_LNT_MI', None), errors='coerce')
    df['TYC_AADT'] = pd.to_numeric(df.get('TYC_AADT', None), errors='coerce')
    df['MILES_DRIVEN'] = df['SEC_LNT_MI'] * df['TYC_AADT']
    total_years = len(years)
    df['TOTAL_CRASHES'] = df['SEGMENT_KEY'].map(
        crash_counts).fillna(0).astype(int)
    df['AVG_CRASHES'] = df['TOTAL_CRASHES'] / total_years
    # TODO: change this if the year range changes
    # 365.20 instead of .25 because there is 1 leap year in the 5-year span we looked at (2019-2023, only 2020 was a leap year).
    df['ANNUAL_VMT'] = df['MILES_DRIVEN'] * 365.20
    df['PER_100M_VMT'] = None
    mask = df['ANNUAL_VMT'].notna() & (df['ANNUAL_VMT'] > 0)
    df.loc[mask, 'PER_100M_VMT'] = (
        df.loc[mask, 'AVG_CRASHES'] / df.loc[mask, 'ANNUAL_VMT']) * 100_000_000

    # load geometries lazily: only for needed segment keys

    # filter low-volume segments and departmental prefixes (exclude R, L, X, U)
    filtered = df.copy()
    filtered['TYC_AADT_NUM'] = pd.to_numeric(
        filtered.get('TYC_AADT', ''), errors='coerce')
    filtered = filtered[filtered['TYC_AADT_NUM'] >= 1]
    depts_exclude = ('R', 'L', 'X', 'U')
    dept_upper = filtered['DEPT_ID'].astype(str).str.strip().str.upper()
    # exclude prefixes R/L/X/U but explicitly keep a small list of U- routes
    keep_u_routes = ['U-5832', 'U-8133', 'U-1216', 'U-602', 'U-8135']
    exclude_mask = dept_upper.str.startswith(depts_exclude, na=False) & (
        ~dept_upper.isin([s.upper() for s in keep_u_routes]))
    before_count = len(filtered)
    filtered = filtered[~exclude_mask]
    removed = before_count - len(filtered)
    if removed > 0:
        print(
            f"Filtered out {removed} segments because DEPT_ID starts with {', '.join(depts_exclude)} (kept {', '.join(keep_u_routes)})")

    needed_keys = set(filtered['SEGMENT_KEY'].tolist())
    geo_map = load_tyc_geojson_map(years, needed_keys=needed_keys)

    lines = []
    for _, row in filtered.iterrows():
        seg_key = row['SEGMENT_KEY']
        if seg_key not in geo_map:
            continue
        feat = geo_map[seg_key]
        geom = feat.get('geometry')
        if geom is None:
            continue
        # look up SIGNED_ROUTE: match DEPT_ID (strip trailing letter) to mapping
        dept = row.get('DEPT_ID', '')
        dept_key = _strip_trailing_letter(dept)
        signed_route = on_system_map.get(dept_key, '')

        props = {
            'SEGMENT_KEY': seg_key,
            'CORRIDOR': row.get('CORR_ID', ''),
            'CORR_MP': row.get('CORR_MP', ''),
            'CORR_ENDMP': row.get('CORR_ENDMP', ''),
            'DEPT_ID': row.get('DEPT_ID', ''),
            'SEC_LNT_MI': float(row.get('SEC_LNT_MI')) if pd.notna(row.get('SEC_LNT_MI')) else '',
            'SIGNED_ROUTE': signed_route,
            'TOTAL_CRASHES': int(row.get('TOTAL_CRASHES', 0)),
            'AVG_CRASHES': float(row.get('AVG_CRASHES', 0.0)),
            'PER_100M_VMT': float(row.get('PER_100M_VMT')) if pd.notna(row.get('PER_100M_VMT')) else '',
            'TYC_AADT': int(row['TYC_AADT']) if pd.notna(row.get('TYC_AADT')) and float(row['TYC_AADT']).is_integer() else (float(row['TYC_AADT']) if pd.notna(row.get('TYC_AADT')) else ''),
        }
        lines.append(
            {'type': 'Feature', 'geometry': geom, 'properties': props})

    lines_gc = {'type': 'FeatureCollection', 'features': lines}
    with open(os.path.join(out_dir, 'merged_traffic_lines.geojson'), 'w') as lf:
        json.dump(lines_gc, lf)

    # Create CSV version for lines (without geometry data)
    if lines:
        # preserve property keys (SIGNED_ROUTE included)
        lines_df = pd.DataFrame([feature['properties'] for feature in lines])
        lines_df.to_csv(os.path.join(
            out_dir, 'merged_traffic_lines.csv'), index=False)

    print(f"Wrote {len(lines)} lines to {out_dir}")


if __name__ == '__main__':
    main()
