"""
Step 2: Download and parse the infotable XML from each 13F-HR filing.

For each filing in the quarterly index, fetches the infotable XML from EDGAR,
parses it, and saves the holdings (cik, period_end, date_filed, cusip, value_thousands).

Saves one parquet per quarter to inputs/13f_holdings/.

Auditor note: we use date_filed (not period_end) as the information date to
avoid look-ahead bias.  Holdings are public only after they are filed.
"""
import sys, time, requests, pandas as pd
import xml.etree.ElementTree as ET
from pathlib import Path
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from config import (
    EDGAR_HEADERS, REQUEST_DELAY, QUARTERS,
    INDEX_DIR, HOLDINGS_DIR, MAX_FILERS_PER_QUARTER,
)

# Common infotable filenames, tried in order before fetching the filing index
INFOTABLE_NAMES = [
    "infotable.xml",
    "InformationTable.xml",
    "informationtable.xml",
    "13fholdings.xml",
    "primary_doc.xml",
]

NS = "http://www.sec.gov/edgar/document/thirteenf/informationTable"


def accession_folder(cik: str, accession_no: str) -> str:
    """Convert accession number to URL path component (no dashes)."""
    return accession_no.replace("-", "")


def fetch_infotable_xml(cik: str, accession_no: str) -> str | None:
    """Try common infotable filenames, then fall back to the filing index."""
    base = (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/"
        f"{accession_folder(cik, accession_no)}"
    )

    for name in INFOTABLE_NAMES:
        url = f"{base}/{name}"
        try:
            r = requests.get(url, headers=EDGAR_HEADERS, timeout=20)
            if r.status_code == 200 and "<informationTable" in r.text.lower():
                return r.text
        except requests.RequestException:
            pass
        time.sleep(REQUEST_DELAY)

    # Fall back: fetch the filing index JSON to find the actual filename
    idx_url = f"{base}-index.json"
    try:
        r = requests.get(idx_url, headers=EDGAR_HEADERS, timeout=20)
        if r.status_code == 200:
            items = r.json().get("directory", {}).get("item", [])
            for item in items:
                name = item.get("name", "")
                if name.lower().endswith(".xml") and "table" in name.lower():
                    r2 = requests.get(f"{base}/{name}", headers=EDGAR_HEADERS, timeout=20)
                    if r2.status_code == 200:
                        return r2.text
    except Exception:
        pass

    return None


def parse_xml(xml_text: str) -> list[dict]:
    """Extract (cusip, value_thousands) rows from an infotable XML."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    # Try with namespace, then without
    rows = root.findall(f"{{{NS}}}infoTable")
    if not rows:
        rows = root.findall(".//infoTable")

    holdings = []
    for row in rows:
        def get(tag: str) -> str | None:
            el = row.find(f"{{{NS}}}{tag}")
            if el is None:
                el = row.find(tag)
            return el.text.strip() if el is not None and el.text else None

        cusip = get("cusip")
        if cusip and len(cusip) == 9:  # valid CUSIP length
            holdings.append(
                {
                    "cusip":           cusip,
                    "value_thousands": get("value"),
                }
            )
    return holdings


def process_quarter(year: int, qtr: int) -> None:
    out = HOLDINGS_DIR / f"holdings_{year}_Q{qtr}.parquet"
    if out.exists():
        df = pd.read_parquet(out)
        print(f"  {year} Q{qtr}: already done ({len(df):,} holdings rows)")
        return

    idx_path = INDEX_DIR / f"filings_{year}_Q{qtr}.parquet"
    if not idx_path.exists():
        print(f"  {year} Q{qtr}: index file missing — run 01_get_13f_filings.py first")
        return

    filings = pd.read_parquet(idx_path).head(MAX_FILERS_PER_QUARTER)
    all_rows = []

    print(f"\n{year} Q{qtr}: downloading {len(filings)} filings...")
    for _, row in tqdm(filings.iterrows(), total=len(filings), unit="filing"):
        xml_text = fetch_infotable_xml(row["cik"], row["accession_no"])
        if xml_text is None:
            continue
        for h in parse_xml(xml_text):
            h.update(
                {
                    "cik":        row["cik"],
                    "period_end": row["period_end"],
                    "date_filed": row["date_filed"],
                }
            )
            all_rows.append(h)

    if all_rows:
        df = pd.DataFrame(all_rows)
        df["value_thousands"] = pd.to_numeric(df["value_thousands"], errors="coerce")
        df.to_parquet(out, index=False)
        print(f"  → saved {len(df):,} holdings rows")
    else:
        print(f"  → no holdings parsed for {year} Q{qtr}")


def main():
    for year, qtr in QUARTERS:
        process_quarter(year, qtr)


if __name__ == "__main__":
    main()
