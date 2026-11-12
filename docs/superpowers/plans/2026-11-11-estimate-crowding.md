# Estimate-Driven Crowding and Earnings Fragility — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing crowded-trades pipeline with IBES analyst consensus data to test whether large estimate revisions drive institutional crowding and whether crowded positions entering earnings produce worse outcomes.

**Architecture:** Seven new or modified files layer on top of the existing 13F pipeline (01–03, unchanged). A new `car_utils.py` module owns the event-study machinery used by both the dataset builder and the analysis script. `run_all.py` is updated to run all steps in order.

**Tech Stack:** Python 3.11+, pandas, yfinance, statsmodels, streamlit, wrds (WRDS Python package), matplotlib, seaborn, scipy, pyarrow.

**Spec:** `docs/superpowers/specs/2026-11-11-estimate-crowding-design.md`

## Global Constraints

- EDGAR request delay ≥ 0.12s between requests (EDGAR terms of service).
- WRDS data pulled once and cached to `inputs/ibes/`; never re-pulled on every run.
- All merges use `validate=` to catch key duplicates.
- `assert` unique keys on the final dataset before saving.
- CAR benchmark = market-adjusted (stock daily return minus SPY daily return).
- `eps_revision` winsorized at 1st/99th percentile before computing `revision_streak`.
- `revision_streak` threshold = eps_revision > 0.01 (1%) to count as "upward."
- `crowding_rank` percentile computed over all S&P 500 constituents in the calendar quarter, not just the filtered sample.
- Fiscal quarter → calendar quarter alignment: use most recent calendar quarter end on or before `fpedats`.
- 13F look-ahead rule: uniform one-quarter lag (crowding from Q predicts CAR at earnings in Q+1).
- Sample: S&P 500 constituent as of each historical quarter, 2019 Q1–2024 Q4, min 5 IBES analysts, min 10 13F filers.

## Review Focus

1. **Earnings date before/after market close** — a stock announcing after close on day T has day 0 = T+1; using T shifts the [−1,+1] window by one day and mixes pre-announcement into the event return. `compute_car` must accept and apply an `after_close` flag per row.
2. **Near-zero EPS denominator in eps_revision** — when `eps_consensus_tm1` is near zero the revision blows up. Winsorization in `build_features` must happen before `revision_streak` is computed; task 6 tests this order.
3. **Non-December fiscal year end alignment** — the fiscal/calendar join silently misaligns for January FYE firms by up to 2 months. The `fiscal_qtr_match` column flags approximate joins; task 6 tests that at least 60% of rows are exact matches.
4. **CUSIP → ticker mismatches propagating into IBES join** — the IBES ticker and the OpenFIGI ticker may differ (IBES uses its own symbol). The join in task 6 must go through the IBES-to-permno-to-ticker link; a hand-check in `audits/hand_check.md` verifies 10 rows.
5. **SPY return window mismatch** — if daily_returns.parquet has gaps (holidays, early close), the SPY return over [−1,+1] may cover fewer days than the stock's return. `compute_car` must use only dates present in both series.

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `config.py` | Extend scope 2019–2024; add IBES_DIR, DAILY_RETURNS, SP500_HISTORY paths |
| Modify | `requirements.txt` | Add `wrds>=3.1.0`, `openpyxl>=3.1.0` |
| Create | `code/sp500_history.py` | Download S&P 500 constituent history from Wikipedia |
| Create | `code/get_ibes.py` | Pull IBES statsum_epsus from WRDS; build consensus snapshot table |
| Modify | `code/04_get_returns.py` | Also save `daily_returns.parquet` and SPY daily series |
| Create | `code/car_utils.py` | `compute_car()`, `align_fiscal_to_calendar()`, `build_features()` |
| Rewrite | `code/05_build_dataset.py` | Merge IBES + crowding + daily returns; call car_utils; save final_dataset.parquet |
| Rewrite | `code/06_analysis.py` | Four new analyses + five figures |
| Rewrite | `app.py` | Three-tab dashboard: Risk Screen, Earnings Outcomes, Stock Explorer |
| Modify | `run_all.py` | Register new steps in correct order |
| Create | `tests/test_car_utils.py` | Unit tests for car_utils functions |
| Create | `audits/hand_check.md` | Template for required manual verification |
| Create | `specs_tried.md` | Log of every specification attempted |

The existing files `01_get_13f_filings.py`, `02_get_holdings.py`, `03_build_crowding.py` are **not modified** — they produce `inputs/crowding.parquet` unchanged.

