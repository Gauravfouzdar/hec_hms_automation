"""
Create simulation Run configurations in a HEC-HMS project: one Run per
precipitation scenario, pairing the project's basin model with that scenario's
meteorologic model and control specification.

Runs live in ``<ProjectName>.run`` (HMS discovers this file by name; it is not
referenced from the .hms project file). Each run gets its own log and output
DSS so scenarios never overwrite each other's results.

"Last Execution Date/Time" is deliberately omitted -- HMS adds those once a
run has actually been computed.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .backup import backup_file
from .parser import parse_blocks
from .scenario_writer import Scenario

IND = "     "


def _run_block(name: str, basin: str, met: str, control: str) -> str:
    now = datetime.now()
    return "\n".join([
        f"Run: {name}",
        f"{IND}Default Description: Yes",
        f"{IND}Log File: {name.replace(' ', '_')}.log",
        f"{IND}DSS File: {name.replace(' ', '_')}.dss",
        f"{IND}Is Save Spatial Results: No",
        f"{IND}Last Modified Date: {now.strftime('%d %B %Y')}",
        f"{IND}Last Modified Time: {now.strftime('%H:%M:%S')}",
        f"{IND}Basin: {basin}",
        f"{IND}Precip: {met}",
        f"{IND}Control: {control}",
        f"{IND}Time-Series Output: Save All",
        f"{IND}Time Series Results Manager Start:",
        f"{IND}Time Series Results Manager End:",
        "End:",
    ])


def build_runs(project: Path, scenarios: list[Scenario]) -> str:
    """Add/replace one ``Run <tag>`` per scenario. Returns a status string."""
    hms_files = sorted(project.glob("*.hms"))
    if len(hms_files) != 1:
        return f"SKIP  expected 1 .hms file, found {len(hms_files)}"
    hms_path = hms_files[0]
    project_name = hms_path.stem

    # The basin model name comes from the .hms registry, never assumed.
    basin_blocks = [b for b in parse_blocks(hms_path) if b.block_type == "Basin"]
    if len(basin_blocks) != 1:
        return f"SKIP  expected 1 Basin in {hms_path.name}, found {len(basin_blocks)}"
    basin_name = basin_blocks[0].name

    run_path = project / f"{project_name}.run"
    new_names = {f"Run {sc.tag}" for sc in scenarios}

    kept: list[str] = []
    if run_path.exists():
        backup_file(run_path)
        lines = run_path.read_text(encoding="utf-8").splitlines()
        for blk in parse_blocks(run_path):
            if blk.block_type == "Run" and blk.name in new_names:
                continue  # this scenario's run is being rewritten
            kept.append("\n".join(lines[blk.start_line - 1: blk.end_line]).rstrip())

    blocks = kept + [
        _run_block(f"Run {sc.tag}", basin_name, sc.met_name, sc.control_name)
        for sc in scenarios
    ]
    run_path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return f"OK    {len(scenarios)} runs (basin '{basin_name}') -> {run_path.name}"
