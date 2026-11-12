"""
Tests for analysis outputs. Run AFTER 06_analysis.py has executed.
"""
import pandas as pd
import pytest
from pathlib import Path

OUTPUTS = Path("outputs")
FIGURES = Path("outputs/figures")


def test_quintile_returns_exists():
    p = OUTPUTS / "quintile_returns.csv"
    assert p.exists(), "quintile_returns.csv not found — run 06_analysis.py first"


def test_quintile_returns_schema():
    df = pd.read_csv(OUTPUTS / "quintile_returns.csv")
    required = {"crowding_q", "mean_car_event", "mean_car_drift", "n_obs"}
    missing = required - set(df.columns)
    assert not missing, f"Missing columns: {missing}"


def test_quintile_returns_has_five_rows():
    df = pd.read_csv(OUTPUTS / "quintile_returns.csv")
    assert len(df) == 5, f"Expected 5 quintiles, got {len(df)}"


def test_two_by_two_table_exists():
    p = OUTPUTS / "two_by_two.csv"
    assert p.exists()


def test_two_by_two_table_schema():
    df = pd.read_csv(OUTPUTS / "two_by_two.csv")
    required = {"crowding_hi", "revision_hi", "mean_car_event", "n_obs"}
    missing = required - set(df.columns)
    assert not missing, f"Missing columns: {missing}"


def test_regression_results_exists():
    p = OUTPUTS / "regression_results.csv"
    assert p.exists()


def test_regression_results_has_crowding_rank_term():
    df = pd.read_csv(OUTPUTS / "regression_results.csv")
    assert "crowding_rank" in df["term"].values, "crowding_rank should appear in regression"


def test_figures_exist():
    expected = [
        "quintile_car.png",
        "two_by_two_heatmap.png",
        "revision_vs_crowding.png",
        "crowding_ts.png",
        "drift_by_quintile.png",
    ]
    for fname in expected:
        p = FIGURES / fname
        assert p.exists(), f"Missing figure: {fname}"
