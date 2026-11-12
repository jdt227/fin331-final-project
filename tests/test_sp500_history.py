import pandas as pd
import pytest
from pathlib import Path

SP500 = Path("inputs/sp500_history.parquet")


def test_schema():
    df = pd.read_parquet(SP500)
    assert {"ticker", "date_added", "date_removed"}.issubset(df.columns)


def test_no_duplicate_active_membership():
    df = pd.read_parquet(SP500)
    active = df[df["date_removed"].isna()]
    assert active["ticker"].duplicated().sum() == 0


def test_apple_present():
    df = pd.read_parquet(SP500)
    assert "AAPL" in df["ticker"].values
