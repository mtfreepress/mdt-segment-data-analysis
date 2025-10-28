# MDT segment level data analysis

## Prerequisites

- Python 3.8+ (recommended 3.10/3.11/3.13). Guide on how to install [here on python.org](https://wiki.python.org/moin/BeginnersGuide/Download)
- npm / Node.js (mapshaper is installed via npm). The [download page on nodejs.org](https://nodejs.org/en/download) has information on how to install and get started

_Notes:_
- The project uses a local Python virtual environment (`.venv`) so Python packages are installed inside the project and do not affect your global Python environment.
- `mapshaper` is installed locally to the repository via `npm install` and used from `node_modules/.bin/mapshaper`. Contributors only need `npm` installed; no global `mapshaper` install is required.

## How to install

From the repository root run the provided setup script which will create a `.venv`, install Python packages and install npm packages locally:

```bash
# make executable
chmod +x setup.sh
# run script
./setup.sh
```

This script does the following:
- Creates a virtual environment in `.venv` (if missing)
- Activates the virtual environment for the duration of the script and installs Python packages from `requirements.txt`
- Runs `npm install` and creates a minimal `package.json` and installs `mapshaper` to the project if missing
- Makes the scripts 


## How to run

Three-step pipeline provided via `run_scripts.sh` which runs
- Python merge script `merge_traffic_accidents.py`, 
- Python script to calculate average VMTs outside of municipalities `calculate_average_vmt.py` (note: excludes Anaconda/Deer Lodge and Butte/Silverbow combined municipalities since the municipality covers the entire county which skews results)  
- Shell script that uses `mapshaper` to simplify GeoJSON files for mapping `simplify_GeoJSON.sh`:

```bash
# Make sure you have run setup.sh or made this executable with `chmod + x` and created a .venv manually
./run_scripts.sh
```

#### What the pipeline does:
- `merge_traffic_accident.py` reads raw input files and writes GeoJSON to `output/merged_data/` (and CSV versions)
- Calculates VMT values on highways (roads outside of municipalities)
- `simplify_GeoJSON.sh` reads the GeoJSON files from `output/merged_data/` and produces simplified files at `simplified_data/{base}-{scale}m.geojson` for scales: 1000m, 100m, 10m, 1m
- `calculate_average_vmt.py` does length weighted average VMT values for:
```
Note: Ananconda Deer Lodge
1. All on system roads (regardless of in/out municipality)
2. All roads outside municipality limits
3. Non-interstates outside municipality limits
4. Interstates outside municipality limits
5. All roads inside municipality limits
6. Non-interstates inside municipality limits
7. Interstates inside municipality limits
```


#### Scripts that are not part of the pipeline (but were used as part of our mapping/story): 
- `minify_mt_highways` takes the `data/mt-highways-1m.geojson` (derived from MDT's "On system routes") and removes all segments where there is overlap with the merged highway data to shrink the size of our mapping data so the interactive map loads more quickly. Outputs to `output/mini_highways/mini_mt_highways-1m.json`

## Project structure
- `raw_mdt_data/` contains data as it came from MDT directly
- `data/` contains the state data we converted in to `GeoJSON` format for easier usage in python and data from [MTFP's Montana Atlas project](https://github.com/mtfreepress/montana-atlas)
- `output/` contains the data output of our analysis and simplification scripts

## License

This project is distributed under the BSD 3-Clause License. See the [LICENSE](LICENSE) file for details.


## Methodology Notes:

Because MDT provides its data in a format meant for engineers (a shapefile), we converted it into more accessible formats, GeoJSON and CSV, so it could be more easily processed in the Python script we wrote. That Python script connected each recorded crash to the correct stretch of road using “corridor” numbers and milepost makers, which are unique identifiers used by the state in both of its traffic and crash databases. 

For traffic numbers we took care to get as accurate a representation of the average traffic over the 2019 to 2023 period. The state sometimes splits a highway segment into two so we used the 2023 traffic data where possible to make our results match the public 2024 traffic information as closely as possible. However, the state does not collect “Annual Average Daily Traffic” (AADT) numbers for every section of highway every year. In the cases where there wasn’t 2023 data, we used data from 2022 as our baseline. We then took and found exact matches in other years using multiple identification numbers and milepost data to ensure an exact match. The sum of all AADT numbers was then divided by the number of years with exact matches. Most years have at least four years of data that was averaged but a small number use only one year. 

For our base crash rate metric, accidents per 100 million vehicle miles traveled (VMT), we used our average traffic number and multiplied it by the length of the road segment to give us a daily vehicle miles traveled. We then multiplied it by 1,826—the total number of days in 5 years, including the leap day in 2020 to get the total estimated vehicle miles traveled in the period that our analysis covered. With that number in hand, we were able to calculate the crash rate using the standard for highway safety numbers. The rate is the key metric we used throughout the story because it allows for a fairer comparison across roads with very different traffic volumes.

The output from our script included both mapping data and summary statistics for each segment, such as total crashes, crash rate, average traffic, the state’s internal road name and the public facing highway name
