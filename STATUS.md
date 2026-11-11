# Status memo: Checkpoint 1 (pick + proof of concept)

**What we picked and why.** We picked the *Crowded trades* seed: do stocks that many 13F institutions bought last quarter do worse the next quarter? We chose it for three reasons. The data are free and official (the SEC's structured Form 13F data sets). The question has a clear buyer, a fund risk manager. And the main pitfall, the 45-day filing lag, is a concrete look-ahead problem we can design around from day one rather than discover late. The unit of observation is stock × 13F report quarter. Our primary signal is the change in ownership breadth (Chen, Hong & Stein 2002), and the MVP is 2022Q1–2024Q4 for the 500 largest stocks.

**What the proof of concept got, and what broke.** The proof of concept downloads the 13F zips, keeps on-time original filings, and produces real stock-quarter rows (holders, change in breadth, forward return) for a handful of large stocks. `[Fill in: e.g. "For 2023Q3 we kept N manager filings; AAPL had X holders"; paste 3–5 rows from outputs/tables/sample_rows.md.]` Several things broke or surprised us along the way, and each is now handled in the code:

1. The SEC files are organized by *filing* date, not report quarter. The "2023q1" zip holds December 2022 holdings, and from 2024 the files cover odd date ranges (e.g. Dec–Feb).
2. The `VALUE` field switched from thousands of dollars to dollars for filings made on or after 3 January 2023.
3. Many filers list the same stock on several lines, which must be summed.
4. Option positions appear in the same table as shares.
5. Share counts are not split-adjusted, so a stock split makes every holder look like a buyer.
6. Yahoo Finance has no data for most delisted tickers.

**Questions for Professor Bowen.**

1. Is Yahoo Finance acceptable for returns if we disclose survivorship, or should we try to get CRSP through WRDS for the delisting returns?
2. The seed says "hedge funds pile in," but 13F covers all managers above $100M. Is all-13F-managers fine for the MVP, with a hedge-fund-only subset as a stretch?
3. Is a 12-quarter sample enough for v1, or should we extend back to 2014 now?
4. Is SPY-adjusted return an acceptable benchmark, or do you want characteristic-adjusted (size/momentum-matched) returns?
