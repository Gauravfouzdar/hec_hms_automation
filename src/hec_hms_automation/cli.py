"""
Command line for the whole toolkit:   hms-auto <command> [options]
                                      python -m hec_hms_automation <command> ...

Commands follow the order of the workflow book (docs/book/):

    read-basin            ch.2  inspect a .basin: elements, methods, missing parameters
    populate              ch.3  fill one project's parameters from its GIS data
    batch-fill            ch.3  recon / fill many projects
    update-impervious     ch.3  refresh only impervious % from a new LULC raster
    inspect-nc            ch.4  list NetCDF variables, suggest the precipitation one
    design-storm          ch.5  design-storm NetCDFs (+ DSS) per return period
    climate               ch.6  CMIP6 clip/export (+ DSS) per scenario
    vortex-convert        ch.7  one NetCDF -> gridded DSS (generic)
    build-scenarios       ch.8  met/control/grid for every scenario
    build-runs            ch.8  one run per scenario
    build-one             ch.8  a single scenario end to end
    compute               ch.9  run HEC-HMS headlessly
    extract-10daily       ch.10 10-daily (dekad) flow workbooks from run DSS
    export-subbasins      ch.11 sub-basin shapefiles
    export-sinks          ch.11 pour-point shapefile

Heavy libraries are imported inside each command so ``hms-auto --help`` is instant
and commands that need no GIS stack (read-basin, build-*) run without it.
"""
from __future__ import annotations

import argparse
import sys


