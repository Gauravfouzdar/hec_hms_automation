# Chapter 4 - Inspect the rainfall NetCDF

## Purpose
Every rainfall source (IMD, CHIRPS, ERA5, CMIP6) names its variables, units and
calendars differently. Look before you process, so chapters 5 and 6 get the
right variable and the right unit conversion.

## You need
A NetCDF file (`.nc`) with a precipitation variable on a `time x lat x lon`
grid, or a CMIP6 "points" file (`pr(time, points)`).

## Run
```cmd
hms-auto inspect-nc "D:\IMD_data\IMD_rain_1950_2025.nc"
hms-auto inspect-nc "D:\CMIP6\pr_ssp245.nc" --judge
```

## What happens
`climate.netcdf_inspect` opens the file with `use_cftime=True` (needed for
noleap / 360-day CMIP6 calendars), lists every data variable except bounds
variables, and reports units, `long_name`, dimensions and the year range. It
then suggests the precipitation variable.

## Check
- The suggested variable's units are what you expect: `mm/day` (IMD, CHIRPS),
  `kg m-2 s-1` (CMIP6 `pr`). Chapter 6 converts flux to mm/day with x 86400
  (1 kg m-2 of water = 1 mm).
- The year range covers what you plan to use.

## Judgment checkpoint
| Decision | Decided by |
|---|---|
| Which variable is precipitation | **Code rule first**: alias list `pr, precip, precipitation, rain, tp, rainfall`; a file with one variable is a `review` suggestion |
| Same, when no alias matches and there are several variables | **Optional Jev advisor** (`--judge`): one yes/no question per variable using its name, `long_name`, units and dimensions. Result is a *suggestion*: the CLI prints `[jev, yes]` or `[jev, review]`. Confirm before using it as `--rain-var` |
| Unit conversion, calendars | **Code only** |

## If it fails
| Symptom | Fix |
|---|---|
| `Could not find lat/lon coordinates` | The file uses other coordinate names; rename them in the file or extend `detect_coord_names` in `climate/clip.py` |
| Suggestion is `(none)` | No alias matched and no advisor available: pick the variable yourself from the printed list |

## Where the code is
`climate/netcdf_inspect.py`, `judgment/advisors.py` (`judge_precip_variable`).
