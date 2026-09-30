"""
Read a HEC-HMS .basin file into a structured, project-agnostic summary of its
elements: subbasins, reaches, junctions, sinks, and the global basin settings.

This is the "readiness" step ahead of parameter calculation: it reports which
elements exist (names come from the .basin file itself -- never assumed from
an external spreadsheet), which method each element uses (LossRate / Transform
/ Baseflow / Route) and which numeric parameters are still unset.

CLI:  hms-auto read-basin "<path to Basin_1.basin>"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .parser import Block, blocks_by_type, parse_blocks


@dataclass
class Element:
    name: str
    area_km2: float | None
    downstream: str | None
    methods: dict[str, str] = field(default_factory=dict)  # LossRate / Transform / Baseflow / Route ...
    fields: dict[str, str] = field(default_factory=dict)


@dataclass
class BasinSummary:
    project_name: str
    global_fields: dict[str, str]
    subbasins: list[Element]
    reaches: list[Element]
    junctions: list[Element]
    sinks: list[Element]

    @property
    def total_area_km2(self) -> float:
        return sum(sb.area_km2 or 0.0 for sb in self.subbasins)


_METHOD_KEYS = ("LossRate", "Transform", "Baseflow", "Route", "Canopy", "Surface")


def _to_element(b: Block) -> Element:
    area = None
    if "Area" in b.fields:
        try:
            area = float(b.fields["Area"])
        except ValueError:
            area = None
    return Element(
        name=b.name,
        area_km2=area,
        downstream=b.fields.get("Downstream"),
        methods={k: b.fields[k] for k in _METHOD_KEYS if k in b.fields},
        fields=b.fields,
    )


def read_basin(path: str | Path) -> BasinSummary:
    """Parse ``path`` (a .basin file) into a :class:`BasinSummary`."""
    blocks = parse_blocks(path)

    global_blocks = blocks_by_type(blocks, "Basin")
    global_fields = global_blocks[0].fields if global_blocks else {}
    project_name = global_blocks[0].name if global_blocks else Path(path).stem

    return BasinSummary(
        project_name=project_name,
        global_fields=global_fields,
        subbasins=[_to_element(b) for b in blocks_by_type(blocks, "Subbasin")],
        reaches=[_to_element(b) for b in blocks_by_type(blocks, "Reach")],
        junctions=[_to_element(b) for b in blocks_by_type(blocks, "Junction")],
        sinks=[_to_element(b) for b in blocks_by_type(blocks, "Sink")],
    )


# Numeric parameters that must exist for an element to count as "filled",
# keyed by the method that governs them.
_EXPECTED_PARAMS = {
    "Deficit Constant": ["Initial Deficit", "Maximum Deficit", "Percolation Rate"],
    "Modified Clark": ["Time of Concentration", "Storage Coefficient"],
    "Linear Reservoir": ["GW-1 Routing Coefficient"],
    "Muskingum": ["Muskingum K", "Muskingum x"],  # HMS writes a lowercase x
}
# To support another method (e.g. SCS Unit Hydrograph), add its expected keys here.


def missing_params(el: Element) -> list[str]:
    """Names of expected parameters that are absent on ``el`` (empty list = filled)."""
    missing = []
    for method_key, expected in _EXPECTED_PARAMS.items():
        if method_key in el.methods.values():
            for p in expected:
                if p not in el.fields:
                    missing.append(p)
    return missing


def fill_state(summary: BasinSummary) -> str:
    """``'skeleton'`` (nothing filled), ``'filled'`` (all complete) or ``'partial'``."""
    elements = summary.subbasins + summary.reaches
    n_missing = sum(1 for el in elements if missing_params(el))
    if n_missing == len(elements):
        return "skeleton"
    if n_missing == 0:
        return "filled"
    return "partial"


def print_summary(summary: BasinSummary) -> None:
    """Human-readable dump of a :class:`BasinSummary` to stdout."""
    print(f"Project: {summary.project_name}")
    print(f"Unit System: {summary.global_fields.get('Unit System', '?')}")
    print(f"Sediment Routing: {summary.global_fields.get('Enable Sediment Routing', '?')}")
    print()
    print(f"Subbasins: {len(summary.subbasins)}  (total area {summary.total_area_km2:.2f} km2)")
    for sb in summary.subbasins:
        miss = missing_params(sb)
        flag = f"  <- missing: {', '.join(miss)}" if miss else ""
        methods = ", ".join(f"{k}={v}" for k, v in sb.methods.items())
        print(f"  {sb.name:14s} area={sb.area_km2 or 0:>8.3f} km2  -> {sb.downstream or '?':14s} [{methods}]{flag}")
    print()
    print(f"Reaches: {len(summary.reaches)}")
    for r in summary.reaches:
        miss = missing_params(r)
        flag = f"  <- missing: {', '.join(miss)}" if miss else ""
        methods = ", ".join(f"{k}={v}" for k, v in r.methods.items())
        print(f"  {r.name:14s} -> {r.downstream or '?':14s} [{methods}]{flag}")
    print()
    print(f"Junctions: {len(summary.junctions)}")
    for j in summary.junctions:
        print(f"  {j.name:14s} -> {j.downstream}")
    print()
    print(f"Sinks: {len(summary.sinks)}")
    for s in summary.sinks:
        print(f"  {s.name:14s} (Computation Point: {s.fields.get('Computation Point', '?')})")
