# Instructor audit: Token Ticklers (jdt227), Checkpoint 3

**Repo:** jdt227/fin331-final-project · **Audited commit:** `1d3b51b` (2026-11-21 19:53 ET, head of PR #2, branch `feat/estimate-crowding`, not merged; `main` has no commits since Checkpoint 2) · **Seed:** 9, crowded trades, as extended in PR #2 ("estimate-driven crowding") · **CP2 audit:** `audits/02_instructor_audit.md` (commit `c7eaba5`)

> Note from your human teacher: This review is generated with minimal supervision from Opus 5.5-high. It is thorough, but can be too generous at times and doesn't know my taste for what is "good". Grades it and I would assign are correlated, but noisy, ok? If you want additional feedback from _me_, you need to find me before/after/during class or during office hours for a guaranteed speedy reply. I will try to respond to emails and issues, but can not respond to student inquiries around the clock across the final weeks of class. Response times will be unpredictable, though during Thanksgiving week, I will do my best to respond quickly virtually, as in person options will be nil.

## Start here: licensed IBES data is on GitHub

### B1 · Blocking · `inputs/ibes/ibes_consensus.parquet` is licensed WRDS data, committed to a public branch

**Evidence:** Commit `e2c90a2` (2026-11-16, "feat: real IBES data + 91% CAR coverage") on `feat/estimate-crowding` (PR #2) commits `inputs/ibes/ibes_consensus.parquet`: 41,034 rows of IBES `statsum_epsus` fields (ticker, fiscal period, consensus, dispersion, analyst count, actual EPS, announcement date). An earlier, synthetic version of the same file is in `3de6f9e`. `.gitignore` doesn't cover `inputs/ibes/`.

**Why it matters:** WRDS data is licensed to Lehigh for our use. It can't be redistributed, and a file pushed to GitHub is redistributed even after you delete it in a later commit, because it stays in the history (and on the PR page).

**Fix:** Keep the file on your computer, ignore it in git, and remove it from GitHub **and** from every commit in the history. Give your coding agent this:

> `inputs/ibes/ibes_consensus.parquet` is licensed WRDS data and must not be anywhere on GitHub, including the git history. (1) Copy it to a folder outside this repo. (2) Add `inputs/ibes/*.parquet` to `.gitignore` and commit that. (3) Remove the file from every commit on every branch with `git filter-repo --invert-paths --path inputs/ibes/ibes_consensus.parquet` (install `git-filter-repo` if needed; work on a fresh clone with all branches). (4) Show me which branches changed, then force-push them (at least `feat/estimate-crowding`). (5) In a brand-new clone, confirm `git log --all -- inputs/ibes/ibes_consensus.parquet` prints nothing. (6) Copy the file back into `inputs/ibes/` locally so the pipeline still runs, and confirm `git status` doesn't show it.

After the force-push, every teammate deletes their local copy of the repo and clones it again, so the old commits aren't pushed back. GitHub can keep old commits reachable from PR #2's page, so if `https://github.com/jdt227/fin331-final-project/commit/e2c90a2` still opens after the rewrite, ask GitHub Support to purge it ("remove sensitive data" request). In the README, say that `code/get_ibes.py` pulls IBES from WRDS, and commit only derived results.

**How to show it's fixed:** On a fresh clone, `git log --all -- inputs/ibes/` is empty, `.gitignore` lists `inputs/ibes/*.parquet`, and the commit link above no longer resolves.

## Summary

First, the licensed IBES file above (B1): please fix that before anything else.

The only work after Checkpoint 2 is PR #2, so it is what this audit covers. It isn't a v1 of the pipeline audited at CP2. It's a different pipeline (13F filer counts plus IBES estimate revisions, then CARs and a random forest), and it **deletes** the CP2 code (`src/`), `audits/01_self_audit.md` and the README.

Its 1-quarter crowding lag is set correctly. Its outputs are internally consistent, and the dashboard launches. But nothing in it can be rebuilt from the repo (B2). Its sample is built by matching IBES tickers and today's S&P 500 list as if they were trading tickers, which drops about half the index non-randomly (B3).

Before Dec 1, decide as a team which pipeline is the project (B4), and make it reproducible.

## Follow-up on your Checkpoint 2 audit

Response file: not found. The CP2 findings were about the `src/` pipeline on `main`, which PR #2 removes. Each is assessed against PR #2.

| CP2 finding | Status | Evidence |
|---|---|---|
| A1 · 2023Q2 13F dollar holdings exceed market value | not verifiable | The code it concerns isn't in PR #2. The new measure counts filers (`code/03_build_crowding.py:42`, `n_filers = ("cik", "nunique")`), so dollar units can't enter it. But steps 01–03 need SEC (not rerun), and `inputs/crowding.parquet` isn't committed, so the new 13F data can't be checked |
| A2 · Numbers that don't trace; quintile convention undocumented | unaddressed | The quintile rule is now in code (`code/06_analysis.py:41-43`: `qcut` on rank within quarter, 1 = least crowded), but still not in `specs_tried.md` (no mention of "quintile") |
| A3 · Survivorship in returns at top 500 | disclosed | Worse in PR #2: the universe is today's index (`inputs/sp500_history.parquet`: 503 rows; `code/05_build_dataset.py:124` "approximate — using current membership"). Disclosed at `PROPOSAL.md:92` ("using current constituents (survivorship bias)"). See B3 |
| A4 · Real-data steps need SEC; versions unpinned | unaddressed | `requirements.txt` still uses `>=` for all 13 packages. `inputs/crowding.parquet`, `cusip_ticker_map.parquet`, `returns/` and `final_dataset.parquet` are git-ignored (`.gitignore:2-7`), so no step after 02 runs on a fresh clone (B2) |

**0 of 4 fixed, 2 still open (1 disclosed, 1 not verifiable).**

## Checkpoint 3 checks

| Check | Result |
|---|---|
| Reruns from scratch (full sample) | ❌ `code/06_analysis.py`: `FileNotFoundError … inputs/final_dataset.parquet`. `pytest`: 10 failed, 27 passed, all 10 on missing git-ignored inputs (B2) |
| Inputs have provenance | ⚠️ IBES and S&P history are committed with no pull date. 13F index and holdings aren't committed |
| Keys unique, merges validated | ✅ `validate="many_to_one"` on the crowding merge (`05_build_dataset.py:118`). ❌ the join keys themselves are wrong across sources (B3) |
| No look-ahead / survivorship | ✅ crowding from quarter Q−1 meets earnings for fiscal quarter Q (`05_build_dataset.py:10-12, 110`), after Q−1's 13F deadline. ❌ today's constituents (A3, B3) |
| LLM leakage handled | n/a |
| `specs_tried.md` complete | ⚠️ design choices logged. The quintile rule (A2) and ML hyperparameters are missing |
| Magnitudes discussed | ⚠️ `crowding_rank` −0.0176 (p = 0.043) in `regression_results.csv`. No economic translation |
| Hand checks | ⚠️ `audits/hand_check.md` exists. Not rerunnable (B2) |
| Threats to validity | ❌ `README.md` is one line ("# fin331-final-project"). Threats appear only in `PROPOSAL.md` |
| Every number traces to `outputs/` | ✅ dashboard and outputs agree ("N = 586 obs, 143 tickers" = `ml_summary.csv`) |
| Dashboard matches `outputs/` | ⚠️ Results tab yes. Intro and Explore need git-ignored `inputs/final_dataset.parquet` |

Steps not rerun by design: `code/01_get_13f_filings.py` and `02_get_holdings.py` (SEC EDGAR; the audit makes no SEC requests), and the CUSIP→ticker step in `04_get_returns.py` (`api.openfigi.com`, blocked at CP2). These are not counted against you. That later steps can't run either is B2.

## Getting ready for Dec 1

Presentations run only from URLs, with a hard cutoff at 9 minutes (10:45 section) or 10 minutes (12:10 section). Put your URL(s) in column G of the Team Projects sheet.

| Check | Result |
|---|---|
| Dashboard launches from a clean clone | ✅ `streamlit run app.py --server.headless true --server.port 8606` (venv from `requirements.txt`) on a clean export of `1d3b51b`: `/_stcore/health` returned `ok` after 3 s, and a headless browser clicked all 4 tabs with no exceptions. But Introduction and Explore show "Run the pipeline first: python run_all.py", because `inputs/final_dataset.parquet` isn't in the repo. A deployed app would show the same |
| Dashboard shows the v1 numbers from `outputs/` | ⚠️ Results tab: yes (`outputs/*.csv`). The header says "Syracuse University" |
| README links the live URL(s) | ❌ the README is empty on PR #2. `main`'s README links a GitHub Pages site for the CP2 pipeline |

**Core story for 9–10 minutes:** one question (does crowding entering earnings predict a worse reaction?); the sample and how it's linked (after B3); the quintile sort and the main regression; one robustness check. The random forest (out-of-sample R² 0.0034) is a one-line footnote.

## What holds up

- **The timing rule is right.** Crowding from calendar quarter Q−1 is matched to earnings for fiscal quarter Q (`prior_quarter` at `05_build_dataset.py:110`). Q−1's 13F filings are due 45 days after Q−1 ends, before fiscal-Q earnings are announced.
- **The crowding measure is robust to the CP2 unit problem.** Counting unique filers (`nunique` of CIK) can't be inflated by a filer reporting dollars instead of thousands.
- **Honest ML reporting.** Walk-forward CV (`TimeSeriesSplit`), with out-of-sample R² 0.0034 and directional accuracy 0.579 in `ml_summary.csv`, and no overclaiming on the dashboard.
- **27 unit tests** that don't need data pass (CAR utilities, IBES features, S&P history, analysis helpers).

## New findings

### B2 · Blocking · Nothing in PR #2 can be rebuilt from the repo

**Evidence:**
- `.gitignore:2-7` ignores `inputs/13f_index/`, `13f_holdings/`, `returns/`, `crowding.parquet`, `cusip_ticker_map.parquet` and `final_dataset.parquet`.
- On a fresh copy, `python code/06_analysis.py` exits 1 with `FileNotFoundError: …/inputs/final_dataset.parquet`.
- `python -m pytest -q tests` gives 10 failed and 27 passed. The failures are all `FileNotFoundError` on `inputs/returns/daily_returns.parquet` or the dataset (`test_dataset_builder.py`, `test_returns.py`).
- `README.md` has one line, so there are no run instructions.

**Why it matters:** None of the outputs or dashboard numbers can be reproduced, and `regression_results.csv` can't be checked against its inputs. CP2 A4 asked for exactly this ("a fresh clone with no network runs … and reproduces `outputs/`").

**Fix:** Commit the derived, shareable intermediates: `crowding.parquet` (filer counts per CUSIP-quarter, from public 13F data), `cusip_ticker_map.parquet`, and `final_dataset.parquet` (unless it contains licensed fields; and B1 for IBES). Add a `run_all.py --from 5` path. Write the README: question, run steps, data sources, threats, dashboard URL.

**How to show it's fixed:** On a fresh clone with no network, `python run_all.py --from 5` (or equivalent) reproduces `outputs/`, and `pytest` passes. I will rerun both.

### B3 · Major · The sample is linked by ticker strings that don't mean the same thing in each source

**Evidence:**
- `code/05_build_dataset.py:99-101` renames IBES's `ibes_ticker` to `ticker`, then joins it to the 13F crowding (tickers from the CUSIP map), to `sp500_history.parquet` (exchange tickers) and to yfinance returns (exchange tickers).
- IBES tickers are IBES's own identifiers, not exchange tickers. Of the 503 tickers in `inputs/sp500_history.parquet`, 246 have no IBES row under the same string, including JPM, BAC, XOM, UNH, V, MA, META and BRK-B (`inputs/ibes/ibes_consensus.parquet`, 41,034 rows). Your own `audits/hand_check.md` plans this check, but its 10-row table is still the synthetic data ("real check pending with WRDS data"), and three of its synthetic "matches" (JPM, V, XOM) have no row in the real IBES file.
- The final sample has 143 tickers (`ml_summary.csv`).
- `sp500_history.parquet` is today's 503 constituents: none of the 503 rows has a `date_removed`, and the code comment says "approximate — using current membership".
- I can't check whether any IBES ticker string matches a *different* company's exchange ticker (**not verified**: no IBES identifier table here).

**Why it matters:** Seed 9's audit list includes CUSIP→ticker mapping. Dropping about half the index by string mismatch is non-random (older, larger firms keep legacy IBES codes), and a false match would attach one firm's earnings to another firm's returns. Today's constituents add survivorship (A3).

**Fix:** Link IBES to the other sources through CUSIP (IBES `cusip`/`ncusip`), or through the WRDS IBES–CRSP link, not through ticker strings. Build the universe from point-in-time membership by quarter. Report the match rate at each join. Keep the IBES pull itself out of the repo (B1).

**How to show it's fixed:** A join-diagnostics table in `outputs/` (rows in, rows matched, by source), with JPM, BAC and XOM present; the real-data version of `audits/hand_check.md`; and a point-in-time universe rule in `specs_tried.md`.

### B4 · Major · Two pipelines, and the submitted one deletes the other and the required files

**Evidence:** `git diff --stat c7eaba5 1d3b51b` deletes `src/01`–`08`, `tests/make_fake_raw.py` and `audits/01_self_audit.md`, and replaces `README.md` with one line. `STATUS.md` on PR #2 is titled "Checkpoint 2 Status — Estimate-Driven Crowding", dated 2026-11-11, "Team: Solo". `main` still holds the CP2 pipeline (13F breadth, audited at CP2) with no later commits.

**Why it matters:** The final repo is judged by `main`. Merging PR #2 as is would remove the self-audit and the README. Not merging it leaves `main` at CP2. Readers can't tell which design, or which team, the project is.

**Fix:** Decide as a team which pipeline is the final project, and record it in `STATUS.md`. If it's PR #2, restore `audits/01_self_audit.md` and a full README, and say in `specs_tried.md` what was dropped and why. Then merge.

**How to show it's fixed:** `main` contains one pipeline, a current `STATUS.md`, the self-audit and a full README.

## How to respond

This audit is `audits/04_instructor_audit.md` in your repo. Fix what you can, then add `audits/05_audit_response.md`, replying to each **B** finding and to each CP2 finding still open (A2, A4): fixed (the commit), disputed (why), or disclosed as a limitation (where).

There's no separate deadline for this response. Keep working through these until your final deliverables are due: the final repo is audited again then.
