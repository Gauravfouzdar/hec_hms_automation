# Developer guide - how to change this project safely

The code will be edited by several people over time. This is the contract.

## Layout and layering

```
src/hec_hms_automation/
  config.py            tool discovery (HMS_HOME, VORTEX_HOME), scratch folder
  cli.py               argparse front end, one command per book chapter
  hmsfiles/            read/write HMS text files          (stdlib only)
  hydrology/           formulas: parameters, design_storm (numpy/scipy)
  gis/                 terrain, landuse, hms_geometry, fromgis, export
  climate/             CMIP6 config, clip, inspect, pipeline
  vortex/              Jython/bat generation, run, locate, process guard
  dss/                 read results, dekads
  compute/             headless HMS runs
  workflows/           populate, scenarios, design_storm  (combine the above)
  plots/               figures
  judgment/            optional Jev advisors + constants
  resources/           bundled data (CWC factors)
tests/                 pure-logic tests (no HEC software, no network)
docs/book/             the workflow book (one chapter per process)
docs/                  LITERATURE, DEPENDENCIES, HMS_FILE_FORMAT, SCRIPT_INDEX
config/                *.example.* config templates
```

Dependencies point **downwards** only: `workflows` may import anything;
`hmsfiles` and `hydrology.parameters` import nothing heavy. Keep it that way so
`hms-auto read-basin` stays instant.

## Rules for any change

1. **Nothing machine-specific.** No literal drive paths, no user names. Take a
   path as an argument or resolve it through `config.py`. Example data belongs
   in `config/*.example.*`, never in code.
2. **Parameters are data.** New constants go into `ParameterSet` (or a config
   dataclass) with a comment stating the source; never a bare number in a
   function body.
3. **Every writer backs up first** (`hmsfiles.backup.backup_file`) and stays
   **idempotent**. Add a test that runs it twice.
4. **Return a status string, do not `sys.exit`, from library functions.** Only
   `cli.py` decides exit codes. Batch functions print one line per project.
5. **Comment the why.** The comments in this repo explain hydrological or
   platform reasons ("why the END shift", "why `&` breaks cmd"). Keep that
   standard, and cite the reference (see `docs/LITERATURE.md`).
6. **Add a chapter line.** A new command means a `cli.py` entry, a section in
   the matching `docs/book/` chapter (or a new chapter using the seven-part
   template) and, if it uses a new source, a `docs/LITERATURE.md` entry.

## Adding a new HMS method (e.g. SCS Unit Hydrograph)
1. Add its expected keys to `_EXPECTED_PARAMS` (`hmsfiles/basin_reader.py`).
2. Add the formulas to `hydrology/parameters.py` and a dataclass for the result.
3. Teach `hmsfiles/basin_writer.py` where to anchor the new lines (follow how
   `Mod Clark Method:` is handled) and add the keys to `_SUB_DROP`.
4. Extend `workflows/populate.py` and the Excel sheet; add tests.

## Adding a Jev question (judgment layer)
Follow the design rules in `docs/book/00_how_this_book_works.md`:
1. Is it really a *text* judgment that a rule cannot make? If a rule can decide
   it exactly, or a wrong answer cannot be undone, use code.
2. Write the question, criteria and thresholds in `judgment/constants.py`.
3. Add an advisor in `judgment/advisors.py`: **rule first**, then Jev, and a
   "no opinion" result when Jev is unavailable. Put all questions for one state
   in one request; one `Noul` per label.
4. Give it a **band**, not authority. Nothing writes a file on a Jev answer
   that a rule has not already allowed. Print the decision with its source.
5. Test the offline path (see `test_judgment_falls_back_without_key`) and probe
   the live endpoint with a handful of labelled examples before trusting the
   thresholds.
6. Never hard-code, print or log the API key.

## Running the tests
```cmd
cd /d E:\hec_hms_automation
python -m pytest -q
```

## Publishing to GitHub (CMD)
```cmd
cd /d E:\hec_hms_automation
git init
git add .
git status
git commit -m "Initial commit: hec_hms_automation"
git branch -M main
git remote add origin https://github.com/<your-user>/hec_hms_automation.git
git push -u origin main
```
Check `git status` before committing: no `.dss`, `.tif`, `.nc`, `.shp`,
`.sqlite`, `*.bak-*` or key file should be staged (`.gitignore` excludes them).
Create the empty repository on GitHub first (without a README).