---

### Task 1: Config + scaffold

**Files:**
- Modify: `config.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `IBES_DIR`, `DAILY_RETURNS`, `SP500_HISTORY` path constants importable by all downstream scripts.

- [ ] **Step 1: Update `config.py`**

  Change `START_YEAR = 2019`, `END_YEAR = 2024`. Add after the existing path block:

  ```python
  IBES_DIR        = INPUTS / "ibes"
  DAILY_RETURNS   = INPUTS / "returns" / "daily_returns.parquet"
  SP500_HISTORY   = INPUTS / "sp500_history.parquet"

  for d in [IBES_DIR]:
      d.mkdir(parents=True, exist_ok=True)
  ```

- [ ] **Step 2: Update `requirements.txt`**

  Add two lines:
  ```
  wrds>=3.1.0
  openpyxl>=3.1.0
  ```

- [ ] **Step 3: Verify imports work**

  Run: `python -c "from code.config import IBES_DIR, DAILY_RETURNS, SP500_HISTORY; print('ok')"` from repo root.
  Expected: `ok`

- [ ] **Step 4: Commit**

  ```bash
  git add config.py requirements.txt
  git commit -m "config: extend scope 2019-2024, add IBES and daily-returns paths"
  ```

---

### Task 2: S&P 500 constituent history

**Files:**
- Create: `code/sp500_history.py`

**Interfaces:**
- Produces: `inputs/sp500_history.parquet` with columns `ticker: str`, `date_added: datetime`, `date_removed: datetime | NaT`.
- Consumed by: Task 6 (`05_build_dataset.py`) to filter the analysis universe per quarter.

- [ ] **Step 1: Write failing test**

  Create `tests/test_sp500_history.py`:

  ```python
  import pandas as pd, pytest
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
  ```

  Run: `pytest tests/test_sp500_history.py -v`
  Expected: FAIL (file doesn't exist yet).

- [ ] **Step 2: Implement `code/sp500_history.py`**

  Scrape Wikipedia "List of S&P 500 companies" using `pd.read_html`. The page has a "Changes" table with additions and removals. Build a full membership history:
  - Start from the current constituents table (always present).
  - Apply removals backward to get historical membership.
  - `date_removed = NaT` for currently active members.
  - Save to `inputs/sp500_history.parquet`.

  Function signature:
  ```python
  def build_sp500_history() -> pd.DataFrame:
      """Returns DataFrame(ticker, date_added, date_removed)."""
  ```

- [ ] **Step 3: Run test**

  Run: `pytest tests/test_sp500_history.py -v`
  Expected: PASS

- [ ] **Step 4: Commit**

  ```bash
  git add code/sp500_history.py tests/test_sp500_history.py inputs/sp500_history.parquet
  git commit -m "feat: S&P 500 constituent history from Wikipedia"
  ```

---

### Task 3: IBES data pull

**Files:**
- Create: `code/get_ibes.py`

**Interfaces:**
- Produces: `inputs/ibes/ibes_consensus.parquet`

  Columns:
  | Column | Type | Description |
  |---|---|---|
  | `ibes_ticker` | str | IBES ticker symbol |
  | `fpedats` | datetime | Fiscal period end date (target quarter) |
  | `eps_consensus_t` | float | Mean EPS estimate at snapshot closest to fpedats |
  | `eps_consensus_tm1` | float | Mean EPS estimate at snapshot ~91 days before fpedats |
  | `dispersion_t` | float | Std dev of estimates at snapshot_t |
  | `n_analysts_t` | int | Number of analysts at snapshot_t |
  | `eps_actual` | float | Actual reported EPS |
  | `anndats_act` | datetime | Actual announcement date |

- Consumed by: Task 6 (`05_build_dataset.py`).

- [ ] **Step 1: Write failing test**

  Append to `tests/test_sp500_history.py` or create `tests/test_ibes.py`:

  ```python
  import pandas as pd
  from pathlib import Path

  IBES = Path("inputs/ibes/ibes_consensus.parquet")

  def test_schema():
      df = pd.read_parquet(IBES)
      required = {"ibes_ticker","fpedats","eps_consensus_t","eps_consensus_tm1",
                  "dispersion_t","n_analysts_t","eps_actual","anndats_act"}
      assert required.issubset(df.columns)

  def test_no_duplicate_keys():
      df = pd.read_parquet(IBES)
      assert df[["ibes_ticker","fpedats"]].duplicated().sum() == 0

  def test_date_range():
      df = pd.read_parquet(IBES)
      df["fpedats"] = pd.to_datetime(df["fpedats"])
      assert df["fpedats"].min() >= pd.Timestamp("2018-10-01")
      assert df["fpedats"].max() <= pd.Timestamp("2025-03-31")
  ```

  Run: `pytest tests/test_ibes.py -v`
  Expected: FAIL.

- [ ] **Step 2: Implement `code/get_ibes.py`**

  Connect to WRDS with `wrds.Connection()`. Query `ibes.statsum_epsus` for US quarterly EPS consensus. For each `(ticker, fpedats)` pair, extract two snapshots:
  - `snapshot_t`: the row where `statpers` is the closest available date ≤ `fpedats`
  - `snapshot_tm1`: the row where `statpers` is the closest available date to `fpedats - 91 days`

  Key function signature:
  ```python
  def pull_ibes(start_year: int, end_year: int) -> pd.DataFrame:
      """Pull raw statsum rows from WRDS and return them."""

  def build_consensus_snapshots(raw: pd.DataFrame) -> pd.DataFrame:
      """
      For each (ticker, fpedats), pivot to get snapshot_t and snapshot_tm1.
      Returns one row per (ticker, fpedats).
      """
  ```

  Save output to `IBES_DIR / "ibes_consensus.parquet"`. Cache: skip the WRDS pull if the file already exists.

  Builder note on WRDS query: filter `ibes.statsum_epsus` where `usfirm = 1`, `measure = 'EPS'`, `curcode = 'USD'`, and the appropriate `fpi` for quarterly frequency. The exact `fpi` codes depend on the WRDS IBES version — check the IBES data manual on WRDS for the current codes before writing the query.

- [ ] **Step 3: Run test**

  Run: `pytest tests/test_ibes.py -v`
  Expected: PASS.

- [ ] **Step 4: Commit**

  ```bash
  git add code/get_ibes.py tests/test_ibes.py inputs/ibes/ibes_consensus.parquet
  git commit -m "feat: IBES consensus snapshot pull via WRDS"
  ```

---

### Task 4: Daily returns + SPY

**Files:**
- Modify: `code/04_get_returns.py`

**Interfaces:**
- Produces (new): `inputs/returns/daily_returns.parquet` with columns `date: datetime`, `ticker: str`, `ret: float` (daily adjusted close pct change). One additional ticker value `"SPY"` for the market benchmark.
- Existing quarterly `returns.parquet` is preserved unchanged.
- Consumed by: `code/car_utils.py`.

- [ ] **Step 1: Write failing test**

  Create `tests/test_returns.py`:

  ```python
  import pandas as pd
  from pathlib import Path

  DAILY = Path("inputs/returns/daily_returns.parquet")

  def test_schema():
      df = pd.read_parquet(DAILY)
      assert {"date","ticker","ret"}.issubset(df.columns)

  def test_spy_present():
      df = pd.read_parquet(DAILY)
      assert "SPY" in df["ticker"].values

  def test_date_range():
      df = pd.read_parquet(DAILY)
      df["date"] = pd.to_datetime(df["date"])
      assert df["date"].min() <= pd.Timestamp("2019-01-15")
      assert df["date"].max() >= pd.Timestamp("2024-12-01")
  ```

  Run: `pytest tests/test_returns.py -v`
  Expected: FAIL.

- [ ] **Step 2: Add `download_daily_returns` to `code/04_get_returns.py`**

  Add a new function after the existing `download_quarterly_returns`:

  ```python
  def download_daily_returns(tickers: list[str]) -> pd.DataFrame:
      """
      Download and return daily adjusted-close pct changes for all tickers + SPY.
      Returns DataFrame(date, ticker, ret) — long format.
      """
  ```

  In `main()`, after the existing quarterly returns block, add:
  ```python
  daily_path = RETURNS_DIR / "daily_returns.parquet"
  if not daily_path.exists():
      all_tickers = tickers + ["SPY"]
      daily = download_daily_returns(all_tickers)
      daily.to_parquet(daily_path, index=False)
  ```

- [ ] **Step 3: Run test**

  Run: `pytest tests/test_returns.py -v`
  Expected: PASS.

- [ ] **Step 4: Commit**

  ```bash
  git add code/04_get_returns.py tests/test_returns.py
  git commit -m "feat: add daily returns + SPY to returns pipeline"
  ```

---

### Task 5: CAR utilities

**Files:**
- Create: `code/car_utils.py`

**Interfaces:**
- Produces three functions consumed by Task 6:

  ```python
  def align_fiscal_to_calendar(fpedats: pd.Timestamp) -> pd.Timestamp:
      """Most recent calendar quarter end (Mar/Jun/Sep/Dec) on or before fpedats."""

  def compute_car(
      ticker: str,
      event_date: pd.Timestamp,
      after_close: bool,
      daily_wide: pd.DataFrame,   # index=date, columns=tickers including SPY
      pre: int,
      post: int,
  ) -> float | None:
      """
      Market-adjusted CAR = sum(stock_ret - SPY_ret) over [event_date-pre, event_date+post]
      trading days. Returns None if fewer than (pre+post) trading days available.
      after_close=True shifts day 0 to the next trading day.
      """

  def build_features(ibes: pd.DataFrame) -> pd.DataFrame:
      """
      Given ibes_consensus DataFrame, add columns:
        eps_revision        (winsorized at 1st/99th before use)
        revision_streak     (count of consecutive eps_revision > 0.01)
        dispersion          (dispersion_t / |eps_consensus_t|, coeff of variation)
        eps_surprise        ((eps_actual - eps_consensus_t) / |eps_consensus_t|)
      Returns ibes with these columns added.
      """
  ```

- [ ] **Step 1: Write failing tests**

  Create `tests/test_car_utils.py`:

  ```python
  import pandas as pd, numpy as np, pytest
  import sys; sys.path.insert(0, "code")
  from car_utils import align_fiscal_to_calendar, compute_car, build_features

  # --- align_fiscal_to_calendar ---
  def test_align_december_fye():
      assert align_fiscal_to_calendar(pd.Timestamp("2023-09-30")) == pd.Timestamp("2023-09-30")

  def test_align_january_fye():
      # fiscal Q1 ends April 30 → most recent calendar Q end is March 31
      assert align_fiscal_to_calendar(pd.Timestamp("2023-04-30")) == pd.Timestamp("2023-03-31")

  def test_align_mid_quarter():
      # May 15 → most recent Q end is March 31
      assert align_fiscal_to_calendar(pd.Timestamp("2023-05-15")) == pd.Timestamp("2023-03-31")

  # --- compute_car ---
  def _make_daily(dates, stock_rets, spy_rets):
      idx = pd.to_datetime(dates)
      return pd.DataFrame({"AAPL": stock_rets, "SPY": spy_rets}, index=idx)

  def test_car_simple():
      # 5 trading days; event on day index 2, pre=1 post=1 → days 1,2,3
      dates = ["2023-10-02","2023-10-03","2023-10-04","2023-10-05","2023-10-06"]
      stock = [0.01, 0.02, -0.03, 0.01, 0.00]
      spy   = [0.00, 0.01,  0.00, 0.00, 0.00]
      wide  = _make_daily(dates, stock, spy)
      car = compute_car("AAPL", pd.Timestamp("2023-10-04"), False, wide, 1, 1)
      # days 3,4,5 (Oct 3,4,5): (0.02-0.01)+(−0.03−0.00)+(0.01−0.00) = -0.01
      assert abs(car - (-0.01)) < 1e-9

  def test_car_after_close_shifts_day0():
      dates = ["2023-10-04","2023-10-05","2023-10-06"]
      wide  = _make_daily(dates, [0.05, 0.10, 0.00], [0.01, 0.02, 0.00])
      # after_close=True; event_date=Oct 04, day 0 becomes Oct 05
      # window [-1,+1] = Oct 04, Oct 05, Oct 06
      car = compute_car("AAPL", pd.Timestamp("2023-10-04"), True, wide, 1, 1)
      expected = (0.05-0.01) + (0.10-0.02) + (0.00-0.00)
      assert abs(car - expected) < 1e-9

  def test_car_returns_none_on_insufficient_data():
      wide = _make_daily(["2023-10-04"], [0.01], [0.00])
      result = compute_car("AAPL", pd.Timestamp("2023-10-04"), False, wide, 1, 1)
      assert result is None

  # --- build_features ---
  def test_revision_streak_winsorize_first():
      """Streak must be computed after winsorizing eps_revision."""
      df = pd.DataFrame({
          "ibes_ticker": ["A"]*4,
          "fpedats": pd.date_range("2022-03-31", periods=4, freq="QE"),
          "eps_consensus_t":   [1.0, 1.1, 50.0, 1.3],   # 50.0 is an outlier
          "eps_consensus_tm1": [0.9, 1.0,  1.1, 1.2],
          "dispersion_t":      [0.1, 0.1,  0.1, 0.1],
          "eps_actual":        [1.0, 1.1,  1.2, 1.3],
          "n_analysts_t":      [5,   5,    5,   5],
          "anndats_act":       pd.date_range("2022-04-20", periods=4, freq="90D"),
      })
      out = build_features(df)
      # After winsorizing, the outlier revision for period 3 should be capped,
      # so the streak should not reach 4.
      assert out["revision_streak"].max() <= 3

  def test_dispersion_zero_mean_handled():
      """dispersion should be NaN (not inf) when eps_consensus_t == 0."""
      df = pd.DataFrame({
          "ibes_ticker": ["B"],
          "fpedats": [pd.Timestamp("2023-03-31")],
          "eps_consensus_t":   [0.0],
          "eps_consensus_tm1": [0.1],
          "dispersion_t":      [0.5],
          "eps_actual":        [0.0],
          "n_analysts_t":      [5],
          "anndats_act":       [pd.Timestamp("2023-04-25")],
      })
      out = build_features(df)
      assert pd.isna(out["dispersion"].iloc[0])
  ```

  Run: `pytest tests/test_car_utils.py -v`
  Expected: all FAIL (module doesn't exist yet).

- [ ] **Step 2: Implement `code/car_utils.py`**

  Implement the three functions matching the signatures above. For `compute_car`, pivot `daily_wide` so rows are dates, columns are tickers (including SPY); slice the window using `iloc` relative to the event date's position in the index.

- [ ] **Step 3: Run tests**

  Run: `pytest tests/test_car_utils.py -v`
  Expected: all PASS.

- [ ] **Step 4: Commit**

  ```bash
  git add code/car_utils.py tests/test_car_utils.py
  git commit -m "feat: CAR utilities — align_fiscal_to_calendar, compute_car, build_features"
  ```

---

### Task 6: Dataset builder

**Files:**
- Rewrite: `code/05_build_dataset.py`

**Interfaces:**
- Consumes: `inputs/crowding.parquet`, `inputs/cusip_ticker_map.parquet`, `inputs/ibes/ibes_consensus.parquet`, `inputs/returns/daily_returns.parquet`, `inputs/sp500_history.parquet`
- Produces: `inputs/final_dataset.parquet`

  Key columns (all spec variables):
  `ticker`, `fpedats`, `calendar_qtr_end`, `fiscal_qtr_match` (bool: exact alignment), `eps_revision`, `revision_streak`, `dispersion`, `eps_surprise`, `n_analysts_t`, `n_filers`, `chg_filers`, `crowding_rank`, `anndats_act`, `after_close` (bool), `car_event`, `car_drift`, `size` (log market cap, if available)

- [ ] **Step 1: Write failing test**

  Append to or create `tests/test_dataset_builder.py`:

  ```python
  import pandas as pd
  from pathlib import Path

  DS = Path("inputs/final_dataset.parquet")

  def test_unique_keys():
      df = pd.read_parquet(DS)
      assert df[["ticker","fpedats"]].duplicated().sum() == 0

  def test_required_columns():
      df = pd.read_parquet(DS)
      required = {"ticker","fpedats","calendar_qtr_end","fiscal_qtr_match",
                  "eps_revision","revision_streak","dispersion","eps_surprise",
                  "crowding_rank","car_event","car_drift"}
      assert required.issubset(df.columns)

  def test_majority_exact_fiscal_match():
      df = pd.read_parquet(DS)
      exact_rate = df["fiscal_qtr_match"].mean()
      assert exact_rate >= 0.60, f"Only {exact_rate:.1%} exact matches — expected ≥60%"

  def test_crowding_rank_in_unit_interval():
      df = pd.read_parquet(DS)
      assert df["crowding_rank"].between(0, 1).all()

  def test_no_lookahead_in_crowding():
      """Calendar quarter end must be before or on the earnings announcement date."""
      df = pd.read_parquet(DS).dropna(subset=["anndats_act"])
      df["calendar_qtr_end"] = pd.to_datetime(df["calendar_qtr_end"])
      df["anndats_act"]      = pd.to_datetime(df["anndats_act"])
      # Allow up to 180 days gap (Q+1 earnings window)
      gap = (df["anndats_act"] - df["calendar_qtr_end"]).dt.days
      assert (gap >= 0).all(), "Some earnings dates precede the crowding quarter — look-ahead!"
  ```

  Run: `pytest tests/test_dataset_builder.py -v`
  Expected: FAIL.

- [ ] **Step 2: Implement `code/05_build_dataset.py`**

  Pipeline:
  1. Load `ibes_consensus.parquet`; call `build_features(ibes)` from `car_utils`.
  2. Add `calendar_qtr_end = ibes["fpedats"].apply(align_fiscal_to_calendar)` and `fiscal_qtr_match = (ibes["calendar_qtr_end"] == ibes["fpedats"])`.
  3. Load `crowding.parquet`; merge `cusip_ticker_map`; compute `crowding_rank` as `n_filers.rank(pct=True)` within each `period_end` group across all S&P 500 constituents (load `sp500_history.parquet` to get the full set, not just the min-10-filer filtered set).
  4. Merge IBES (on `ticker`, `calendar_qtr_end` = `period_end` from crowding, using one-quarter lag: crowding `period_end` = ibes `calendar_qtr_end` minus one quarter). Use `validate="many_to_one"`.
  5. Load `daily_returns.parquet`; pivot wide (index=date, columns=ticker).
  6. For each row, call `compute_car(ticker, anndats_act, after_close, daily_wide, pre=1, post=1)` → `car_event`; call `compute_car(..., pre=0, post=60)` → `car_drift` (window starts day +2: pass `pre=-2` and handle offset inside `compute_car`, or add a `start_offset` parameter).

     Builder call: add an optional `start_offset: int = 0` parameter to `compute_car` so the caller can request `[+2, +60]` as `compute_car(..., pre=0, post=60, start_offset=2)`.

  7. Assert `df[["ticker","fpedats"]].duplicated().sum() == 0`.
  8. Apply S&P 500 filter: keep only rows where `ticker` was an S&P 500 constituent during `calendar_qtr_end` per `sp500_history.parquet`.
  9. Keep rows with `n_analysts_t >= 5` and `n_filers >= 10`.
  10. Save to `inputs/final_dataset.parquet`.

- [ ] **Step 3: Run tests**

  Run: `pytest tests/test_dataset_builder.py -v`
  Expected: PASS.

- [ ] **Step 4: Hand-check (required by spec)**

  For AAPL, 2023-Q3 (fpedats = 2023-09-30):
  - Open `ibes_consensus.parquet`, locate the row, record `eps_consensus_t` and `eps_consensus_tm1`.
  - Compute `eps_revision` by hand and verify it matches the dataset.
  - Open `daily_returns.parquet`, locate the earnings announcement date, sum the [−1,+1] market-adjusted returns, and verify `car_event` matches.
  - Write results to `audits/hand_check.md`.

- [ ] **Step 5: Commit**

  ```bash
  git add code/05_build_dataset.py tests/test_dataset_builder.py audits/hand_check.md
  git commit -m "feat: dataset builder — IBES + crowding + CAR merge"
  ```

---

### Task 7: Analysis outputs

**Files:**
- Rewrite: `code/06_analysis.py`

**Interfaces:**
- Consumes: `inputs/final_dataset.parquet`
- Produces:
  - `outputs/channel_test.csv` — eps_revision quintile → mean next-quarter chg_filers
  - `outputs/fragility_table.csv` — crowding_rank quintile × revision_streak bucket → mean car_event, N
  - `outputs/crowding_dispersion_2x2.csv` — high/low crowding × high/low dispersion → mean car_event
  - `outputs/regression_results.csv` — OLS coefficient table
  - `outputs/figures/channel_test.png`
  - `outputs/figures/fragility_quintiles.png`
  - `outputs/figures/dispersion_2x2.png`
  - `outputs/figures/drift_plot.png` (car_drift by crowded vs. not crowded, days +2 to +60)
  - `outputs/figures/streak_heatmap.png` (revision_streak × crowding_rank quintile → mean car_event)

- [ ] **Step 1: Write smoke test**

  Append to `tests/test_dataset_builder.py`:

  ```python
  def test_analysis_outputs_exist():
      import subprocess, sys
      result = subprocess.run([sys.executable, "code/06_analysis.py"])
      assert result.returncode == 0
      from pathlib import Path
      for f in ["outputs/channel_test.csv","outputs/fragility_table.csv",
                "outputs/regression_results.csv","outputs/figures/drift_plot.png"]:
          assert Path(f).exists(), f"Missing: {f}"
  ```

  Run: `pytest tests/test_dataset_builder.py::test_analysis_outputs_exist -v`
  Expected: FAIL.

- [ ] **Step 2: Implement `code/06_analysis.py`**

  Four analyses in `main()`:

  **A — Channel test** (do revisions predict crowding?):
  Within each quarter, assign `eps_revision` quintiles. Compute mean `chg_filers` by quintile. Save to `outputs/channel_test.csv`. Bar chart → `figures/channel_test.png`.

  **B — Fragility sort** (do crowded stocks disappoint at earnings?):
  Within each quarter, assign `crowding_rank` quintiles. Compute mean `car_event` by quintile. Save to `outputs/fragility_table.csv`. Bar chart → `figures/fragility_quintiles.png`.

  **C — 2×2 crowding × dispersion**:
  Split on median `crowding_rank` and median `dispersion` within each quarter. Compute mean `car_event` for each of the four cells. Save to `outputs/crowding_dispersion_2x2.csv`. Heatmap → `figures/dispersion_2x2.png`.

  **D — Regression**:
  ```
  car_event ~ eps_revision + revision_streak + dispersion + crowding_rank + log(n_analysts_t) + C(sector) + C(quarter)
  ```
  HC3 robust SEs. Save coefficient table to `outputs/regression_results.csv`.

  **E — Post-earnings drift plot**:
  For top-crowding quintile vs. bottom-crowding quintile, plot average `car_drift` as a function of holding period (day +2 through +60). Requires computing CAR for each day offset — load `daily_returns.parquet` and vectorize. → `figures/drift_plot.png`.

  **F — Streak heatmap**:
  `revision_streak` (0,1,2,3+) on x-axis, crowding_rank quintile on y-axis, cell value = mean `car_event`. → `figures/streak_heatmap.png`.

- [ ] **Step 3: Run test**

  Run: `pytest tests/test_dataset_builder.py::test_analysis_outputs_exist -v`
  Expected: PASS.

- [ ] **Step 4: Commit**

  ```bash
  git add code/06_analysis.py outputs/
  git commit -m "feat: analysis — channel test, fragility sort, 2x2, regression, drift"
  ```

---

### Task 8: Dashboard

**Files:**
- Rewrite: `app.py`

**Interfaces:**
- Consumes: `inputs/final_dataset.parquet`, `outputs/*.csv`, `outputs/figures/*.png`
- Produces: interactive Streamlit app at `localhost:8501`

- [ ] **Step 1: Implement `app.py`** (three tabs)

  **Tab 1 — Risk Screen**:
  Scatter plot: x-axis = `revision_streak` (jittered), y-axis = `crowding_rank` percentile, dot color = `dispersion` level (low/mid/high tercile, three distinct colors), dot size = proportional to market cap if available else uniform. Quadrant lines at median `revision_streak` and 75th percentile `crowding_rank`. Hover shows `ticker`, `anndats_act`, `eps_revision`. Sector filter dropdown. Restrict to latest quarter available.

  **Tab 2 — Earnings Outcomes**:
  Bar chart of mean `car_event` by `crowding_rank` quintile. Integer slider (2–60) controls holding period: when changed, recompute displayed CAR using the daily returns loaded from `daily_returns.parquet`. Table below shows count, mean, and 95% CI per quintile bucket. Display the streak × crowding heatmap image from `outputs/figures/streak_heatmap.png`.

  **Tab 3 — Stock Explorer**:
  Text input → ticker. If found: line chart of `eps_revision` over time, bar chart of `crowding_rank` over time, scatter of `eps_surprise` vs. `car_event` (each dot = one quarter), table of raw rows sorted by `fpedats` descending.

- [ ] **Step 2: Run app and verify golden path**

  ```bash
  streamlit run app.py
  ```

  Check:
  - Tab 1 renders scatter with colored dots; sector dropdown filters.
  - Tab 2 bar chart appears; moving the slider changes displayed values.
  - Tab 3: type `AAPL` → all three charts render, table has ≥ 1 row.

- [ ] **Step 3: Commit**

  ```bash
  git add app.py
  git commit -m "feat: three-tab dashboard — risk screen, earnings outcomes, stock explorer"
  ```

---

### Task 9: Wire-up and audit

**Files:**
- Modify: `run_all.py`
- Create: `specs_tried.md`
- Create/update: `audits/hand_check.md` (populated in Task 6 Step 4)
- Create: `README.md` (replace stub)

- [ ] **Step 1: Update `run_all.py`**

  Replace the `STEPS` list with:
  ```python
  STEPS = [
      ("Step 1 — S&P 500 constituent history",   "code/sp500_history.py"),
      ("Step 2 — IBES consensus from WRDS",       "code/get_ibes.py"),
      ("Step 3 — 13F filing index from EDGAR",    "code/01_get_13f_filings.py"),
      ("Step 4 — 13F holdings XML",              "code/02_get_holdings.py"),
      ("Step 5 — Crowding metrics",              "code/03_build_crowding.py"),
      ("Step 6 — Daily returns + SPY",           "code/04_get_returns.py"),
      ("Step 7 — Build analysis dataset",        "code/05_build_dataset.py"),
      ("Step 8 — Analysis + figures",            "code/06_analysis.py"),
  ]
  ```

- [ ] **Step 2: Create `specs_tried.md`**

  Header only — the team fills this in as analysis runs:
  ```markdown
  # Specifications Tried

  Log every model specification and robustness check here, not just the ones that worked.

  | Date | Change | Key result | Kept? |
  |------|--------|-----------|-------|
  ```

- [ ] **Step 3: Write `README.md`**

  Sections: Research Question, Data Sources (with provenance table), Pipeline Steps, How to Reproduce, Hand-Check Results (from `audits/hand_check.md`), Threats to Validity, Sample Statistics (fill in after pipeline runs).

- [ ] **Step 4: Full pipeline smoke test**

  Run: `python run_all.py`
  Expected: all 8 steps exit 0; `inputs/final_dataset.parquet` and all `outputs/` files exist.

- [ ] **Step 5: Commit**

  ```bash
  git add run_all.py specs_tried.md README.md audits/
  git commit -m "chore: wire up full pipeline, add specs_tried and README"
  ```

---

### Task 10: STATUS.md (Checkpoint 1 memo — overdue)

**Files:**
- Create: `STATUS.md`

**Interfaces:** None — standalone required file.

- [ ] **Step 1: Write `STATUS.md`**

  Three paragraphs as specified in the project description:
  1. What we picked and why (Seed 9 enhanced with IBES analyst estimates + crowding chain)
  2. What the proof of concept produced (13F pipeline scaffold, crowding metrics, Streamlit skeleton) and what broke / was harder than expected
  3. Questions for the professor (IBES WRDS access confirmed; ask about whether revision_streak threshold of 1% is defensible; ask about whether market-adjusted CAR is preferred over factor-adjusted for a student project)

- [ ] **Step 2: Commit**

  ```bash
  git add STATUS.md
  git commit -m "docs: add STATUS.md checkpoint 1 memo"
  ```

---

### Task 11: PROPOSAL.md + dashboard mockup image

**Files:**
- Create: `PROPOSAL.md`
- Create: `docs/mockup.png` (or `.svg`) — dashboard mockup image committed to repo

**Interfaces:** Consumes real rows from `inputs/final_dataset.parquet` for the "unit of observation" table.

- [ ] **Step 1: Create dashboard mockup image**

  Generate a mockup image of the three-tab dashboard using an ASCII/text description saved as `docs/mockup_description.md`, then create a simple HTML mockup saved as `docs/mockup.html` that shows the layout. This serves as the "picture of what the finished dashboard will look like" that the proposal requires. Commit both files.

- [ ] **Step 2: Write `PROPOSAL.md`**

  Sections (all required by the grading rubric):

  1. **Question and Motivation** — who would pay, the crowding chain mechanism
  2. **Creativity** — why this extends beyond base Seed 9 (estimate momentum + dispersion + post-earnings drift)
  3. **Course Ideas Applied** — event studies (HW6 machinery), 13F analysis, OLS regression with FE
  4. **Data**
     - Unit of observation (stock × fiscal quarter) with real rows from `inputs/final_dataset.parquet`
     - Sample period (2019 Q1 – 2024 Q4)
     - Sample conditions (S&P 500 constituent, ≥5 analysts, ≥10 13F filers)
     - Variables table (necessary vs. nice-to-have)
     - Raw inputs table (source, how to get it, where it lives in repo)
  5. **Method** — pipeline steps matching repo filenames, analysis steps, why each fits the question
  6. **Threats and Checks** — look-ahead (13F filing lag + earnings timing), survivorship, CUSIP/IBES ticker mismatch, near-zero EPS denominator, multiple testing
  7. **Dashboard Mockup** — link to `docs/mockup.html` and embedded image

- [ ] **Step 3: Commit**

  ```bash
  git add PROPOSAL.md docs/mockup.html docs/mockup_description.md
  git commit -m "docs: add PROPOSAL.md and dashboard mockup for Checkpoint 2"
  ```
