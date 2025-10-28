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

Three-step pipeline provided via `run_scripts.sh` which runs:
- `merge_traffic_accidents.py` 
- `simplify_GeoJSON.sh`:
- `calculate_average_vmt.py`

```bash
# Make sure you have run setup.sh or made this file executable with `chmod +x ./run_scripts.sh` and created a .venv manually
./run_scripts.sh
```

#### What the pipeline does:
- `merge_traffic_accident.py` reads raw input files and writes GeoJSON to `output/merged_data/` (and CSV versions)
- `simplify_GeoJSON.sh` reads the GeoJSON files from `output/merged_data/` and uses `mapshaper` to produce simplified files at `simplified_data/{base}-{scale}m.geojson` for scales: 1000m, 100m, 10m, 1m
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
- `output/` contains the data output of our analysis and simplification script
- `resources/` contains the "Highway Safety Improvement Manual" as a PDF just in case™ it gets deleted from the US DOT's website  

## License

This project is distributed under the BSD 3-Clause License. See the [LICENSE](LICENSE) file for details.


## Methodology Notes:

Because MDT provides its data in a format meant for traffic engineers (a shapefile), we converted it into more accessible formats, GeoJSON and CSV, so it could be more easily processed in the Python script we wrote. That Python script connected each recorded crash to the correct stretch of road using “corridor” numbers and milepost makers, which are unique identifiers used by the state in both of its traffic and crash databases. 

For traffic numbers we took care to get as accurate a representation of the average traffic over the 2019 to 2023 period. The state sometimes splits a highway segment into two so we used the 2023 traffic data where possible to make our results match the public 2024 traffic information as closely as possible. However, the state does not collect “Annual Average Daily Traffic” (AADT) numbers for every section of highway every year. In the cases where there wasn’t 2023 data, we used data from 2022 as our baseline. We then took and found _exact_ matches in other years using multiple identification numbers and milepost data to ensure an exact match. The sum of all AADT numbers was then divided by the number of years with exact matches. Most years have at least four years of data that was averaged but a small number use only one year. 

For our base crash rate metric, we used accidents per `100 million vehicle miles traveled (VMT)`, the industry standard prescribed by the US DOT in the [Highway Safety Improvement Manual](https://highways.dot.gov/sites/fhwa.dot.gov/files/2022-06/fhwasa09029.pdf). We used our average traffic number and multiplied it by the length of the road segment to give us a daily vehicle miles traveled. We then multiplied it by 1,826—the total number of days in 5 years, including the leap day in 2020, to get the total estimated vehicle miles traveled in the period that our analysis covered. With that number in hand, we were able to calculate the crash rate as the standard `100 million VMT` metric. The rate is the key metric we used throughout the story because it allows for a direct comparison by nomalizing for traffic and segment length.

The output from `merge_traffic_accidents.py` includes both mapping data and summary statistics for each segment, such as total crashes, crash rate, average traffic, segment length, the state’s internal road name, the public facing highway name and GPS coordinates to map out each road segment. That and the output of `minify_mt_highways.py` are what was used in our maps after being simplified to reduce file size further using [mapshaper's](https://mapshaper.org/) node.js package. 

The `calculate_average_vmt.py` scipt was set up to calculate a variety of statistics to see how different highways compared, the numbers used from that in the piece is the accident rate for all "on-system" highways (MT, US and Interstate) and the accident rates for all highways (including interstates) and just Interstates outside of municipalities, excluding the combined Anaconda-Deer Lodge and Butte-Silver Bow city/county due to most of those counties being rural.
