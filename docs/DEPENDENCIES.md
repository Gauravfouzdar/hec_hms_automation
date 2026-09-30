# Dependencies

## Python (pip / conda)

Python **3.10+** (developed on 3.12). Install with `pip install -r requirements.txt`
or `conda env create -f environment.yml`.

| Library | Needed by | Why |
|---|---|---|
| `numpy`, `pandas` | almost everything | arrays, tables, Excel/CSV |
| `openpyxl` | `workflows/populate`, `dss/timeseries` | write `.xlsx` |
| `pyyaml` | `workflows/scenarios` | scenarios file |
| `scipy` | `hydrology/design_storm` | Gumbel distribution (`gumbel_r.ppf`) |
| `shapely`, `geopandas`, `pyogrio` | `gis/*`, `climate/*`, `workflows/design_storm` | polygons, basin sqlite layers, shapefiles |
| `rasterio` | `gis/terrain`, `gis/landuse`, `workflows/populate` | flow-direction, slope and LULC rasters |
| `xarray`, `netCDF4`, `cftime` | `climate/*`, `workflows/design_storm` | read/write NetCDF, CMIP6 calendars |
| `matplotlib` | `plots/*` | diagnostic figures (Agg backend) |
| `pydsstools` *(optional)* | `dss/timeseries` | **read** HMS results from DSS. Limited Windows wheels per Python version |
| `typesafe-sdk` *(optional)* | `judgment/*` | Jev advisor; also needs `TYPESAFE_API_KEY` |
| `pytest` *(dev)* | `tests/` | test runner |

Import layering (so a light command never drags in the GIS stack):

| Package | Imports |
|---|---|
| `hmsfiles`, `hydrology.parameters`, `vortex`, `compute`, `config` | standard library only |
| `hydrology.design_storm` | numpy, scipy |
| `gis`, `climate`, `workflows`, `plots`, `dss` | the heavy libraries above, imported lazily by the CLI |
| `judgment` | standard library at import time; `typesafe_sdk` only when a question is actually asked |

## External tools (NOT pip-installable)

| Tool | Version tested | Needed from | How the toolkit finds it |
|---|---|---|---|
| **HEC-HMS** | 4.13 | chapter 9 | `--hms-home`, `HMS_HOME`, then `C:\Program Files\HEC\HEC-HMS\*` |
| **HEC-Vortex** (with bundled `jre\`) | 0.13.3 and 0.11.16-rc.1 | chapter 7 | `--vortex-home`, `VORTEX_HOME`, `<app>\vortex`, `C:\Program Files\vortex*` |
| **Jython standalone jar** | 2.7.4 | chapter 7 | inside the Vortex folder or one level above it |

Vortex ships its own JRE and GDAL/PROJ; nothing else needs installing for it.

## Environment variables

| Variable | Purpose |
|---|---|
| `HMS_HOME` | HEC-HMS install folder (contains `HEC-HMS.cmd`) |
| `VORTEX_HOME` | Vortex folder (contains `jre\bin\java.exe`, `lib\`) |
| `TYPESAFE_API_KEY` | optional: enables the Jev advisor. Read only by the SDK; never printed or stored |
| `TYPESAFE_LOG_LEVEL` | leave at default. `debug` logs request bodies unredacted |

## What was left out on purpose
The original tools also contained GUI applications (CustomTkinter, PyInstaller
builds). They are **not** part of this library; the library exposes the same
processing through the CLI and importable functions. The GUIs can be rebuilt as
thin front ends over `workflows/` without duplicating logic.
