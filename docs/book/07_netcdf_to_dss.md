# Chapter 7 - NetCDF to gridded DSS (HEC-Vortex)

## Purpose
HEC-HMS reads gridded rainfall from HEC-DSS. Only HEC-Vortex can write those
gridded records, so this chapter turns any rainfall NetCDF into a DSS that HMS
can use. Chapters 5 and 6 call it for you; use this chapter directly for other
sources such as IMD or CHIRPS.

## You need
Vortex installed (chapter 1), a NetCDF, a clip polygon shapefile, the target
projection label (`UTM46N`), and the record time step.

## Run
```cmd
hms-auto vortex-convert --nc "D:\IMD_data\IMD_rain_1950_2025.nc" --shp "E:\basins\Dikrong.shp" ^
  --out-dss "E:\out\Dikrong_IMD_ts.dss" --wkt UTM46N --part-b Dikrong_IMD ^
  --var rain --shift-hours 24 --cell-size 2000
```

## What happens
The toolkit generates a **Jython 2.7 script** and a launcher `.bat`, then runs
them inside Vortex's own JVM:

1. `BatchImporter`: NetCDF, clipped to the shapefile, reprojected, resampled
   (bilinear) to the cell size, written as `PER-CUM` grids ("raw" DSS).
2. `TimeShifter`: shifts the **END** timestamp of every grid by `--shift-hours`
   and writes the final DSS.

**Why the shift?** Daily rainfall files carry only a date, so Vortex writes each
record with identical start and end times, a zero-length period HMS cannot use.
Shifting the end by one record step makes it a valid period-cumulative record.
Values are untouched. `--shift-hours` **must equal the time step**: 24 daily,
1 hourly.

## Check
- Log ends with `VORTEX_CONVERSION_OK` and `Done <label>`.
- Catalogue the result and note the exact pathname (you need it in chapter 8):
  ```cmd
  python -c "from pydsstools.heclib.dss import HecDss; f=HecDss.Open(r'E:\out\Dikrong_IMD_ts.dss'); print(f.search_path('/*/*/*/*/*/*/')[:3]); f.close()"
  ```
  Expected shape: `/UTM46N/<part-b>/PRECIPITATION/01JAN1950:0000/01JAN1950:2400/ts/`

## Judgment checkpoint
**Code and you.** The shift, cell size and projection are exact settings, not
opinions. The one human decision is the DSS **B-part spelling**: it appears in
the pathname, and HMS needs an exact match (`Meghalaya` is not `Meghalya`). Copy
it from the catalogue output above rather than retyping.

## If it fails
| Symptom | Fix |
|---|---|
| `VORTEX_CONVERSION_FAILED` | The streamed Java log above it names the cause; the `.bat` and `.py` are kept in `_vortex_run/` for manual reruns |
| Spurious "path not found" lines | Paths with `&` break `echo %CLASSPATH%`; the generated `.bat` deliberately omits that echo |
| `No jython-standalone*.jar` | Put the jar in `VORTEX_HOME` or its parent folder |
| Class `TimeShifter` not found | Handled: the script tries `TimeShifter` (0.13+) then `Shifter` (0.11) |
| Out of memory | Raise `xmx` (e.g. `Xmx4g`) in `convert_netcdf_to_dss`; lower `max_workers` when running many jobs |
| Orphan `java.exe` after closing a tool | Call `vortex.process_guard.install_kill_children_on_exit()` at startup of your own long-running tools |

Jython 2.7 has **no f-strings**. If you edit `vortex/jython_templates.py`, keep
`%` formatting inside the templates; `tests/test_core.py` guards this.

## Where the code is
`vortex/jython_templates.py` (scripts and `.bat`), `vortex/converter.py`
(run + parallelism), `vortex/locator.py`, `vortex/process_guard.py`.
