# Aviation fuel price tracker (`backend/fuel_prices/`)

Independent module: tracks jet-fuel prices by operator class (`scheduled` / `non_scheduled`) and place (airport IATA, country ISO-2, region, global), and explains
price behaviour. API under `/api/fuel/*` (`backend/routers/fuel_prices.py`); UI in COS/Expenses ▸ **Fuel Statistics** (`src/components/fuelStatistics/`).
Prices are stored canonically as **USD per US gallon**; the original value/unit is kept on every row. Non-price drivers (stocks, utilization, production, exports) keep
their own unit in `fuel_driver_points`.

## Sources and terms status

| id | what | terms_status | how data gets in |
| --- | --- | --- | --- |
| `eia_api` | **EIA API v2** (primary): Gulf Coast jet spot daily/weekly/monthly, Brent daily/weekly/monthly, U.S. jet and distillate stocks, refinery utilization, jet production, jet exports | `unverified` until you sign off in the UI (terms read, no blocker found — see below) | automatic, key in `EIA_API_KEY` (`.env`) |
| `bts_socrata` | BTS P-12(a) **annual** fuel cost / gallons by carrier group from data.bts.gov (datasets `navd-gpqa`, `33xp-y9fx`; public domain U.S. Government) | `unverified` until you sign off | automatic (weekly poll) |
| `bts_p12` | BTS P-12(a) **monthly** (TranStats fuel table) | `unverified` until you sign off | **automatic public history table**, checked daily; CSV/drop folder fallback |
| `iata_regional` | IATA-Platts regional weekly index | `unverified` — licensing not confirmed | CSV import (`POST /import/iata`) |
| `manual_csv` | your own country/airport/region data | `verified_ok` (your data) | `POST /import/csv` |
| `eia_fred` | FRED copy of the same series | **`restricted`** — FRED's terms bar scraping and storing its content; the adapter is unregistered, rows are purged at startup | — |
| `platts_stub`, `argus_stub` | paid providers, interface only | `unverified`, cannot be enabled | — |
| `airnav_stub` | AirNav FBO prices: no terms/API found, **not scraped** | `restricted`, cannot be enabled | — |

Every source starts **disabled** except `manual_csv`. Enabling an unverified source requires `signed_off_by` (your name), stored with the time. A disabled source's
observations vanish from prices, charts, coverage and statistics (they stay in the tables).

### EIA terms (https://www.eia.gov/opendata/terms-of-service.php, read 2026-11-09)
Use: you may build a service that searches, displays, analyzes, retrieves EIA data. Attribution: name "EIA" / "U.S. Energy Information Administration" as the source (the copyright page
https://www.eia.gov/about/copyrights_reuse.php suggests "Source: U.S. Energy Information Administration"); do not imply endorsement; the EIA logo needs written permission (not used);
do not modify content and still claim it is EIA's (derived values here are labelled as this app's own). Limits: EIA may limit calls and block use that tries to exceed or circumvent them;
**no numeric rate limit is published** — the adapter pages at 5000 rows, pauses 0.6 s between calls and backs off on 429/5xx. Data are US-government public domain.

### EIA series (all confirmed by querying the API route listings and pulling rows on 2026-11-09)
`petroleum/pri/spt`: `EER_EPJK_PF4_RGC_DPG` jet (daily 9,201 rows from 1990-04-02, weekly 1,909, monthly 439), `RBRTE` Brent (daily 10,013 from 1987-05-20, weekly 2,060, monthly 474) ·
`petroleum/stoc/wstk`: `WKJSTUS1` jet stocks, `WDISTUS1` distillate stocks (weekly, 2,301 rows from 1982-08-20) · `petroleum/pnp/wiup`: `WPULEUS3` refinery utilization (1,879 rows from 1990-11-02) ·
`petroleum/pnp/wprodrb`: `WKJRPUS2` jet production (2,301 rows) · `petroleum/move/wkly`: `WKJEXUS2` jet exports (857 rows from 2010-06-04). All U.S. national; no PADD split is loaded.

### BTS findings
- data.bts.gov (Socrata) has **annual** P-12(a) datasets only (cost, consumption, average cost, efficiency by carrier group, 37 rows, plus a part-year row that is skipped). No monthly P-12(a), no
  scheduled/non-scheduled split. Used by `bts_socrata` (operator class `unspecified`).
