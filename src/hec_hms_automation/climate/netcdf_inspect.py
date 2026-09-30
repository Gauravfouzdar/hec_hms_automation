"""Inspect a NetCDF: list plottable data variables (bounds variables filtered
out), their units, and the file's time range.

CMIP6-style files call precipitation ``pr``, ``precip``, ``precipitation``,
``rain``, ... so nothing is hard-coded: the ALIAS LIST decides first; only when
it finds nothing does the optional Jev advisor (judgment.advisors) look at each
variable's name / long_name / units.  Its answer is only ever a *suggestion* --
``suggestion_band`` tells the caller whether to accept ('yes') or ask the user
('review'); with no key it is simply absent.

CLI:  hms-auto inspect-nc "<file.nc>"
"""
from __future__ import annotations

import xarray as xr

_BOUNDS_NAMES = {
    "time_bnds", "lat_bnds", "lon_bnds",
    "time_bounds", "lat_bounds", "lon_bounds",
    "crs", "spatial_ref",
}

PRECIP_ALIASES = ["pr", "precip", "precipitation", "rain", "tp", "rainfall"]


def inspect_netcdf(nc_path: str, judge_variable: bool = False) -> dict:
    """
    Returns::

        {
          "variables": [{"name","units","long_name","dims"}, ...],
          "suggested": "<name or ''>",       # best precipitation candidate
          "suggestion_source": "rule" | "jev" | "",
          "suggestion_band":   "yes" | "review" | "no" | "none" | "",
          "time_start": <year or None>,
          "time_end":   <year or None>,
        }

    ``judge_variable=True`` allows the Jev advisor when no alias matches.
    """
    ds = xr.open_dataset(nc_path, use_cftime=True)
    try:
        variables = []
        for name, da in ds.data_vars.items():
            if name in _BOUNDS_NAMES or name.endswith(("_bnds", "_bounds")):
                continue
            variables.append({
                "name": name,
                "units": da.attrs.get("units", ""),
                "long_name": da.attrs.get("long_name", ""),
                "dims": tuple(da.dims),
            })

        suggested, source, band = "", "", ""
        names = [v["name"] for v in variables]
        for alias in PRECIP_ALIASES:                       # rule first
            if alias in names:
                suggested, source, band = alias, "rule", "yes"
                break
        if not suggested and len(variables) == 1:
            suggested, source, band = variables[0]["name"], "rule", "review"
        if not suggested and judge_variable and variables:  # Jev only as a fallback
            from ..judgment import judge_precip_variable
            s = judge_precip_variable(
                [dict(v, dims=list(v["dims"])) for v in variables])
            suggested, source, band = s.value, s.source, s.band

        time_start = time_end = None
        if "time" in ds.coords:
            tvals = ds["time"].values
            if len(tvals):
                time_start = int(tvals[0].year if hasattr(tvals[0], "year") else str(tvals[0])[:4])
                time_end = int(tvals[-1].year if hasattr(tvals[-1], "year") else str(tvals[-1])[:4])

        return {
            "variables": variables,
            "suggested": suggested,
            "suggestion_source": source,
            "suggestion_band": band,
            "time_start": time_start,
            "time_end": time_end,
        }
    finally:
        ds.close()
