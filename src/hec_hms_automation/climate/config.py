"""ClimateRunConfig -- the single source of truth handed to the clip/export
pipeline and to the Vortex bridge (no GUI required: fill it in code or from CLI)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SCENARIOS = ["historical", "ssp126", "ssp245", "ssp370", "ssp585"]

SCN_LABEL = {
    "historical": "Historical",
    "ssp126": "SSP1-2.6",
    "ssp245": "SSP2-4.5",
    "ssp370": "SSP3-7.0",
    "ssp585": "SSP5-8.5",
}

SCN_COLOR = {
    "historical": "#555555",
    "ssp126": "#1a9850",
    "ssp245": "#f6e34e",
    "ssp370": "#f4a101",
    "ssp585": "#d73027",
}


@dataclass
class ClimateRunConfig:
    # --- Basin / clipping ---
    basin_shapefile: str = ""
    buffer_km: float = 25.0
    basin_name: str = ""

    # --- Scenario NetCDFs (blank path = skip that scenario) ---
    scenario_files: dict = field(default_factory=lambda: {s: "" for s in SCENARIOS})

    # --- Variable / units ---
    rain_var: str = "pr"
    unit_mode: str = "auto"          # "auto" | "x86400" | "none"

    # --- Time subsetting ---
    start_year: int = 0               # 0 = from file start
    end_year: int = 0                 # 0 = to file end

    # --- Change-signal reference period (used only if historical provided) ---
    ref_start: int = 1981
    ref_end: int = 2014

    # --- Vortex / DSS ---
    target_projection_label: str = ""
    target_cell_size_m: str = "2000"
    vortex_home: str = ""

    # --- Output ---
    output_dir: str = ""

    def active_scenarios(self) -> list[str]:
        return [s for s in SCENARIOS if self.scenario_files.get(s, "").strip()]

    def buffered_shapefile_path(self) -> str:
        return str(Path(self.output_dir) / "buffered_boundary.shp")

    def clipped_nc_path(self, scenario: str) -> str:
        return str(Path(self.output_dir) / f"{scenario}_{self.rain_var}_clipped.nc")

    def timeseries_csv_path(self, scenario: str) -> str:
        return str(Path(self.output_dir) / f"timeseries_{scenario}.csv")

    def output_raw_dss_path(self, scenario: str) -> str:
        return str(Path(self.output_dir) / f"{self.basin_name}_{scenario}_raw.dss")

    def output_final_dss_path(self, scenario: str) -> str:
        return str(Path(self.output_dir) / f"{self.basin_name}_{scenario}_ts.dss")

    def validate(self) -> list[str]:
        """Human-readable problems; an empty list means the config is runnable."""
        problems = []
        if not self.basin_shapefile or not Path(self.basin_shapefile).exists():
            problems.append("Basin shapefile not found.")
        if not self.output_dir:
            problems.append("Output directory not set.")
        if not self.basin_name:
            problems.append("Basin name is empty.")
        if not self.rain_var:
            problems.append("Precipitation variable not selected.")
        if self.buffer_km <= 0:
            problems.append("Buffer (km) must be positive.")
        if not self.target_projection_label:
            problems.append("Target projection (e.g. UTM46N) is empty.")

        active = self.active_scenarios()
        if not active:
            problems.append("Provide at least one scenario NetCDF file.")
        for s in active:
            if not Path(self.scenario_files[s]).exists():
                problems.append(f"NetCDF for {s} not found: {self.scenario_files[s]}")

        if self.start_year and self.end_year and self.start_year > self.end_year:
            problems.append("Start year must be <= end year.")
        if self.ref_start > self.ref_end:
            problems.append("Reference period start must be <= end.")
        return problems
