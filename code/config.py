"""
Central config for the crowded-trades pipeline.
Adjust START_YEAR / END_YEAR and MAX_FILERS_PER_QUARTER to change scope.
  100 filers / 2 years  → fast checkpoint run (~10 min)
  500 filers / 6 years  → solid MVP (v1)
"""
from pathlib import Path

# ── Sample scope ───────────────────────────────────────────────────────────────
START_YEAR = 2022
END_YEAR   = 2023

# How many 13F filers to download per quarter.
# 100 → fast test (~5 min); 500 → solid MVP; 2000 → near-complete.
MAX_FILERS_PER_QUARTER = 100

# Only keep stocks held by at least this many filers (noise filter)
MIN_HOLDER_COUNT = 10

# Minimum IBES analysts for a consensus to be meaningful
MIN_ANALYSTS = 5

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
INPUTS        = ROOT / "inputs"
INDEX_DIR     = INPUTS / "13f_index"
HOLDINGS_DIR  = INPUTS / "13f_holdings"
RETURNS_DIR   = INPUTS / "returns"
IBES_DIR      = INPUTS / "ibes"
DAILY_RETURNS = INPUTS / "returns" / "daily_returns.parquet"
SP500_HISTORY = INPUTS / "sp500_history.parquet"
OUTPUTS       = ROOT / "outputs"
FIGURES       = OUTPUTS / "figures"

for d in [INDEX_DIR, HOLDINGS_DIR, RETURNS_DIR, IBES_DIR, OUTPUTS, FIGURES]:
    d.mkdir(parents=True, exist_ok=True)

# ── SEC EDGAR ──────────────────────────────────────────────────────────────────
# The SEC requires a descriptive User-Agent. Update this with your team info.
EDGAR_HEADERS  = {"User-Agent": "FIN331 Research Project fin331team@university.edu"}
REQUEST_DELAY  = 0.12   # seconds between EDGAR requests (stay under 10/sec)

QUARTERS = [(y, q) for y in range(START_YEAR, END_YEAR + 1) for q in range(1, 5)]
