"""
Design-storm figures and QA exports.

* :func:`plot_diagnostics`  one summary PNG made right after generation
* :func:`run_analysis`      optional QA pass over already-written per-RP NetCDFs:
  hourly CSV per RP, storm-summary CSVs and five plots.
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.gridspec as gridspec  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402

RP_COLORS = {5: "#4575b4", 10: "#74add1", 25: "#fdae61", 50: "#f46d43", 100: "#d73027"}


def _color(rp):
    return RP_COLORS.get(rp, "#555555")


def _small_multiples(n, ncols, w, h):
    ncols = min(ncols, n)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * w, nrows * h), squeeze=False)
    for k in range(n, nrows * ncols):
        axes[k // ncols][k % ncols].set_visible(False)
    return fig, axes, ncols


def _save(fig, cfg, name):
    path = os.path.join(cfg.output_dir, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")
    return path


# --------------------------------------------------------- summary at generation
def plot_diagnostics(rp_rainfall, hourly_data, cwc_factors, basin_mask, lats, lons, cfg) -> str:
    """RP rainfall maps, CWC factors, sample hyetographs and full profile."""
    rps = cfg.return_periods
    s0 = (cfg.storm_day - 1) * 24
    fig = plt.figure(figsize=(20, 12))
    gs = gridspec.GridSpec(2, len(rps) + 1, figure=fig, hspace=0.4, wspace=0.3)

    vmin = np.nanmin([np.nanmin(rp_rainfall[r]) for r in rps])
    vmax = np.nanmax([np.nanmax(rp_rainfall[r]) for r in rps])
    for k, rp in enumerate(rps):
        ax = fig.add_subplot(gs[0, k])
        im = ax.pcolormesh(lons, lats, np.where(basin_mask, rp_rainfall[rp], np.nan),
                           vmin=vmin, vmax=vmax, cmap="Blues")
        ax.set_title(f"RP {rp} yr\n(mm/day)", fontsize=9)
        plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    ax = fig.add_subplot(gs[0, -1])
    ax.bar(range(1, len(cwc_factors) + 1), cwc_factors, color="steelblue", alpha=0.8)
    ax.set_title(f"CWC Zone {cfg.cwc_zone}\nIncremental Factors", fontsize=9)

    vi, vj = np.where(basin_mask)
    ci, cj = vi[len(vi) // 2], vj[len(vj) // 2]          # a representative in-basin cell
    colors = plt.cm.viridis(np.linspace(0.2, 0.9, len(rps)))
    for k, rp in enumerate(rps):
        ax = fig.add_subplot(gs[1, k])
        hy = hourly_data[rp][s0:s0 + 24, ci, cj]
        ax.bar(range(1, 25), hy, color=colors[k], alpha=0.8)
        ax.set_title(f"Hyetograph RP {rp} yr\nLat:{lats[ci]:.2f} Lon:{lons[cj]:.2f}", fontsize=8)
        ax.text(0.98, 0.95, f"Total={hy.sum():.1f}mm", transform=ax.transAxes,
                ha="right", va="top", fontsize=7)

    ax = fig.add_subplot(gs[1, -1])
    for k, rp in enumerate(rps):
        ax.plot(hourly_data[rp][:, ci, cj], label=f"RP {rp}", color=colors[k], lw=1)
    ax.axvspan(s0, s0 + 24, alpha=0.1, color="red", label=f"Storm Day {cfg.storm_day}")
    ax.set_title("Full Profile\n(all RPs)", fontsize=9)
    ax.legend(fontsize=6)

    plt.suptitle("Design Storm NetCDF - Diagnostic Summary\n"
                 f"CWC Zone {cfg.cwc_zone} | Regional Index Rainfall | L-moments Gumbel | Alternating Block",
                 fontsize=11, fontweight="bold")
    return _save(fig, cfg, "design_storm_diagnostics.png")


# ------------------------------------------------------------- optional QA pass
def _load_all_rp(cfg):
    datasets = {}
    for rp in cfg.return_periods:
        path = cfg.output_netcdf_path(rp)
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}\nRun the pipeline for this RP first.")
        datasets[rp] = xr.open_dataset(path)
    ds0 = datasets[cfg.return_periods[0]]
    lats, lons = ds0[cfg.lat_var].values, ds0[cfg.lon_var].values
    times = pd.to_datetime(ds0[cfg.time_var].values)
    mask = ~np.all(np.isnan(ds0[cfg.rain_var].values), axis=0)
    s0 = (cfg.storm_day - 1) * 24
    cells = [(i, j, lats[i], lons[j]) for i in range(len(lats)) for j in range(len(lons)) if mask[i, j]]
    return datasets, lats, lons, times, mask, cells, s0, s0 + 24


def export_csvs(datasets, times, cells, s0, s1, cfg):
    """Hourly CSV per RP + storm summary (total, peak, peak hour, centroid hour)."""
    for rp, ds in datasets.items():
        rain = ds[cfg.rain_var].values
        rec = {f"lat{la:.2f}_lon{lo:.2f}": rain[:, i, j] for i, j, la, lo in cells}
        df = pd.DataFrame(rec, index=times)
        df.index.name = "datetime"
        df.insert(0, "day", [f"Day{(k // 24) + 1}" for k in range(len(times))])
        df.to_csv(os.path.join(cfg.output_dir, f"timeseries_RP{rp}.csv"))

    rows = []
    hours = np.arange(1, 25)
    for rp, ds in datasets.items():
        storm = ds[cfg.rain_var].values[s0:s1]
        for i, j, la, lo in cells:
            s = storm[:, i, j]
            total = np.nansum(s)
            rows.append({"lat": la, "lon": lo, "return_period_yr": rp,
                         "storm_total_mm": round(total, 2),
                         "peak_intensity_mm_hr": round(np.nanmax(s), 2),
                         "peak_hour_in_storm": int(np.nanargmax(s)) + 1,
                         "centroid_hour": round(np.nansum(s * hours) / total, 2) if total > 0 else np.nan})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(cfg.output_dir, "storm_summary_all_rp.csv"), index=False)
    pivot = df.pivot_table(index=["lat", "lon"], columns="return_period_yr", values="storm_total_mm")
    pivot.columns = [f"RP{c}_total_mm" for c in pivot.columns]
    pivot.reset_index().to_csv(os.path.join(cfg.output_dir, "storm_total_pivot.csv"), index=False)
    return df, pivot


def _plot_basin_avg(datasets, times, cells, s0, s1, cfg):
    fig, ax = plt.subplots(figsize=(14, 5))
    for rp, ds in datasets.items():
        rain = ds[cfg.rain_var].values
        avg = np.array([np.nanmean([rain[t, i, j] for i, j, _, _ in cells]) for t in range(rain.shape[0])])
        ax.plot(times, avg, color=_color(rp), linewidth=1.8, label=f"RP {rp} yr")
    ax.axvspan(times[s0], times[s1 - 1], alpha=0.12, color="red", label=f"Storm Day {cfg.storm_day}")
    ax.set_ylabel("Rainfall (mm/hr)")
    ax.set_title(f"Basin-Average Design Storm - All Return Periods (CWC Zone {cfg.cwc_zone})")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    _save(fig, cfg, "plot_basin_avg_timeseries.png")


def _plot_hyetographs(datasets, cells, s0, s1, cfg):
    hours = np.arange(1, 25)
    for rp, ds in datasets.items():
        storm = ds[cfg.rain_var].values[s0:s1]
        fig, axes, nc_ = _small_multiples(len(cells), 4, 4, 3.5)
        for k, (i, j, la, lo) in enumerate(cells):
            ax = axes[k // nc_][k % nc_]
            s = storm[:, i, j]
            ax.bar(hours, s, color=_color(rp), alpha=0.85)
            ax.bar(hours[int(np.nanargmax(s))], np.nanmax(s), color="darkred")   # peak hour highlighted
            ax.set_title(f"Lat {la:.2f}N Lon {lo:.2f}E\nTotal = {np.nansum(s):.1f} mm", fontsize=8)
        fig.suptitle(f"Storm Day Hyetographs - RP {rp} yr", fontweight="bold")
        fig.tight_layout()
        _save(fig, cfg, f"plot_hyetographs_RP{rp}.png")


def _plot_spatial(datasets, lats, lons, mask, s0, s1, cfg):
    rps = cfg.return_periods
    fig, axes = plt.subplots(2, len(rps), figsize=(len(rps) * 4, 7), squeeze=False)
    tot, pk = {}, {}
    for rp, ds in datasets.items():
        storm = ds[cfg.rain_var].values[s0:s1]
        tot[rp], pk[rp] = np.nansum(storm, axis=0), np.nanmax(storm, axis=0)
        tot[rp][~mask] = np.nan
        pk[rp][~mask] = np.nan
    lim = lambda d: (np.nanmin(list(d.values())), np.nanmax(list(d.values())))  # noqa: E731
    (t0, t1), (p0, p1) = lim(tot), lim(pk)
    for c, rp in enumerate(rps):
        im = axes[0][c].pcolormesh(lons, lats, tot[rp], vmin=t0, vmax=t1, cmap="YlOrRd", shading="auto")
        axes[0][c].set_title(f"RP {rp} yr\nStorm Total (mm)", fontsize=9)
        plt.colorbar(im, ax=axes[0][c], fraction=0.046, pad=0.04)
        im = axes[1][c].pcolormesh(lons, lats, pk[rp], vmin=p0, vmax=p1, cmap="Blues", shading="auto")
        axes[1][c].set_title(f"RP {rp} yr\nPeak (mm/hr)", fontsize=9)
        plt.colorbar(im, ax=axes[1][c], fraction=0.046, pad=0.04)
    fig.tight_layout()
    _save(fig, cfg, "plot_spatial_maps.png")


def _plot_growth(datasets, cells, s0, s1, cfg):
    rps = cfg.return_periods
    fig, axes, nc_ = _small_multiples(len(cells), 4, 3.5, 3)
    for k, (i, j, la, lo) in enumerate(cells):
        ax = axes[k // nc_][k % nc_]
        ax.plot(rps, [np.nansum(ds[cfg.rain_var].values[s0:s1, i, j]) for ds in datasets.values()],
                "o-", color="steelblue", linewidth=2)
        ax.set_xscale("log")
        ax.set_xticks(rps)
        ax.set_xticklabels([str(r) for r in rps], fontsize=7)
        ax.set_title(f"Lat {la:.2f} Lon {lo:.2f}", fontsize=8)
        ax.grid(True, alpha=0.3, which="both")
    fig.suptitle("Return Period Growth Curve - Storm Total per Grid", fontweight="bold")
    fig.tight_layout()
    _save(fig, cfg, "plot_rp_growth_per_grid.png")


def _plot_full_ts(datasets, times, cells, s0, s1, cfg):
    fig, axes, nc_ = _small_multiples(len(cells), 3, 5.5, 3.5)
    for k, (i, j, la, lo) in enumerate(cells):
        ax = axes[k // nc_][k % nc_]
        for rp, ds in datasets.items():
            ax.plot(times, ds[cfg.rain_var].values[:, i, j], color=_color(rp), lw=1.4, label=f"RP {rp}yr")
        ax.axvspan(times[s0], times[s1 - 1], alpha=0.1, color="red")
        ax.set_title(f"Lat {la:.2f}N Lon {lo:.2f}E", fontsize=9)
        ax.legend(fontsize=6, loc="upper right")
    fig.suptitle("Full Hourly Design Storm per Grid (shaded = storm day)", fontweight="bold")
    fig.tight_layout()
    _save(fig, cfg, "plot_full_timeseries_per_grid.png")


def run_analysis(cfg):
    """Optional QA over an already-completed run's NetCDFs: 2 CSV sets + 5 plots."""
    datasets, lats, lons, times, mask, cells, s0, s1 = _load_all_rp(cfg)
    print(f"QA: {len(cells)} basin cells, storm hours {s0}-{s1 - 1}")
    summary, pivot = export_csvs(datasets, times, cells, s0, s1, cfg)
    _plot_basin_avg(datasets, times, cells, s0, s1, cfg)
    _plot_hyetographs(datasets, cells, s0, s1, cfg)
    _plot_spatial(datasets, lats, lons, mask, s0, s1, cfg)
    _plot_growth(datasets, cells, s0, s1, cfg)
    _plot_full_ts(datasets, times, cells, s0, s1, cfg)
    return summary, pivot
