"""
Step 1: Download S&P 500 constituent history from Wikipedia.

Builds a full membership table (ticker, date_added, date_removed) so the
analysis universe is free of survivorship bias.

Output: inputs/sp500_history.parquet
"""
import sys, io, requests, pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import SP500_HISTORY

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
HEADERS  = {"User-Agent": "Mozilla/5.0 (compatible; FIN331-research/1.0)"}


def _fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def build_sp500_history() -> pd.DataFrame:
    """
    Returns DataFrame(ticker, date_added, date_removed).
    date_removed is NaT for currently active members.
    """
    html = _fetch_html(WIKI_URL)
    tables = pd.read_html(io.StringIO(html), attrs={"id": "constituents"})
    current = tables[0][["Symbol", "Date added"]].copy()
    current.columns = ["ticker", "date_added"]
    current["ticker"] = current["ticker"].str.replace(".", "-", regex=False)
    current["date_added"] = pd.to_datetime(current["date_added"], errors="coerce")
    current["date_removed"] = pd.NaT

    # Changes table (second table on the page)
    try:
        changes_tables = pd.read_html(io.StringIO(html), attrs={"id": "changes"})
        changes = changes_tables[0]
        # Flatten multi-level columns if present
        if isinstance(changes.columns, pd.MultiIndex):
            changes.columns = ["_".join(c).strip("_") for c in changes.columns]

        # Normalize column names
        changes.columns = [c.lower().replace(" ", "_") for c in changes.columns]

        # Find date, added ticker, removed ticker columns
        date_col  = next((c for c in changes.columns if "date" in c), None)
        added_col = next((c for c in changes.columns if "added" in c and "ticker" in c), None)
        removed_col = next((c for c in changes.columns if "removed" in c and "ticker" in c), None)

        if date_col and added_col and removed_col:
            changes[date_col] = pd.to_datetime(changes[date_col], errors="coerce")

            # Build removed rows
            removed = changes[[date_col, removed_col]].dropna(subset=[removed_col]).copy()
            removed.columns = ["date_removed", "ticker"]
            removed["ticker"] = removed["ticker"].str.replace(".", "-", regex=False)
            removed["date_added"] = pd.NaT

            # Merge removals into current: set date_removed for tickers no longer active
            for _, row in removed.iterrows():
                mask = current["ticker"] == row["ticker"]
                if mask.any():
                    current.loc[mask, "date_removed"] = row["date_removed"]
                else:
                    # Was removed before we started tracking — add as historical row
                    current = pd.concat([current, pd.DataFrame([row])], ignore_index=True)

    except Exception as e:
        print(f"  Warning: could not parse changes table ({e}). Using current constituents only.")

    current = current.dropna(subset=["ticker"])
    current["ticker"] = current["ticker"].str.strip()
    return current.reset_index(drop=True)


def main():
    if SP500_HISTORY.exists():
        print(f"S&P 500 history already exists ({SP500_HISTORY})")
        return

    print("Downloading S&P 500 constituent history from Wikipedia...")
    df = build_sp500_history()
    df.to_parquet(SP500_HISTORY, index=False)
    print(f"Saved {len(df):,} rows → {SP500_HISTORY}")
    print(f"  Active members: {df['date_removed'].isna().sum():,}")
    print(f"  Historical: {df['date_removed'].notna().sum():,}")


if __name__ == "__main__":
    main()