- The monthly table lives only on TranStats (https://www.transtats.bts.gov/fuel.asp, "Airline Fuel Cost and Consumption (U.S. Carriers - Scheduled)"): a POST form with no file URL or API.
  `www.bts.gov`, `transportation.gov` answer automated clients with 403 (so their terms pages — https://www.bts.gov/ntl/policies, https://www.transportation.gov/web-policies — could not be read
  by script), `transtats.bts.gov/robots.txt` returns an error page (no rules published). The public `fuel.asp` history table is retrievable by HTTP GET (verified 2026-11-09); `sources/bts_monthly.py` imports scheduled total-system monthly prices automatically. The interactive export is not needed for this feed. CSV/drop folder remains a fallback.

## Scheduling (`scheduler.py`, `service.refresh_due`)
APScheduler (the app's existing pattern) ticks hourly and once at startup. Each source job runs on its own rhythm: daily series daily, weekly weekly, monthly monthly (`INTERVAL_DAYS`).
Last-run times live in `fuel_job_runs`, so after downtime everything overdue runs at the next startup (catch-up). First run backfills full history (paginated); later runs fetch only
from the newest stored point minus an overlap (revisions are picked up); upserts are idempotent. A failed job is retried no sooner than 6 h later; failures are stored (sanitised) and never crash the app.
The Data coverage page lists every job with status (`ok` / `stale` / `error` / `never_run` / `disabled`): stale = job not succeeded for >2 intervals, or newest data older than 7 / 16 / 75 days (daily / weekly / monthly).
**BTS drop folder:** put the monthly CSV in `drop/bts_p12/` with a `column_map.json` (see `column_map.example.json`); the hourly tick imports it (needs `bts_p12` enabled), moves it to `processed/`
(or `failed/` + `.error.txt`). A reminder shows in the UI while the newest imported month is older than the month TranStats should have published (~45 days after month end).

## Resolution (`resolve.get_price`)
airport → country → region → global (observed only), then a labelled **estimate** (regional/global scheduled benchmark + a country adjustment you added in
`fuel_adjustments`, confidence 0.3, formula shown). The answer always carries `geo_level_requested` and `geo_level_used`, and the source attribution. `non_scheduled` never falls back to a
wholesale price: it answers `no_retail_data` (the scheduled price appears only as a separate `scheduled_reference`).

## Statistics (`stats/`)
descriptive, volatility, seasonality, decomposition (jet = Brent + crack), regression on Brent, lagged correlations (-4..8 weeks), crack half-life (AR(1)), crack vs each EIA driver
(`drivers`, or `inventories?driver=jet_stocks|distillate_stocks|refinery_util|jet_production|jet_exports`, lags 0..8 weeks, driver leading), pass-through (spot → BTS monthly, lags 0..6 months),
retail premium, event windows. Each result has n, date range and quality mix; thin or missing data returns `{"status": "refused", "reason": ...}`.

## How to
- **Add a source:** add a row to `SEED_SOURCES` in `sources/__init__.py`; for an automatic one write an adapter (`jobs()` + `fetch_job(key, since)`, no DB access, secrets only from env vars)
  and register it in `ADAPTERS`; add a parser test with a saved fixture. Re-seeding refreshes metadata of existing rows but never downgrades a status you signed off.
- **Import CSV:** `POST /api/fuel/import/csv {"text": "..."}`; columns are listed at the top of `sources/csv_import.py`. Whole file validated first; re-importing is a no-op.
  Non-USD units need an `fx_to_usd` column, which is stored with the row.
- **Add an event:** `POST /api/fuel/events` (seeded: 2026-02-28 Strait of Hormuz closure, per EIA — as you stated; no URL recorded).

## Known gaps / assumptions (not verified)
- No free official country- or airport-level jet price outside the US exists in any source verified; those places show region/global, an estimate, or "no data".
- `BBL_PER_METRIC_TON = 7.9` (config, env `FUEL_BBL_PER_MT`) is an assumption to confirm against IATA's published pairs.
- The country → IATA region mapping (`geo.py`) is my placement, not IATA's list.
- The TranStats monthly CSV's column names are not verified (needs a real download); hence the explicit `column_map.json`. Avoid double counting aggregate rows (`carrier_exclude`).
- The annual BTS datasets do not say whether non-scheduled flying is included.
- The jet crack spread is jet − Brent (Gulf Coast spot vs Europe Brent), not a refinery margin. Driver correlations are on levels of seasonal series; read the lag pattern, not one number.
- FX: no dated FX table yet — rates are supplied per row (`fx_to_usd`) and stored.
- Airports: OurAirports (public domain), trimmed to rows with an IATA code, bundled in `data/airports.csv`.
- If the app becomes multi-user, check each source's redistribution terms first.

### Monthly BTS automatic feed
`bts_p12` now uses `BtsMonthlyAdapter`: one daily GET of the public history table, full-history reconciliation, strict row validation, and published USD/US gallon values. `GET /api/fuel/bts/monthly` returns the latest enabled scheduled airline-paid observation for the separate dashboard card. It is a U.S. carrier benchmark, not a selected-airport quote. Monthly data age limits apply even though checks run daily. Existing source enablement/sign-off is preserved.
