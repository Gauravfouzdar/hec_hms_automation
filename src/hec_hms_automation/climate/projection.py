"""Derive a Vortex ``WktFactory`` projection label (e.g. ``"UTM46N"``) from a
shapefile's own CRS, so users do not have to type it."""
from __future__ import annotations

import re

import geopandas as gpd


def guess_wkt_label(shapefile_path: str) -> str:
    """Return ``'UTM46N'``-style label if the shapefile CRS is a UTM zone,
    otherwise ``''`` (the caller must then ask the user / take ``--wkt``)."""
    if not shapefile_path:
        return ""
    try:
        gdf = gpd.read_file(shapefile_path)
    except Exception:
        return ""

    crs = gdf.crs
    if crs is None or not crs.is_projected:
        return ""

    match = re.search(r"UTM zone (\d+)\s*([NS])", crs.name, re.IGNORECASE)  # "WGS 84 / UTM zone 46N"
    if match:
        return f"UTM{match.group(1)}{match.group(2).upper()}"
    return ""
