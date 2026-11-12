"""
Run the full crowded-trades pipeline from scratch.

Usage:
    python run_all.py

Each step is skipped if its output already exists (resumable).
To rerun a step from scratch, delete its output file(s) in inputs/ or outputs/.
"""
import subprocess, sys, time
from pathlib import Path

STEPS = [
    ("Step 1 — Download 13F filing index",    "code/01_get_13f_filings.py"),
    ("Step 2 — Download 13F holdings XML",    "code/02_get_holdings.py"),
    ("Step 3 — Build crowding metrics",       "code/03_build_crowding.py"),
    ("Step 4 — Pull IBES EPS consensus",      "code/get_ibes.py"),
    ("Step 5 — CUSIP→ticker + returns",       "code/04_get_returns.py"),
    ("Step 6 — Build analysis dataset",       "code/05_build_dataset.py"),
    ("Step 7 — Analysis + figures",           "code/06_analysis.py"),
]

def run_step(label: str, script: str) -> None:
    print(f"\n{'='*65}")
    print(f"  {label}")
    print(f"{'='*65}")
    start = time.time()
    result = subprocess.run([sys.executable, script])
    elapsed = time.time() - start
    if result.returncode != 0:
        print(f"\n  ✗  {script} failed (exit code {result.returncode})")
        sys.exit(result.returncode)
    print(f"\n  ✓  Done in {elapsed:.0f}s")


def main():
    root = Path(__file__).parent
    for label, script in STEPS:
        run_step(label, str(root / script))

    print(f"\n{'='*65}")
    print("  Pipeline complete!")
    print(f"{'='*65}")
    print("\nNext steps:")
    print("  1. Review outputs/  for tables and figures")
    print("  2. Launch the dashboard:  streamlit run app.py")
    print("  3. Write PROPOSAL.md using the real numbers you just produced")


if __name__ == "__main__":
    main()
