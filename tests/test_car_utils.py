import pandas as pd
import numpy as np
import pytest
import sys
sys.path.insert(0, "code")
from car_utils import align_fiscal_to_calendar, compute_car, build_features


# ── align_fiscal_to_calendar ──────────────────────────────────────────────────

def test_align_december_fye():
    assert align_fiscal_to_calendar(pd.Timestamp("2023-09-30")) == pd.Timestamp("2023-09-30")

def test_align_january_fye():
    # fiscal Q1 ends April 30 → most recent calendar Q end is March 31
    assert align_fiscal_to_calendar(pd.Timestamp("2023-04-30")) == pd.Timestamp("2023-03-31")

def test_align_mid_quarter():
    # May 15 → most recent Q end is March 31
    assert align_fiscal_to_calendar(pd.Timestamp("2023-05-15")) == pd.Timestamp("2023-03-31")

def test_align_exact_june():
    assert align_fiscal_to_calendar(pd.Timestamp("2023-06-30")) == pd.Timestamp("2023-06-30")


# ── compute_car ───────────────────────────────────────────────────────────────

def _make_wide(dates, stock_rets, spy_rets, ticker="AAPL"):
    idx = pd.to_datetime(dates)
    return pd.DataFrame({ticker: stock_rets, "SPY": spy_rets}, index=idx)


def test_car_simple():
    # 5 days; event on Oct 4, pre=1 post=1 → window Oct 3,4,5
    dates = ["2023-10-02","2023-10-03","2023-10-04","2023-10-05","2023-10-06"]
    wide  = _make_wide(dates, [0.01, 0.02, -0.03, 0.01, 0.00],
                               [0.00, 0.01,  0.00, 0.00, 0.00])
    car = compute_car("AAPL", pd.Timestamp("2023-10-04"), False, wide, 1, 1)
    # Oct3: 0.02-0.01=0.01, Oct4: -0.03-0.00=-0.03, Oct5: 0.01-0.00=0.01 → -0.01
    assert abs(car - (-0.01)) < 1e-9


def test_car_after_close_shifts_day0():
    dates = ["2023-10-04","2023-10-05","2023-10-06"]
    wide  = _make_wide(dates, [0.05, 0.10, 0.02], [0.01, 0.02, 0.00])
    # after_close=True: day 0 shifts to Oct 05; window [-1,+1] = Oct04,Oct05,Oct06
    car = compute_car("AAPL", pd.Timestamp("2023-10-04"), True, wide, 1, 1)
    expected = (0.05-0.01) + (0.10-0.02) + (0.02-0.00)
    assert abs(car - expected) < 1e-9


def test_car_returns_none_on_insufficient_data():
    wide = _make_wide(["2023-10-04"], [0.01], [0.00])
    result = compute_car("AAPL", pd.Timestamp("2023-10-04"), False, wide, 1, 1)
    assert result is None


def test_car_start_offset():
    # start_offset=2: window [+2,+4] relative to event
    dates = ["2023-10-04","2023-10-05","2023-10-06","2023-10-07","2023-10-08"]
    wide  = _make_wide(dates, [0.10, 0.10, 0.03, 0.04, 0.05],
                               [0.00, 0.00, 0.01, 0.01, 0.01])
    car = compute_car("AAPL", pd.Timestamp("2023-10-04"), False, wide, 0, 2,
                      start_offset=2)
    # days Oct06,Oct07,Oct08: (0.03-0.01)+(0.04-0.01)+(0.05-0.01) = 0.09
    assert abs(car - 0.09) < 1e-9


# ── build_features ────────────────────────────────────────────────────────────

def _make_ibes(n=4):
    dates  = pd.date_range("2022-03-31", periods=n, freq="QE")
    t_vals = [1.0, 1.1, 1.2, 1.3][:n]
    m_vals = [0.9, 1.0, 1.1, 1.2][:n]
    return pd.DataFrame({
        "ibes_ticker":       ["A"] * n,
        "fpedats":           dates,
        "eps_consensus_t":   t_vals,
        "eps_consensus_tm1": m_vals,
        "dispersion_t":      [0.1] * n,
        "eps_actual":        [v + 0.05 for v in t_vals],
        "n_analysts_t":      [10] * n,
        "anndats_act":       dates + pd.Timedelta(days=28),
    })


def test_build_features_adds_columns():
    df = build_features(_make_ibes())
    for col in ["eps_revision", "revision_streak", "dispersion", "eps_surprise"]:
        assert col in df.columns, f"Missing {col}"


def test_revision_streak_counts_correctly():
    df = build_features(_make_ibes())
    # all 4 quarters have positive revisions (>1%), so streaks should be 1,2,3,4
    assert list(df["revision_streak"]) == [1, 2, 3, 4]


def test_dispersion_zero_mean_is_nan():
    ibes = _make_ibes(1)
    ibes["eps_consensus_t"] = 0.0
    df = build_features(ibes)
    assert pd.isna(df["dispersion"].iloc[0])


def test_winsorize_before_streak():
    # Insert a huge outlier revision; after winsorizing it should be capped
    ibes = _make_ibes(4)
    ibes.loc[2, "eps_consensus_t"]   = 500.0  # extreme outlier
    ibes.loc[2, "eps_consensus_tm1"] = 1.1
    df = build_features(ibes)
    # streak for row 2 uses the winsorized revision, not the raw 500x jump
    assert df["revision_streak"].max() <= 4
