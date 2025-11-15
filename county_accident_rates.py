"""Aggregate crash counts by county and compute accidents per 100k residents.

Reads:
 - `raw-mdt-source-data/2019-2023-crash-data.csv`
 - `data/2024-census-county.csv`

Writes:
 - `output/eliza-analysis/ranking-by-county/ranking_by_county.csv`

Output columns: `county,totalAccidents,accidentsPer100kResidents` sorted
descending by `accidentsPer100kResidents`.

County matching is case-insensitive and trims whitespace.
"""

import csv
import os
from collections import Counter, defaultdict

# Paths (relative to repo root)
CRASH_CSV = os.path.join("raw-mdt-source-data", "2019-2023-crash-data.csv")
CENSUS_CSV = os.path.join("data", "2024-census-county.csv")
OUTPUT_DIR = os.path.join("output", "eliza-analysis", "ranking-by-county")
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "ranking_by_county.csv")


def load_census_populations(census_path):
	pops = {}
	with open(census_path, newline="", encoding="utf-8") as fh:
		reader = csv.DictReader(fh)
		for row in reader:
			county = (row.get("COUNTY") or "").strip().lower()
			try:
				pop = int(row.get("TOT_POP") or 0)
			except ValueError:
				pop = 0
			if county:
				pops[county] = pop
	return pops


def count_crashes_by_county(crash_path):
	counts = Counter()
	with open(crash_path, newline="", encoding="utf-8") as fh:
		reader = csv.DictReader(fh)
		for row in reader:
			county = (row.get("COUNTY") or "").strip().lower()
			if not county:
				continue
			counts[county] += 1
	return counts


def compute_and_write(counts, pops, outpath):
	os.makedirs(os.path.dirname(outpath), exist_ok=True)
	rows = []
	for county_lower, total in counts.items():
		pop = pops.get(county_lower, 0)
		if pop and pop > 0:
			rate = (total / pop) * 100000.0
		else:
			rate = None
		# Keep original county capitalization from census if available
		county_name = None
		# find census canonical name
		for k, v in pops.items():
			if k == county_lower:
				county_name = k.title()
				break
		if county_name is None:
			county_name = county_lower.title()
		rows.append((county_name, total, rate if rate is not None else ""))

	# sort descending by rate; treat missing rates as -inf so they go to bottom
	def sort_key(r):
		val = r[2]
		return float(val) if val != "" else -1.0

	rows.sort(key=sort_key, reverse=True)

	with open(outpath, "w", newline="", encoding="utf-8") as outfh:
		writer = csv.writer(outfh)
		writer.writerow(["county", "totalAccidents", "accidentsPer100kResidents"])
		for county_name, total, rate in rows:
			if rate == "":
				writer.writerow([county_name, total, ""])
			else:
				writer.writerow([county_name, total, f"{rate:.2f}"])


def main():
	if not os.path.exists(CENSUS_CSV):
		raise SystemExit(f"Census file not found: {CENSUS_CSV}")
	if not os.path.exists(CRASH_CSV):
		raise SystemExit(f"Crash data file not found: {CRASH_CSV}")

	pops = load_census_populations(CENSUS_CSV)
	counts = count_crashes_by_county(CRASH_CSV)
	# Ensure we include counties that appear in census but have zero crashes
	for county in pops.keys():
		if county not in counts:
			counts[county] = 0

	compute_and_write(counts, pops, OUTPUT_CSV)
	print(f"Wrote ranking CSV to: {OUTPUT_CSV}")


if __name__ == "__main__":
	main()
