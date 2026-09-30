"""
Pure design-storm mathematics (numpy/scipy only -- no files, no GIS), so each
step can be unit-tested and reused outside the pipeline.

Method chain (Regional Index-Rainfall / L-moments, Gumbel, CWC factors, ABM):

    annual-maximum daily rainfall per grid cell
      -> L-moments (Hosking 1990)
      -> regional homogeneity check (H-statistic, Hosking & Wallis 1997)
      -> regional growth curve: pooled normalised L-moments -> Gumbel
      -> RP rainfall per cell = index value (mean annual max) x growth factor
      -> distribute the 24 h depth with CWC hourly incremental factors
      -> re-order with the Alternating Block Method (Chow et al. 1988)

KNOWN SIMPLIFICATIONS (kept faithful to the original scripts; flagged so they
are not mistaken for the full published method):
  * :func:`homogeneity_test` simulates Gaussian L-skewness values (sd 0.15)
    rather than sampling a 4-parameter Kappa distribution, and measures spread
    of t3 instead of L-CV (t) as Hosking & Wallis's V1.  Treat H as a rough
    screen, not a formal test.
  * Only the Gumbel distribution is fitted; no goodness-of-fit (Z-statistic)
    comparison against GEV/GLO etc.
See docs/LITERATURE.md.
"""
from __future__ import annotations

import numpy as np
from scipy import stats

EULER_GAMMA = 0.5772156649


def compute_lmoments(data):
    """L-moments (l1, l2, t3) of a 1-D sample, Hosking (1990) unbiased PWM estimators.

    Returns (L-mean, L-scale, L-skewness); NaNs when fewer than 5 valid values.
    """
    x = np.sort(np.asarray(data, dtype=float)[~np.isnan(data)])
    n = len(x)
    if n < 5:
        return np.nan, np.nan, np.nan

    i = np.arange(1, n + 1)
    b0 = np.mean(x)
    b1 = np.sum((i - 1) / (n - 1) * x) / n
    b2 = np.sum((i - 1) * (i - 2) / ((n - 1) * (n - 2)) * x) / n

    l1 = b0
    l2 = 2 * b1 - b0
    l3 = 6 * b2 - 6 * b1 + b0
    t3 = l3 / l2 if l2 > 0 else 0.0
    return l1, l2, t3


def homogeneity_test(annual_max, basin_mask, n_simulations=500, min_years=10, seed=None):
    """Simplified regional H-statistic (see module docstring).

    H < 1 acceptably homogeneous; 1 <= H < 2 possibly heterogeneous; H >= 2
    definitely heterogeneous.  ``seed`` makes the Monte-Carlo part reproducible.
    """
    n_lats, n_lons = basin_mask.shape
    site_t3, site_n = [], []
    for i in range(n_lats):
        for j in range(n_lons):
            if basin_mask[i, j]:
                series = annual_max[:, i, j]
                valid = series[~np.isnan(series)]
                if len(valid) >= min_years and np.mean(valid) > 0:
                    _, _, t3 = compute_lmoments(valid / np.mean(valid))
                    site_t3.append(t3)
                    site_n.append(len(valid))

    if len(site_t3) < 2:
        print("  Not enough sites for homogeneity test -- assuming homogeneous")
        return 0.0

    site_t3, site_n = np.array(site_t3), np.array(site_n)
    n_total = np.sum(site_n)
    t3_bar = np.sum(site_n * site_t3) / n_total
    v_obs = np.sum(site_n * (site_t3 - t3_bar) ** 2) / n_total

    rng = np.random.default_rng(seed)
    sim_v = []
    for _ in range(n_simulations):
        sim_t3 = rng.normal(t3_bar, 0.15, len(site_n))
        sim_v.append(np.sum(site_n * (sim_t3 - np.mean(sim_t3)) ** 2) / n_total)

    mu_v, sigma_v = np.mean(sim_v), np.std(sim_v)
    return (v_obs - mu_v) / sigma_v if sigma_v > 0 else 0.0


def fit_gumbel_lmoments_regional(annual_max, basin_mask, return_periods, min_years=10):
    """Regional index-rainfall growth curve with a Gumbel fit by L-moments.

    Returns (index_map, growth_factors {RP: factor}, {'loc','scale'}).
    ``return_periods`` is an explicit argument (never a module global) so the
    function is safe to call repeatedly with different configurations.
    """
    _, n_lats, n_lons = annual_max.shape
    index_map = np.full((n_lats, n_lons), np.nan)
    pooled = []

    for i in range(n_lats):
        for j in range(n_lons):
            if basin_mask[i, j]:
                series = annual_max[:, i, j]
                valid = series[~np.isnan(series)]
                if len(valid) >= min_years:
                    mean_val = np.mean(valid)          # the "index" value of the cell
                    index_map[i, j] = mean_val
                    pooled.extend((valid / mean_val).tolist())

    l1, l2, _ = compute_lmoments(np.array(pooled))
    scale = l2 / np.log(2)                 # Gumbel: alpha = l2 / ln 2
    loc = l1 - EULER_GAMMA * scale         # Gumbel: xi = l1 - gamma * alpha

    growth = {rp: float(stats.gumbel_r.ppf(1.0 - 1.0 / rp, loc=loc, scale=scale))
              for rp in return_periods}
    return index_map, growth, {"loc": loc, "scale": scale}


def compute_rp_rainfall(index_map, growth_factors, basin_mask):
    """RP rainfall map per return period = index value x growth factor."""
    out = {}
    valid = basin_mask & ~np.isnan(index_map)
    for rp, gf in growth_factors.items():
        rp_map = np.full_like(index_map, np.nan)
        rp_map[valid] = index_map[valid] * gf
        out[rp] = rp_map
    return out


def alternating_block_method(incremental_values):
    """Alternating Block hyetograph: the peak goes in the centre and the
    remaining values (sorted descending) alternate left / right of it."""
    values = np.sort(incremental_values)[::-1]
    n = len(values)
    hyeto = np.zeros(n)
    center = n // 2
    left, right = center - 1, center + 1
    hyeto[center] = values[0]
    for i in range(1, n):
        if i % 2 != 0:
            if left >= 0:
                hyeto[left] = values[i]
                left -= 1
        elif right < n:
            hyeto[right] = values[i]
            right += 1
    return hyeto


def generate_hourly_hyetograph(rp_rainfall_value, cwc_factors):
    """24 h hyetograph for one cell and RP: depth x hourly factors, ABM-ordered."""
    return alternating_block_method(rp_rainfall_value * np.asarray(cwc_factors))
