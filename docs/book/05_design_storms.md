# Chapter 5 - Design storms (return-period rainfall)

## Purpose
Create an hourly design storm for return periods such as 5, 10, 25, 50 and 100
years for one basin, as gridded NetCDF (and, with Vortex, as DSS ready for HMS).

## You need
- IMD (or similar) **daily** gridded rainfall NetCDF with a long record.
- The basin polygon shapefile (with a CRS).
- CWC hourly incremental rainfall factors for the basin's sub-zone. A workbook
  is bundled (`resources/cwc_default.xlsx`, sheet *Incremental rainfall
  factor*); pass `--cwc-excel` to use your own.
- For DSS output: Vortex (chapter 1).

## Run
```cmd
hms-auto design-storm --imd "D:\IMD_data\IMD_rain_1950_2025.nc" ^
  --basin-shp "E:\basins\Dikhow.shp" --out "E:\out\Dikhow_RP" --name Dikhow ^
  --cwc-zone 2b --rp 5,10,25,50,100 --vortex --qa
```
(`^` is CMD's line continuation.) Drop `--vortex` for NetCDF only, drop `--qa`
to skip the extra plots and CSVs.

## What happens
1. Clip IMD to the basin's bounding box plus `--buffer-km` (default 25). The
   exact basin mask uses the **unbuffered** polygon.
2. Annual-maximum daily rainfall per cell (last 30 years).
3. Homogeneity screen (H-statistic).
4. Regional growth curve: pooled normalised L-moments, Gumbel fit.
5. RP rainfall per cell = cell mean annual maximum x growth factor.
6. Distribute each 24 h depth with the CWC hourly factors and order it with the
   Alternating Block Method (peak in the middle).
7. Write `design_storm_RP<n>.nc` (hourly, `--total-days` long, storm on
   `--storm-day`), diagnostics PNG, and with `--vortex` the DSS files
   `<name>_<n>RP_ts.dss` with a **1 hour** END shift.

## Check
- The log shows `H-statistic`, Gumbel parameters and a growth factor that
  **increases** with return period.
- `CWC factors ... sum = 1.0000`. The run **stops** if the sum is not within
  0.01 of 1.
- Open `design_storm_diagnostics.png`; storm totals should rise with RP.
- With `--qa`: `plot_*.png`, `timeseries_RP*.csv`, `storm_summary_all_rp.csv`.

## Judgment checkpoint
Everything here is **numeric, so code decides**: statistics, factor sums, unit
handling, dates. There is deliberately no model advice in this chapter.
The one judgment call left to **you** is homogeneity: `H < 1` is fine, `1-2` is
"possibly heterogeneous", `>= 2` means consider splitting the basin. Note that
the H-statistic here is a *simplified screen* (see `hydrology/design_storm.py`
and `docs/LITERATURE.md`), so treat it as a warning light, not a verdict.

## If it fails
| Symptom | Fix |
|---|---|
| `Basin shapefile has no CRS defined` | Assign the CRS in GIS and re-save |
| `No grid cells found inside basin` | CRS or extent mismatch, or the basin is smaller than one IMD cell: check the shapefile against the grid |
| `Zone '...' not found in CWC Excel` | The message lists the valid zones |
| `Target projection ... is empty` (with `--vortex`) | Pass `--wkt UTM46N` (derived automatically only for UTM shapefiles) |
| RP totals look too small | IMD 0.25 degree cells smooth extremes; this is a property of the data |

## Where the code is
`workflows/design_storm.py` (pipeline, config), `hydrology/design_storm.py`
(maths), `plots/design_storm.py`.
