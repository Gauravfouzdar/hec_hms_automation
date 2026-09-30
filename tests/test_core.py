"""Tests for the pure-logic core (no GIS stack, no HEC software, no network)."""
import ast
import re
from datetime import datetime, timedelta

import numpy as np
import pytest

from hec_hms_automation.hmsfiles import basin_reader, parser
from hec_hms_automation.hmsfiles.basin_writer import update_percent_impervious, write_basin
from hec_hms_automation.hmsfiles.scenario_writer import Scenario, build_project
from hec_hms_automation.hmsfiles.run_writer import build_runs
from hec_hms_automation.hydrology import design_storm as ds
from hec_hms_automation.hydrology.parameters import (DEFAULT_PARAMETERS, ParameterSet,
                                                     kirpich_tc_hr, muskingum_steps,
                                                     reach_params, subbasin_params)
from hec_hms_automation.vortex import jython_templates as jt

BASIN = """Basin: Test
     Unit System: Metric
End:

Subbasin: SB1
     Area: 10.0
     Downstream: R1
     LossRate: Deficit Constant
     Percent Impervious Area: 0
     Transform: Modified Clark
     Mod Clark Method: Specified
     Baseflow: Linear Reservoir
     Discretization: None
End:

Reach: R1
     Downstream: Sink-1
     Route: Muskingum
     Initial Variable: Combined Inflow
End:

Sink: Sink-1
     Computation Point: Yes
End:
"""


def test_kirpich_matches_formula():
    expected = 0.0195 * 5000 ** 0.77 * 0.02 ** -0.385 / 60
    assert kirpich_tc_hr(5000, 0.02) == pytest.approx(expected)


def test_kirpich_floors_degenerate_inputs():
    assert kirpich_tc_hr(0, 0) == kirpich_tc_hr(DEFAULT_PARAMETERS.min_length_m,
                                                DEFAULT_PARAMETERS.min_slope)


def test_subbasin_params_relations():
    p = subbasin_params("S", 8000, 0.05, 1.5)
    assert p.storage_coeff_hr == pytest.approx(13 / 7 * p.tc_hr)
    assert p.gw1_coeff_hr == pytest.approx(3 * p.storage_coeff_hr)
    assert p.gw2_coeff_hr == pytest.approx(10 * p.storage_coeff_hr)
    assert p.percent_impervious == 1.5


def test_custom_parameter_set_is_used():
    p = subbasin_params("S", 8000, 0.05, 0, ParameterSet(initial_deficit_mm=10, gw_baseflow_fraction=0.7))
    assert p.initial_deficit_mm == 10 and p.gw1_fraction == 0.7


def test_reach_k_floor_and_steps():
    # 30 m on a steep 0.5 slope -> Kirpich K ~ 0.006 hr, far below the floor
    assert kirpich_tc_hr(30, 0.5) < DEFAULT_PARAMETERS.min_muskingum_k_hr
    r = reach_params("R", 30, 0.5)
    assert r.muskingum_k_hr == DEFAULT_PARAMETERS.min_muskingum_k_hr
    assert muskingum_steps(5.0, 1.0, 0.2) == 2       # ceil(2*0.2*5/1)


def test_parse_and_read_basin(tmp_path):
    f = tmp_path / "Basin_1.basin"
    f.write_text(BASIN)
    blocks = parser.parse_blocks(f)
    assert [b.block_type for b in blocks] == ["Basin", "Subbasin", "Reach", "Sink"]
    s = basin_reader.read_basin(f)
    assert s.subbasins[0].area_km2 == 10.0
    assert basin_reader.fill_state(s) == "skeleton"
    assert "Time of Concentration" in basin_reader.missing_params(s.subbasins[0])


