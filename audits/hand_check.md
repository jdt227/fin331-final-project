# Hand Check — IBES Ticker Join Verification

**Purpose:** Confirm that IBES tickers map correctly to the same tickers used
in the 13F crowding data, so the join in `05_build_dataset.py` is not silently
mismatching symbols.

**Status:** Checkpoint 2 uses synthetic IBES data where IBES tickers are
already standard exchange tickers (AAPL, MSFT, etc.), so no mapping step is
needed. This audit will be completed with real WRDS data before the final
submission.

---

## Procedure (for real data)

1. Pull 10 random rows from `inputs/ibes/ibes_consensus.parquet`
2. For each `ibes_ticker`, look up the CUSIP via WRDS IBES identifier file
3. Cross-reference against `inputs/cusip_ticker_map.parquet` (OpenFIGI output)
4. Confirm tickers match; flag any discrepancies

## Checkpoint sample (synthetic data — 10 rows)

| ibes_ticker | fpedats    | eps_consensus_t | Joined ticker in final_dataset | Match? |
|-------------|------------|-----------------|-------------------------------|--------|
| AAPL        | 2022-03-31 | 1.52            | AAPL                          | ✓      |
| MSFT        | 2022-03-31 | 2.20            | MSFT                          | ✓      |
| GOOGL       | 2022-03-31 | 26.30           | GOOGL                         | ✓      |
| NVDA        | 2022-06-30 | 1.36            | NVDA                          | ✓      |
| JPM         | 2022-06-30 | 3.65            | JPM                           | ✓      |
| TSLA        | 2022-09-30 | 1.05            | TSLA                          | ✓      |
| V           | 2022-09-30 | 2.00            | V                             | ✓      |
| XOM         | 2022-12-31 | 4.45            | XOM                           | ✓      |
| PG          | 2023-03-31 | 1.44            | PG                            | ✓      |
| KO          | 2023-06-30 | 0.72            | KO                            | ✓      |

**Result:** 10/10 match (synthetic data — real check pending with WRDS data).

---

## TODO (before final submission)

- [ ] Run with real IBES data from WRDS
- [ ] Verify IBES identifier file maps to same CUSIPs as 13F filings
- [ ] Document any tickers that require manual override
