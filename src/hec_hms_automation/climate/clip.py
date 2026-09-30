"""
Clip CMIP6 scenario NetCDFs to the BUFFERED basin polygon and export
per-scenario artifacts: a clipped NetCDF (mm/day, IMD-style structure so the
Vortex bridge imports it exactly like the design-storm NetCDFs) and a
per-grid-cell time-series CSV.

Key semantic point: the BUFFERED polygon is the real selection geometry --
cells under the buffered area are exported, and the buffered polygon itself
(written to buffered_boundary.shp) is the Vortex clip shape.  A larger buffer
means more cells, by design.  (In the design-storm pipeline the buffer only
widens the bounding-box pre-selection; there the exact mask uses the unbuffered
basin.)

CMIP6 time handling: open with ``use_cftime=True`` and convert via
``to_datetimeindex``, because noleap / 360-day calendars break plain
``pd.to_datetime``.  Missing dates (e.g. Feb 29 in noleap models) simply do not
produce a record -- harmless for DSS.

Also accepts "points-format" input -- ``pr(time, points)`` with lat/lon as
auxiliary coordinates over ``points`` rather than independent grid axes.  It is
detected and reconstructed into a regular (time, lat, lon) grid before anything
else runs (see :func:`is_points_format` / :func:`coerce_points_to_grid`).

Literature: Eyring et al. 2016 (CMIP6), O'Neill et al. 2016 (ScenarioMIP) --
docs/LITERATURE.md.
"""
from __future__ import annotations

import os
from datetime import datetime

import geopandas as gpd
import netCDF4 as nc
import numpy as np
import pandas as pd
import xarray as xr
from shapely.geometry import Point

from .config import ClimateRunConfig


def cftime_to_datetime(cftime_index):
    """Convert a cftime/CFTimeIndex (any calendar) to a pandas DatetimeIndex."""
    try:
        return cftime_index.to_datetimeindex(unsafe=True)
    except AttributeError:
        return pd.DatetimeIndex(cftime_index)  # already datetime64-backed
    except Exception:
        return pd.DatetimeIndex([
            pd.Timestamp(f"{t.year:04d}-{t.month:02d}-{t.day:02d}") for t in cftime_index
        ])


def detect_coord_names(ds) -> tuple[str, str]:
    lat_name = "lat" if "lat" in ds.coords else ("latitude" if "latitude" in ds.coords else None)
    lon_name = "lon" if "lon" in ds.coords else ("longitude" if "longitude" in ds.coords else None)
    if lat_name is None or lon_name is None:
        raise ValueError(f"Could not find lat/lon coordinates. Coords present: {list(ds.coords)}")
    return lat_name, lon_name


def is_points_format(ds, lat_name: str, lon_name: str) -> bool:
    """True when lat/lon are auxiliary coordinates over a non-spatial dimension
    (e.g. dims=('points',)) rather than independent grid axes."""
    return not (ds[lat_name].dims == (lat_name,) and ds[lon_name].dims == (lon_name,))


def coerce_points_to_grid(ds, var: str, lat_name: str, lon_name: str):
    """Reconstruct a (time, lat, lon) grid from a sparse points-format dataset,
    assuming the points lie on a regular lattice; NaN wherever no point exists."""
    lat_vals = ds[lat_name].values
    lon_vals = ds[lon_name].values

    lat_r = np.round(lat_vals, 4)   # rounding avoids spurious extra rows/cols from float noise
    lon_r = np.round(lon_vals, 4)
    lats_u = np.unique(lat_r)
    lons_u = np.unique(lon_r)

    for label, arr in (("latitudes", lats_u), ("longitudes", lons_u)):
        if len(arr) > 1:
            steps = np.diff(np.sort(arr))
            if not np.allclose(steps, steps[0], atol=1e-6):
                print(f"  WARNING: point {label} are not evenly spaced ({arr}); "
                      f"reconstructed grid cell sizes will be uneven.")

    n_time = ds.sizes["time"]
    grid = np.full((n_time, len(lats_u), len(lons_u)), np.nan, dtype=np.float64)
    src = ds[var].values  # (time, points)

    lat_idx = np.searchsorted(lats_u, lat_r)
    lon_idx = np.searchsorted(lons_u, lon_r)
    for p in range(src.shape[1]):
        grid[:, lat_idx[p], lon_idx[p]] = src[:, p]

    print(f"  Points-format input detected ({src.shape[1]} points) -- "
          f"reconstructed as a {len(lats_u)} x {len(lons_u)} regular grid.")

    return xr.Dataset(
        {var: (("time", "lat", "lon"), grid, dict(ds[var].attrs))},
        coords={"time": ds["time"].values, "lat": lats_u, "lon": lons_u},
        attrs=dict(ds.attrs),
    )


