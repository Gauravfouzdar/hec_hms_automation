"""
Design-storm workflow: hourly design-storm NetCDF per return period from IMD
gridded daily rainfall, then (optionally) gridded DSS through Vortex.

    IMD NetCDF (daily)
      -> clip to basin (buffer_km pad on the bounding box, EXACT unbuffered polygon mask)
      -> annual maxima per cell (last 30 years)
      -> regional L-moment/Gumbel growth curve + index rainfall (hydrology.design_storm)
      -> RP rainfall per cell -> CWC hourly factors -> Alternating Block Method
      -> hourly NetCDF per RP (storm on ``storm_day`` of ``total_days``)
      -> [Vortex] gridded DSS with a 1 h END shift

Literature and simplifications: hydrology/design_storm.py and docs/LITERATURE.md.

Run:  hms-auto design-storm --help
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from importlib import resources
from pathlib import Path

import geopandas as gpd
import netCDF4 as nc
import numpy as np
import pandas as pd
import xarray as xr
from shapely.geometry import Point

from ..hydrology import design_storm as ds_math

CWC_SHEET = "Incremental rainfall factor"
HOURLY_SHIFT_HOURS = 1   # design-storm NetCDFs are hourly -> 1 h END shift for DSS


# ------------------------------------------------------------------ configuration
@dataclass
class DesignStormConfig:
    imd_netcdf: str = ""
    basin_shapefile: str = ""
    buffer_km: float = 25.0
    cwc_excel: str = ""              # blank -> bundled resources/cwc_default.xlsx
    cwc_zone: str = "2b"

    rain_var: str = "rain"
    lat_var: str = "lat"
    lon_var: str = "lon"
    time_var: str = "time"

    return_periods: list[int] = field(default_factory=lambda: [5, 10, 25, 50, 100])

    total_days: int = 10
    storm_day: int = 5
    storm_start_date: str = "2024-01-01"

    target_projection_label: str = ""   # Vortex label, e.g. "UTM46N"
    target_cell_size_m: str = "2000"
    output_dir: str = ""
    basin_name: str = ""

    def resolved_cwc_excel(self) -> str:
        if self.cwc_excel:
            return self.cwc_excel
        return str(resources.files("hec_hms_automation") / "resources" / "cwc_default.xlsx")

    def output_netcdf_path(self, rp: int) -> str:
        return str(Path(self.output_dir) / f"design_storm_RP{rp}.nc")

    def output_raw_dss_path(self, rp: int) -> str:
        return str(Path(self.output_dir) / f"{self.basin_name}_{rp}RP_raw.dss")

    def output_final_dss_path(self, rp: int) -> str:
        return str(Path(self.output_dir) / f"{self.basin_name}_{rp}RP_ts.dss")

    def validate(self, need_projection: bool = False) -> list[str]:
        p = []
        if not self.imd_netcdf or not Path(self.imd_netcdf).exists():
            p.append("IMD NetCDF file not found.")
        if not self.basin_shapefile or not Path(self.basin_shapefile).exists():
            p.append("Basin shapefile not found.")
        if not self.output_dir:
            p.append("Output directory not set.")
        if not self.return_periods:
            p.append("Select at least one return period.")
        if not self.basin_name:
            p.append("Basin name is empty.")
        if need_projection and not self.target_projection_label:
            p.append("Target projection (e.g. UTM46N) is empty.")
        if self.storm_day < 1 or self.storm_day > self.total_days:
            p.append("Storm day must be between 1 and total days.")
        if self.buffer_km <= 0:
            p.append("Buffer (km) must be positive.")
        return p


# ---------------------------------------------------------------- CWC factors
def _read_cwc_sheet(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=CWC_SHEET)
    # str() coercion: at least one real sub-zone header (zone "7") is a bare int.
    df.columns = [str(c) for c in df.columns]
    return df


def list_cwc_zones(cwc_excel_path: str) -> list[str]:
    return [c for c in _read_cwc_sheet(cwc_excel_path).columns if c != "Hour"]


def load_cwc_factors(cwc_excel_path: str, zone: str) -> np.ndarray:
    """24 hourly incremental factors for a CWC sub-zone (should sum to 1.0)."""
    df = _read_cwc_sheet(cwc_excel_path)
    zone = str(zone)
    if zone not in df.columns:
        raise ValueError(f"Zone '{zone}' not found in CWC Excel. "
                         f"Available: {[c for c in df.columns if c != 'Hour']}")
    return df[zone].values


# ---------------------------------------------------------------- step 1: clip
def load_and_clip_imd(cfg: DesignStormConfig):
    """Load IMD NetCDF, clip to the basin bounding box (+buffer), build the EXACT
    basin mask from the UNBUFFERED polygon.  Returns (ds_clipped, mask, lats, lons)."""
    ds = xr.open_dataset(cfg.imd_netcdf)
    lats = ds[cfg.lat_var].values
    lons = ds[cfg.lon_var].values

    basin = gpd.read_file(cfg.basin_shapefile)
    if basin.crs is None:
        raise ValueError("Basin shapefile has no CRS defined -- cannot compute buffer or reproject.")
    basin_wgs84 = basin.to_crs(epsg=4326) if basin.crs.to_epsg() != 4326 else basin

    if basin.crs.is_projected:
        # Buffer in the basin's own metric CRS, then reproject the bounds to WGS84.
        buffered = gpd.GeoDataFrame(geometry=basin.geometry.buffer(cfg.buffer_km * 1000.0),
                                    crs=basin.crs).to_crs(epsg=4326)
        minx, miny, maxx, maxy = buffered.total_bounds
    else:
        d = cfg.buffer_km / 111.0    # 1 deg latitude ~ 111 km
        x0, y0, x1, y1 = basin_wgs84.total_bounds
        minx, miny, maxx, maxy = x0 - d, y0 - d, x1 + d, y1 + d

    ds_clipped = ds.sel({cfg.lat_var: lats[(lats >= miny) & (lats <= maxy)],
                         cfg.lon_var: lons[(lons >= minx) & (lons <= maxx)]})
    lats_c = ds_clipped[cfg.lat_var].values
    lons_c = ds_clipped[cfg.lon_var].values

    union = basin_wgs84.union_all() if hasattr(basin_wgs84, "union_all") else basin_wgs84.unary_union
    mask = np.zeros((len(lats_c), len(lons_c)), dtype=bool)
    for i, la in enumerate(lats_c):
        for j, lo in enumerate(lons_c):
            mask[i, j] = union.contains(Point(lo, la))
    if not mask.any():
        raise ValueError("No grid cells found inside basin! Check shapefile CRS or basin extent vs IMD grid.")
    return ds_clipped, mask, lats_c, lons_c


# ------------------------------------------------------- step 2: annual maxima
def extract_annual_max(ds_clipped, basin_mask, cfg: DesignStormConfig, last_n_years: int = 30):
    """Annual maximum daily rainfall per cell, masked to the basin.  Uses the
    LAST ``last_n_years`` years when the record is longer."""
    rain = ds_clipped[cfg.rain_var]
    per_year = rain.groupby(f"{cfg.time_var}.year").max()
    annual_max, years = per_year.values, per_year.year.values
    if len(years) > last_n_years:
        annual_max, years = annual_max[-last_n_years:], years[-last_n_years:]
    annual_max = np.where(annual_max < 0, np.nan, annual_max)          # negative = missing flag
    annual_max = np.where(np.broadcast_to(basin_mask, annual_max.shape), annual_max, np.nan)
    return annual_max, years


# -------------------------------------------------------- step 7: hourly window
def build_hourly_window(rp_rainfall, cwc_factors, basin_mask, cfg: DesignStormConfig):
    """N-day hourly array per RP: dry days, one 24 h storm on ``storm_day``, dry days.

    Returns ({RP: (hours, lat, lon)}, storm_start_hour, storm_end_hour).
    """
    total_hours = cfg.total_days * 24
    s0 = (cfg.storm_day - 1) * 24
    s1 = s0 + 24
    n_lats, n_lons = basin_mask.shape
    hourly = {}
    for rp in cfg.return_periods:
        cube = np.zeros((total_hours, n_lats, n_lons))
        for i in range(n_lats):
            for j in range(n_lons):
                if basin_mask[i, j] and not np.isnan(rp_rainfall[rp][i, j]):
                    cube[s0:s1, i, j] = ds_math.generate_hourly_hyetograph(rp_rainfall[rp][i, j], cwc_factors)
        hourly[rp] = cube
    return hourly, s0, s1


# ----------------------------------------------------------- step 8: NetCDF out
def write_netcdf(hourly_data, lats, lons, basin_mask, cfg: DesignStormConfig) -> list[str]:
    """One CF-style NetCDF per RP (dims time/lat/lon, variable = cfg.rain_var, mm/hr)."""
    os.makedirs(cfg.output_dir, exist_ok=True)
    total_hours = cfg.total_days * 24
    t0 = datetime.strptime(cfg.storm_start_date, "%Y-%m-%d")
    times = [t0 + timedelta(hours=h) for h in range(total_hours)]
    written = []

    for rp in cfg.return_periods:
        path = cfg.output_netcdf_path(rp)
        with nc.Dataset(path, "w", format="NETCDF4") as ds:
            ds.Conventions = "CF-1.7"
            ds.title = f"Design Storm - Return Period {rp} years"
            ds.source = "IMD gridded rainfall + CWC hourly factors"
            ds.history = (f"{datetime.now():%Y-%m-%d %H:%M:%S} hec_hms_automation - Regional Index "
                          f"Rainfall, L-moments Gumbel, Alternating Block Method")
            ds.references = "Hosking & Wallis (1997)"
            ds.comment = (f"Hourly design storm. Storm on Day {cfg.storm_day} (hours "
                          f"{(cfg.storm_day - 1) * 24}-{cfg.storm_day * 24 - 1}). Return period: {rp} years.")
            ds.crs = "epsg:4326"

            ds.createDimension("time", total_hours)
            ds.createDimension("lat", len(lats))
            ds.createDimension("lon", len(lons))

            v = ds.createVariable("lat", "f8", ("lat",))
            v[:] = lats.astype(np.float64)
            v.units, v.long_name, v.standard_name, v.axis = "degrees_north", "latitude", "latitude", "Y"

            v = ds.createVariable("lon", "f8", ("lon",))
            v[:] = lons.astype(np.float64)
            v.units, v.long_name, v.standard_name, v.axis = "degrees_east", "longitude", "longitude", "X"

            v = ds.createVariable("time", "f8", ("time",))
            v[:] = nc.date2num(times, units="hours since 1900-01-01 00:00:00", calendar="standard")
            v.units, v.long_name, v.standard_name = "hours since 1900-01-01 00:00:00", "time", "time"
            v.calendar, v.axis = "standard", "T"

            v = ds.createVariable(cfg.rain_var, "f8", ("time", "lat", "lon"),
                                  zlib=True, complevel=4, fill_value=np.nan)
            v.units, v.long_name, v.standard_name = "mm hr-1", "Hourly Design Rainfall", "precipitation_flux"
            v.coordinates = "lat lon time"
            v.return_period = f"{rp} years"
            v.cwc_zone = cfg.cwc_zone

            data = hourly_data[rp].astype(np.float64)
            data[np.broadcast_to(~basin_mask, data.shape)] = np.nan   # NaN outside the basin
            v[:, :, :] = data
        written.append(path)
        print(f"  RP {rp:>4} yr -> {os.path.basename(path)}  [time={total_hours}, lat={len(lats)}, lon={len(lons)}]")
    return written


# -------------------------------------------------------------- orchestration
def run_pipeline(cfg: DesignStormConfig, make_plots: bool = True) -> dict:
    """Run everything up to and including the per-RP NetCDF files."""
    problems = cfg.validate()
    if problems:
        raise ValueError("Invalid configuration: " + "; ".join(problems))

    print(f"Design storm: CWC zone {cfg.cwc_zone}, RPs {cfg.return_periods}, "
          f"storm day {cfg.storm_day} of {cfg.total_days}")
    ds_clipped, mask, lats, lons = load_and_clip_imd(cfg)
    print(f"  Cells inside basin: {int(mask.sum())}")
    annual_max, years = extract_annual_max(ds_clipped, mask, cfg)
    print(f"  Annual maxima {years[0]}-{years[-1]} ({len(years)} years)")

    h = ds_math.homogeneity_test(annual_max, mask)
    print(f"  H-statistic {h:.3f}  ({'homogeneous' if h < 1 else 'possibly heterogeneous' if h < 2 else 'HETEROGENEOUS'})")
    index_map, growth, gumbel = ds_math.fit_gumbel_lmoments_regional(annual_max, mask, cfg.return_periods)
    print(f"  Gumbel loc={gumbel['loc']:.4f} scale={gumbel['scale']:.4f}; growth factors "
          + ", ".join(f"RP{rp}={g:.3f}" for rp, g in growth.items()))
    rp_rain = ds_math.compute_rp_rainfall(index_map, growth, mask)

    factors = load_cwc_factors(cfg.resolved_cwc_excel(), cfg.cwc_zone)
    print(f"  CWC zone {cfg.cwc_zone}: {len(factors)} factors, sum = {factors.sum():.4f} (should be 1.0)")
    if abs(float(factors.sum()) - 1.0) > 0.01:      # code-enforced guard, not a judgment
        raise ValueError(f"CWC factors for zone {cfg.cwc_zone} sum to {factors.sum():.4f}, not 1.0 -- "
                         f"check the Excel sheet before generating storms.")

    hourly, s0, s1 = build_hourly_window(rp_rain, factors, mask, cfg)
    written = write_netcdf(hourly, lats, lons, mask, cfg)

    result = {"basin_mask": mask, "index_map": index_map, "rp_rainfall": rp_rain,
              "growth_factors": growth, "gumbel_params": gumbel, "hourly_data": hourly,
              "H_statistic": h, "written_files": written, "cwc_factors": factors,
              "lats": lats, "lons": lons}
    if make_plots:
        from ..plots.design_storm import plot_diagnostics
        result["diagnostic_plot"] = plot_diagnostics(rp_rain, hourly, factors, mask, lats, lons, cfg)
    return result


def run_full(cfg: DesignStormConfig, vortex_home: str | Path, make_plots: bool = True,
             log_cb=print, max_workers: int | None = None) -> dict:
    """Pipeline + Vortex conversion of every RP NetCDF into a gridded DSS."""
    from ..vortex.converter import convert_netcdf_to_dss
    from ..vortex.jython_templates import VortexJob, sanitize_part_b

    problems = cfg.validate(need_projection=True)
    if problems:
        raise ValueError("Invalid configuration: " + "; ".join(problems))
    result = run_pipeline(cfg, make_plots=make_plots)
    jobs = [VortexJob(label=f"{rp}RP", nc=cfg.output_netcdf_path(rp),
                      raw_dss=cfg.output_raw_dss_path(rp), final_dss=cfg.output_final_dss_path(rp),
                      clip_shp=cfg.basin_shapefile, part_b=sanitize_part_b(cfg.basin_name))
            for rp in cfg.return_periods]
    result["dss_files"] = convert_netcdf_to_dss(
        jobs, vortex_home, Path(cfg.output_dir) / "_vortex_run",
        wkt_label=cfg.target_projection_label, rain_var=cfg.rain_var,
        shift_hours=HOURLY_SHIFT_HOURS, target_cell_size_m=cfg.target_cell_size_m,
        max_workers=max_workers, log_cb=log_cb)
    return result
