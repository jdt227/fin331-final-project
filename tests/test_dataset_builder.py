import pandas as pd
import pytest
from pathlib import Path

DS = Path("inputs/final_dataset.parquet")


def test_unique_keys():
    df = pd.read_parquet(DS)
    assert df[["ticker", "fpedats"]].duplicated().sum() == 0, \
        "Duplicate (ticker, fpedats) rows found"


def test_required_columns():
    df = pd.read_parquet(DS)
    required = {
        "ticker", "fpedats", "calendar_qtr_end", "fiscal_qtr_match",
        "eps_revision", "revision_streak", "dispersion", "eps_surprise",
        "crowding_rank", "car_event", "car_drift",
    }
    missing = required - set(df.columns)
    assert not missing, f"Missing columns: {missing}"


def test_crowding_rank_in_unit_interval():
    df = pd.read_parquet(DS)
    valid = df["crowding_rank"].dropna()
    assert valid.between(0, 1).all()


def test_majority_exact_fiscal_match():
    df = pd.read_parquet(DS)
    exact_rate = df["fiscal_qtr_match"].mean()
    assert exact_rate >= 0.50, f"Only {exact_rate:.1%} exact matches"


def test_no_lookahead_in_crowding():
    df = pd.read_parquet(DS).dropna(subset=["anndats_act", "calendar_qtr_end"])
    df["calendar_qtr_end"] = pd.to_datetime(df["calendar_qtr_end"])
    df["anndats_act"]      = pd.to_datetime(df["anndats_act"])
    gap = (df["anndats_act"] - df["calendar_qtr_end"]).dt.days
    assert (gap >= 0).all(), "Some earnings dates precede the crowding quarter — look-ahead!"


def test_has_rows():
    df = pd.read_parquet(DS)
    assert len(df) >= 10, "Expected at least 10 rows in dataset"