def build_buffered_geometry(cfg: ClimateRunConfig):
    """Buffer the basin polygon by ``cfg.buffer_km`` (in its own projected CRS
    when available, a degree approximation otherwise).

    Returns (buffered_wgs84_gdf, basin_wgs84_gdf).
    """
    basin = gpd.read_file(cfg.basin_shapefile)
    if basin.crs is None:
        raise ValueError("Basin shapefile has no CRS defined -- cannot buffer or reproject.")

    basin_wgs84 = basin.to_crs(epsg=4326) if basin.crs.to_epsg() != 4326 else basin

    if basin.crs.is_projected:
        buffered = basin.geometry.buffer(cfg.buffer_km * 1000.0)
        buffered_gdf = gpd.GeoDataFrame(geometry=buffered, crs=basin.crs).to_crs(epsg=4326)
        print(f"  Buffer: {cfg.buffer_km} km applied in {basin.crs}")
    else:
        deg = cfg.buffer_km / 111.0   # 1 deg latitude ~ 111 km
        buffered_gdf = gpd.GeoDataFrame(geometry=basin_wgs84.geometry.buffer(deg), crs="EPSG:4326")
        print(f"  Buffer: {cfg.buffer_km} km approximated as {deg:.4f} deg (geographic CRS)")

    return buffered_gdf, basin_wgs84


def write_buffered_shapefile(cfg: ClimateRunConfig, buffered_gdf, extra_cells=None,
                             cell_step_deg: float = 0.25) -> str:
    """Write the Vortex clip shape (also a plot overlay) to the output dir.

    Normally just the buffered basin polygon.  When the boundary-basin fallback
    fired, ``extra_cells`` (lat, lon centres possibly OUTSIDE the buffer) must be
    covered too -- otherwise Vortex's clip would exclude the only cells that
    carry data and the DSS would come out empty.  Each is added as a small box.
    """
    from shapely.geometry import box
    from shapely.ops import unary_union

    os.makedirs(cfg.output_dir, exist_ok=True)
    out_path = cfg.buffered_shapefile_path()

    geoms = list(buffered_gdf.geometry.values)
    if extra_cells:
        half = cell_step_deg / 2.0
        for la, lo in extra_cells:
            geoms.append(box(lo - half, la - half, lo + half, la + half))
        print(f"  Clip shape widened with {len(extra_cells)} fallback cell footprint(s).")

    gpd.GeoDataFrame(geometry=[unary_union(geoms)], crs="EPSG:4326").to_file(out_path)
    print(f"  Buffered boundary shapefile: {out_path}")
    return out_path


def select_cells(lats, lons, buffered_gdf):
    """Boolean mask (lat x lon) of cells whose centres lie inside the buffered polygon."""
    union = buffered_gdf.union_all() if hasattr(buffered_gdf, "union_all") else buffered_gdf.unary_union
    mask = np.zeros((len(lats), len(lons)), dtype=bool)
    for i, la in enumerate(lats):
        for j, lo in enumerate(lons):
            if union.contains(Point(lo, la)):
                mask[i, j] = True
    return mask


def resolve_conversion(da, unit_mode: str):
    """Return (factor, note) converting the variable to mm/day.

    CMIP6 ``pr`` is a flux in kg m-2 s-1; 1 kg m-2 of water = 1 mm, so
    mm/day = flux * 86400.  Unit conversion is pure arithmetic and is
    deliberately done in code (never delegated to any model).
    """
    if unit_mode == "x86400":
        return 86400.0, "forced x86400 (kg m-2 s-1 -> mm/day)"
    if unit_mode == "none":
        return 1.0, "no conversion (forced)"
    units = str(da.attrs.get("units", "")).lower().strip()
    if "kg" in units and "s-1" in units.replace("/s", " s-1"):
        return 86400.0, f"auto: '{units}' -> x86400 -> mm/day"
    if units in ("kg m-2 s-1", "kg/m2/s", "kg m^-2 s^-1"):
        return 86400.0, f"auto: '{units}' -> x86400 -> mm/day"
    return 1.0, f"auto: '{units or 'no units attr'}' -> assumed already mm/day, no conversion"


N_FALLBACK_CELLS = 4  # nearest valid-data cells used when the buffer holds none


