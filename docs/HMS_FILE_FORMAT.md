# HEC-HMS 4.x text-file formats (as this toolkit reads and writes them)

USACE does not publish a formal specification. Everything below was derived
from real HMS 4.13 projects. Treat it as "what HMS accepted", and verify on a
copy of your model when you change a writer.

## Block format (all of `.hms .basin .met .control .grid .run .pdata .terrain`)

```
ElementType: Element Name
     Key: Value
     Key: Value
     Nested Block:
          Key: Value
     End Nested Block:
End:
```

- A top-level block starts at **column 0** as `Type: Name` and ends with a
  column-0 `End:`. The name may be empty.
- Fields are indented (HMS writes **5 spaces**). Strings are unquoted; booleans
  are `Yes` / `No`; dates `DD Month YYYY`; times `HH:MM`, where `24:00` is the
  midnight ending that day (`31 December 1970 24:00` = `01 Jan 1971 00:00`).
- Inner blocks use `End <Word>:` inconsistently; the parser treats them as
  opaque text.

## Project layout

```
<Project>.hms          registry: Precipitation / Basin / Control components
Basin_1.basin          elements + all parameters
Basin_1.sqlite         structured discretization: layers subbasin2d, reach2d
Control_<tag>.control  start/end/interval
Met_<tag>.met          precipitation method (gridded) + ET
<Project>.grid         grid manager: one Grid block per precipitation grid
<Project>.run          Run blocks (basin + met + control -> log + dss)
Run_<tag>.dss / .log   results and compute log
terrain\<T>\<NN>\      flowdir.tif demsd8.tif elevation.tif ... (NN increments)
gis\<Basin>\           fromGIS.sqlite / toGIS.sqlite
```

## Keys the writers manage

| File | Written by | Keys |
|---|---|---|
| `.basin` subbasin | `hmsfiles/basin_writer.py` | `Discretization/File/Projection/Cell Size`, `Percent Impervious Area`, `Initial Deficit`, `Maximum Deficit`, `Percolation Rate`, `Time of Concentration`, `Storage Coefficient`, `Groundwater Layer` + `GW-n ...` |
| `.basin` reach | same | `Muskingum K`, `Muskingum x` (lowercase x), `Muskingum Steps` |
| `.control` | `scenario_writer.write_control` | `Start Date`, `Start Time`, `End Date`, `End Time`, `Time Interval` (minutes), time-zone keys |
| `.met` | `scenario_writer.write_met` | `Precipitation Method: Gridded Precipitation` + `Precip Grid Name` |
| `.grid` | `scenario_writer.write_grid_file` | `Data Source Type: External DSS`, `Filename`, `Pathname` |
| `.run` | `run_writer.build_runs` | `Basin`, `Precip`, `Control`, `Log File`, `DSS File` |
| `.hms` | `scenario_writer.register_in_hms` | `Precipitation:` and `Control:` entries |

## HEC-DSS pathnames

```
Input grid  : /UTM46N/<basin>/PRECIPITATION/01JAN2024:0000/01JAN2024:0100/ts/
                A       B          C                D               E        F
Result      : //SUBBASIN-1/FLOW/31Dec1980 - 30Dec2018/1DAY/RUN:RUN 1/
                  B(element) C      D(date block)       E     F(run)
```
Gridded input is **written by Vortex** (`PER-CUM`, `MM`). Results are **read by
pydsstools**. The two cannot be swapped.

## Two data conventions worth remembering

- Daily rainfall NetCDF has no time-of-day, so Vortex writes zero-length
  periods; the END shift equal to the time step (24 h daily, 1 h hourly) fixes it.
- HMS stamps a daily average at 24:00, i.e. the next day's midnight.

## Typical HMS warnings that are *not* problems here
`WARNING 40909` no ET method; `40334` no canopy method; `40508` storage
coefficient below 0.5 x dt clamped (daily runs); `NOTE 41904` linear-reservoir
coefficient clamped.
