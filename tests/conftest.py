import sys
from pathlib import Path

# Allow running the tests without `pip install -e .`
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
