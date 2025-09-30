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
    # map scale -> percent string expected by mapshaper
    case "$scale" in
      1000) pct="10%" ;; 
      100) pct="5%" ;;
      10) pct="1%" ;;
      1) pct="0.1%" ;;
      *) pct="1%" ;;
    esac
    # Use Douglas-Peucker (dp) simplification algorithm with "keep-shapes" option to preserve topology
    "$MAPSHAPER" "$input_file" \
      -simplify dp "$pct" keep-shapes \
      -o gj2008 precision=0.00001 "$out_file"
  done
done
