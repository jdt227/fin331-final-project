"""
Project-wide settings. Every script imports this file, so a setting lives in ONE place.

Environment variables (all optional except SEC_USER_AGENT for downloading):
    SEC_USER_AGENT     "Your Name your.email@lehigh.edu"  (the SEC blocks requests without one)
    OPENFIGI_API_KEY   free key from openfigi.com; makes CUSIP mapping ~10x faster
    CROWD_QUICK=1      v0 / small-sample mode: 2023 only, top 100 stocks
    CROWD_DATA_DIR     override where data/ lives (used by tests)
    CROWD_OUTPUT_DIR   override where outputs/ lives (used by tests)
    CROWD_UNIVERSE_SIZE, CROWD_CANDIDATE_POOL   override universe sizes (used by tests)
"""
from pathlib import Path
import os

import pandas as pd

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("CROWD_DATA_DIR", ROOT / "data"))
RAW = DATA / "raw"
RAW_13F = RAW / "sec_13f"              # SEC zip files, untouched
INTERIM = DATA / "interim"             # parsed / filtered intermediate files
OUTPUTS = Path(os.environ.get("CROWD_OUTPUT_DIR", ROOT / "outputs"))
TABLES = OUTPUTS / "tables"
FIGURES = OUTPUTS / "figures"

PROVENANCE_FILE = RAW / "provenance.csv"     # one row per raw input pull
FIGI_CACHE = RAW / "openfigi_cache.json"     # raw OpenFIGI responses by CUSIP
CUSIP_MAP = RAW / "cusip_ticker_map.csv"     # parsed CUSIP -> ticker map
PRICES = RAW / "prices_daily.parquet"        # yfinance adjusted closes + splits


def ensure_dirs():
    for p in [RAW_13F, INTERIM, TABLES, FIGURES]:
        p.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- sample
QUICK = os.environ.get("CROWD_QUICK", "0") == "1"

# Signal quarters = the 13F report quarters whose holdings form the crowding signal.
FIRST_QUARTER = pd.Period("2023Q1" if QUICK else "2022Q1", freq="Q")
LAST_QUARTER = pd.Period("2023Q4" if QUICK else "2024Q4", freq="Q")
SIGNAL_QUARTERS = list(pd.period_range(FIRST_QUARTER, LAST_QUARTER, freq="Q"))
# Holdings are also needed for the quarter BEFORE the first one (to measure changes).
HOLDINGS_QUARTERS = [FIRST_QUARTER - 1] + SIGNAL_QUARTERS

UNIVERSE_SIZE = int(os.environ.get("CROWD_UNIVERSE_SIZE", 100 if QUICK else 500))
CANDIDATE_POOL = int(os.environ.get("CROWD_CANDIDATE_POOL", int(UNIVERSE_SIZE * 1.6)))

# ---------------------------------------------------------------- timing rules
FILING_DEADLINE_DAYS = 45                        # 13F due 45 days after quarter end
VALUE_IN_DOLLARS_FROM = pd.Timestamp("2023-01-03")  # before this, 13F VALUE is in $000s


def quarter_end(q: pd.Period) -> pd.Timestamp:
    return q.end_time.normalize()


def filing_deadline(q: pd.Period) -> pd.Timestamp:
    """Last calendar day a 13F for quarter q counts as 'on time' in this project."""
    return quarter_end(q) + pd.Timedelta(days=FILING_DEADLINE_DAYS)


# Price window: from well before the first lagged formation date (for past-return and
# volatility controls) to after the formation date that ends the last holding period.
PRICE_START = (quarter_end(FIRST_QUARTER - 2) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
PRICE_END = (filing_deadline(LAST_QUARTER + 1) + pd.Timedelta(days=20)).strftime("%Y-%m-%d")
MARKET_TICKER = "SPY"

# ---------------------------------------------------------------- SEC files
SEC_BASE = "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/"
# (file name, first filing date covered, last filing date covered).
# SEC data sets are organized by FILING date, not by report quarter. Source:
# https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets
SEC_FILES = [
    ("2021q4_form13f.zip", "2021-10-01", "2021-12-31"),
    ("2022q1_form13f.zip", "2022-01-01", "2022-03-31"),
    ("2022q2_form13f.zip", "2022-04-01", "2022-06-30"),
    ("2022q3_form13f.zip", "2022-07-01", "2022-09-30"),
    ("2022q4_form13f.zip", "2022-10-01", "2022-12-31"),
    ("2023q1_form13f.zip", "2023-01-01", "2023-03-31"),
    ("2023q2_form13f.zip", "2023-04-01", "2023-06-30"),
    ("2023q3_form13f.zip", "2023-07-01", "2023-09-30"),
    ("2023q4_form13f.zip", "2023-10-01", "2023-12-31"),
    ("01jan2024-29feb2024_form13f.zip", "2024-01-01", "2024-02-29"),
    ("01mar2024-31may2024_form13f.zip", "2024-03-01", "2024-05-31"),
    ("01jun2024-31aug2024_form13f.zip", "2024-06-01", "2024-08-31"),
    ("01sep2024-30nov2024_form13f.zip", "2024-09-01", "2024-11-30"),
    ("01dec2024-28feb2025_form13f.zip", "2024-12-01", "2025-02-28"),
    ("01mar2025-31may2025_form13f.zip", "2025-03-01", "2025-05-31"),
    ("01jun2025-31aug2025_form13f.zip", "2025-06-01", "2025-08-31"),
    ("01sep2025-30nov2025_form13f.zip", "2025-09-01", "2025-11-30"),
    ("01dec2025-28feb2026_form13f.zip", "2025-12-01", "2026-02-28"),
]


def sec_files_needed():
    """Only the zip files whose filing-date window overlaps an on-time filing window
    (quarter end + 1 day ... quarter end + 45 days) for a quarter we need."""
    needed = []
    for name, start, end in SEC_FILES:
        start, end = pd.Timestamp(start), pd.Timestamp(end)
        for q in HOLDINGS_QUARTERS:
            w0, w1 = quarter_end(q) + pd.Timedelta(days=1), filing_deadline(q)
            if start <= w1 and end >= w0:
                needed.append(name)
                break
    return needed


# ---------------------------------------------------------------- analysis
PRIMARY_SIGNAL = "dbreadth"   # pre-registered; see specs_tried.md
SIGNALS = ["dbreadth", "pct_chg_holders", "net_buyer_frac", "n_holders"]
N_BINS = 5                    # quintiles
COST_BPS_PER_SIDE = 10        # assumed one-way trading cost for large caps