def test_write_basin_fills_and_is_idempotent(tmp_path):
    f = tmp_path / "Basin_1.basin"
    f.write_text(BASIN)
    sp = {"SB1": subbasin_params("SB1", 8000, 0.05, 2.0)}
    rp = {"R1": reach_params("R1", 3000, 0.01)}
    write_basin(f, sp, rp, "Basin_1.sqlite", 32646, 2000.0)
    once = f.read_text()
    assert basin_reader.fill_state(basin_reader.read_basin(f)) == "filled"
    write_basin(f, sp, rp, "Basin_1.sqlite", 32646, 2000.0)
    assert f.read_text() == once, "writer must be idempotent"
    assert len(list(tmp_path.glob("*.bak-*"))) >= 1, "a timestamped backup must be kept"


def test_update_percent_impervious_touches_only_that_line(tmp_path):
    f = tmp_path / "Basin_1.basin"
    f.write_text(BASIN)
    before = f.read_text().splitlines()
    changed = update_percent_impervious(f, {"SB1": 7.25})
    after = f.read_text().splitlines()
    assert changed == {"SB1": ("0", "7.25")}
    diff = [(a, b) for a, b in zip(before, after) if a != b]
    assert len(diff) == 1 and "7.25" in diff[0][1]


def _hms_project(tmp_path):
    (tmp_path / "P.hms").write_text(
        "Project: P\n     Version: 4.13\nEnd:\n\nBasin: Basin 1\n     FileName: Basin_1.basin\nEnd:\n")
    return tmp_path


def _scenario(tag="RP5", interval=60):
    return Scenario(tag, "C:/x.dss", "/A/B/PRECIPITATION/01JAN2024:0000/01JAN2024:0100/ts/",
                    "01 January 2024", "00:00", "10 January 2024", "24:00", interval)


DEFAULTS = {"version": "4.13", "unit_system": "Metric", "timezone_id": "Asia/Calcutta",
            "timezone_gmt_offset_ms": 19800000}


def test_build_project_and_runs_preserve_and_replace(tmp_path):
    proj = _hms_project(tmp_path)
    assert build_project(proj, [_scenario("RP5")], DEFAULTS).startswith("OK")
    assert build_runs(proj, [_scenario("RP5")]).startswith("OK")
    build_project(proj, [_scenario("RP10")], DEFAULTS)
    build_runs(proj, [_scenario("RP10")])
    build_project(proj, [_scenario("RP5")], DEFAULTS)
    build_runs(proj, [_scenario("RP5")])
    run_names = [b.name for b in parser.parse_blocks(proj / "P.run") if b.block_type == "Run"]
    assert sorted(run_names) == ["Run RP10", "Run RP5"]
    grid_names = [b.name for b in parser.parse_blocks(proj / "P.grid") if b.block_type == "Grid"]
    assert sorted(grid_names) == ["Grid RP10", "Grid RP5"]
    hms = (proj / "P.hms").read_text()
    assert hms.count("Precipitation: Met RP5") == 1 and "Control: Control RP10" in hms


def test_lmoments_known_sample():
    l1, l2, t3 = ds.compute_lmoments(np.array([1.0, 2, 3, 4, 5, 6, 7, 8, 9, 10]))
    assert l1 == pytest.approx(5.5)
    # l2 = half the mean absolute difference over distinct pairs = (n+1)/6 for 1..n
    assert l2 == pytest.approx(11 / 6)
    assert t3 == pytest.approx(0.0, abs=1e-9)          # symmetric sample -> zero L-skewness


