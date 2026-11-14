"""
Step 1. Download the SEC Form 13F structured data sets we need.

Input : nothing (reads the file list from config.SEC_FILES)
Output: data/raw/sec_13f/*.zip  (+ a row per file in data/raw/provenance.csv)

The SEC requires a descriptive User-Agent with contact info:
    export SEC_USER_AGENT="Jane Doe jdoe@lehigh.edu"
Files that already exist are skipped, so re-running is cheap.
Each zip is roughly 50-150 MB; the full 2022-2024 sample is on the order of 1-2 GB.
These files are git-ignored. This script recreates them.
"""
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(__file__))
import config
from common import log_provenance

config.ensure_dirs()
user_agent = os.environ.get("SEC_USER_AGENT")

files = config.sec_files_needed()
print(f"Need {len(files)} SEC 13F zip files for report quarters "
      f"{config.HOLDINGS_QUARTERS[0]}..{config.HOLDINGS_QUARTERS[-1]}")

for name in files:
    dest = config.RAW_13F / name
    url = config.SEC_BASE + name
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  exists, skipping: {name}")
        continue
    if not user_agent:
        sys.exit("Set SEC_USER_AGENT='Your Name your.email@school.edu' before downloading.")
    print(f"  downloading {url}")
    tmp = dest.with_suffix(".part")
    with requests.get(url, headers={"User-Agent": user_agent}, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    tmp.rename(dest)
    log_provenance(name, url, dest, note="SEC Form 13F structured data set")
    time.sleep(1)  # be polite: SEC fair-access limit is 10 requests/second

print("Done.")
