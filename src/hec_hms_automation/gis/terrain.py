"""
Longest flow path and mean basin slope per subbasin, from the HMS project's own
terrain derivatives (``terrain/<Terrain>/<NN>/``):

- flowdir.tif : TauDEM D8 flow directions (1=E, 2=NE, 3=N, 4=NW, 5=W, 6=SW,
                7=S, 8=SE), produced by the HMS GUI's terrain preprocessing.
- demsd8.tif  : TauDEM D8 slope (drop/distance, m/m).

Longest flow path of a subbasin = the maximum over its cells of the D8 flow
distance from that cell until the flow first leaves the subbasin (diagonal
steps count sqrt(2) cells).  Basin slope = mean of demsd8 over its cells.

Reference: D8 flow routing -- O'Callaghan & Mark (1984); TauDEM -- Tarboton
(1997).  See docs/LITERATURE.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize

# TauDEM D8 code -> (drow, dcol); the row axis points DOWN (north-up rasters).
D8_OFFSETS = {
    1: (0, 1),    # E
    2: (-1, 1),   # NE
    3: (-1, 0),   # N
    4: (-1, -1),  # NW
    5: (0, -1),   # W
    6: (1, -1),   # SW
    7: (1, 0),    # S
    8: (1, 1),    # SE
}


@dataclass
class SubbasinTerrain:
    element_name: str
    longest_flowpath_m: float
    basin_slope: float  # mean D8 slope, m/m
    cell_count: int


def compute_terrain_stats(
    flowdir_tif: str | Path,
    demsd8_tif: str | Path,
    subbasin_geoms: dict[str, object],  # element name -> shapely geometry (project CRS)
) -> dict[str, SubbasinTerrain]:
    """Return {element name: SubbasinTerrain} for every geometry given."""
    with rasterio.open(flowdir_tif) as ds:
        fdir = ds.read(1)
        transform = ds.transform
        cell = float(ds.res[0])
        fdir_nodata = ds.nodata
    with rasterio.open(demsd8_tif) as ds:
        slope = ds.read(1)
        slope_nodata = ds.nodata

    names = list(subbasin_geoms.keys())
    # Zone raster: 0 = outside every subbasin, i+1 = subbasin i.
    zones = rasterize(
        [(subbasin_geoms[n], i + 1) for i, n in enumerate(names)],
        out_shape=fdir.shape,
        transform=transform,
        fill=0,
        dtype="int32",
    )

    # Length of one D8 step per direction code (index 0 unused).
    step = np.zeros(9, dtype=np.float64)
    for code, (dr, dc) in D8_OFFSETS.items():
        step[code] = cell * (2 ** 0.5 if dr != 0 and dc != 0 else 1.0)

    nrow, ncol = fdir.shape
    # dist[r, c] = flow distance from this cell until it leaves its zone; -1 = unknown
    dist = np.full(fdir.shape, -1.0, dtype=np.float64)
    valid = (zones > 0) & (fdir >= 1) & (fdir <= 8)
    if fdir_nodata is not None:
        valid &= fdir != fdir_nodata

    # Walk each unresolved cell downstream, remembering the cells of the walk
    # so all of them get their distance once the walk terminates (memoised).
    rows, cols = np.nonzero(valid)
    for r0, c0 in zip(rows, cols):
        if dist[r0, c0] >= 0:
            continue
        path: list[tuple[int, int]] = []
        r, c = r0, c0
        base = 0.0  # distance of the cell the walk ended on (0 if it left the zone)
        while True:
            if dist[r, c] >= 0:
                base = dist[r, c]
                break
            code = int(fdir[r, c])
            if code < 1 or code > 8:
                base = 0.0
                break
            path.append((r, c))
            dr, dc = D8_OFFSETS[code]
            r2, c2 = r + dr, c + dc
            exited = (
                r2 < 0 or r2 >= nrow or c2 < 0 or c2 >= ncol
                or zones[r2, c2] != zones[r, c]
            )
            if exited:
                base = 0.0
                break
            r, c = r2, c2
        # Unwind: the last cell in `path` flows into `base`.
        acc = base
        for (pr, pc) in reversed(path):
            acc += step[int(fdir[pr, pc])]
            dist[pr, pc] = acc

    results: dict[str, SubbasinTerrain] = {}
    for i, name in enumerate(names):
        mask = zones == (i + 1)
        zone_dist = dist[mask]
        zone_slope = slope[mask]
        good_slope = zone_slope[zone_slope != slope_nodata] if slope_nodata is not None else zone_slope
        results[name] = SubbasinTerrain(
            element_name=name,
            longest_flowpath_m=float(zone_dist.max()) if zone_dist.size else 0.0,
            basin_slope=float(good_slope.mean()) if good_slope.size else 0.0,
            cell_count=int(mask.sum()),
        )
    return results
