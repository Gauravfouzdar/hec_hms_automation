"""
Populate a parameter-empty HEC-HMS project from its own GIS data.

Given an HMS project directory this workflow

  1. auto-discovers the inputs (.basin, terrain flowdir/demsd8 rasters, LULC
     raster + VAT, the basin sqlite),
  2. computes every parameter (Kirpich Tc, storage coeff. R, baseflow
     coefficients, Muskingum K, impervious %),
  3. saves the full calculation table as ``computed_parameters.xlsx`` next to
     the LULC raster (for review / records),
  4. writes the values into the .basin file (timestamped backup kept).

Safety rails (all enforced in code -- none is delegated to any model):
  * dry-run computes and reports, writes nothing to the .basin
  * an already-filled .basin is NOT rewritten unless ``force=True``
  * the LULC raster must share the project CRS and overlap the subbasins,
    otherwise the project is skipped (catches misnamed/misplaced rasters)
  * impervious classes are resolved by NAME through the raster's VAT

CLI:  hms-auto populate "<project dir>" [--dry-run] [--force]
      hms-auto batch-fill "<parent dir>" [--write] [--force]
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import rasterio

from ..gis.hms_geometry import load_reaches_2d, load_subbasins_2d
from ..gis.landuse import (IMPERVIOUS_CLASS_NAMES, compute_impervious, read_vat_classes,
                           resolve_impervious_values, vat_sidecar)
from ..gis.terrain import compute_terrain_stats
from ..hmsfiles.basin_reader import fill_state, missing_params, read_basin
from ..hmsfiles.basin_writer import write_basin
from ..hydrology.parameters import DEFAULT_PARAMETERS, ParameterSet, reach_params, subbasin_params

CELL_SIZE_M = 2000.0   # structured-grid cell size HMS discretization used for these models


class InputDiscoveryError(Exception):
    """The project folder lacks (or has ambiguous) required inputs."""


@dataclass
class ProjectInputs:
    basin: Path
    sqlite: Path      # HMS basin geometry (subbasin2d / reach2d)
    flowdir: Path
    demsd8: Path
    dem: Path | None
    lulc: Path


def _pick_terrain(project: Path) -> tuple[Path, Path]:
    """(flowdir, demsd8) from ``terrain/<Terrain>/<NN>/``.

    HMS writes a new numbered folder when terrain is re-preprocessed (00, 01,
    ...); only a folder holding BOTH rasters qualifies, and the highest number
    wins.
    """
    pairs = [(f, f.with_name("demsd8.tif")) for f in sorted(project.glob("terrain/*/*/flowdir.tif"))]
    pairs = [p for p in pairs if p[1].exists()]
    if not pairs:
        raise InputDiscoveryError("no terrain/*/*/ folder holding both flowdir.tif and demsd8.tif")
    if len(pairs) > 1:
        print(f"  note: {len(pairs)} terrain versions found; using {pairs[-1][0].parent.relative_to(project)}")
    return pairs[-1]


def discover_inputs(project: Path, lulc_override: Path | None = None) -> ProjectInputs:
    """Locate the required inputs inside ``project`` or raise InputDiscoveryError
    listing exactly what is missing / ambiguous."""
    problems = []
    basins = sorted(project.glob("*.basin"))
    if len(basins) != 1:
        problems.append(f"basin: found {len(basins)}, need exactly 1")
    lulc = [lulc_override] if lulc_override else (
        sorted(project.glob("Input_data/*LULC*.tif")) + sorted(project.glob("Input data/*LULC*.tif")))
    if len(lulc) != 1:
        problems.append(f"lulc: found {len(lulc)}, need exactly 1 (Input data/*LULC*.tif)")
    try:
        flowdir, demsd8 = _pick_terrain(project)
    except InputDiscoveryError as e:
        problems.append(str(e))
        flowdir = demsd8 = None
    if problems:
        raise InputDiscoveryError(f"Cannot auto-discover inputs under {project}:\n  " + "\n  ".join(problems))

    # The basin sqlite sits next to the .basin with the same stem (Basin_1.basin -> Basin_1.sqlite).
    sqlite = basins[0].with_suffix(".sqlite")
    if not sqlite.exists():
        raise InputDiscoveryError(f"{sqlite.name} not found -- open the project in HMS and define "
                                  f"the structured discretization first.")
    dem = flowdir.parent / "elevation.tif"
    return ProjectInputs(basins[0], sqlite, flowdir, demsd8, dem if dem.exists() else None, lulc[0])


def check_lulc_overlap(lulc: Path, flowdir: Path, geoms: dict) -> str | None:
    """None if the LULC raster is usable, else a one-line reason to SKIP."""
    with rasterio.open(flowdir) as ds:
        epsg = ds.crs.to_epsg()
    with rasterio.open(lulc) as ds:
        crs, b = ds.crs, ds.bounds
    if crs.to_epsg() != epsg:
        return f"LULC CRS {crs} != project EPSG:{epsg} ({lulc.name})"
    bx = [g.bounds for g in geoms.values()]
    xmin, ymin = min(v[0] for v in bx), min(v[1] for v in bx)
    xmax, ymax = max(v[2] for v in bx), max(v[3] for v in bx)
    if b.right < xmin or b.left > xmax or b.top < ymin or b.bottom > ymax:
        return f"LULC does not overlap basin extent ({lulc.name})"
    return None


def _method_rows(project, files, epsg, imp_values, lulc_classes, pset: ParameterSet):
    return [
        ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("Project", str(project)),
        ("Basin file", files.basin.name),
        ("LULC raster", files.lulc.name),
        ("Impervious classes", ", ".join(f"{v}={lulc_classes[v]}" for v in imp_values)),
        ("Projection EPSG", epsg),
        ("Discretization cell size (m)", CELL_SIZE_M),
        ("Tc formula", "Kirpich: Tc_min = 0.0195 * L^0.77 * S^-0.385"),
        ("R formula", f"R = {pset.storage_coeff_ratio:.4f} * Tc   [from R/(Tc+R) = 0.65]"),
        ("Muskingum K", "Kirpich Tc of reach (network length & slope)"),
        ("Muskingum x", pset.muskingum_x),
        ("Slope/length floors", f"S >= {pset.min_slope}, L >= {pset.min_length_m} m"),
    ]


def populate_project(project: str | Path, dry_run: bool = False, force: bool = False,
                     write_excel: bool = True, lulc_override: str | Path | None = None,
                     judge_lulc: bool = False, pset: ParameterSet = DEFAULT_PARAMETERS,
                     verbose: bool = True) -> str:
    """Populate one project. Returns a one-line status (``WROTE`` / ``READY`` / ``SKIP`` ...).

    write_excel   write ``computed_parameters.xlsx`` (single-project mode);
                  batch reconnaissance passes False
    judge_lulc    let the optional Jev advisor classify LULC class names when
                  the exact-name list matches nothing (see judgment/)
    """
    project = Path(project)
    say = print if verbose else (lambda *a, **k: None)
    try:
        files = discover_inputs(project, Path(lulc_override) if lulc_override else None)
    except InputDiscoveryError as e:
        return f"SKIP  {e}"

    basin = read_basin(files.basin)
    state = fill_state(basin)
    if state != "skeleton" and not force and not write_excel:
        return f"SKIP  .basin already {state} ({len(basin.subbasins)} subbasins) -- use --force to re-populate"

    say(f"Project : {project.name}")
    with rasterio.open(files.flowdir) as ds:
        epsg = ds.crs.to_epsg()
    geoms = load_subbasins_2d(files.sqlite, [el.name for el in basin.subbasins])

    reason = check_lulc_overlap(files.lulc, files.flowdir, geoms)
    if reason:
        return f"SKIP  {reason}"

    imp_values = resolve_impervious_values(files.lulc, IMPERVIOUS_CLASS_NAMES, judge_unmatched=judge_lulc)
    if not imp_values:
        return f"SKIP  no impervious classes found in VAT of {files.lulc.name}"
    say(f"  impervious raster values {imp_values}")

    say("  computing longest flow paths, slopes, impervious fractions ...")
    reaches_gis = load_reaches_2d(files.sqlite, [el.name for el in basin.reaches],
                                  dem_path=files.dem, min_slope=pset.min_slope)
    terrain = compute_terrain_stats(files.flowdir, files.demsd8, geoms)
    imperv = compute_impervious(files.lulc, geoms, imp_values)

    sub_p, sub_rows = {}, []
    for el in basin.subbasins:
        t = terrain[el.name]
        p = subbasin_params(el.name, t.longest_flowpath_m, t.basin_slope,
                            imperv[el.name].percent_impervious, pset)
        sub_p[el.name] = p
        sub_rows.append({
            "Subbasin": el.name, "Area (km2)": el.area_km2, "Downstream": el.downstream,
            "Longest Flow Path (m)": round(t.longest_flowpath_m, 1),
            "Basin Slope (m/m)": round(t.basin_slope, 5),
            "Tc (hr)": round(p.tc_hr, 3), "Storage Coefficient R (hr)": round(p.storage_coeff_hr, 3),
            "Initial Deficit (mm)": p.initial_deficit_mm, "Maximum Deficit (mm)": p.maximum_deficit_mm,
            "Percolation Rate (mm/hr)": p.percolation_rate_mm_hr,
            "Impervious (%)": round(p.percent_impervious, 3),
            "GW-1 Fraction": p.gw1_fraction, "GW-1 Coefficient (hr) = 3R": round(p.gw1_coeff_hr, 3),
            "GW-2 Fraction": p.gw2_fraction, "GW-2 Coefficient (hr) = 10R": round(p.gw2_coeff_hr, 3),
            "GW Initial Baseflow (m3/s)": p.gw1_initial_m3s,
        })

    reach_p, reach_rows = {}, []
    for el in basin.reaches:
        g = reaches_gis[el.name]
        p = reach_params(el.name, g.length_m, g.slope, pset)
        reach_p[el.name] = p
        reach_rows.append({
            "Reach": el.name, "Downstream": el.downstream, "Length (m)": round(g.length_m, 1),
            "Slope (m/m)": round(g.slope, 6), "Slope Source": g.slope_source,
            "Muskingum K (hr)": round(p.muskingum_k_hr, 3), "Muskingum x": p.muskingum_x,
            "Muskingum Steps": p.muskingum_steps,
        })

    if write_excel:
        vat = vat_sidecar(files.lulc)
        classes = read_vat_classes(vat) if vat else {v: str(v) for v in imp_values}
        xlsx = files.lulc.parent / "computed_parameters.xlsx"
        with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
            pd.DataFrame(sub_rows).to_excel(xw, sheet_name="Subbasins", index=False)
            pd.DataFrame(reach_rows).to_excel(xw, sheet_name="Reaches", index=False)
            pd.DataFrame(_method_rows(project, files, epsg, imp_values, classes, pset),
                         columns=["Item", "Value"]).to_excel(xw, sheet_name="Method", index=False)
        say(f"  intermediate output written: {xlsx}")

    if dry_run:
        return (f"READY {len(sub_p)} subbasins, {len(reach_p)} reaches | EPSG:{epsg} | "
                f"LULC {files.lulc.name} (dry-run: .basin not modified)")
    if state != "skeleton" and not force:
        return ".basin already fully parameterised -- not rewritten (use --force to re-populate)"

    write_basin(files.basin, sub_p, reach_p, grid_file=files.sqlite.name,
                projection_epsg=epsg, cell_size_m=CELL_SIZE_M)
    check = read_basin(files.basin)
    left = [el.name for el in check.subbasins + check.reaches if missing_params(el)]
    if left:
        return f"WROTE but still missing params on: {', '.join(left)}"
    return (f"WROTE {len(check.subbasins)} subbasins, {len(check.reaches)} reaches complete "
            f"(backup saved alongside)")


def update_impervious(project: str | Path, lulc_tif: str | Path, judge_lulc: bool = False) -> None:
    """Recompute ONLY ``Percent Impervious Area`` from a new/corrected LULC raster.

    Impervious % is the only parameter derived from LULC, so nothing else in the
    filled .basin is touched.  Uses HMS's own ``subbasin2d`` geometry (the same
    source as :func:`populate_project`).  A timestamped backup is kept.
    """
    from ..hmsfiles.basin_writer import update_percent_impervious

    project, lulc_tif = Path(project), Path(lulc_tif)
    files = discover_inputs(project, lulc_override=lulc_tif)
    basin = read_basin(files.basin)
    geoms = load_subbasins_2d(files.sqlite, [el.name for el in basin.subbasins])

    reason = check_lulc_overlap(lulc_tif, files.flowdir, geoms)
    if reason:
        raise SystemExit(f"Refusing to update: {reason}")
    values = resolve_impervious_values(lulc_tif, IMPERVIOUS_CLASS_NAMES, judge_unmatched=judge_lulc)
    if not values:
        raise SystemExit(f"No impervious classes found in the VAT of {lulc_tif.name}")
    print(f"Impervious classes in {lulc_tif.name}: values {values}")

    stats = compute_impervious(lulc_tif, geoms, values)
    changed = update_percent_impervious(files.basin, {n: s.percent_impervious for n, s in stats.items()})
    for name, (old, new) in changed.items():
        print(f"  {name:10s} {old} -> {new}")
    print(f"\nUpdated {len(changed)} subbasins in {files.basin} (backup kept alongside).")


def batch_populate(parent: str | Path, write: bool = False, force: bool = False,
                   debug: bool = False, judge_lulc: bool = False) -> None:
    """Run :func:`populate_project` over every folder under ``parent``.
    Without ``write`` it only reports what it WOULD do (recon mode)."""
    projects = sorted(p for p in Path(parent).iterdir() if p.is_dir())
    mode = ("FORCE-WRITE" if force else "WRITE") if write else "RECON (dry)"
    print(f"Mode: {mode} | {len(projects)} project folders under {parent}\n")
    for proj in projects:
        try:
            result = populate_project(proj, dry_run=not write, force=force, write_excel=False,
                                      judge_lulc=judge_lulc, verbose=False)
        except Exception as e:
            result = f"ERROR {type(e).__name__}: {e}"
            if debug:
                traceback.print_exc()
        print(f"{proj.name:22s} {result}")
