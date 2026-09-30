"""
Compute HEC-HMS simulation runs headlessly across many projects.

Drives HEC-HMS's own Jython scripting interface (``HEC-HMS.cmd -s script``),
the supported way to compute without the GUI.  One script per project opens the
project once and computes the requested runs in sequence, then saves.

Success/failure is judged from each run's own log (HMS returns exit code 0 even
for a failed compute), so results reflect what HMS actually reported.  A log
older than the launch time is reported as STALE, never as a fresh success.

CLI:  hms-auto compute "<parent dir>" --tags RP5,RP10 [--project NAME] [--hms-home ...]
"""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from ..config import find_hms_home, scratch_dir


def write_compute_script(project: Path, run_names: list[str], scratch: Path) -> Path:
    """Jython script for HMS: open project, compute each run (errors caught per
    run so one failure does not abort the rest), save, exit."""
    hms = sorted(project.glob("*.hms"))[0]
    body = ["from hms.model.JythonHms import *", "import sys", ""]
    body.append(f'OpenProject("{hms.stem}", "{project.as_posix()}")')
    for rn in run_names:
        body += ["try:",
                 f'    Compute("{rn}")',
                 f'    print("COMPUTED::{rn}")',
                 "except:",
                 f'    print("FAILED::{rn}::%s" % str(sys.exc_info()[1]))']
    body += ["SaveAllProjectComponents()", "Exit(0)", ""]
    path = scratch / f"compute_{project.name}.script"
    path.write_text("\n".join(body), encoding="utf-8")
    return path


def _write_launcher(script: Path, hms_home: Path) -> Path:
    bat = script.with_suffix(".bat")
    bat.write_text("@echo off\r\n"
                   f'cd /d "{hms_home}"\r\n'
                   f'call ".\\HEC-HMS.cmd" -s "{script}"\r\n', encoding="utf-8")
    return bat


def log_verdict(project: Path, tag: str, since: float = 0.0) -> str:
    """One-line verdict for a run from its ``Run_<tag>.log``.

    ``since`` (epoch seconds) guards against reading a STALE log from an earlier
    session and reporting it as a fresh success.
    """
    log = project / f"Run_{tag}.log"
    if not log.exists():
        return "no log"
    if since and log.stat().st_mtime < since:
        return "STALE log (run did not execute)"
    txt = log.read_text(encoding="utf-8", errors="replace")
    errors = re.findall(r"^ERROR \d+:.*$", txt, re.M)
    if re.search(r"Finished computing simulation run", txt):
        n_warn = len(re.findall(r"^WARNING \d+:", txt, re.M))
        rt = re.search(r"total runtime for this simulation is (\S+)", txt)
        base = f"OK ({rt.group(1) if rt else '?'}, {n_warn} warn)"
        return base + (f" +{len(errors)} ERR" if errors else "")
    if errors:
        return f"FAILED: {errors[0][:70]}"
    return "FAILED (no completion note)"


def run_project(project: Path, tags: list[str], hms_home: Path,
                timeout_s: int = 60 * 60 * 12) -> tuple[dict[str, str], str]:
    """Compute ``Run <tag>`` for each tag in one project. Returns ({tag: verdict}, hms_output_tail)."""
    script = write_compute_script(project, [f"Run {t}" for t in tags], scratch_dir("hms_compute_scripts"))
    bat = _write_launcher(script, hms_home)
    started = time.time()
    time.sleep(1.1)  # make the mtime comparison unambiguous on 1-2 s filesystems
    proc = subprocess.run([str(bat)], capture_output=True, text=True, shell=False, timeout=timeout_s)
    tail = (proc.stdout or "") + (proc.stderr or "")
    return {t: log_verdict(project, t, since=started) for t in tags}, tail


def compute_all(parent: str | Path, tags: list[str], only: str | None = None,
                hms_home: str | Path | None = None) -> None:
    """Compute the given run tags in every HMS project under ``parent``."""
    home = find_hms_home(hms_home)
    projects = sorted(p for p in Path(parent).iterdir()
                      if p.is_dir() and (only is None or p.name == only) and list(p.glob("*.hms")))
    print(f"Computing {len(tags)} run(s) x {len(projects)} project(s) = {len(tags) * len(projects)} simulations")
    print(f"HEC-HMS: {home}\nScenarios: {', '.join(tags)}\n")

    t_all, ok, fail = time.time(), 0, 0
    for proj in projects:
        t0 = time.time()
        try:
            verdicts, tail = run_project(proj, tags, home)
        except Exception as e:
            print(f"{proj.name:22s} ERROR {type(e).__name__}: {e}")
            fail += len(tags)
            continue
        for t in tags:
            ok, fail = (ok + 1, fail) if verdicts[t].startswith("OK") else (ok, fail + 1)
        print(f"{proj.name:22s} [{time.time() - t0:6.0f}s] "
              + "  ".join(f"{t}={verdicts[t]}" for t in tags), flush=True)
        if any(not v.startswith("OK") for v in verdicts.values()) and tail.strip():
            print("    hms output: " + tail.strip().replace("\n", "\n    ")[:600], flush=True)
    print(f"\nDone in {time.time() - t_all:.0f}s -- {ok} succeeded, {fail} failed")
