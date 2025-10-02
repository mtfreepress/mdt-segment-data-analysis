#!/bin/bash

# Use local node_modules mapshaper if available, otherwise fallback to global mapshaper
MAPSHAPER="./node_modules/.bin/mapshaper"
if [ ! -x "$MAPSHAPER" ]; then
  MAPSHAPER="mapshaper"
fi

mkdir -p output/simplified_data
for input_file in output/merged_data/*.geojson; do
  [ -e "$input_file" ] || continue
  base=$(basename "$input_file" .geojson)

  for scale in 1000 100 10 1; do
    out_file="output/simplified_data/${base}-${scale}m.geojson"
    # Use mapshaper's interval simplification in meters. The 'interval' parameter
    # specifies the minimum distance (in the coordinate units, here meters when
    # using projected coordinates) between consecutive points after simplification.
    # Keep 'keep-shapes' to preserve topology.
    # Detect and skip Git LFS pointer files which are small text files starting
    # with 'version https://git-lfs.github.com/spec/v1' instead of real GeoJSON.
    # Feeding those to mapshaper causes a JSON parsing error.
    if head -n1 "$input_file" | grep -q "^version https://git-lfs.github.com/spec/v1"; then
      echo "Skipping LFS pointer file: $input_file — pull LFS contents (git lfs pull) to process this file"
      continue
    fi

    "$MAPSHAPER" "$input_file" \
      -simplify keep-shapes interval=${scale} \
      -o gj2008 precision=0.00001 "$out_file"
  done
done
