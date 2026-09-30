"""
Geometry for the parameter pipeline, taken from HMS's own current layers in the
basin sqlite (``Basin_1.sqlite``): ``reach2d`` (channel length/slope) and
``subbasin2d`` (sub-basin polygons).

This is preferred over walking the raw TauDEM network in fromGIS.sqlite
(see gis.fromgis): reach2d/subbasin2d are maintained by HMS itself, carry the
LIVE element names, and already reflect subbasins/reaches merged or edited in
the GUI.

Slope resolution order (reach2d's own slope is blank for merged reaches):
  1. reach2d.slope          when present and > 0
  2. strmdrop / length      when strmdrop is present and > 0
  3. DEM drop / length      elevation sampled at the reach line's endpoints
  4. min_slope floor        last resort; reported via ReachGeom.slope_source
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio

from ..hydrology.parameters import DEFAULT_PARAMETERS


def load_subbasins_2d(sqlite_path: str | Path,
                      element_names: list[str]) -> dict[str, object]:
    """Return {element name: shapely geometry} from HMS's ``subbasin2d`` layer."""
    from shapely import make_valid

    gdf = gpd.read_file(sqlite_path, layer="subbasin2d")
    by_name = {str(r["name"]): r.geometry for _, r in gdf.iterrows()}
    missing = [n for n in element_names if n not in by_name]
    if missing:
        raise ValueError(
            f"These .basin subbasins have no matching row in subbasin2d: {missing}. "
            f"Open the project in HMS so it refreshes the basin sqlite."
        )
    out = {}
    for n in element_names:
        g = by_name[n]
        out[n] = g if g.is_valid else make_valid(g)
    return out


@dataclass
class ReachGeom:
    element_name: str
    length_m: float
    slope: float
    slope_source: str


def _sample(dem, xy):
    """DEM value at (x, y), NaN on nodata / outside the raster."""
    try:
        v = list(dem.sample([xy]))[0][0]
        if dem.nodata is not None and v == dem.nodata:
            return np.nan
        return float(v)
    except Exception:
        return np.nan


def _isnan(v) -> bool:
    return isinstance(v, float) and np.isnan(v)


def load_reaches_2d(sqlite_path: str | Path, element_names: list[str],
                    dem_path: str | Path | None = None,
                    min_slope: float = DEFAULT_PARAMETERS.min_slope) -> dict[str, ReachGeom]:
    """Return {element name: ReachGeom} for the given .basin reach elements."""
    gdf = gpd.read_file(sqlite_path, layer="reach2d")
    by_name = {str(r["name"]): r for _, r in gdf.iterrows()}

    dem = rasterio.open(dem_path) if dem_path and Path(dem_path).exists() else None

    out: dict[str, ReachGeom] = {}
    missing: list[str] = []
    try:
        for name in element_names:
            row = by_name.get(name)
            if row is None:
                missing.append(name)
                continue

            geom = row.geometry
            length = float(row["length"]) if row["length"] and not np.isnan(row["length"]) else 0.0
            if length <= 0:
                length = float(geom.length)

            slope, src = np.nan, ""
            s = row.get("slope")
            if s is not None and not _isnan(s) and float(s) > 0:
                slope, src = float(s), "reach2d.slope"
            if np.isnan(slope):
                d = row.get("strmdrop")
                if d is not None and not _isnan(d) and float(d) > 0 and length > 0:
                    slope, src = float(d) / length, "strmdrop/length"
            if np.isnan(slope) and dem is not None and length > 0:
                coords = list(geom.geoms[0].coords) if geom.geom_type == "MultiLineString" \
                    else list(geom.coords)
                z0, z1 = _sample(dem, coords[0]), _sample(dem, coords[-1])
                if not (np.isnan(z0) or np.isnan(z1)):
                    drop = abs(z0 - z1)
                    if drop > 0:
                        slope, src = drop / length, "DEM endpoints"
            if np.isnan(slope) or slope <= 0:
                slope, src = min_slope, "MIN_SLOPE floor"

            out[name] = ReachGeom(name, length, slope, src)
    finally:
        if dem is not None:
            dem.close()

    if missing:
        raise ValueError(
            f"These .basin reaches have no matching row in reach2d: {missing}. "
            f"Open the project in HMS so it refreshes the basin sqlite."
        )
    return out
