"""CMIP6 climate-scenario pipeline: clip NetCDF to a buffered basin -> mm/day
NetCDF + CSV -> plots -> gridded DSS through Vortex."""
from .config import ClimateRunConfig, SCENARIOS, SCN_LABEL, SCN_COLOR

__all__ = ["ClimateRunConfig", "SCENARIOS", "SCN_LABEL", "SCN_COLOR"]
