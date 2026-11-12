"""
Step 1: Download SEC EDGAR quarterly index and extract 13F-HR filing metadata.

For each quarter in config.QUARTERS, fetches the EDGAR company.idx file and
keeps only 13F-HR rows.  Saves one parquet per quarter to inputs/13f_index/.

Output columns:
  company | cik | date_filed | accession_no | period_end
"""
import sys, time, re, requests, pandas as pd
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from config import EDGAR_HEADERS, REQUEST_DELAY, QUARTERS, INDEX_DIR

# The company.idx file is fixed-width (not pipe-delimited).
# This regex matches any line where the form type field is exactly "13F-HR".
_ROW_RE = re.compile(
    r'^(.+?)\s{2,}(13F-HR)\s+(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(edgar\S+)',
    re.MULTILINE,
)


def infer_period_end(filing_date: str) -> str:
    """
    Map a 13F filing date to the quarter-end it covers.
    13Fs are due 45 days after quarter end:
      Q1 (Mar 31) → file by May 15
      Q2 (Jun 30) → file by Aug 14
      Q3 (Sep 30) → file by Nov 14
      Q4 (Dec 31) → file by Feb 14 of next year
    """
    dt = pd.to_datetime(filing_date)
    m, y = dt.month, dt.year
    if m <= 2 or (m == 2 and dt.day <= 14):
        return f"{y - 1}-12-31"
    elif m <= 5:
        return f"{y}-03-31"
    elif m <= 8:
        return f"{y}-06-30"
    elif m <= 11:
        return f"{y}-09-30"
    else:
        return f"{y}-12-31"


def download_quarter_index(year: int, qtr: int) -> pd.DataFrame:
    url = (
        f"https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{qtr}/company.idx"
    )
    r = requests.get(url, headers=EDGAR_HEADERS, timeout=60)
    r.raise_for_status()

    rows = []
    for m in _ROW_RE.finditer(r.text):
        company, _, cik, date_filed, filename = m.groups()
        accession_no = filename.split("/")[-1].replace(".txt", "")
        rows.append(
            {
                "company":      company.strip(),
                "cik":          cik.lstrip("0") or "0",
                "date_filed":   date_filed,
                "accession_no": accession_no,
                "period_end":   infer_period_end(date_filed),
            }
        )
    return pd.DataFrame(rows)


def main():
    total = 0
    for year, qtr in QUARTERS:
        out = INDEX_DIR / f"filings_{year}_Q{qtr}.parquet"
        if out.exists():
            df = pd.read_parquet(out)
            print(f"  {year} Q{qtr}: already downloaded ({len(df)} filers)")
            total += len(df)
            continue

        print(f"Downloading {year} Q{qtr} index...", end="", flush=True)
        try:
            df = download_quarter_index(year, qtr)
            df.to_parquet(out, index=False)
            print(f" {len(df)} 13F-HR filers")
            total += len(df)
        except Exception as e:
            print(f" ERROR: {e}")
        time.sleep(REQUEST_DELAY)

    print(f"\nTotal 13F-HR filings indexed: {total:,}")


if __name__ == "__main__":
    main()
