# Script index - where every original script went

Every script from the five source folders is either **ported** (same behaviour,
now global), **merged** into a shared function, or **left out** with a reason.

## `HMS Input data module`

| Original | Now | Command / function | Notes |
|---|---|---|---|
| `populate_hms.py` | `workflows/populate.py` | `hms-auto populate` | Terrain folder is chosen by highest `NN` holding both rasters |
| `batch_fill.py` | `workflows/populate.py` | `hms-auto batch-fill` | **Merged** with populate (they duplicated the compute path). The hard-coded `Basin_1.sqlite` and `terrain\...\00` are gone |
| `fill_basin.py` (YAML, fromGIS) | superseded | - | Same result as populate; the fromGIS route is kept as `gis/fromgis.py` |
| `hms_files/update_impervious.py` | `workflows/populate.update_impervious` + `hmsfiles/basin_writer.update_percent_impervious` | `hms-auto update-impervious` | Now uses `subbasin2d` (like populate) instead of fromGIS polygons |
| `hms_files/write_basin.py` | `hmsfiles/basin_writer.py` | `write_basin` | Backup via shared helper |
| `hms_files/write_scenarios.py` | `hmsfiles/scenario_writer.py` | `build_project` | |
| `hms_files/write_runs.py` | `hmsfiles/run_writer.py` | `build_runs` | |
| `build_scenarios.py`, `build_runs.py`, `build_one.py` | `workflows/scenarios.py` | `hms-auto build-scenarios / build-runs / build-one` | Config path is now `--config` (was a fixed file) |
| `run_simulations.py` | `compute/runner.py` | `hms-auto compute` | HMS folder from `--hms-home` / `HMS_HOME` (was fixed to 4.13 path) |
| `extract_10daily.py` | `dss/timeseries.py` | `hms-auto extract-10daily` | Scenarios come from `--config` |
| `export_subbasins.py`, `export_sinks.py` | `gis/export.py` | `hms-auto export-subbasins / export-sinks` | |
| `readers/read_basin.py` | `hmsfiles/basin_reader.py` | `hms-auto read-basin` | Adds `fill_state` |
| `readers/read_reaches.py` | `gis/hms_geometry.py` | `load_subbasins_2d`, `load_reaches_2d` | |
| `readers/read_gis.py` | `gis/fromgis.py` | `load_subbasins`, `load_reaches` | |
| `utils/basin_parser.py` | `hmsfiles/parser.py` | `parse_blocks` | |
| `calculators/params.py` | `hydrology/parameters.py` | `ParameterSet`, `subbasin_params`, `reach_params` | Constants became an overridable dataclass |
| `calculators/flowpath.py` | `gis/terrain.py` | `compute_terrain_stats` | |
| `calculators/impervious.py` | `gis/landuse.py` | `compute_impervious`, `resolve_impervious_values` | + optional Jev fallback |
| `tests/test_lukha_calcs.py` | not ported | - | Basin-specific; replaced by generic tests in `tests/test_core.py` |
| `_hms_scripts/compute_*.bat` | not ported | - | Generated at run time by `compute/runner.py` (they hard-coded one machine) |
| `config/lukha_config.yaml` | not ported | - | Only used by the superseded `fill_basin.py` |
| `config/scenarios.yaml` | `config/scenarios.example.yaml` | - | Machine paths replaced by examples with a field guide |
| `CLAUDE.md` | `docs/book/`, `docs/HMS_FILE_FORMAT.md` | - | Distilled into the book |

## `Climate change DSS Tool`

| Original | Now |
|---|---|
| `app/core/clip_export.py` | `climate/clip.py` |
| `app/core/run_config.py` | `climate/config.py` |
| `app/core/nc_inspect.py` | `climate/netcdf_inspect.py` (+ optional advisor) |
| `app/core/projection.py` | `climate/projection.py` (`guess_wkt_label`) |
| `app/core/pipeline_runner.py` | `climate/pipeline.py` (GUI queue plumbing removed) |
| `app/core/climate_plots.py` | `plots/climate.py` |
| `app/core/process_guard.py` | `vortex/process_guard.py` |
| `app/vortex_bridge/*` | `vortex/locator.py`, `jython_templates.py`, `converter.py` |
| `app/gui/*`, `app/main.py`, `settings_store.py`, PyInstaller build | **left out** (GUI). Rebuild as a front end over `workflows/` if needed |
| `tests/_debug_*.py` | left out (scratch debugging) |

## `Design Storm DSS Tool`

| Original | Now |
|---|---|
| `app/core/design_storm_pipeline.py` | `workflows/design_storm.py` (orchestration) + `hydrology/design_storm.py` (maths) |
| `app/core/cwc_factors.py` | `workflows/design_storm.py` (`load_cwc_factors`) |
| `app/core/design_storm_analysis.py` | `plots/design_storm.py` (`run_analysis`) |
| `app/core/run_config.py` | `workflows/design_storm.DesignStormConfig` |
| `app/vortex_bridge/*` | shared with the climate tool in `vortex/` (one template, per-job clip shape and B-part) |
| `app/resources/cwc_default.xlsx` | `src/hec_hms_automation/resources/cwc_default.xlsx` |
| `vortex/` (Vortex 0.13.3 binaries), `.venv_build/`, `DesignStormDSSTool/` build output | **not copied**: third-party binaries and build artefacts. Install Vortex separately |

## `hms_scripts`

| Original | Now |
|---|---|
| `convert_imd_full.py` | generated Jython: `hms-auto vortex-convert` (one call per basin; shift 24 h) |
| `vortex_test_grid_to_point.py` | `vortex/jython_templates.build_grid_to_point_script` |
| `run_vortex_test.bat`, `run_all_basins.bat` | replaced by `vortex/converter.run_jython_script` (machine paths removed) |

## `hms_test_dikrong`
A sample HMS project (rasters, DSS, sqlite). It is **data, not scripts**, so it
was not copied. It is the natural first project to try chapters 2, 3 and 9 on:
`hms-auto read-basin "E:\AI & ML\hms_test_dikrong\Hms_test_dikrong\Basin_1.basin"`.
Note its terrain has folders `00` (elevation only) and `01` (all derivatives);
the toolkit picks `01` automatically.
