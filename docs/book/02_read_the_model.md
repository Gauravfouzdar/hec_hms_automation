# Chapter 2 - Read the model

## Purpose
Before changing anything, find out what the HMS project contains and how filled
it is. HMS models are plain-text files; this chapter shows how to read them.

## You need
A HEC-HMS project built in the GUI: sub-basins delineated, reaches and junctions
connected, a `.basin` file present. (The parameters may all be empty.)

## Run
```cmd
hms-auto read-basin "E:\MyModels\Lukha_basin\Basin_1.basin"
```

## What happens
`hmsfiles.parser` splits the file into top-level blocks (`Subbasin: Name` ...
`End:`). `hmsfiles.basin_reader` turns them into elements with their methods
(`LossRate`, `Transform`, `Baseflow`, `Route`) and lists any *expected* numeric
parameter that is absent for that method (e.g. `Time of Concentration` for a
Modified Clark subbasin).

Element names always come from the file itself, never from a spreadsheet.

## Check
The summary prints, per subbasin and reach, `<- missing: ...` for unset
parameters. `fill_state()` classifies the whole basin:

| State | Meaning | What later chapters do |
|---|---|---|
| `skeleton` | nothing filled | populate writes |
| `partial` | some elements filled | populate refuses unless `--force` |
| `filled` | all complete | populate refuses unless `--force` |

## Judgment checkpoint
**Rule only.** "Is this element filled" is exact: a parameter key is present or
not. To support another method (say SCS Unit Hydrograph) add its expected keys
to `_EXPECTED_PARAMS` in `basin_reader.py`.

## If it fails
- *`Subbasins: 0`* - you pointed at the wrong file, or the model was saved by a
  different HMS major version. Open it in HMS 4.x and save.
- Odd names in the output - the parser keeps names verbatim (including spaces).

## Where the code is
`hmsfiles/parser.py`, `hmsfiles/basin_reader.py`, and the file-format guide
`docs/HMS_FILE_FORMAT.md`.
