"""
Patch a HEC-HMS .basin file in place with computed subbasin and reach
parameters, following the exact key names and block layout HMS 4.13 itself
writes (verified against a completed reference model).

Only lines belonging to the sections being filled are touched; everything else
round-trips verbatim. The writer is IDEMPOTENT: lines it manages are dropped
inside a block and re-emitted at fixed anchor points, so running it on an empty
skeleton and on an already-filled file gives the same result.

A timestamped backup ``<name>.basin.bak-YYYYmmdd-HHMMSS`` is written first.
"""
from __future__ import annotations

from pathlib import Path

from ..hydrology.parameters import ReachParams, SubbasinParams
from .backup import backup_file

IND = "     "  # HMS uses 5-space indentation for element fields


def _fmt(v: float, nd: int = 2) -> str:
    return f"{round(v, nd):g}"


def _loss_lines(p: SubbasinParams) -> list[str]:
    return [
        f"{IND}Percent Impervious Area: {_fmt(p.percent_impervious)}",
        f"{IND}Initial Deficit: {_fmt(p.initial_deficit_mm)}",
        f"{IND}Maximum Deficit: {_fmt(p.maximum_deficit_mm)}",
        f"{IND}Percolation Rate: {_fmt(p.percolation_rate_mm_hr)}",
    ]


def _baseflow_lines(p: SubbasinParams) -> list[str]:
    return [
        f"{IND}Groundwater Layer: 1",
        f"{IND}GW-1 Baseflow Fraction: {_fmt(p.gw1_fraction)}",
        f"{IND}GW-1 Number Reservoirs: 1",
        f"{IND}GW-1 Routing Coefficient: {_fmt(p.gw1_coeff_hr)}",
        f"{IND}GW-1 Initial Baseflow: {_fmt(p.gw1_initial_m3s)}",
        f"{IND}Groundwater Layer: 2",
        f"{IND}GW-2 Baseflow Fraction: {_fmt(p.gw2_fraction)}",
        f"{IND}GW-2 Number Reservoirs: 1",
        f"{IND}GW-2 Routing Coefficient: {_fmt(p.gw2_coeff_hr)}",
        f"{IND}GW-2 Initial Baseflow: {_fmt(p.gw2_initial_m3s)}",
    ]


# Lines with these prefixes are DROPPED inside a block being (re)written --
# they are re-emitted at their anchor points below (that is what makes the
# writer idempotent).
_SUB_DROP = (
    "File:", "Projection:", "Cell Size:",                          # discretization
    "Initial Deficit:", "Maximum Deficit:", "Percolation Rate:",   # loss
    "Time of Concentration:", "Storage Coefficient:",              # transform
    "Groundwater Layer:", "GW-1 ", "GW-2 ",                        # baseflow
)
_REACH_DROP = ("Muskingum K:", "Muskingum x:", "Muskingum Steps:")


def write_basin(
    basin_path: str | Path,
    sub_params: dict[str, SubbasinParams],
    reach_pars: dict[str, ReachParams],
    grid_file: str,
    projection_epsg: int,
    cell_size_m: float,
    backup: bool = True,
) -> Path:
    """Write computed parameters into ``basin_path``.

    sub_params / reach_pars   keyed by element NAME as it appears in the file
    grid_file                 the project's structured-grid sqlite file name
    projection_epsg           EPSG of the project CRS (e.g. 32646)
    cell_size_m               structured discretization cell size
    """
    basin_path = Path(basin_path)
    lines = basin_path.read_text(encoding="utf-8").splitlines()

    out: list[str] = []
    block_type = ""
    block_name = ""

    for line in lines:
        stripped = line.strip()
        at_top = len(line) - len(line.lstrip(" ")) == 0

        # Track which top-level block we are inside.
        if at_top and stripped and ":" in stripped and not stripped.startswith("End"):
            btype, _, bname = stripped.partition(":")
            block_type, block_name = btype.strip(), bname.strip()
        if at_top and stripped.startswith("End"):
            block_type, block_name = "", ""

        sp = sub_params.get(block_name) if block_type == "Subbasin" else None
        rp = reach_pars.get(block_name) if block_type == "Reach" else None

        if sp is not None:
            if stripped.startswith(_SUB_DROP):
                continue
            if stripped.startswith("Discretization:"):
                out.append(f"{IND}Discretization: Structured")
                out.append(f"{IND}File: {grid_file}")
                out.append(f"{IND}Projection: {projection_epsg}")
                out.append(f"{IND}Cell Size: {cell_size_m}")
                continue
            if stripped.startswith("Percent Impervious Area:"):
                out.extend(_loss_lines(sp))
                continue
            if stripped.startswith("Mod Clark Method:"):
                out.append(line)
                out.append(f"{IND}Time of Concentration: {_fmt(sp.tc_hr)}")
                out.append(f"{IND}Storage Coefficient: {_fmt(sp.storage_coeff_hr)}")
                continue
            if stripped == "Baseflow: Linear Reservoir":
                out.append(line)
                out.extend(_baseflow_lines(sp))
                continue

        if rp is not None:
            if stripped.startswith(_REACH_DROP):
                continue
            if stripped.startswith("Initial Variable:"):
                out.append(line)
                out.append(f"{IND}Muskingum K: {_fmt(rp.muskingum_k_hr)}")
                out.append(f"{IND}Muskingum x: {_fmt(rp.muskingum_x)}")
                out.append(f"{IND}Muskingum Steps: {rp.muskingum_steps}")
                continue

        out.append(line)

    if backup:
        backup_file(basin_path)

    basin_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return basin_path


def update_percent_impervious(basin_path: str | Path,
                              impervious_pct: dict[str, float],
                              backup: bool = True) -> dict[str, tuple[str, str]]:
    """Rewrite ONLY the ``Percent Impervious Area`` lines of a filled .basin.

    Use when the LULC raster changes after a full fill: impervious % is the
    only parameter derived from LULC, so nothing else needs rewriting (Tc / R /
    baseflow / K are DEM- and network-derived).

    Returns {subbasin: (old_value, new_value)} for the subbasins that changed.
    """
    basin_path = Path(basin_path)
    lines = basin_path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    changed: dict[str, tuple[str, str]] = {}
    block_type = block_name = ""
    for line in lines:
        stripped = line.strip()
        if len(line) - len(line.lstrip(" ")) == 0 and stripped:
            if stripped.startswith("End"):
                block_type = block_name = ""
            elif ":" in stripped:
                t, _, n = stripped.partition(":")
                block_type, block_name = t.strip(), n.strip()
        if (block_type == "Subbasin" and block_name in impervious_pct
                and stripped.startswith("Percent Impervious Area:")):
            old = stripped.split(":", 1)[1].strip()
            new = _fmt(impervious_pct[block_name])
            out.append(f"{IND}Percent Impervious Area: {new}")
            if old != new:
                changed[block_name] = (old, new)
            continue
        out.append(line)

    if backup:
        backup_file(basin_path)
    basin_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return changed
