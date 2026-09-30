# hec_hms_automation

Automation toolkit for **HEC-HMS 4.x**: fill model parameters from GIS data,
build precipitation scenarios and runs across many projects, generate design
storms and climate-scenario rainfall, convert NetCDF to gridded DSS through
HEC-Vortex, compute simulations headlessly, and extract 10-daily flows.

Everything is global: no drive letters, no machine names. Tools are found
through arguments and environment variables.

> **Read it as a book.** [`docs/book/`](docs/book/00_how_this_book_works.md) walks
> the whole workflow from an empty machine to 10-daily flow workbooks, one
> chapter per process, each with *Run / Check / Judgment checkpoint / If it fails*.

## Quick start (CMD)

```cmd
cd /d E:\hec_hms_automation
pip install -r requirements.txt
pip install -e .
hms-auto --help
python -m pytest -q
```

## The workflow

| Ch. | Process | Command |
|---|---|---|
| 1 | Setup | `pip install -e .` |
| 2 | Read the model | `hms-auto read-basin <Basin_1.basin>` |
| 3 | Fill parameters | `hms-auto populate <project>` / `batch-fill <parent>` / `update-impervious` |
| 4 | Inspect rainfall NetCDF | `hms-auto inspect-nc <file.nc>` |
| 5 | Design storms | `hms-auto design-storm ...` |
| 6 | Climate scenarios (CMIP6) | `hms-auto climate ...` |
| 7 | NetCDF to gridded DSS | `hms-auto vortex-convert ...` |
| 8 | Scenarios and runs | `hms-auto build-scenarios / build-runs / build-one` |
| 9 | Compute | `hms-auto compute <parent> --tags RP5,RP10` |
| 10 | Extract 10-daily flow | `hms-auto extract-10daily <parent> <out>` |
| 11 | Export GIS layers | `hms-auto export-subbasins / export-sinks` |
| 12 | Troubleshooting | see the chapter |

## Requirements

Python 3.10+, the libraries in `requirements.txt`, and (from chapters 7 and 9)
**HEC-Vortex** and **HEC-HMS**, which are separate USACE products installed
independently. Details: [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md).

## Judgment: code first, Jev second (optional)

Numbers and safety checks are always decided by code. The optional
[TypeSafe Jev](https://docs.typesafe.ai/) advisor helps in exactly three places
where code would otherwise guess from *words* (impervious LULC class names, the
precipitation variable of a NetCDF, fuzzy basin-name matching). It only gives
banded advice, runs only after a rule found nothing, is logged, and is fully
optional: without `TYPESAFE_API_KEY` nothing changes. See chapter 0.

## Documentation

| | |
|---|---|
| [`docs/book/`](docs/book/00_how_this_book_works.md) | the workflow book, chapters 0-12 |
| [`docs/LITERATURE.md`](docs/LITERATURE.md) | what to read, by chapter (with a caveat to verify citations) |
| [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md) | libraries, external tools, environment variables |
| [`docs/HMS_FILE_FORMAT.md`](docs/HMS_FILE_FORMAT.md) | the HMS text formats and DSS pathnames |
| [`docs/DEVELOPER_GUIDE.md`](docs/DEVELOPER_GUIDE.md) | how to change the code safely; publishing to GitHub |
| [`docs/SCRIPT_INDEX.md`](docs/SCRIPT_INDEX.md) | where each original script went |

## Layout

```
src/hec_hms_automation/   hmsfiles  hydrology  gis  climate  vortex  dss
                          compute  workflows  plots  judgment  cli.py  config.py
tests/                    pure-logic tests
config/                   scenarios.example.yaml
docs/                     book + reference
```

## Known limitations

- The design-storm homogeneity test is a **simplified** screen, not the full
  Hosking and Wallis procedure (documented in `hydrology/design_storm.py`).
- CMIP6 output is clipped and unit-converted, **not bias-corrected**.
- HMS parameter defaults reflect one reference model; review them for other
  climates and terrains (`ParameterSet`).
- `populate` writes **Deficit and Constant** loss, **Modified Clark** transform,
  **Linear Reservoir** baseflow and **Muskingum** routing. A model using another
  method (e.g. the Smith-Parlange loss in `hms_test_dikrong`) is not fully
  parameterised by it; add the method as described in `docs/DEVELOPER_GUIDE.md`.
- The original GUI applications are not included.

## Licence
MIT (see `LICENSE`). HEC-HMS, HEC-DSS and HEC-Vortex are USACE software with
their own licences and are not distributed here.
