"""
Diagnostic plots for the clipped CMIP6 scenarios.

Gridded cells under the buffered polygon are drawn with pcolormesh / per-cell
statistics.  No cartopy on purpose: it bloats a frozen bundle and downloads
Natural Earth data at runtime (breaks offline machines); the basin + buffered
outlines from the user's own shapefile provide the map context.

All plots operate on the in-memory ``clip`` dicts made by ``climate.clip``.
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ..climate.config import SCN_COLOR, SCN_LABEL, ClimateRunConfig  # noqa: E402


def _area_mean_series(clip) -> pd.Series:
    """Daily area-mean over in-polygon cells."""
    return pd.Series(np.nanmean(clip["data"], axis=(1, 2)), index=clip["times"])


def _overlay_boundaries(ax, basin_gdf, buffered_gdf):
    buffered_gdf.boundary.plot(ax=ax, color="tab:blue", linewidth=1.2, linestyle="--")
    basin_gdf.boundary.plot(ax=ax, color="k", linewidth=1.2)


def _cell_edges(centers):
    """Cell-edge coordinates for pcolormesh from 1-D centre coordinates."""
    centers = np.asarray(centers, dtype=float)
    step = 0.25 if len(centers) == 1 else np.diff(centers).mean()
    return np.concatenate([centers - step / 2, [centers[-1] + step / 2]])


def _panel_grid(n: int, w: float, h: float, **kw):
    """Create an (nrow x ncol) panel figure for n scenarios; returns fig, flat axes."""
    ncol = min(n, 3)
    nrow = (n + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(w * ncol, h * nrow),
                             squeeze=False, constrained_layout=True, **kw)
    return fig, axes.flatten()


def _save(fig, cfg, name):
    out = os.path.join(cfg.output_dir, name)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Plot: {out}")
    return out


def _annotate_cells(ax, clip, values, fmt):
    for i, la in enumerate(clip["lats"]):
        for j, lo in enumerate(clip["lons"]):
            if clip["mask"][i, j] and not np.isnan(values[i, j]):
                ax.text(lo, la, fmt.format(values[i, j]), ha="center", va="center", fontsize=7,
                        bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.6))


def plot_spatial_mean_map(cfg: ClimateRunConfig, clips: dict, basin_gdf, buffered_gdf) -> str:
    """1. Climatological-mean precipitation map, one panel per scenario."""
    scenarios = list(clips)
    fig, axes = _panel_grid(len(scenarios), 6, 5)
    means = {s: np.nanmean(clips[s]["data"], axis=0) for s in scenarios}
    vmin = min(np.nanmin(m) for m in means.values())
    vmax = max(np.nanmax(m) for m in means.values())

    pcm = None
    for k, s in enumerate(scenarios):
        ax, clip = axes[k], clips[s]
        pcm = ax.pcolormesh(_cell_edges(clip["lons"]), _cell_edges(clip["lats"]), means[s],
                            cmap="YlGnBu", vmin=vmin, vmax=vmax, shading="flat")
        _overlay_boundaries(ax, basin_gdf, buffered_gdf)
        _annotate_cells(ax, clip, means[s], "{:.1f}")
        ax.set_title(SCN_LABEL.get(s, s), fontsize=12, fontweight="bold", color=SCN_COLOR.get(s, "k"))
        ax.set_xlabel("Lon")
        ax.set_ylabel("Lat")
    for k in range(len(scenarios), len(axes)):
        axes[k].set_visible(False)

    fig.colorbar(pcm, ax=axes[:len(scenarios)].tolist(), orientation="horizontal",
                 fraction=0.04, pad=0.05, shrink=0.6).set_label("Mean precipitation [mm/day]")
    fig.suptitle(f"Climatological Mean Precipitation - {cfg.basin_name} (buffered area)",
                 fontsize=14, fontweight="bold")
    return _save(fig, cfg, "spatial_mean_map.png")


def plot_timeseries_annual(cfg: ClimateRunConfig, clips: dict) -> str:
    """2. Annual area-mean series, all scenarios overlaid (also writes annual_summary.csv)."""
    fig, ax = plt.subplots(figsize=(12, 5))
    annual_all = {}
    for s, clip in clips.items():
        annual = _area_mean_series(clip).resample("YE").mean()
        annual_all[s] = pd.Series(annual.values, index=annual.index.year)
        ax.plot(annual.index.year, annual.values, label=SCN_LABEL.get(s, s),
                color=SCN_COLOR.get(s, "k"), linewidth=1.6)
        smooth = annual.rolling(10, center=True, min_periods=3).mean()   # 10-yr running mean
        ax.plot(smooth.index.year, smooth.values, color=SCN_COLOR.get(s, "k"), linewidth=3, alpha=0.45)

    ax.set_xlabel("Year", fontsize=11)
    ax.set_ylabel("Precipitation [mm/day]", fontsize=11)
    ax.set_title(f"Annual Mean Precipitation - {cfg.basin_name} (buffered-area average)",
                 fontsize=13, fontweight="bold")
    ax.legend(fontsize=10, framealpha=0.9)
    ax.grid(True, linestyle="--", alpha=0.4)
    fig.tight_layout()
    out = _save(fig, cfg, "timeseries_annual.png")

    summary = pd.DataFrame(annual_all)
    summary.index.name = "year"
    path = os.path.join(cfg.output_dir, "annual_summary.csv")
    summary.to_csv(path)
    print(f"  Annual summary CSV: {path}")
    return out


def plot_monthly_climatology(cfg: ClimateRunConfig, clips: dict) -> str:
    """3. Monthly climatology bars (mean +- std across cells), one panel per scenario."""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    scenarios = list(clips)
    fig, axes = _panel_grid(len(scenarios), 5, 4, sharey=True)

    for k, s in enumerate(scenarios):
        ax, clip, mask = axes[k], clips[s], clips[s]["mask"]
        cells = {(i, j): pd.Series(clip["data"][:, i, j], index=clip["times"])
                 for i in range(mask.shape[0]) for j in range(mask.shape[1]) if mask[i, j]}
        clim = pd.DataFrame({c: v.groupby(v.index.month).mean() for c, v in cells.items()})
        mean, std = clim.mean(axis=1), clim.std(axis=1)

        ax.bar(range(1, 13), mean.values, color=SCN_COLOR.get(s, "#888"), alpha=0.85,
               edgecolor="k", linewidth=0.5)
        ax.errorbar(range(1, 13), mean.values, yerr=std.values, fmt="none", color="k",
                    linewidth=1.2, capsize=3)
        ax.set_xticks(range(1, 13))
        ax.set_xticklabels(months, fontsize=8)
        ax.set_title(SCN_LABEL.get(s, s), fontsize=11, fontweight="bold", color=SCN_COLOR.get(s, "k"))
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.set_ylabel("mm/day", fontsize=9)
    for k in range(len(scenarios), len(axes)):
        axes[k].set_visible(False)

    fig.suptitle(f"Monthly Climatology - Precipitation, {cfg.basin_name}\n"
                 f"(mean +/- std across buffered-area cells)", fontsize=13, fontweight="bold")
    return _save(fig, cfg, "monthly_climatology.png")


def plot_raster_heatmaps(cfg: ClimateRunConfig, clips: dict) -> list:
    """4. Monthly-mean heatmap (time x cell) per scenario."""
    outs = []
    for s, clip in clips.items():
        mask, lats, lons = clip["mask"], clip["lats"], clip["lons"]
        labels, cols = [], []
        for i in range(mask.shape[0]):
            for j in range(mask.shape[1]):
                if mask[i, j]:
                    labels.append(f"lat{lats[i]:.2f}_lon{lons[j]:.2f}")
                    cols.append(clip["data"][:, i, j])

        df_m = pd.DataFrame(np.array(cols).T, index=clip["times"], columns=labels).resample("ME").mean()
        fig, ax = plt.subplots(figsize=(max(14, len(df_m) // 12), max(4, len(labels) * 0.35)))
        img = ax.imshow(df_m.values.T, aspect="auto", origin="lower", cmap="YlGnBu",
                        interpolation="nearest")
        jan_pos = [i for i, d in enumerate(df_m.index) if d.month == 1]
        jan_lab = [str(d.year) for d in df_m.index if d.month == 1]
        ax.set_xticks(jan_pos[::5])
        ax.set_xticklabels(jan_lab[::5], rotation=45, ha="right", fontsize=8)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=7)
        ax.set_xlabel("Time (monthly mean)", fontsize=11)
        ax.set_ylabel("Grid cell", fontsize=11)
        ax.set_title(f"Precipitation [mm/day] - {SCN_LABEL.get(s, s)} (monthly mean)",
                     fontsize=12, fontweight="bold", color=SCN_COLOR.get(s, "k"))
        fig.colorbar(img, ax=ax, fraction=0.025, pad=0.02, label="mm/day")
        fig.tight_layout()
        outs.append(_save(fig, cfg, f"heatmap_{s}.png"))
    return outs


def plot_change_signal(cfg: ClimateRunConfig, clips: dict, basin_gdf, buffered_gdf):
    """5. Change signal: end-of-record 30-yr mean of each future scenario minus the
    historical reference climatology (cfg.ref_start..ref_end)."""
    if "historical" not in clips:
        print("  Change-signal plot skipped: no historical scenario provided.")
        return None
    future = [s for s in clips if s != "historical"]
    if not future:
        print("  Change-signal plot skipped: no future scenario provided.")
        return None

    hist = clips["historical"]
    yrs = hist["times"].year
    ref = (yrs >= cfg.ref_start) & (yrs <= cfg.ref_end)
    if not ref.any():
        print(f"  Change-signal plot skipped: historical file has no data in "
              f"reference period {cfg.ref_start}-{cfg.ref_end}.")
        return None
    hist_clim = np.nanmean(hist["data"][ref], axis=0)

    fig, axes = plt.subplots(1, len(future), figsize=(5.5 * len(future), 5),
                             squeeze=False, constrained_layout=True)
    axes = axes.flatten()
    for k, s in enumerate(future):
        ax, clip = axes[k], clips[s]
        fy = clip["times"].year
        fut_mean = np.nanmean(clip["data"][fy >= (fy.max() - 29)], axis=0)

        if fut_mean.shape != hist_clim.shape:      # grids may differ between files
            ax.text(0.5, 0.5, "Grid mismatch\nvs historical", ha="center", va="center",
                    transform=ax.transAxes)
        else:
            delta = fut_mean - hist_clim
            maxd = np.nanmax(np.abs(delta)) or 1e-9
            norm = mcolors.TwoSlopeNorm(vmin=-maxd, vcenter=0, vmax=maxd)
            pcm = ax.pcolormesh(_cell_edges(clip["lons"]), _cell_edges(clip["lats"]), delta,
                                cmap="BrBG", norm=norm, shading="flat")
            _overlay_boundaries(ax, basin_gdf, buffered_gdf)
            _annotate_cells(ax, clip, delta, "{:+.2f}")
            fig.colorbar(pcm, ax=ax, orientation="horizontal", pad=0.06, shrink=0.8,
                         label="Delta precipitation [mm/day]")
        ax.set_title(f"{SCN_LABEL.get(s, s)}\nvs Historical ({cfg.ref_start}-{cfg.ref_end})",
                     fontsize=11, fontweight="bold", color=SCN_COLOR.get(s, "k"))

    fig.suptitle("Change Signal - Precipitation\n"
                 "(future end-of-record 30-yr mean - historical reference climatology)",
                 fontsize=13, fontweight="bold")
    return _save(fig, cfg, "change_signal.png")


def generate_all_plots(cfg: ClimateRunConfig, clips: dict, basin_gdf, buffered_gdf):
    """Make every climate diagnostic plot."""
    print("\n[PLOTS] Generating diagnostic plots...")
    plot_spatial_mean_map(cfg, clips, basin_gdf, buffered_gdf)
    plot_timeseries_annual(cfg, clips)
    plot_monthly_climatology(cfg, clips)
    plot_raster_heatmaps(cfg, clips)
    plot_change_signal(cfg, clips, basin_gdf, buffered_gdf)
