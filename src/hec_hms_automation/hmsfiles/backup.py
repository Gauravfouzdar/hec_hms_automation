"""Timestamped backups -- every writer in this package calls this before it
modifies a user's HMS file, so a bad run can always be undone by copying the
``.bak-YYYYmmdd-HHMMSS`` file back over the original."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def backup_path(path: str | Path) -> Path:
    """Return the (not yet created) backup path for ``path``."""
    path = Path(path)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return path.with_suffix(path.suffix + f".bak-{stamp}")


def backup_file(path: str | Path) -> Path:
    """Copy ``path`` to ``<name><ext>.bak-<timestamp>`` next to it and return the copy."""
    bak = backup_path(path)
    shutil.copy2(path, bak)
    return bak
