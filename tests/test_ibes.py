import pandas as pd
import pytest
from pathlib import Path

IBES = Path("inputs/ibes/ibes_consensus.parquet")


def test_schema():
    df = pd.read_parquet(IBES)
    required = {
        "ibes_ticker", "fpedats", "eps_consensus_t", "eps_consensus_tm1",
        "dispersion_t", "n_analysts_t", "eps_actual", "anndats_act",
    }
    assert required.issubset(df.columns), f"Missing: {required - set(df.columns)}"


def test_no_duplicate_keys():
    df = pd.read_parquet(IBES)
    assert df[["ibes_ticker", "fpedats"]].duplicated().sum() == 0


def test_date_range():
    df = pd.read_parquet(IBES)
    df["fpedats"] = pd.to_datetime(df["fpedats"])
    assert df["fpedats"].min() >= pd.Timestamp("2021-10-01")
    assert df["fpedats"].max() <= pd.Timestamp("2024-06-30")


def test_has_rows():
    df = pd.read_parquet(IBES)
    assert len(df) > 100, "Expected at least 100 rows"
