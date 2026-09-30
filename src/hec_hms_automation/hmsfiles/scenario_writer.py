"""
Create meteorologic models (.met), control specifications (.control) and
precipitation grid records (.grid) for a set of precipitation scenarios in a
HEC-HMS project, and register them in the project's .hms file.

File layouts mirror what HMS 4.13 writes itself (verified against a working
project): a Meteorology block + a "Precip Method Parameters" block per .met
file, one Control block per .control file, and one "Grid:" block per scenario
inside the project's grid manager file.

Existing components are preserved -- scenario components are added, and a
re-run overwrites only its own entries.  Every modified file is backed up.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .backup import backup_file
from .parser import parse_blocks

IND = "     "


@dataclass
class Scenario:
    """One precipitation scenario (a Met + Control + Grid trio and, later, a Run).

    tag           short id used in component names, e.g. ``RP100`` or ``SSP245``
    dss           precipitation DSS file (gridded, built by Vortex)
    pathname      DSS pathname of the FIRST grid record
    start_date    e.g. ``"01 January 2024"`` (HMS date format)
    start_time    ``"00:00"``  (``"24:00"`` = midnight ending that day)
    end_date/end_time
    interval_min  MUST equal the DSS record spacing (60 hourly, 1440 daily),
                  otherwise HMS reports missing precipitation.
    """

    tag: str
    dss: str
    pathname: str
    start_date: str
    start_time: str
    end_date: str
    end_time: str
    interval_min: int

    @property
    def met_name(self) -> str:
        return f"Met {self.tag}"

    @property
    def control_name(self) -> str:
        return f"Control {self.tag}"

    @property
    def grid_name(self) -> str:
        return f"Grid {self.tag}"

    @property
    def met_file(self) -> str:
        return f"Met_{self.tag}.met"

    @property
    def control_file(self) -> str:
        return f"Control_{self.tag}.control"


def _stamp() -> tuple[str, str]:
    now = datetime.now()
    return now.strftime("%d %B %Y"), now.strftime("%H:%M:%S")


def write_control(project: Path, sc: Scenario, d: dict) -> Path:
    """Write ``Control_<tag>.control``. ``d`` = defaults (version, timezone ...)."""
    date, time = _stamp()
    text = "\n".join([
        f"Control: {sc.control_name}",
        f"{IND}Last Modified Date: {date}",
        f"{IND}Last Modified Time: {time}",
        f"{IND}Version: {d['version']}",
        f"{IND}Time Zone ID: {d['timezone_id']}",
        f"{IND}Time Zone GMT Offset: {d['timezone_gmt_offset_ms']}",
        f"{IND}Start Date: {sc.start_date}",
        f"{IND}Start Time: {sc.start_time}",
        f"{IND}End Date: {sc.end_date}",
        f"{IND}End Time: {sc.end_time}",
        f"{IND}Time Interval: {sc.interval_min}",
        "End:",
        "",
    ])
    out = project / sc.control_file
    out.write_text(text, encoding="utf-8")
    return out


def write_met(project: Path, sc: Scenario, d: dict) -> Path:
    """Write ``Met_<tag>.met`` (gridded precipitation, no ET / other methods)."""
    date, time = _stamp()
    text = "\n".join([
        f"Meteorology: {sc.met_name}",
        f"{IND}Last Modified Date: {date}",
        f"{IND}Last Modified Time: {time}",
        f"{IND}Version: {d['version']}",
        f"{IND}Unit System: {d['unit_system']}",
        f"{IND}Set Missing Data to Default: Yes",
        f"{IND}Precipitation Method: Gridded Precipitation",
        f"{IND}Air Temperature Method: None",
        f"{IND}Atmospheric Pressure Method: None",
        f"{IND}Dew Point Method: None",
        f"{IND}Wind Speed Method: None",
        f"{IND}Shortwave Radiation Method: None",
        f"{IND}Longwave Radiation Method: None",
        f"{IND}Snowmelt Method: None",
        f"{IND}Evapotranspiration Method: No Evapotranspiration",
        "End:",
        "",
        "Precip Method Parameters: Gridded Precipitation",
        f"{IND}Last Modified Date: {date}",
        f"{IND}Last Modified Time: {time}",
        f"{IND}Precip Grid Name: {sc.grid_name}",
        f"{IND}Time Shift Method: NONE",
        "End:",
        "",
    ])
    out = project / sc.met_file
    out.write_text(text, encoding="utf-8")
    return out


def _grid_block(sc: Scenario) -> str:
    date, time = _stamp()
    dss_win = str(Path(sc.dss))  # native separators for HMS
    return "\n".join([
        f"Grid: {sc.grid_name}",
        f"{IND}Grid: {sc.grid_name}",
        f"{IND}Grid Type: Precipitation",
        f"{IND}Description: ",
        f"{IND}Last Modified Date: {date}",
        f"{IND}Last Modified Time: {time}",
        f"{IND}Storm Center X: 0.0",
        f"{IND}Storm Center Y: 0.0",
        f"{IND}Data Source Type: External DSS",
        f"{IND}Filename: {dss_win}",
        f"{IND}Pathname: {sc.pathname}",
        "End:",
    ])


def write_grid_file(project: Path, project_name: str,
                    scenarios: list[Scenario], d: dict) -> Path:
    """Append/replace scenario Grid blocks in ``<project>.grid``, keeping others."""
    grid_path = project / f"{project_name}.grid"
    new_names = {sc.grid_name for sc in scenarios}

    kept: list[str] = []
    if grid_path.exists():
        backup_file(grid_path)
        lines = grid_path.read_text(encoding="utf-8").splitlines()
        for blk in parse_blocks(grid_path):
            if blk.block_type == "Grid Manager":
                continue          # header is regenerated below
            if blk.block_type == "Grid" and blk.name in new_names:
                continue          # this scenario is being rewritten
            kept.append("\n".join(lines[blk.start_line - 1: blk.end_line]).rstrip())

    header = "\n".join([
        "Grid Manager: ",
        f"{IND}Grid Manager: ",
        f"{IND}Version: {d['version']}",
        f"{IND}Filepath Separator: \\",
        "End: ",
    ])
    blocks = [header] + kept + [_grid_block(sc) for sc in scenarios]
    grid_path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return grid_path


def register_in_hms(hms_path: Path, scenarios: list[Scenario]) -> None:
    """Add Precipitation/Control entries for each scenario to the ``.hms`` file,
    keeping existing components and the canonical Project / Precipitation /
    Basin / Control ordering HMS writes."""
    backup_file(hms_path)
    lines = hms_path.read_text(encoding="utf-8").splitlines()
    blocks = parse_blocks(hms_path)

    def raw(blk) -> str:
        return "\n".join(lines[blk.start_line - 1: blk.end_line]).rstrip()

    project_blk = [b for b in blocks if b.block_type == "Project"]
    precip = [b for b in blocks if b.block_type == "Precipitation"]
    basins = [b for b in blocks if b.block_type == "Basin"]
    controls = [b for b in blocks if b.block_type == "Control"]

    new_met = {sc.met_name for sc in scenarios}
    new_ctl = {sc.control_name for sc in scenarios}
    date, time = _stamp()
    hm = time[:5]

    out: list[str] = [raw(b) for b in project_blk]
    out += [raw(b) for b in precip if b.name not in new_met]
    for sc in scenarios:
        out.append("\n".join([
            f"Precipitation: {sc.met_name}",
            f"{IND}Filename: {sc.met_file}",
            f"{IND}Description: ",
            f"{IND}Last Modified Date: {date}",
            f"{IND}Last Modified Time: {hm}",
            "End:",
        ]))
    out += [raw(b) for b in basins]
    out += [raw(b) for b in controls if b.name not in new_ctl]
    for sc in scenarios:
        out.append("\n".join([
            f"Control: {sc.control_name}",
            f"{IND}FileName: {sc.control_file}",
            f"{IND}Description: ",
            "End:",
        ]))

    hms_path.write_text("\n\n".join(out) + "\n", encoding="utf-8")


def build_project(project: Path, scenarios: list[Scenario], d: dict) -> str:
    """Create met + control + grid for every scenario in ONE project and
    register them. Returns a one-line status string (``OK ...`` / ``SKIP ...``)."""
    hms_files = sorted(project.glob("*.hms"))
    if len(hms_files) != 1:
        return f"SKIP  expected 1 .hms file, found {len(hms_files)}"
    hms_path = hms_files[0]
    project_name = hms_path.stem

    for sc in scenarios:
        write_control(project, sc, d)
        write_met(project, sc, d)
    write_grid_file(project, project_name, scenarios, d)
    register_in_hms(hms_path, scenarios)
    return (f"OK    {len(scenarios)} met + {len(scenarios)} control + "
            f"{len(scenarios)} grid -> {project_name}")