def _add_common_paths(p):
    p.add_argument("--hms-home", help="HEC-HMS install folder (default: HMS_HOME env var / auto-detect)")
    p.add_argument("--vortex-home", help="HEC-Vortex folder (default: VORTEX_HOME env var / auto-detect)")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="hms-auto", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("read-basin", help="summarise a .basin file")
    p.add_argument("basin")

    p = sub.add_parser("populate", help="fill one project's parameters from its GIS data")
    p.add_argument("project")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="re-populate an already-filled .basin")
    p.add_argument("--lulc", help="explicit LULC raster (default: Input data/*LULC*.tif)")
    p.add_argument("--judge-lulc", action="store_true",
                   help="optional: Jev advises on unrecognised LULC class names (needs TYPESAFE_API_KEY)")

    p = sub.add_parser("batch-fill", help="recon (default) or fill every project under a folder")
    p.add_argument("parent")
    p.add_argument("--write", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--judge-lulc", action="store_true")

    p = sub.add_parser("update-impervious", help="recompute only impervious %% from a LULC raster")
    p.add_argument("project")
    p.add_argument("lulc")
    p.add_argument("--judge-lulc", action="store_true")

    p = sub.add_parser("inspect-nc", help="list NetCDF variables and suggest the precipitation one")
    p.add_argument("netcdf")
    p.add_argument("--judge", action="store_true", help="allow Jev when no alias matches")

    p = sub.add_parser("design-storm", help="design-storm NetCDFs (and DSS with --vortex) per return period")
    p.add_argument("--imd", required=True, help="IMD daily gridded NetCDF")
    p.add_argument("--basin-shp", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--name", required=True, help="basin name used in file names / DSS B-part")
    p.add_argument("--cwc-zone", default="2b")
    p.add_argument("--cwc-excel", default="")
    p.add_argument("--rp", default="5,10,25,50,100")
    p.add_argument("--buffer-km", type=float, default=25.0)
    p.add_argument("--total-days", type=int, default=10)
    p.add_argument("--storm-day", type=int, default=5)
    p.add_argument("--start-date", default="2024-01-01")
    p.add_argument("--rain-var", default="rain")
    p.add_argument("--wkt", default="", help="Vortex projection label, e.g. UTM46N (default: from shapefile)")
    p.add_argument("--vortex", action="store_true", help="also convert to gridded DSS via Vortex")
    p.add_argument("--qa", action="store_true", help="also run the QA plots/CSVs")
    _add_common_paths(p)

    p = sub.add_parser("climate", help="CMIP6 clip/export (and DSS with --vortex) per scenario")
    p.add_argument("--basin-shp", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--scenario", action="append", default=[], metavar="NAME=FILE",
                   help="repeatable, e.g. --scenario historical=hist.nc --scenario ssp245=ssp245.nc")
    p.add_argument("--rain-var", default="pr")
    p.add_argument("--buffer-km", type=float, default=25.0)
    p.add_argument("--start-year", type=int, default=0)
    p.add_argument("--end-year", type=int, default=0)
    p.add_argument("--ref", default="1981-2014", help="change-signal reference period")
    p.add_argument("--wkt", default="")
    p.add_argument("--vortex", action="store_true")
    p.add_argument("--no-plots", action="store_true")
    _add_common_paths(p)

    p = sub.add_parser("vortex-convert", help="one NetCDF -> gridded DSS (import + END time shift)")
    p.add_argument("--nc", required=True)
    p.add_argument("--shp", required=True, help="clip polygon shapefile")
    p.add_argument("--out-dss", required=True, help="final DSS path")
    p.add_argument("--wkt", required=True, help="projection label, e.g. UTM46N")
    p.add_argument("--part-b", required=True)
    p.add_argument("--var", default="rain")
    p.add_argument("--shift-hours", type=int, required=True, help="record step: 24 daily, 1 hourly")
    p.add_argument("--cell-size", default="2000")
    _add_common_paths(p)

    for name, hlp in (("build-scenarios", "met/control/grid for every scenario"),
                      ("build-runs", "one run per scenario")):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("parent")
        p.add_argument("--config", required=True, help="scenarios.yaml")
        p.add_argument("--project")
        if name == "build-scenarios":
            p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("build-one", help="a single scenario (met/control/grid + run)")
    p.add_argument("parent")
    p.add_argument("tag")
    p.add_argument("--config", required=True)
    p.add_argument("--project")

    p = sub.add_parser("compute", help="run HEC-HMS headlessly")
    p.add_argument("parent")
    p.add_argument("--tags", required=True, help="comma-separated run tags, e.g. RP5,RP10")
    p.add_argument("--project")
    _add_common_paths(p)

    p = sub.add_parser("extract-10daily", help="10-daily flow workbooks from run DSS files")
    p.add_argument("parent")
    p.add_argument("out")
    p.add_argument("--variable", default="FLOW")
    p.add_argument("--project")
    p.add_argument("--scenarios", action="store_true", help="extract scenario runs (needs --config)")
    p.add_argument("--config", help="scenarios.yaml (with --scenarios)")

    for name in ("export-subbasins", "export-sinks"):
        p = sub.add_parser(name)
        p.add_argument("parent")
        p.add_argument("out")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    c = args.cmd

    if c == "read-basin":
        from .hmsfiles.basin_reader import print_summary, read_basin
        print_summary(read_basin(args.basin))

    elif c == "populate":
        from .workflows.populate import populate_project
        status = populate_project(args.project, dry_run=args.dry_run, force=args.force,
                                  lulc_override=args.lulc, judge_lulc=args.judge_lulc)
        print(status)
        return 1 if status.startswith(("SKIP", "ERROR")) else 0

    elif c == "batch-fill":
        from .workflows.populate import batch_populate
        batch_populate(args.parent, write=args.write, force=args.force, debug=args.debug,
                       judge_lulc=args.judge_lulc)

    elif c == "update-impervious":
        from .workflows.populate import update_impervious
        update_impervious(args.project, args.lulc, judge_lulc=args.judge_lulc)

    elif c == "inspect-nc":
        from .climate.netcdf_inspect import inspect_netcdf
        info = inspect_netcdf(args.netcdf, judge_variable=args.judge)
        for v in info["variables"]:
            print(f"  {v['name']:24s} {v['units']:12s} {v['dims']}  {v['long_name']}")
        print(f"suggested precipitation variable: {info['suggested'] or '(none)'} "
              f"[{info['suggestion_source'] or '-'}, {info['suggestion_band'] or '-'}]")
        print(f"years: {info['time_start']} - {info['time_end']}")

    elif c == "design-storm":
        from .workflows import design_storm as dsw
        cfg = dsw.DesignStormConfig(
            imd_netcdf=args.imd, basin_shapefile=args.basin_shp, output_dir=args.out,
            basin_name=args.name, cwc_zone=args.cwc_zone, cwc_excel=args.cwc_excel,
            return_periods=[int(x) for x in args.rp.split(",")], buffer_km=args.buffer_km,
            total_days=args.total_days, storm_day=args.storm_day, storm_start_date=args.start_date,
            rain_var=args.rain_var, target_projection_label=args.wkt)
        if args.vortex:
            from .climate.projection import guess_wkt_label
            from .config import find_vortex_home
            cfg.target_projection_label = args.wkt or guess_wkt_label(args.basin_shp)
            home = find_vortex_home(args.vortex_home)
            if home is None:
                raise SystemExit("Vortex not found: set VORTEX_HOME or pass --vortex-home.")
            dsw.run_full(cfg, home)
        else:
            dsw.run_pipeline(cfg)
        if args.qa:
            from .plots.design_storm import run_analysis
            run_analysis(cfg)

    elif c == "climate":
        from .climate.config import SCENARIOS, ClimateRunConfig
        from .climate.pipeline import run_full, run_pipeline
        from .climate.projection import guess_wkt_label
        files = {s: "" for s in SCENARIOS}
        for item in args.scenario:
            name, _, path = item.partition("=")
            if name not in files:
                raise SystemExit(f"unknown scenario '{name}' (use one of {SCENARIOS})")
            files[name] = path
        r0, r1 = (int(x) for x in args.ref.split("-"))
        cfg = ClimateRunConfig(basin_shapefile=args.basin_shp, output_dir=args.out, basin_name=args.name,
                               scenario_files=files, rain_var=args.rain_var, buffer_km=args.buffer_km,
                               start_year=args.start_year, end_year=args.end_year, ref_start=r0, ref_end=r1,
                               target_projection_label=args.wkt or guess_wkt_label(args.basin_shp))
        if args.vortex:
            from .config import find_vortex_home
            home = find_vortex_home(args.vortex_home)
            if home is None:
                raise SystemExit("Vortex not found: set VORTEX_HOME or pass --vortex-home.")
            run_full(cfg, home, make_plots=not args.no_plots)
        else:
            run_pipeline(cfg, make_plots=not args.no_plots)

    elif c == "vortex-convert":
        from pathlib import Path
        from .config import find_vortex_home
        from .vortex.converter import convert_netcdf_to_dss
        from .vortex.jython_templates import VortexJob
        home = find_vortex_home(args.vortex_home)
        if home is None:
            raise SystemExit("Vortex not found: set VORTEX_HOME or pass --vortex-home.")
        final = Path(args.out_dss)
        job = VortexJob(label=final.stem, nc=args.nc, raw_dss=str(final.with_name(final.stem + "_raw.dss")),
                        final_dss=str(final), clip_shp=args.shp, part_b=args.part_b)
        convert_netcdf_to_dss([job], home, final.parent / "_vortex_run", args.wkt, args.var,
                              args.shift_hours, args.cell_size, log_cb=print)

    elif c == "build-scenarios":
        from .workflows.scenarios import build_scenarios
        build_scenarios(args.parent, args.config, dry_run=args.dry_run, only=args.project)
    elif c == "build-runs":
        from .workflows.scenarios import build_all_runs
        build_all_runs(args.parent, args.config, only=args.project)
    elif c == "build-one":
        from .workflows.scenarios import build_one
        build_one(args.parent, args.tag, args.config, only=args.project)

    elif c == "compute":
        from .compute.runner import compute_all
        compute_all(args.parent, args.tags.split(","), only=args.project, hms_home=args.hms_home)

    elif c == "extract-10daily":
        from .dss.timeseries import extract_10daily
        scen = None
        if args.scenarios:
            if not args.config:
                raise SystemExit("--scenarios needs --config scenarios.yaml")
            from .workflows.scenarios import load_scenarios
            scen = load_scenarios(args.config)[0]
        extract_10daily(args.parent, args.out, args.variable, args.project, scen)

    elif c == "export-subbasins":
        from .gis.export import export_subbasins
        export_subbasins(args.parent, args.out)
    elif c == "export-sinks":
        from .gis.export import export_sinks
        export_sinks(args.parent, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
