# Chapter 1 - Setup

## Purpose
Get a machine to the point where every later command works. Nothing here is
hard-coded: tools are found through arguments and environment variables.

## You need
- Windows with **Python 3.10+** (the project was developed on Anaconda 3.12).
- **HEC-HMS 4.x** (needed from chapter 9).
- **HEC-Vortex** with its bundled JRE (needed from chapter 7). Download from the
  HEC-Vortex releases page (see `docs/LITERATURE.md`, section E).
- Optional: a `TYPESAFE_API_KEY` for the Jev advisor (chapter 0).

## Run
```cmd
cd /d E:\hec_hms_automation
pip install -r requirements.txt
pip install -e .
hms-auto --help
```

Tell the toolkit where the external tools live (once per machine):
```cmd
setx HMS_HOME "C:\Program Files\HEC\HEC-HMS\4.13"
setx VORTEX_HOME "C:\Tools\vortex-0.13.3"
```
Open a new Command Prompt afterwards so the variables are visible. Or skip this
and pass `--hms-home` / `--vortex-home` on each command.

Optional Jev advisor (never paste the key into a file or a chat):
```cmd
pip install typesafe-sdk
setx TYPESAFE_API_KEY "<your key>"
```

## What happens
`pip install -e .` registers the `hms-auto` command and installs the package in
editable mode, so edits to the source take effect immediately.

## Check
```cmd
python -m pytest -q
```
The tests cover the pure logic and need neither HEC software nor a network.
Then confirm the tools resolve:
```cmd
python -c "from hec_hms_automation.config import find_hms_home, find_vortex_home; print(find_hms_home()); print(find_vortex_home())"
```

## Judgment checkpoint
None. Setup is fully deterministic. `judgment.available()` reports whether the
Jev advisor can run (SDK importable and key present); it never prints the key.

## If it fails
| Symptom | Cause and fix |
|---|---|
| `pip install rasterio` fails | Use the conda route: `conda env create -f environment.yml` |
| `HEC-HMS not found` | Set `HMS_HOME` to the folder that contains `HEC-HMS.cmd` |
| `Vortex not found` | `VORTEX_HOME` must contain `jre\bin\java.exe`, `lib\` and a `jython-standalone*.jar` (in it or one level above) |
| `pydsstools` will not install | Only needed for chapter 10. It ships wheels for limited Python versions; use a matching Python or a separate environment |

## Where the code is
`src/hec_hms_automation/config.py`, `vortex/locator.py`, `requirements.txt`,
`environment.yml`, `docs/DEPENDENCIES.md`.
