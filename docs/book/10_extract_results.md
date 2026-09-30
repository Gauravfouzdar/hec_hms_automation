# Chapter 10 - Extract 10-daily flow

## Purpose
Turn each run's daily (or hourly) DSS flows into **10-daily (dekad) mean flow**
workbooks for water-availability work.

## You need
Computed runs (chapter 9) and `pip install pydsstools` (reads DSS; it cannot
write gridded data, which is why Vortex is used in chapter 7).

## Run
```cmd
:: baseline "Run 1" of every project
hms-auto extract-10daily "E:\MyModels" "E:\out\10daily"

:: one variable / one project
hms-auto extract-10daily "E:\MyModels" "E:\out\10daily" --variable FLOW --project Lukha_basin

:: the RP / climate scenario runs instead
hms-auto extract-10daily "E:\MyModels" "E:\out\10daily" --scenarios --config config\scenarios.local.yaml
```

## What happens
For each project it reads the sub-basin names from the `.basin`, then for each
sub-basin reads `//<name>/FLOW//<interval>/RUN:<run>/` from `Run_<tag>.dss`.
Run 1's window and interval are read back off the DSS itself (its date range
differs per basin). Values are grouped into dekads and averaged.

Dekad convention: **1 = days 1-10, 2 = days 11-20, 3 = day 21 to month end.**
Output: `<project>_10daily_flow.xlsx`, one sheet per run, columns `Year, Month,
Dekad` then one column per sub-basin.

HMS stamps a daily average at **24:00, the next day's midnight**; one second is
subtracted so every value lands in the day it describes. pydsstools returns
value buffers that can be reused, so the code **copies** them.

## Check
- The printed line per project: `OK  17 subbasins  [Run 1: 1116 dekads 1971-2001]`
  (36 dekads per year).
- Pick one sub-basin and one dekad and recompute the mean of its 10 daily values
  by hand.

## Judgment checkpoint
**Code only.** Dekad boundaries, the 24:00 shift and the mean are exact rules.
The choice of *mean* (not sum or median) is a modelling decision fixed by the
project convention; change it in `extract_project` if your report needs another.

## If it fails
| Symptom | Fix |
|---|---|
| `Reading DSS needs pydsstools` | `pip install pydsstools` |
| `SKIP no Run 1 records` | Run 1 has no `FLOW` records in its DSS |
| Empty workbook for a sub-basin | That element has no record in the run: check names |
| Some dekads missing | Nodata in the DSS; the code drops nodata rather than filling |

## Where the code is
`dss/timeseries.py`.