def _nearest_valid_cells(ds, var, lat_name, lon_name, center_lat, center_lon, n=N_FALLBACK_CELLS):
    """Boundary-basin fallback: the ``n`` nearest grid cells that actually hold
    data, anywhere in the file.  Validity is judged from the first timestep --
    masked products have static NaN masks, so one slice is representative.

    Returns [(lat, lon, distance_km)] nearest first (equirectangular distance).
    """
    first = ds[var].isel(time=0).values.astype(np.float64)
    lats = ds[lat_name].values
    lons = ds[lon_name].values
    valid_i, valid_j = np.where(np.isfinite(first))
    if len(valid_i) == 0:
        return []

    cell_lats = lats[valid_i]
    cell_lons = lons[valid_j]
    d_km = np.sqrt(
        ((cell_lats - center_lat) * 111.0) ** 2
        + ((cell_lons - center_lon) * 111.0 * np.cos(np.radians(center_lat))) ** 2
    )
    order = np.argsort(d_km)[:n]
    return [(float(cell_lats[k]), float(cell_lons[k]), float(d_km[k])) for k in order]


def clip_scenario(cfg: ClimateRunConfig, scenario: str, buffered_gdf):
    """Clip one scenario's NetCDF to the buffered polygon, subset years, convert to mm/day.

    Cells are selected by geometry AND data availability: a cell under the
    buffered polygon whose data is all-NaN (masked in the source product, common
    at a country/domain boundary) is dropped.  If NO cell under the buffer has
    valid data, the tool falls back to the N nearest valid-data cells anywhere
    in the grid, with a loud log warning.

    Returns a dict: scenario, times, lats, lons (clipped window), mask (2D bool),
    data (time, lat, lon) mm/day with NaN outside selected cells, and
    fallback_cells (empty unless the fallback fired; the Vortex clip shape must
    then be widened to cover them).
    """
    nc_path = cfg.scenario_files[scenario]
    print(f"\n[{scenario}] Loading {nc_path}")
    ds = xr.open_dataset(nc_path, use_cftime=True)
    try:
        lat_name, lon_name = detect_coord_names(ds)
        if cfg.rain_var not in ds.data_vars:
            raise ValueError(
                f"Variable '{cfg.rain_var}' not in {os.path.basename(nc_path)}. "
                f"Available: {list(ds.data_vars)}"
            )

        if is_points_format(ds, lat_name, lon_name):
            new_ds = coerce_points_to_grid(ds, cfg.rain_var, lat_name, lon_name)
            ds.close()
            ds = new_ds
            lat_name, lon_name = "lat", "lon"

        lats = ds[lat_name].values
        lons = ds[lon_name].values

        minx, miny, maxx, maxy = buffered_gdf.total_bounds
        lat_bb = (lats >= miny) & (lats <= maxy)
        lon_bb = (lons >= minx) & (lons <= maxx)

        fallback_cells = []
        centroid = buffered_gdf.geometry.iloc[0].centroid

        if not lat_bb.any() or not lon_bb.any():
            # Basin entirely outside the grid window -> straight to the fallback.
            nearest = _nearest_valid_cells(ds, cfg.rain_var, lat_name, lon_name,
                                           centroid.y, centroid.x)
            if not nearest:
                raise ValueError(
                    f"{scenario}: buffered basin does not overlap this NetCDF's grid and "
                    f"no valid-data cells exist anywhere in the file."
                )
            fallback_cells = [(la, lo) for la, lo, _ in nearest]
        else:
            ds_w = ds.sel({lat_name: lats[lat_bb], lon_name: lons[lon_bb]})
            lats_w = ds_w[lat_name].values
            lons_w = ds_w[lon_name].values
            geo_mask = select_cells(lats_w, lons_w, buffered_gdf)

            first = ds_w[cfg.rain_var].isel(time=0).values.astype(np.float64)
            valid_mask = np.isfinite(first)
            n_geo = int(geo_mask.sum())
            mask = geo_mask & valid_mask
            n_valid = int(mask.sum())
            if n_geo > n_valid:
                print(f"  NOTE: {n_geo - n_valid} of {n_geo} cells under the buffered polygon "
                      f"have no data in the source file (masked) and were dropped.")
            if n_valid == 0:
                nearest = _nearest_valid_cells(ds, cfg.rain_var, lat_name, lon_name,
                                               centroid.y, centroid.x)
                if not nearest:
                    raise ValueError(
                        f"{scenario}: no valid-data cells under the buffered polygon and "
                        f"none anywhere in the file."
                    )
                fallback_cells = [(la, lo) for la, lo, _ in nearest]

        if fallback_cells:
            dists = _nearest_valid_cells(ds, cfg.rain_var, lat_name, lon_name,
                                         centroid.y, centroid.x)
            print(f"  WARNING [{scenario}]: buffered area has NO grid cells with data "
                  f"(boundary basin). Falling back to the {len(fallback_cells)} nearest "
                  f"valid cells:")
            for la, lo, dk in dists:
                print(f"    lat {la:.3f}, lon {lo:.3f}  (~{dk:.0f} km from basin centroid)")
            fb_lats = sorted({la for la, _ in fallback_cells})
            fb_lons = sorted({lo for _, lo in fallback_cells})
            ds_w = ds.sel({lat_name: fb_lats, lon_name: fb_lons})
            lats_w = ds_w[lat_name].values
            lons_w = ds_w[lon_name].values
            mask = np.zeros((len(lats_w), len(lons_w)), dtype=bool)
            for la, lo in fallback_cells:
                mask[int(np.argmin(np.abs(lats_w - la))), int(np.argmin(np.abs(lons_w - lo)))] = True

        print(f"  Selected cells with data: {int(mask.sum())}"
              + (" (nearest-cell fallback)" if fallback_cells else ""))

        times = cftime_to_datetime(ds_w.indexes["time"])
        year_mask = np.ones(len(times), dtype=bool)
        if cfg.start_year:
            year_mask &= times.year >= cfg.start_year
        if cfg.end_year:
            year_mask &= times.year <= cfg.end_year
        if not year_mask.any():
            raise ValueError(
                f"{scenario}: no time steps in {cfg.start_year}-{cfg.end_year} "
                f"(file covers {times[0].year}-{times[-1].year})."
            )

        da = ds_w[cfg.rain_var]
        factor, note = resolve_conversion(da, cfg.unit_mode)
        print(f"  Units: {note}")

        data = da.values[year_mask].astype(np.float64) * factor
        times = times[year_mask]
        data = np.where(np.broadcast_to(mask, data.shape), data, np.nan)
        data = np.where(data < 0, 0.0, data)  # clamp tiny negative model artefacts

        print(f"  Time: {times[0].date()} .. {times[-1].date()} ({len(times)} days)")
        print(f"  Basin-mean daily precip: {np.nanmean(data):.2f} mm/day")

        return {
            "scenario": scenario,
            "times": times,
            "lats": lats_w,
            "lons": lons_w,
            "mask": mask,
            "data": data,
            "fallback_cells": fallback_cells,
        }
    finally:
        ds.close()


