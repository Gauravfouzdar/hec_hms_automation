# Chapter 6 - Climate scenarios (CMIP6)

## Purpose
Prepare historical and future (SSP) precipitation for one basin: clipped to a
buffered basin, in mm/day, with plots, and (with Vortex) as gridded DSS.

## You need
- One CMIP6 NetCDF per scenario (`historical`, `ssp126`, `ssp245`, `ssp370`,
  `ssp585`); any subset is fine. Points-format files are supported.
- The basin shapefile. For DSS: Vortex.

## Run
```cmd
hms-auto climate --basin-shp "E:\basins\Umngi.shp" --out "E:\out\Umngi_climate" --name Umngi ^
  --scenario historical="D:\cmip6\pr_hist.nc" --scenario ssp245="D:\cmip6\pr_ssp245.nc" ^
  --rain-var pr --buffer-km 25 --ref 1981-2014 --vortex
```

## What happens
1. Buffer the basin (in its own metric CRS when it has one).
2. Per scenario, in parallel worker processes: select cells under the buffer
   **that actually hold data**, subset years, convert flux to mm/day, clamp tiny
   negatives to 0, write `<scenario>_<var>_clipped.nc` and `timeseries_<scenario>.csv`.
3. **Boundary basins:** if no cell under the buffer has data (masked products),
   fall back to the 4 nearest valid cells with a loud warning, and widen the clip
   shape to cover them.
4. Write `buffered_boundary.shp` (the Vortex clip shape) and five plots:
   spatial mean map, annual series (+`annual_summary.csv`), monthly climatology,
   heatmaps, change signal versus the reference period.
5. With `--vortex`: one JVM per scenario converts to DSS with a **24 hour** END
   shift (chapter 7).

## Check
- Log lines `Selected cells with data: n` and `Units: auto: 'kg m-2 s-1' -> x86400`.
- **Look for `WARNING ... nearest valid cells`** - it means the basin is outside
  the data mask and results come from neighbouring cells.
- `Basin-mean daily precip` is plausible (a few mm/day for most Indian basins).
- The change-signal plot shows the sign you expect for your region.

## Judgment checkpoint
Code decides every number: cell selection, unit conversion, calendar handling.
The **human judgment** here is scientific: choosing scenarios, the reference
period, and whether raw CMIP6 output (not bias-corrected) is acceptable for
your purpose. The toolkit does not bias-correct; see Hay et al. (2000) in
`docs/LITERATURE.md` for the delta-change alternative. The variable name comes
from chapter 4.

## If it fails
| Symptom | Fix |
|---|---|
| `Variable 'pr' not in <file>` | Run chapter 4 and pass the right `--rain-var` |
| `no time steps in A-B` | `--start-year/--end-year` outside the file |
| `N scenario(s) failed to clip/export` | The message lists every failed scenario with its error |
| Units look wrong | `ClimateRunConfig.unit_mode`: `auto`, `x86400` or `none` |
| Empty DSS | Clip shape did not cover data cells; see the fallback warning |

## Where the code is
`climate/clip.py`, `climate/pipeline.py`, `climate/config.py`,
`plots/climate.py`.
