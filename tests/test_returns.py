import pandas as pd
import pytest
from pathlib import Path

DAILY = Path("inputs/returns/daily_returns.parquet")


def test_schema():
    df = pd.read_parquet(DAILY)
    assert {"date", "ticker", "ret"}.issubset(df.columns)


def test_spy_present():
    df = pd.read_parquet(DAILY)
    assert "SPY" in df["ticker"].values


def test_date_range():
    df = pd.read_parquet(DAILY)
    df["date"] = pd.to_datetime(df["date"])
    assert df["date"].min() <= pd.Timestamp("2022-01-15")
    assert df["date"].max() >= pd.Timestamp("2023-12-01")


def test_no_nulls_in_ret():
    df = pd.read_parquet(DAILY)
    assert df["ret"].notna().mean() > 0.95
