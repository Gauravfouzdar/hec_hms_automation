"""
Extract GIS data for a HEC-HMS project from ``gis/<Basin>/fromGIS.sqlite``:

- subbasin polygons (with area/centroid) matched to .basin Subbasin elements by
  exact centroid latitude/longitude (the values HMS writes into both files), so
  element NAMES are never assumed -- they are read live from the .basin file.
- the TauDEM stream network (linkno/dslinkno connectivity, length, strmdrop),
  chained into the model's Reach elements by walking the network from each
  reach's upstream canvas coordinate to its downstream canvas coordinate.

This is the "raw delineation" route.  The main pipeline prefers
``gis.hms_geometry`` (HMS's own current layers).  Keep this module for
projects whose basin sqlite has no subbasin2d/reach2d yet, or to cross-check.

Nothing here is basin-specific: any HMS 4.x project delineated through the
GUI's GIS tools produces the same fromGIS.sqlite schema.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd

from ..hmsfiles.basin_reader import BasinSummary
from ..hydrology.parameters import DEFAULT_PARAMETERS

# Tolerances for matching coordinates between the .basin file and the GIS
# tables. HMS writes the same numbers into both, so this only needs to absorb
# float round-trip noise -- but node snapping can be off by up to a cell.
COORD_TOL_DEG = 1e-6   # ~0.1 m, for lat/lon centroid matching
COORD_TOL_M = 60.0     # canvas-vs-network-node matching (up to ~2 cells of 30 m)


@dataclass
class SubbasinGIS:
    element_name: str          # name as written in the .basin file (live)
    geometry: object           # shapely polygon, in the project CRS
    area_sqkm: float
    latitude: float
    longitude: float


@dataclass
class ReachGIS:
    element_name: str
    link_ids: list[int]        # TauDEM linkno chain, upstream -> downstream
    length_m: float            # summed channel length
    drop_m: float              # summed stream drop
    slope: float               # drop / length (m/m), floored at min_slope

    @staticmethod
    def compute_slope(drop_m: float, length_m: float,
                      min_slope: float = DEFAULT_PARAMETERS.min_slope) -> float:
        if length_m <= 0:
            return min_slope
        return max(drop_m / length_m, min_slope)


def load_subbasins(fromgis_sqlite: str | Path, basin: BasinSummary) -> dict[str, SubbasinGIS]:
    """Match fromGIS subbasin polygons to .basin Subbasin elements by centroid.

    Handles GUI-side subbasin MERGES: merging elements in HMS updates the
    .basin (area = sum, centroid = area-weighted mean of the constituents) but
    fromGIS.sqlite keeps the original delineation polygons. Elements with no
    exact centroid match are resolved by searching combinations of the leftover
    polygons whose summed area and area-weighted centroid reproduce the
    element; their geometries are unioned.
    """
    from itertools import combinations
    from shapely import make_valid
    from shapely.ops import unary_union

    gdf = gpd.read_file(fromgis_sqlite, layer="subbasin")

    matched: dict[str, SubbasinGIS] = {}
    unmatched_elements = []
    used_idx: set[int] = set()
    for el in basin.subbasins:
        lat = float(el.fields["Latitude Degrees"])
        lon = float(el.fields["Longitude Degrees"])
        hit = gdf[
            (abs(gdf["latitude"] - lat) < COORD_TOL_DEG)
            & (abs(gdf["longitude"] - lon) < COORD_TOL_DEG)
        ]
        if len(hit) == 1:
            row = hit.iloc[0]
            used_idx.add(hit.index[0])
            matched[el.name] = SubbasinGIS(el.name, row.geometry,
                                           float(row["area_sqkm"]), lat, lon)
        else:
            unmatched_elements.append((el, lat, lon))

    if unmatched_elements:
        free = gdf[~gdf.index.isin(used_idx)]
        deferred: list[tuple] = []   # elements no combination could resolve
        for el, lat, lon in unmatched_elements:
            target_area = float(el.fields.get("Area", 0.0))
            best = None
            for k in range(2, min(len(free), 4) + 1):
                for combo in combinations(free.index, k):
                    rows = free.loc[list(combo)]
                    a = rows["area_sqkm"].sum()
                    if abs(a - target_area) > 0.01 * target_area:
                        continue
                    clat = (rows["latitude"] * rows["area_sqkm"]).sum() / a
                    clon = (rows["longitude"] * rows["area_sqkm"]).sum() / a
                    d = math.hypot(clat - lat, clon - lon)
                    if d < 1e-3 and (best is None or d < best[0]):
                        best = (d, combo, a)
                if best:
                    break
            if best is None:
                deferred.append((el, lat, lon, target_area))
                continue
            _, combo, a = best
            rows = free.loc[list(combo)]
            matched[el.name] = SubbasinGIS(
                el.name, unary_union([make_valid(g) for g in rows.geometry]),
                float(a), lat, lon)
            used_idx.update(combo)
            free = gdf[~gdf.index.isin(used_idx)]
            print(f"  note: {el.name} = merge of {len(combo)} fromGIS polygons "
                  f"(sum area {a:.2f} km2)")

        # Remainder fallback: with exactly ONE element unresolved after all
        # combination matching, it must own whatever polygons are left (covers
        # boundary edits no clean polygon combination reproduces).
        if len(deferred) == 1 and len(free) > 0:
            el, lat, lon, target_area = deferred.pop()
            a = float(free["area_sqkm"].sum())
            mismatch = abs(a - target_area) / target_area if target_area else 1.0
            matched[el.name] = SubbasinGIS(
                el.name, unary_union([make_valid(g) for g in free.geometry]),
                a, lat, lon)
            used_idx.update(free.index)
            print(f"  note: {el.name} = remainder ({len(free)} leftover polygons; "
                  f"sum area {a:.2f} vs element {target_area:.2f} km2, "
                  f"{mismatch:.1%} mismatch)")
            if mismatch > 0.05:
                print(f"  WARNING: {el.name} remainder area differs {mismatch:.1%} "
                      f"from the .basin value -- check this subbasin in the GUI")

        if deferred:
            raise ValueError(
                "Could not match these .basin subbasins to fromGIS polygons "
                "(no exact centroid hit and no area/centroid-consistent merge "
                "combination): "
                + ", ".join(f"{el.name} (area {ta} km2)" for el, _, _, ta in deferred)
            )
    return matched


def _dist(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x1 - x2, y1 - y2)


def load_reaches(fromgis_sqlite: str | Path, basin: BasinSummary) -> dict[str, ReachGIS]:
    """Chain TauDEM network links into each .basin model Reach.

    A model reach runs from its upstream junction (From Canvas X/Y) to its
    downstream element (Canvas X/Y). Junctions inserted in the HMS GUI can sit
    MID-LINK (not on an original network node), so both entry and termination
    work geometrically: the walk starts at the projection of the upstream point
    onto its link and ends at the projection of the downstream point, with
    partial links contributing a proportional share of length and stream drop.
    """
    from shapely.geometry import Point
    from shapely.ops import linemerge

    net = gpd.read_file(fromgis_sqlite, layer="reach")
    by_link = {}
    for r in net.itertuples():
        geom = r.geometry
        if geom.geom_type == "MultiLineString":
            geom = linemerge(geom)
        by_link[int(r.linkno)] = (r, geom)

    def entry_link(pt: Point):
        """Link on which the walk starts: prefer a link whose upstream node is
        at the point; else the link whose line passes nearest the point with
        usable length remaining downstream of the projection."""
        node_hits = sorted(
            (r for r, _ in by_link.values()
             if _dist(r.upstream_x, r.upstream_y, pt.x, pt.y) <= COORD_TOL_M),
            key=lambda r: _dist(r.upstream_x, r.upstream_y, pt.x, pt.y),
        )
        if node_hits:
            return node_hits[0], 0.0
        geom_hits = []
        for r, geom in by_link.values():
            d = geom.distance(pt)
            if d <= COORD_TOL_M:
                s = geom.project(pt)
                if geom.length - s > COORD_TOL_M:  # not at the very end
                    geom_hits.append((d, r, s))
        if not geom_hits:
            return None, 0.0
        geom_hits.sort(key=lambda t: t[0])
        _, r, s = geom_hits[0]
        return r, s

    matched: dict[str, ReachGIS] = {}
    problems: list[str] = []
    for el in basin.reaches:
        up = Point(float(el.fields["From Canvas X"]), float(el.fields["From Canvas Y"]))
        dn = Point(float(el.fields["Canvas X"]), float(el.fields["Canvas Y"]))

        cur, start_s = entry_link(up)
        if cur is None:
            problems.append(f"{el.name}: no entry link near ({up.x:.1f}, {up.y:.1f})")
            continue

        chain: list[int] = []
        length = 0.0
        drop = 0.0
        ok = False
        for _ in range(len(by_link) + 1):  # bounded walk (guards against cycles)
            r, geom = by_link[int(cur.linkno)]
            chain.append(int(cur.linkno))
            glen = geom.length or 1.0
            s0 = start_s
            start_s = 0.0  # only the first link starts mid-line

            # Does the reach end on this link?
            end_here = (
                geom.distance(dn) <= COORD_TOL_M
                and geom.project(dn) > s0 + 1.0
            ) or _dist(r.dnstream_x, r.dnstream_y, dn.x, dn.y) <= COORD_TOL_M
            s1 = min(geom.project(dn), glen) if geom.distance(dn) <= COORD_TOL_M else glen
            if not end_here:
                s1 = glen

            frac = max(s1 - s0, 0.0) / glen
            length += float(r.length) * frac
            drop += float(r.strmdrop) * frac
            if end_here:
                ok = True
                break
            nxt = by_link.get(int(r.dslinkno))
            if nxt is None:
                break
            cur = nxt[0]
        if not ok:
            problems.append(f"{el.name}: walk from link {chain[0]} never reached "
                            f"downstream coordinate ({dn.x:.1f}, {dn.y:.1f})")
            continue

        matched[el.name] = ReachGIS(el.name, chain, length, drop,
                                    ReachGIS.compute_slope(drop, length))

    if problems:
        raise ValueError("Reach-to-network matching failed:\n  " + "\n  ".join(problems))
    return matched
