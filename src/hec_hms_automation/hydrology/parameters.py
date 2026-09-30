"""
HEC-HMS parameter estimation formulas.

Methods this module parameterises (all HEC-HMS 4.x built-ins; see
docs/LITERATURE.md for the references behind each):

Loss -- Deficit and Constant (identical for every subbasin)
    Initial Deficit 30 mm, Maximum Deficit 50 mm, Percolation 0.5 mm/hr,
    Percent Impervious from LULC (computed separately, gis.landuse).

Transform -- Modified Clark (ModClark)
    Kirpich:  Tc_min = 0.0195 * L**0.77 * S**-0.385      (L in m, S in m/m)
    Tc_hr    = Tc_min / 60
    Storage coefficient from R/(Tc+R) = 0.65  ->  R = (13/7) * Tc

Baseflow -- Linear Reservoir, two groundwater layers
    Initial baseflow 0.1 m3/s and fraction 0.4 per layer;
    GW-1 routing coefficient = 3*R, GW-2 = 10*R.

Routing -- Muskingum
    K_hr = Kirpich Tc of the reach (its channel length and slope), X = 0.2.

The numbers above are the DEFAULTS of :class:`ParameterSet`; they were
specified by the project owner (Lukha basin reference model). To use different
values for a project, build your own ``ParameterSet(...)`` and pass it to
:func:`subbasin_params` / :func:`reach_params` -- nothing is hard-coded.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ParameterSet:
    """All tunable constants in one place (frozen -> safe to share)."""

    # --- Loss: Deficit and Constant ---
    initial_deficit_mm: float = 30.0
    maximum_deficit_mm: float = 50.0
    percolation_rate_mm_hr: float = 0.5
    recovery_factor: float = 1.0

    # --- Baseflow: Linear Reservoir ---
    gw_initial_baseflow_m3s: float = 0.1
    gw_baseflow_fraction: float = 0.4
    gw1_coeff_multiplier: float = 3.0     # GW-1 RC = 3 * R
    gw2_coeff_multiplier: float = 10.0    # GW-2 RC = 10 * R

    # --- Transform: Modified Clark ---
    storage_coeff_ratio: float = 13.0 / 7.0   # from R/(Tc+R) = 0.65

    # --- Routing: Muskingum ---
    muskingum_x: float = 0.2
    # Design timestep the subreach count is tuned for (hourly RP runs).
    muskingum_timestep_hr: float = 1.0
    # HEC-HMS rejects a very small Muskingum K outright (ERROR 41161 "Invalid
    # Muskingum K"), killing the whole compute. Short connector/stub reaches
    # (e.g. a 31 m link with zero drop) legitimately compute K ~ 0.01 hr, so K
    # is floored. Routing over such a stub is negligible either way.
    min_muskingum_k_hr: float = 0.1

    # --- Floors so Kirpich stays defined on sliver subbasins ---
    min_slope: float = 1e-4        # m/m
    min_length_m: float = 30.0     # ~ one DEM cell


DEFAULT_PARAMETERS = ParameterSet()


def kirpich_tc_hr(length_m: float, slope_m_per_m: float,
                  pset: ParameterSet = DEFAULT_PARAMETERS) -> float:
    """Kirpich (1940) time of concentration, in hours.

    Tiny sliver subbasins can come out of delineation with a zero slope or a
    sub-cell flow path; those are floored (``min_slope`` / ``min_length_m``)
    rather than rejected, matching how reach slopes are floored.
    """
    length_m = max(length_m, pset.min_length_m)
    slope_m_per_m = max(slope_m_per_m, pset.min_slope)
    tc_min = 0.0195 * (length_m ** 0.77) * (slope_m_per_m ** -0.385)
    return tc_min / 60.0


def muskingum_steps(k_hr: float, timestep_hr: float | None = None,
                    x: float | None = None,
                    pset: ParameterSet = DEFAULT_PARAMETERS) -> int:
    """Number of Muskingum subreaches that keeps the scheme numerically stable.

    Muskingum is stable only when  2*K_sub*X <= dt <= 2*K_sub*(1-X),  with
    K_sub = K / n subreaches. Splitting a reach into n subreaches shrinks
    K_sub, so n is the smallest value satisfying the UPPER bound
    (2*K_sub*X <= dt), i.e. n = ceil(2*X*K/dt). Reaches whose K is already
    below dt/(2*(1-X)) cannot be fixed by any n >= 1 -- they are simply faster
    than one timestep, and HMS clips their coefficients.
    """
    dt = pset.muskingum_timestep_hr if timestep_hr is None else timestep_hr
    x = pset.muskingum_x if x is None else x
    return max(1, math.ceil(2.0 * x * k_hr / dt))


@dataclass
class SubbasinParams:
    element_name: str
    # loss
    percent_impervious: float
    initial_deficit_mm: float
    maximum_deficit_mm: float
    percolation_rate_mm_hr: float
    # transform
    tc_hr: float
    storage_coeff_hr: float
    # baseflow
    gw1_fraction: float
    gw1_coeff_hr: float
    gw1_initial_m3s: float
    gw2_fraction: float
    gw2_coeff_hr: float
    gw2_initial_m3s: float


@dataclass
class ReachParams:
    element_name: str
    muskingum_k_hr: float
    muskingum_x: float
    muskingum_steps: int


def subbasin_params(
    element_name: str,
    longest_flowpath_m: float,
    basin_slope: float,
    percent_impervious: float,
    pset: ParameterSet = DEFAULT_PARAMETERS,
) -> SubbasinParams:
    """Full loss/transform/baseflow parameter set for one subbasin."""
    tc = kirpich_tc_hr(longest_flowpath_m, basin_slope, pset)
    r = pset.storage_coeff_ratio * tc
    return SubbasinParams(
        element_name=element_name,
        percent_impervious=percent_impervious,
        initial_deficit_mm=pset.initial_deficit_mm,
        maximum_deficit_mm=pset.maximum_deficit_mm,
        percolation_rate_mm_hr=pset.percolation_rate_mm_hr,
        tc_hr=tc,
        storage_coeff_hr=r,
        gw1_fraction=pset.gw_baseflow_fraction,
        gw1_coeff_hr=pset.gw1_coeff_multiplier * r,
        gw1_initial_m3s=pset.gw_initial_baseflow_m3s,
        gw2_fraction=pset.gw_baseflow_fraction,
        gw2_coeff_hr=pset.gw2_coeff_multiplier * r,
        gw2_initial_m3s=pset.gw_initial_baseflow_m3s,
    )


def reach_params(element_name: str, length_m: float, slope: float,
                 pset: ParameterSet = DEFAULT_PARAMETERS) -> ReachParams:
    """Muskingum K, x and subreach count for one reach."""
    k = max(kirpich_tc_hr(length_m, slope, pset), pset.min_muskingum_k_hr)
    return ReachParams(
        element_name=element_name,
        muskingum_k_hr=k,
        muskingum_x=pset.muskingum_x,
        muskingum_steps=muskingum_steps(k, pset=pset),
    )
