"""
Rebuild every table and figure from the raw inputs with one command.

    python run_all.py                  # full sample, 2022Q1-2024Q4, top 500 stocks
    CROWD_QUICK=1 python run_all.py    # v0 small sample: 2023 only, top 100 stocks
    python run_all.py --from 5         # re-run from step 5 onward (raw data already pulled)

Downloads are cached in data/raw/, so a second run skips them. The SEC requires
SEC_USER_AGENT to be set ("Your Name your.email@lehigh.edu") for the first download.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

STEPS = [
    "01_download_13f.py",
    "02_parse_13f.py",
    "03_universe_and_cusip_map.py",
    "04_download_prices.py",
    "05_build_dataset.py",
    "06_analysis.py",
    "07_hand_checks.py",
]

ap = argparse.ArgumentParser()
ap.add_argument("--from", dest="start", type=int, default=1, help="first step to run (1-7)")
args = ap.parse_args()

src = Path(__file__).resolve().parent / "src"
t0 = time.time()
for i, step in enumerate(STEPS, start=1):
    if i < args.start:
        continue
    print(f"\n{'=' * 70}\nStep {i}: {step}\n{'=' * 70}", flush=True)
    t = time.time()
    subprocess.run([sys.executable, str(src / step)], check=True,
                   cwd=Path(__file__).resolve().parent)
    print(f"[step {i} took {time.time() - t:.0f}s]")
print(f"\nAll steps finished in {(time.time() - t0) / 60:.1f} min. Results are in outputs/.")
