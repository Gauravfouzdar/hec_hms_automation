"""
Build precipitation scenarios and simulation runs across many HMS projects.

A *scenario* = Met model + Control spec + Grid record (+ a Run tying them to the
basin).  Scenarios are defined once in a YAML file (see
``config/scenarios.example.yaml``) and stamped into every project under a
parent folder.  Writers are surgical: existing components are preserved and only
the tags passed in are added/replaced, so already-computed runs stay intact.

CLI:
    hms-auto build-scenarios "<parent>" --config scenarios.yaml [--project N] [--dry-run]
    hms-auto build-runs      "<parent>" --config scenarios.yaml [--project N]
    hms-auto build-one       "<parent>" <tag> --config scenarios.yaml [--project N]
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ..hmsfiles.run_writer import build_runs
from ..hmsfiles.scenario_writer import Scenario, build_project


def load_scenarios(cfg_path: str | Path) -> tuple[list[Scenario], dict]:
    """Return (scenarios, defaults) from a scenarios YAML file."""
    cfg = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
    return [Scenario(**s) for s in cfg["scenarios"]], cfg["defaults"]


def find_projects(parent: str | Path, only: str | None = None, need_hms: bool = True) -> list[Path]:
    projects = sorted(p for p in Path(parent).iterdir() if p.is_dir()
                      and (only is None or p.name == only)
                      and (not need_hms or list(p.glob("*.hms"))))
    if not projects:
        raise SystemExit(f"No project folders matched under {parent}")
    return projects


def _check_dss_exist(scenarios: list[Scenario]) -> None:
    missing = [s.tag for s in scenarios if not Path(s.dss).exists()]
    if missing:
        raise SystemExit(f"DSS file(s) not found for scenarios: {missing}")


def build_scenarios(parent, cfg_path, dry_run=False, only=None) -> None:
    """Create met + control + grid for every scenario in every project."""
    scenarios, defaults = load_scenarios(cfg_path)
    _check_dss_exist(scenarios)          # rule: never register a grid whose DSS is absent
    print(f"{len(scenarios)} scenarios: {', '.join(s.tag for s in scenarios)}")
    for s in scenarios:
        print(f"  {s.tag:11s} {s.start_date} {s.start_time} -> {s.end_date} {s.end_time}  @{s.interval_min} min")
    print()
    projects = find_projects(parent, only, need_hms=False)
    if dry_run:
        print(f"--dry-run: would write into {len(projects)} projects "
              f"({len(projects) * len(scenarios) * 2} files + grid/hms edits)")
        for p in projects:
            print(f"  {p.name}")
        return
    for proj in projects:
        try:
            result = build_project(proj, scenarios, defaults)
        except Exception as e:
            result = f"ERROR {type(e).__name__}: {e}"
        print(f"{proj.name:22s} {result}")


def build_all_runs(parent, cfg_path, only=None) -> None:
    """Create one Run per scenario in every project."""
    scenarios, _ = load_scenarios(cfg_path)
    projects = find_projects(parent, only, need_hms=False)
    print(f"Creating {len(scenarios)} runs in each of {len(projects)} projects "
          f"({len(scenarios) * len(projects)} total)\n")
    for proj in projects:
        try:
            result = build_runs(proj, scenarios)
        except Exception as e:
            result = f"ERROR {type(e).__name__}: {e}"
        print(f"{proj.name:22s} {result}")


def build_one(parent, tag, cfg_path, only=None) -> None:
    """Met/control/grid + run for ONE scenario tag, leaving all others untouched."""
    scenarios, defaults = load_scenarios(cfg_path)
    match = [s for s in scenarios if s.tag == tag]
    if not match:
        raise SystemExit(f"tag '{tag}' not in {cfg_path} (have: {', '.join(s.tag for s in scenarios)})")
    sc = match[0]
    _check_dss_exist([sc])
    print(f"Scenario '{tag}': {sc.dss}\n  pathname {sc.pathname}\n  window   "
          f"{sc.start_date} {sc.start_time} -> {sc.end_date} {sc.end_time} @{sc.interval_min} min\n")
    for proj in find_projects(parent, only):
        try:
            r1, r2 = build_project(proj, [sc], defaults), build_runs(proj, [sc])
        except Exception as e:
            print(f"{proj.name:22s} ERROR {type(e).__name__}: {e}")
            continue
        print(f"{proj.name:22s} {r1}\n{'':22s} {r2}")
    print(f'\nDone. Compute with:  hms-auto compute "{parent}" --tags {tag}')
