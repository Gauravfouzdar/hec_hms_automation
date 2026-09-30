# Chapter 12 - Troubleshooting and hard-won gotchas

Each entry is something that actually went wrong on real projects and is now
handled in code. Knowing them tells you what *not* to "simplify" later.

| Area | Gotcha | Where it is handled |
|---|---|---|
| Paths | A path containing `&` (`E:\AI & ML`) breaks `cmd /c <bat>` and `echo %CLASSPATH%` | scripts go to the temp folder; the Vortex `.bat` omits the echo (`config.scratch_dir`, `jython_templates.BAT_TEMPLATE`) |
| Jython | Vortex scripts run under Jython 2.7: **no f-strings** | templates use `%`; `tests/test_core.py` asserts it |
| Vortex versions | Class `Shifter` (0.11) became `TimeShifter` (0.13); the jython jar moved outside the versioned folder | try/except import; `find_jython_jar` checks both places |
| Time shift | Daily NetCDF gives zero-length PER-CUM periods | END shift equal to the time step (chapter 7) |
| DSS names | The B-part must match exactly (`Meghalaya` vs `Meghalya`) | copy from the catalogue, chapter 7 |
| DSS reading | `ts.values` can be a reused buffer; times are `HecTime` objects; HMS stamps daily values at 24:00 | copy, `.datetime()`, subtract one second (`dss/timeseries.py`) |
| LULC | Raster **values** differ between rasters, class **names** do not | resolve impervious classes by name via the VAT |
| Terrain | HMS creates new numbered terrain folders (`00`, `01`) | `populate._pick_terrain` uses the highest folder that holds both rasters |
| Discretization | The basin sqlite is named after the `.basin`, not always `Basin_1.sqlite` | `discover_inputs` derives it from the basin file |
| Muskingum | K below ~0.1 hr makes HMS abort (error 41161) | K floored; subreach count `ceil(2xK/dt)` |
| Windows | Child processes outlive a killed parent | `taskkill /T` tree kill, and a kill-on-close Job Object (`process_guard`); 64-bit HANDLEs need explicit `restype/argtypes` |
| HMS exit code | HMS returns 0 even on a failed compute | verdict from `Run_<tag>.log` plus a staleness guard |
| netCDF4 | The HDF5 layer is not reliably thread-safe across files | process pool for clip/export, threads only for external JVMs |
| CMIP6 | noleap / 360-day calendars break `pd.to_datetime` | `use_cftime=True` and `to_datetimeindex` |
| Boundary basins | Masked products have no data under the buffer | nearest-4-cells fallback with a warning and a widened clip shape |

## When a Jev answer looks wrong
Work through this order before touching the question text:

1. **Missing evidence** - did the state contain what the question needed (was
   the class name / variable metadata actually sent)?
2. **Model error** - the state held the answer but the band is wrong: reword the
   question in `judgment/constants.py` (say exactly what counts) and re-test on
   the same case, or route that case to human review.
3. **Code error** - wrong path, inverted yes/no, wrong threshold.
4. **Service failure** - timeouts and 429s are retried by the SDK; a failed
   call returns "no opinion" and the rule-based path continues.

Never raise a `yes` threshold's risk by lowering it to make a case pass: add the
exact name to the rule list instead.

## Undoing anything
Every HMS file edit writes `*.bak-<timestamp>` first. Copy it over the edited
file. `.gitignore` keeps backups, DSS, rasters and shapefiles out of git.