def write_clipped_netcdf(cfg: ClimateRunConfig, clip: dict) -> str:
    """IMD-style structure (time/lat/lon, rain variable named as in config,
    standard calendar) so Vortex imports it exactly like the design-storm files."""
    out_path = cfg.clipped_nc_path(clip["scenario"])
    times = clip["times"]
    lats, lons = clip["lats"], clip["lons"]

    with nc.Dataset(out_path, "w", format="NETCDF4") as ds:
        ds.Conventions = "CF-1.7"
        ds.title = f"CMIP6 {clip['scenario']} precipitation clipped to buffered basin"
        ds.history = (f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
                      f"hec_hms_automation -- buffered-polygon clip, mm/day")
        ds.crs = "epsg:4326"

        ds.createDimension("time", len(times))
        ds.createDimension("lat", len(lats))
        ds.createDimension("lon", len(lons))

        v_lat = ds.createVariable("lat", "f8", ("lat",))
        v_lat[:] = lats.astype(np.float64)
        v_lat.units, v_lat.standard_name, v_lat.axis = "degrees_north", "latitude", "Y"

        v_lon = ds.createVariable("lon", "f8", ("lon",))
        v_lon[:] = lons.astype(np.float64)
        v_lon.units, v_lon.standard_name, v_lon.axis = "degrees_east", "longitude", "X"

        v_time = ds.createVariable("time", "f8", ("time",))
        v_time[:] = nc.date2num(times.to_pydatetime().tolist(),
                                units="days since 1900-01-01 00:00:00", calendar="standard")
        v_time.units = "days since 1900-01-01 00:00:00"
        v_time.calendar = "standard"
        v_time.standard_name = "time"
        v_time.axis = "T"

        v_rain = ds.createVariable(cfg.rain_var, "f8", ("time", "lat", "lon"),
                                   zlib=True, complevel=4, fill_value=np.nan)
        v_rain.units = "mm/day"
        v_rain.long_name = f"Daily precipitation ({clip['scenario']})"
        v_rain.standard_name = "precipitation_flux"
        v_rain[:, :, :] = clip["data"]

    print(f"  Clipped NetCDF: {out_path}")
    return out_path


def write_timeseries_csv(cfg: ClimateRunConfig, clip: dict) -> str:
    """Datetime rows x one column per in-polygon grid cell."""
    out_path = cfg.timeseries_csv_path(clip["scenario"])
    mask, lats, lons, data = clip["mask"], clip["lats"], clip["lons"], clip["data"]

    records = {}
    for i in range(len(lats)):
        for j in range(len(lons)):
            if mask[i, j]:
                records[f"lat{lats[i]:.2f}_lon{lons[j]:.2f}"] = data[:, i, j]

    df = pd.DataFrame(records, index=clip["times"])
    df.index.name = "datetime"
    df.to_csv(out_path)
    print(f"  Time-series CSV: {out_path}  ({df.shape[0]} rows x {df.shape[1]} cells)")
    return out_path
