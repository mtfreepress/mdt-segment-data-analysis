# mdt-segment-data-analysis

## Prerequisites

- Python 3.8+ (recommended 3.10/3.11/3.13). Install from: https://www.python.org/
- npm / Node.js (mapshaper is installed via npm). Install from: https://nodejs.org/
- Git (clone repository): https://git-scm.com/

Notes:
- The project uses a local Python virtual environment (`.venv`) so Python packages are installed inside the project and do not affect your global Python environment.
- `mapshaper` is installed locally to the repository via `npm install` and used from `node_modules/.bin/mapshaper`. Contributors only need `npm` installed; no global `mapshaper` install is required.

## How to install

From the repository root run the provided setup script which will create a `.venv`, install Python packages and install npm packages locally:

```bash
./setup.sh
```

This script does the following:
- Creates a virtual environment in `.venv` (if missing)
- Activates the virtual environment for the duration of the script and installs Python packages from `requirements.txt`
- Runs `npm install` (or creates a minimal `package.json` and installs `mapshaper` if missing)

After the script finishes, activate the venv in your shell before running Python commands:

```bash
source .venv/bin/activate
```

## How to run

Two-step pipeline provided via `merge_simplify.sh` which runs the Python merge script and then simplifies GeoJSONs using `mapshaper`:

```bash
# Make sure your venv is active or run ./setup.sh first
source .venv/bin/activate
./merge_simplify.sh
```

What the pipeline does:
- `merge_traffic_accident.py` reads raw input files and writes GeoJSON to `output/merged_data/` (and CSV versions)
- `simplify_geojson.sh` reads the GeoJSON files from `output/merged_data/` and produces simplified files at `simplified_data/{base}-{scale}m.geojson` for scales: 1000m, 100m, 10m, 1m

If you prefer to run only the simplifier (mapshaper), call:

```bash
./simplify_geojson.sh
```

## Files and scripts added
- `setup.sh` — creates `.venv`, installs Python and npm deps
- `merge_simplify.sh` — runs the python merge and simplification pipeline (requires `.venv`)
- `simplify_geojson.sh` — runs `mapshaper` over `output/merged_data/*.geojson` and writes to `simplified_data/`
- `package.json` — records the local npm dependency (`mapshaper`)

## License

This project is distributed under the BSD 3-Clause License. See the `LICENSE` file for details.


Because MDT provides its data in a format meant for engineers (a shapefile), we converted it into more accessible formats, GEOjson and CSV, so it could be more easily processed in the Python script we wrote. That Python script connected each recorded crash to the correct stretch of road using “corridor” numbers and milepost makers, which are unique identifiers used by the state in both of its traffic and crash databases. 

For traffic numbers we took care to get as accurate a representation of the average traffic over the 2019 to 2023 period. The state sometimes splits a highway segment into two so we used the 2023 traffic data where possible to make our results match the public 2024 traffic information as closely as possible. However, the state does not collect “Annual Average Daily Traffic” (AADT) numbers for every section of highway every year. In the cases where there wasn’t 2023 data, we used data from 2022 as our baseline. We then took and found exact matches in other years using multiple identification numbers and milepost data to ensure an exact match. The sum of all AADT numbers was then divided by the number of years with exact matches. Most years have at least four years of data that was averaged but a small number use only one year. 

For our base crash rate metric, accidents per 100 million vehicle miles traveled (VMT), we used our average traffic number and multiplied it by the length of the road segment to give us a daily vehicle miles traveled. We then multiplied it by 1,826—the total number of days in 5 years, including the leap day in 2020 to get the total estimated vehicle miles traveled in the period that our analysis covered. With that number in hand, we were able to calculate the crash rate using the standard for highway safety numbers. The rate is the key metric we used throughout the story because it allows for a fairer comparison across roads with very different traffic volumes.

The output form our script included both mapping data and summary statistics for each segment, such as total crashes, crash rate, average traffic, the state’s internal road name and the public facing highway name