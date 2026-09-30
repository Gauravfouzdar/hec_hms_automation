"""
Read HMS output time series from ``Run_<tag>.dss`` and aggregate to 10-daily
(dekad) values, one Excel workbook per project.

DSS is read with ``pydsstools`` (pip install pydsstools).  pydsstools can NOT
write gridded records -- gridded precipitation is written by Vortex
(see vortex/); the two tools are not interchangeable.

Dekad convention: 1 = days 1-10, 2 = days 11-20, 3 = day 21 to month end.  The
value reported is the MEAN of the daily series over the dekad (the dekad
mean-flow convention used for water-availability work).

Output layout: one workbook per project, one sheet per run, rows = dekads,
columns = subbasin elements (live names read from the .basin file).

DSS pathname anatomy of an HMS result record::

    //SUBBASIN-1/FLOW/31Dec1980 - 30Dec2018/1DAY/RUN:RUN 1/
      A  B(element) C(variable) D(date block) E(interval) F(run)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..hmsfiles.basin_reader import read_basin

VARIABLE = "FLOW"
BASELINE_RUN = "1"


def _hecdss():
    """Import pydsstools lazily so the rest of the package works without it."""
    try:
        from pydsstools.heclib.dss import HecDss
    except ImportError as exc:
        raise ImportError("Reading DSS needs pydsstools:  pip install pydsstools") from exc
    return HecDss


@dataclass
class RunSpec:
    """A run to extract: enough to locate the DSS and window the read."""
    tag: str          # sheet name / Run_<tag>.dss
    fpart: str        # DSS F-part, e.g. "RUN:Run 1"
    start: str        # read_ts window start
    end: str          # read_ts window end
    interval: str     # DSS E-part, e.g. "1Day"


def scenario_runs(scenarios) -> list[RunSpec]:
    """RunSpecs for scenario runs (RP / climate) built by build-scenarios."""
    return [RunSpec(tag=sc.tag, fpart=f"RUN:Run {sc.tag}",
                    start=f"{sc.start_date.replace(' ', '')} 00:00:00",
                    end=f"{sc.end_date.replace(' ', '')} 24:00:00",
                    interval="1Hour" if sc.interval_min == 60 else "1Day")
            for sc in scenarios]


def baseline_run(project: Path, variable: str = VARIABLE,
                 label: str = BASELINE_RUN) -> RunSpec | None:
    """RunSpec for ``Run <label>``, derived by inspecting its DSS directly.

    A project's original run predates any scenario config and its date range
    differs per basin, so the window comes from the D-part year blocks and the
    E-part interval actually present.
    """
    dss = project / f"Run_{label}.dss"
    if not dss.exists():
        return None
    fpart = f"RUN:Run {label}"
    fid = _hecdss().Open(str(dss))
    try:
        paths = fid.search_path("/*/*/*/*/*/*/") or []
    finally:
        fid.close()

    recs = [p.split("/") for p in paths]
    recs = [r for r in recs if len(r) > 6 and r[3].upper() == variable.upper() and r[6] == fpart]
    if not recs:
        return None

    years = pd.to_datetime(sorted({r[4] for r in recs}), format="%d%b%Y").year
    intervals = {r[5] for r in recs}
    interval = "1Day" if "1Day" in intervals else sorted(intervals)[0]   # prefer the daily block
    return RunSpec(tag=f"Run {label}", fpart=fpart,
                   start=f"01Jan{years.min()} 00:00:00",
                   end=f"31Dec{years.max()} 24:00:00", interval=interval)


def dekad_frame(times, values, nodata) -> pd.DataFrame:
    """Tidy frame (d, v, year, month, dekad) from pydsstools arrays.

    Two pydsstools gotchas handled here:
      * ``ts.times`` holds HecTime objects (``str()`` is a repr) -> ``.datetime()``.
      * ``ts.values`` can be a VIEW onto a reused buffer -> ``np.array(...)`` COPIES it.
    HMS stamps a daily period-average at 24:00, i.e. midnight of the NEXT day,
    so one second is subtracted so a value belongs to the day it describes.
    """
    stamps = pd.to_datetime([t.datetime() for t in times])
    df = pd.DataFrame({"d": stamps, "v": np.array(values, dtype=float)})   # copy, not a view
    df = df[~np.asarray(nodata, dtype=bool)]
    df = df[np.isfinite(df["v"])]
    if df.empty:
        return df
    d = df["d"] - pd.Timedelta(seconds=1)
    return df.assign(year=d.dt.year, month=d.dt.month,
                     dekad=np.where(d.dt.day <= 10, 1, np.where(d.dt.day <= 20, 2, 3)))


def extract_project(project: Path, runs: list[RunSpec], variable: str) -> dict[str, pd.DataFrame]:
    """{run tag: DataFrame(Year, Month, Dekad, <subbasin columns>)} for one project."""
    basin = read_basin(sorted(project.glob("*.basin"))[0])
    sub_names = [el.name for el in basin.subbasins]
    HecDss = _hecdss()

    sheets: dict[str, pd.DataFrame] = {}
    for run in runs:
        dss = project / f"Run_{run.tag.replace('Run ', '')}.dss"
        if not dss.exists():
            continue
        series: dict[str, pd.Series] = {}
        fid = HecDss.Open(str(dss))
        try:
            for name in sub_names:
                path = f"//{name}/{variable}//{run.interval}/{run.fpart}/"
                try:
                    ts = fid.read_ts(path, window=(run.start, run.end), trim_missing=True)
                except Exception:
                    continue      # element has no such record in this run
                df = dekad_frame(ts.times, ts.values, ts.nodata)
                if not df.empty:
                    series[name] = df.groupby(["year", "month", "dekad"])["v"].mean()
        finally:
            fid.close()

        if series:
            out = pd.DataFrame(series)
            out.index = pd.MultiIndex.from_tuples(out.index, names=["Year", "Month", "Dekad"])
            sheets[run.tag] = out.sort_index().round(4).reset_index()
    return sheets


def extract_10daily(parent: str | Path, out_dir: str | Path, variable: str = VARIABLE,
                    only: str | None = None, scenarios=None) -> None:
    """Write ``<project>_10daily_<variable>.xlsx`` for every HMS project under
    ``parent``.  ``scenarios`` (list of hmsfiles Scenario) selects the RP/climate
    runs; ``None`` extracts the baseline Run 1 only."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    projects = sorted(p for p in Path(parent).iterdir()
                      if p.is_dir() and list(p.glob("*.basin")) and (only is None or p.name == only))
    which = "RP + climate scenarios" if scenarios else f"Run {BASELINE_RUN} only"
    print(f"Extracting 10-daily {variable} ({which}) for {len(projects)} projects -> {out_path}\n")

    fixed = scenario_runs(scenarios) if scenarios else None
    for proj in projects:
        try:
            runs = fixed or [r for r in [baseline_run(proj, variable)] if r]
            if not runs:
                print(f"{proj.name:22s} SKIP  no Run {BASELINE_RUN} records")
                continue
            sheets = extract_project(proj, runs, variable)
        except Exception as e:
            print(f"{proj.name:22s} ERROR {type(e).__name__}: {e}")
            continue
        if not sheets:
            print(f"{proj.name:22s} SKIP  no run output found")
            continue
        xlsx = out_path / f"{proj.name}_10daily_{variable.lower()}.xlsx"
        with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
            for tag, df in sheets.items():
                df.to_excel(xw, sheet_name=tag[:31], index=False)   # Excel sheet names max 31 chars
        ncols = max(len(d.columns) - 3 for d in sheets.values())
        span = "; ".join(f"{t}: {len(d)} dekads {d.Year.min()}-{d.Year.max()}" for t, d in sheets.items())
        print(f"{proj.name:22s} OK  {ncols} subbasins  [{span}]")
    print("\nDone.")
