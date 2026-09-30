"""
Headless CMIP6 pipeline:

    buffered polygon -> per-scenario clip/export (NetCDF + CSV) -> plots
    -> Vortex/Jython conversion to gridded DSS (24 h END shift, buffered clip shape)

Per-scenario clip/export runs in a ProcessPoolExecutor.  A PROCESS pool is used
(not threads) because the netCDF4/HDF5 C library under xarray's default engine
is not reliably thread-safe for concurrent reads across files (documented
xarray/dask gotcha), whereas each scenario here reads/writes an independent
file, so process isolation is both safe and gives real multi-core speed-up
(clip/regrid/unit work is CPU-bound).  Each worker's print() output is captured
and replayed by the parent so logs stay in clean per-scenario blocks.

Call :func:`run_pipeline` for clip/export/plots only, or :func:`run_full` to
also produce DSS files.  Both take a :class:`ClimateRunConfig`.
"""
from __future__ import annotations

import contextlib
import io
import multiprocessing
import os
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from ..vortex.converter import convert_netcdf_to_dss
from ..vortex.jython_templates import VortexJob, sanitize_part_b
from .clip import (build_buffered_geometry, clip_scenario, write_buffered_shapefile,
                   write_clipped_netcdf, write_timeseries_csv)
from .config import ClimateRunConfig

DAILY_SHIFT_HOURS = 24  # CMIP6 daily data -> END timestamp shift equals the time step


def kill_all_pipeline_processes() -> None:
    """Terminate any still-running clip/export worker processes (call on app exit)."""
    for child in multiprocessing.active_children():
        try:
            child.terminate()
        except Exception:
            pass


def _clip_and_export_one(cfg: ClimateRunConfig, scenario: str, buffered_gdf):
    """Worker-process body: clip one scenario and write its NetCDF/CSV.

    Module-level (picklable) and dependent only on its arguments.  stdout/stderr
    are captured locally and returned as text for the parent to replay.
    """
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            clip = clip_scenario(cfg, scenario, buffered_gdf)
            nc_path = write_clipped_netcdf(cfg, clip)
            write_timeseries_csv(cfg, clip)
        return scenario, clip, nc_path, buf.getvalue(), None
    except Exception as exc:
        buf.write(f"\n  ERROR [{scenario}]: {exc}\n")
        buf.write(traceback.format_exc())
        return scenario, None, None, buf.getvalue(), str(exc)


def _run_scenarios_parallel(cfg, scenarios, buffered_gdf, tick):
    """Clip/export every active scenario (in parallel if more than one).

    Returns (clips, clipped_paths, fallback_cells) in ``scenarios`` order.
    Raises RuntimeError listing EVERY failed scenario, not just the first.
    """
    clips, clipped_paths, fallback = {}, {}, []
    errors = []

    def collect(result):
        s, clip, nc_path, log_text, err = result
        if log_text:
            print(log_text, end="")
        if err:
            errors.append((s, err))
        else:
            clips[s], clipped_paths[s] = clip, nc_path
            fallback.extend(clip.get("fallback_cells", []))
        tick(f"Clipped and exported {s}")

    if len(scenarios) <= 1:      # no pool: skip process-spawn overhead
        for s in scenarios:
            collect(_clip_and_export_one(cfg, s, buffered_gdf))
    else:
        n_workers = min(len(scenarios), os.cpu_count() or 4)
        print(f"  Processing {len(scenarios)} scenarios in parallel (workers={n_workers})")
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            futures = {pool.submit(_clip_and_export_one, cfg, s, buffered_gdf): s for s in scenarios}
            for fut in as_completed(futures):
                try:
                    collect(fut.result())
                except Exception as exc:   # worker crashed outright (e.g. segfault)
                    errors.append((futures[fut], str(exc)))

    if errors:
        raise RuntimeError(f"{len(errors)} scenario(s) failed to clip/export: "
                           + "; ".join(f"{s}: {e}" for s, e in errors))

    # Restore deterministic order (completion order is non-deterministic in a pool).
    return ({s: clips[s] for s in scenarios}, {s: clipped_paths[s] for s in scenarios}, fallback)


def run_pipeline(cfg: ClimateRunConfig, progress_cb=None, make_plots: bool = True):
    """Clip/export (+ plots). Returns dict: clips, clipped_paths, buffered_gdf, basin_gdf."""
    problems = cfg.validate()
    if problems:
        raise ValueError("Invalid configuration: " + "; ".join(problems))

    Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)
    scenarios = cfg.active_scenarios()
    total = len(scenarios) + 2

    def tick(step, label):
        if progress_cb:
            progress_cb(step, total, label)

    print("=" * 60)
    print("  CLIMATE CHANGE (CMIP6) PIPELINE")
    print("=" * 60)
    print(f"  Basin      : {cfg.basin_name}")
    print(f"  Buffer     : {cfg.buffer_km} km (buffered polygon = selection + DSS clip shape)")
    print(f"  Variable   : {cfg.rain_var} (unit mode: {cfg.unit_mode})")
    print(f"  Scenarios  : {scenarios}")
    print(f"  Years      : {cfg.start_year or 'file start'} - {cfg.end_year or 'file end'}")

    tick(1, "Buffering basin polygon...")
    buffered_gdf, basin_gdf = build_buffered_geometry(cfg)

    done = 0

    def tick_scenario(label):
        nonlocal done
        done += 1
        tick(1 + done, label)

    clips, clipped_paths, fallback = _run_scenarios_parallel(cfg, scenarios, buffered_gdf, tick_scenario)

    # Written AFTER clipping so that, for boundary basins where the
    # nearest-valid-cell fallback fired, the Vortex clip shape covers those
    # out-of-buffer cells (otherwise the import would clip away the only cells
    # that carry data).
    write_buffered_shapefile(cfg, buffered_gdf, extra_cells=list(dict.fromkeys(fallback)) or None)

    if make_plots:
        from ..plots.climate import generate_all_plots
        tick(total, "Generating plots...")
        generate_all_plots(cfg, clips, basin_gdf, buffered_gdf)

    print("\n" + "=" * 60 + "\n  CLIP/EXPORT/PLOTS COMPLETE\n" + "=" * 60)
    return {"clips": clips, "clipped_paths": clipped_paths,
            "buffered_gdf": buffered_gdf, "basin_gdf": basin_gdf}


def run_full(cfg: ClimateRunConfig, vortex_home: str | Path, progress_cb=None,
             log_cb=print, make_plots: bool = True, max_workers: int | None = None):
    """Clip/export/plots AND Vortex conversion. Adds ``dss_files`` to the result dict."""
    result = run_pipeline(cfg, progress_cb=progress_cb, make_plots=make_plots)
    jobs = [
        VortexJob(label=s, nc=p, raw_dss=cfg.output_raw_dss_path(s),
                  final_dss=cfg.output_final_dss_path(s),
                  clip_shp=cfg.buffered_shapefile_path(),
                  part_b=sanitize_part_b(cfg.basin_name))
        for s, p in result["clipped_paths"].items()
    ]
    result["dss_files"] = convert_netcdf_to_dss(
        jobs, vortex_home, Path(cfg.output_dir) / "_vortex_run",
        wkt_label=cfg.target_projection_label, rain_var=cfg.rain_var,
        shift_hours=DAILY_SHIFT_HOURS, target_cell_size_m=cfg.target_cell_size_m,
        max_workers=max_workers, log_cb=log_cb)
    return result
