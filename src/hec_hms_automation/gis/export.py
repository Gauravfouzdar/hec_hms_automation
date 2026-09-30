"""
Export GIS layers from every HEC-HMS project under a parent folder:

- :func:`export_subbasins`  one polygon shapefile per project
  (``<Project>_subbasins.shp``) from the basin sqlite ``subbasin2d`` table,
  HMS's own current geometry (reflects GUI merges/edits, live element names).
  If subbasin2d is empty the structured discretization has not been generated
  in HMS yet -- open the project, define it, and re-run.
- :func:`export_sinks`      ONE point shapefile (``pour_points.shp``) of every
  project's Sink (basin outlet) from the .basin ``Canvas X / Canvas Y``.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

from ..hmsfiles.basin_reader import read_basin

SUBBASIN_LAYER = "subbasin2d"
KEEP_COLUMNS = ["name", "latitude", "longitude"]
POUR_POINTS_NAME = "pour_points.shp"


def _project_sqlite(project: Path) -> Path | None:
    """The project's basin sqlite: ``<basin>.sqlite`` next to the .basin file,
    else any single ``*.sqlite`` in the project root."""
    basins = sorted(project.glob("*.basin"))
    if basins:
        cand = basins[0].with_suffix(".sqlite")
        if cand.exists():
            return cand
    return next(iter(sorted(project.glob("*.sqlite"))), None)


def export_project_subbasins(project: Path, out_dir: Path) -> str:
    sqlite = _project_sqlite(project)
    if sqlite is None:
        return "SKIP  no .sqlite in project"
    try:
        gdf = gpd.read_file(sqlite, layer=SUBBASIN_LAYER)
    except Exception as e:
        return f"SKIP  cannot read {SUBBASIN_LAYER}: {type(e).__name__}"
    if gdf.empty:
        return f"SKIP  {SUBBASIN_LAYER} is empty (define discretization in HMS first)"

    gdf = gdf[[c for c in KEEP_COLUMNS if c in gdf.columns] + ["geometry"]].copy()

    # HMS polygons can be topologically invalid (self-intersections); repair so
    # downstream GIS/zonal tools don't choke. area_sqkm in subbasin2d is only
    # partly populated, so area is computed from geometry (CRS is metric).
    invalid = int((~gdf.geometry.is_valid).sum())
    if invalid:
        gdf["geometry"] = gdf.geometry.make_valid()
    gdf["area_km2"] = (gdf.geometry.area / 1e6).round(4)
    gdf["project"] = project.name

    out = out_dir / f"{project.name}_subbasins.shp"
    gdf.to_file(out)
    note = f" ({invalid} geom repaired)" if invalid else ""
    return f"OK    {len(gdf)} subbasins, {gdf.area_km2.sum():8.2f} km2 -> {out.name}{note}"


def export_subbasins(parent: str | Path, out_dir: str | Path) -> None:
    """Export sub-basins of every project folder under ``parent`` into ``out_dir``."""
    parent_path, out_path = Path(parent), Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    projects = sorted(p for p in parent_path.iterdir() if p.is_dir())
    print(f"Exporting sub-basins from {len(projects)} projects to {out_path}\n")
    for proj in projects:
        try:
            result = export_project_subbasins(proj, out_path)
        except Exception as e:
            result = f"ERROR {type(e).__name__}: {e}"
        print(f"{proj.name:22s} {result}")


def collect_sinks(project: Path):
    """Return (rows, crs, status) for one project's Sink elements."""
    basins = sorted(project.glob("*.basin"))
    fromgis = sorted(project.glob("gis/*/fromGIS.sqlite"))
    if len(basins) != 1:
        return [], None, "SKIP  no unique .basin"

    basin = read_basin(basins[0])
    crs = None
    if len(fromgis) == 1:
        crs = gpd.read_file(fromgis[0], layer="subbasin", rows=1).crs

    rows = []
    for s in basin.sinks:
        try:
            x = float(s.fields["Canvas X"])
            y = float(s.fields["Canvas Y"])
        except (KeyError, ValueError):
            continue
        rows.append({"project": project.name, "sink_name": s.name,
                     "x": x, "y": y, "geometry": Point(x, y)})
    return rows, crs, f"OK    {len(rows)} sink(s)"


def export_sinks(parent: str | Path, out_dir: str | Path) -> None:
    """Combine every project's Sink into one point shapefile in ``out_dir``.

    The CRS is taken from the first project that has a fromGIS.sqlite; projects
    in one region normally share it (e.g. EPSG:32646).
    """
    parent_path, out_path = Path(parent), Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    projects = sorted(p for p in parent_path.iterdir() if p.is_dir())

    all_rows, crs_seen = [], None
    print(f"Extracting sinks (pour points) from {len(projects)} projects\n")
    for proj in projects:
        try:
            rows, crs, status = collect_sinks(proj)
        except Exception as e:
            print(f"{proj.name:22s} ERROR {type(e).__name__}: {e}")
            continue
        if crs is not None and crs_seen is None:
            crs_seen = crs
        all_rows.extend(rows)
        print(f"{proj.name:22s} {status}")

    if not all_rows:
        print("\nNo sinks found -- nothing written.")
        return

    gdf = gpd.GeoDataFrame(all_rows, geometry="geometry", crs=crs_seen)
    out = out_path / POUR_POINTS_NAME
    gdf.to_file(out)
    print(f"\nWrote {len(gdf)} pour points -> {out}  (CRS {crs_seen})")