def test_alternating_block_peak_centre_and_total_preserved():
    inc = np.array([1.0, 5, 2, 8, 3, 1, 1, 2, 4, 6, 2, 1])
    h = ds.alternating_block_method(inc)
    assert h.sum() == pytest.approx(inc.sum())
    assert h[len(inc) // 2] == inc.max()
    assert sorted(h) == sorted(inc)


def test_gumbel_growth_curve_increases_with_rp():
    rng = np.random.default_rng(1)
    am = rng.gumbel(100, 20, size=(30, 3, 3))
    mask = np.ones((3, 3), bool)
    idx, growth, g = ds.fit_gumbel_lmoments_regional(am, mask, [5, 10, 50, 100])
    vals = [growth[r] for r in (5, 10, 50, 100)]
    assert vals == sorted(vals) and vals[0] > 1.0


def test_homogeneity_reproducible_with_seed():
    rng = np.random.default_rng(2)
    am = rng.gumbel(100, 20, size=(30, 3, 3))
    mask = np.ones((3, 3), bool)
    assert ds.homogeneity_test(am, mask, seed=7) == ds.homogeneity_test(am, mask, seed=7)


def test_jython_template_has_no_fstrings_and_paths_are_posix():
    job = jt.VortexJob("t", r"E:\a b\x.nc", r"E:\o\raw.dss", r"E:\o\fin.dss", r"E:\s\b.shp", "My_Basin")
    text = jt.build_import_shift_script([job], "UTM46N", "rain", 24)
    ast.parse(text.replace("\r", ""))
    assert "E:/a b/x.nc" in text
    # Jython 2.7 has no f-strings: no f"..." / f'...' literal anywhere in the generated text
    assert not re.search(r"""(?<![A-Za-z0-9_])f["']""", text)
    assert "SHIFT_HOURS = 24" in text


def test_bat_does_not_echo_classpath():
    from pathlib import Path
    bat = jt.build_bat(Path("C:/v"), Path("C:/v/j.jar"), Path("C:/s.py"), "Xmx4g")
    assert "-Xmx4g" in bat and "echo %CLASSPATH%" not in bat


def test_vortex_locator_validates_layout(tmp_path):
    """Machine-independent: build a fake Vortex tree (0.13-style, jar one level up)."""
    from hec_hms_automation.vortex.locator import find_jython_jar, find_vortex_home, resolve_vortex_root
    assert resolve_vortex_root(tmp_path / "missing") is None
    assert resolve_vortex_root(tmp_path) is None                     # empty folder is not Vortex
    home = tmp_path / "vortex-0.13.3"
    (home / "jre" / "bin").mkdir(parents=True)
    (home / "jre" / "bin" / "java.exe").write_text("")
    (home / "lib").mkdir()
    assert resolve_vortex_root(home) is None                         # no jython jar yet
    (tmp_path / "jython-standalone-2.7.4.jar").write_text("")
    assert find_jython_jar(home).name == "jython-standalone-2.7.4.jar"
    assert resolve_vortex_root(tmp_path) == home                     # parent folder resolves to the versioned child
    assert find_vortex_home(explicit=tmp_path) == home


class _T:
    def __init__(self, d):
        self._d = d

    def datetime(self):
        return self._d


def test_dekad_frame_shifts_2400_stamp_and_bins():
    from hec_hms_automation.dss.timeseries import dekad_frame
    # HMS stamps 10 Jan's value at 24:00 => 11 Jan 00:00; it must land in dekad 1 of January.
    times = [_T(datetime(2000, 1, 1) + timedelta(days=i + 1)) for i in (9, 19, 30)]   # 10th, 20th, 31st
    df = dekad_frame(times, np.array([1.0, 2.0, 3.0]), np.array([False, False, False]))
    assert list(df["dekad"]) == [1, 2, 3]
    assert list(df["month"]) == [1, 1, 1]


def test_log_verdict(tmp_path):
    from hec_hms_automation.compute.runner import log_verdict
    (tmp_path / "Run_A.log").write_text("Finished computing simulation run A\nWARNING 1: x\n")
    assert log_verdict(tmp_path, "A").startswith("OK")
    (tmp_path / "Run_B.log").write_text("ERROR 41161: Invalid Muskingum K\n")
    assert log_verdict(tmp_path, "B").startswith("FAILED")
    assert log_verdict(tmp_path, "C") == "no log"


def test_judgment_falls_back_without_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    from hec_hms_automation.judgment import advisors
    out = advisors.judge_impervious_classes(["Built-up", "Settlement"], ["Built-up"])
    assert out["Built-up"].source == "rule" and out["Built-up"].band == "yes"
    assert out["Settlement"].band == "none"
    assert advisors.match_name("umsohrenkew basin", ["Umsohrenkew_Basin"]).source == "rule"
    assert advisors.judge_precip_variable([{"name": "rain"}, {"name": "t2m"}]).value == "rain"
