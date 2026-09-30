"""Enable ``python -m hec_hms_automation ...`` (same as the ``hms-auto`` command)."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
