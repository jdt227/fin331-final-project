"""
Shared utilities for the estimate-crowding pipeline.

  align_fiscal_to_calendar(fpedats) → calendar quarter end
  compute_car(ticker, event_date, after_close, daily_wide, pre, post, start_offset) → float | None
  build_features(ibes_df) → ibes_df with eps_revision, revision_streak, dispersion, eps_surprise
"""
import pandas as pd
import numpy as np
from typing import Optional

# Calendar quarter ends in a year — used by align_fiscal_to_calendar
_MONTH_TO_QEND = {1: 31, 3: 31, 6: 30, 9: 30, 12: 31}
_QEND_MONTHS   = [3, 6, 9, 12]


def align_fiscal_to_calendar(fpedats: pd.Timestamp) -> pd.Timestamp:
    """
    Return the most recent calendar quarter end (Mar 31, Jun 30, Sep 30, Dec 31)
    that falls on or before fpedats.
    """
    y = fpedats.year
    candidates = [
        pd.Timestamp(y - 1, 12, 31),
        pd.Timestamp(y, 3, 31),
        pd.Timestamp(y, 6, 30),
        pd.Timestamp(y, 9, 30),
        pd.Timestamp(y, 12, 31),
    ]
    valid = [c for c in candidates if c <= fpedats]
    return max(valid)


def compute_car(
    ticker: str,
    event_date: pd.Timestamp,
    after_close: bool,
    daily_wide: pd.DataFrame,
    pre: int,
    post: int,
    start_offset: int = 0,
) -> Optional[float]:
    """
    Market-adjusted CAR = sum(stock_ret - SPY_ret) over the event window.

    Parameters
    ----------
    ticker       : column name in daily_wide
    event_date   : the earnings announcement date
    after_close  : if True, day 0 is shifted to the next trading day
    daily_wide   : DataFrame indexed by date, columns = tickers incl. SPY
    pre          : trading days before day 0 (ignored when start_offset > 0)
    post         : trading days after day 0 (or after start_offset)
    start_offset : if > 0, window starts at day +start_offset instead of day -pre

    Returns None if the ticker or SPY is missing, or fewer than (pre+post+1)
    trading days are available in the window.
    """
    if ticker not in daily_wide.columns or "SPY" not in daily_wide.columns:
        return None

    dates = daily_wide.index.sort_values()

    # Locate day 0
    event_date = pd.Timestamp(event_date)
    if after_close:
        # Shift: find first trading day strictly after event_date
        future = dates[dates > event_date]
        if future.empty:
            return None
        day0 = future[0]
    else:
        # Find the first trading day on or after event_date
        on_or_after = dates[dates >= event_date]
        if on_or_after.empty:
            return None
        day0 = on_or_after[0]

    day0_idx = dates.get_loc(day0)

    if start_offset > 0:
        # Window is [day0 + start_offset, day0 + start_offset + post]
        win_start_idx = day0_idx + start_offset
        win_end_idx   = day0_idx + start_offset + post
    else:
        win_start_idx = day0_idx - pre
        win_end_idx   = day0_idx + post

    if win_start_idx < 0 or win_end_idx >= len(dates):
        return None

    window_dates = dates[win_start_idx : win_end_idx + 1]
    needed = post + 1 if start_offset > 0 else pre + post + 1
    if len(window_dates) < needed:
        return None

    stock_ret = daily_wide.loc[window_dates, ticker].fillna(0.0)
    spy_ret   = daily_wide.loc[window_dates, "SPY"].fillna(0.0)

    return float((stock_ret - spy_ret).sum())


def build_features(ibes: pd.DataFrame) -> pd.DataFrame:
    """
    Add eps_revision, revision_streak, dispersion, eps_surprise to IBES DataFrame.

    Rules (per spec):
    - eps_revision = (eps_consensus_t - eps_consensus_tm1) / |eps_consensus_tm1|
    - Winsorize eps_revision at 1st/99th percentile BEFORE computing streak
    - revision_streak = consecutive quarters with eps_revision > 0.01 (1% threshold)
    - dispersion = dispersion_t / |eps_consensus_t| (NaN when eps_consensus_t == 0)
    - eps_surprise = (eps_actual - eps_consensus_t) / |eps_consensus_t|
    """
    df = ibes.copy()

    # Raw revision (avoid division by zero → NaN)
    denom_rev = df["eps_consensus_tm1"].abs().replace(0, np.nan)
    df["eps_revision_raw"] = (df["eps_consensus_t"] - df["eps_consensus_tm1"]) / denom_rev

    # Winsorize at 1st / 99th percentile
    lo = df["eps_revision_raw"].quantile(0.01)
    hi = df["eps_revision_raw"].quantile(0.99)
    df["eps_revision"] = df["eps_revision_raw"].clip(lo, hi)
    df = df.drop(columns=["eps_revision_raw"])

    # Revision streak — per ticker, sorted by fpedats
    df = df.sort_values(["ibes_ticker", "fpedats"]).reset_index(drop=True)

    streaks = []
    for _, grp in df.groupby("ibes_ticker", sort=False):
        streak = 0
        s = []
        for rev in grp["eps_revision"]:
            if pd.notna(rev) and rev > 0.01:
                streak += 1
            else:
                streak = 0
            s.append(streak)
        streaks.extend(s)
    df["revision_streak"] = streaks

    # Dispersion = CV of analyst estimates
    denom_disp = df["eps_consensus_t"].abs().replace(0, np.nan)
    df["dispersion"] = df["dispersion_t"] / denom_disp

    # EPS surprise
    denom_surp = df["eps_consensus_t"].abs().replace(0, np.nan)
    df["eps_surprise"] = (df["eps_actual"] - df["eps_consensus_t"]) / denom_surp

    return df
