"""
Where external tools live -- resolved from arguments / environment, never
hard-coded to one machine.

Environment variables (set once per machine, CMD):

    set HMS_HOME=C:\\Program Files\\HEC\\HEC-HMS\\4.13
    set VORTEX_HOME=C:\\Tools\\vortex-0.13.3

or pass ``--hms-home`` / ``--vortex-home`` on the command line.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .vortex.locator import find_vortex_home  # re-exported for convenience

__all__ = ["find_hms_home", "find_vortex_home", "scratch_dir"]


def _looks_like_hms_home(p: Path) -> bool:
    return (p / "HEC-HMS.cmd").exists()


def find_hms_home(explicit: str | Path | None = None) -> Path:
    """Locate the HEC-HMS install folder (the one holding ``HEC-HMS.cmd``).

    Order: ``explicit`` -> ``HMS_HOME`` env var -> newest folder matching
    ``C:\\Program Files\\HEC\\HEC-HMS\\*``. Raises FileNotFoundError with a hint
    if nothing valid is found.
    """
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("HMS_HOME"):
        candidates.append(Path(os.environ["HMS_HOME"]))
    for pf in (os.environ.get("ProgramFiles"), "C:/Program Files"):
        if pf:
            candidates += sorted((Path(pf) / "HEC" / "HEC-HMS").glob("*"), reverse=True)
    for cand in candidates:
        if _looks_like_hms_home(cand):
            return cand
    raise FileNotFoundError(
        "HEC-HMS not found. Install HEC-HMS 4.x, then set HMS_HOME (CMD: "
        "set HMS_HOME=C:\\Program Files\\HEC\\HEC-HMS\\4.13) or pass --hms-home."
    )


def scratch_dir(name: str = "hms_automation") -> Path:
    """A scratch folder for generated scripts.

    It lives in the system temp dir ON PURPOSE: project folders often contain
    ``&`` (e.g. ``E:\\AI & ML``), which cmd.exe treats as a command separator and
    which silently breaks ``cmd /c <batfile>``.  The temp path has no such
    characters.
    """
    p = Path(tempfile.gettempdir()) / name
    p.mkdir(exist_ok=True)
    return p
