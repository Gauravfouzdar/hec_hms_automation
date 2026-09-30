# Chapter 8 - Scenarios and runs in every project

## Purpose
Attach each rainfall DSS to your HMS projects as a *scenario* (a Met model, a
Control specification and a Grid record) and create one *Run* per scenario, in
one command for as many projects as you have.

## You need
- Projects with a `.hms` file (filled in chapter 3).
- The DSS files from chapter 7 and their **exact** first-record pathnames.
- A scenarios YAML: copy `config/scenarios.example.yaml` to
  `config/scenarios.local.yaml` (git-ignored) and edit it.

Field guide for the YAML: `interval_min` **must equal the DSS record spacing**
(60 hourly, 1440 daily); `end_time: "24:00"` means the midnight that ends that
day; `pathname` is the first grid record.

## Run
```cmd
hms-auto build-scenarios "E:\MyModels" --config config\scenarios.local.yaml --dry-run
hms-auto build-scenarios "E:\MyModels" --config config\scenarios.local.yaml
hms-auto build-runs      "E:\MyModels" --config config\scenarios.local.yaml

:: or a single scenario, leaving all others untouched
hms-auto build-one "E:\MyModels" 30yr_chirps --config config\scenarios.local.yaml
```

## What happens
For each project: `Control_<tag>.control` and `Met_<tag>.met` are written, the
scenario's `Grid:` block is added to `<project>.grid`, both are registered in
`<project>.hms`, and `Run <tag>` is added to `<project>.run` pairing the
project's basin model with that Met and Control. Each run has its own log and
output DSS (`Run_<tag>.log`, `Run_<tag>.dss`). Existing components are kept; a
re-run replaces only that tag.

## Check
- Every project prints `OK  n met + n control + n grid` and `OK  n runs`.
- Open one project in HMS: the runs appear in the Compute tab.
- Automated evidence: `tests/test_core.py` proves that adding, then re-running,
  scenarios never duplicates or drops components.

## Judgment checkpoint
| Decision | Decided by |
|---|---|
| Does each scenario's DSS file exist? | **Code rule**: the command stops before touching any project if one is missing |
| Are `pathname` and `interval_min` right? | **You**, verified against the DSS catalogue (chapter 7). A wrong B-part or interval produces "missing precipitation" in HMS, not an error here |
| Which basin/project does a scenario belong to? | You, by folder. If you need to *map names* between sources (for example a data set that spells `Umsohryngkew` while the model says `Umsohrenkew_Basin`), use `judgment.match_name`: it tries an exact normalised match first, then shortlists candidates in code and lets Jev choose among them or answer `none_of_the_above`. It returns a suggestion band only; you confirm |

## If it fails
| Symptom | Fix |
|---|---|
| `DSS file(s) not found for scenarios` | Fix the path in the YAML |
| `SKIP expected 1 .hms file` | The folder is not a single HMS project |
| HMS says precipitation is missing | Wrong pathname or `interval_min` |
| Something went wrong after a build | Copy the `*.bak-*` of `.hms`, `.grid` or `.run` back |

## Where the code is
`workflows/scenarios.py`, `hmsfiles/scenario_writer.py`, `hmsfiles/run_writer.py`,
`config/scenarios.example.yaml`.
