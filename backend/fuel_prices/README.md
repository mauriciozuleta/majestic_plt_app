# Aviation fuel price tracker (`backend/fuel_prices/`)

Independent module: tracks jet-fuel prices by operator class (`scheduled` / `non_scheduled`) and place (airport IATA, country ISO-2, region, global), and explains
price behaviour. API under `/api/fuel/*` (`backend/routers/fuel_prices.py`); UI in COS/Expenses ▸ **Fuel Statistics** (`src/components/fuelStatistics/`).
Prices are stored canonically as **USD per US gallon**; the original value/unit is kept on every row.

## Sources and terms status

| id | what | terms_status | how data gets in |
| --- | --- | --- | --- |
| `eia_fred` | US Gulf Coast jet spot (daily + monthly) and Brent, EIA series via FRED's public CSV (no key; robots.txt allows it, 1 s crawl delay) | `unverified` — read https://fred.stlouisfed.org/legal/ before enabling | automatic refresh (daily frequency) |
| `bts_p12` | BTS Form 41 P-12(a) airline-paid price, scheduled and non-scheduled, US | `unverified` | file import (`POST /import/bts`) |
| `iata_regional` | IATA-Platts regional weekly index | `unverified` — licensing not confirmed | CSV import (`POST /import/iata`) |
| `manual_csv` | your own country/airport/region data | `verified_ok` (your data) | `POST /import/csv` |
| `platts_stub`, `argus_stub` | paid providers, interface only | `unverified`, cannot be enabled | — |
| `airnav_stub` | AirNav FBO prices: no terms/API found, **not scraped** | `restricted`, cannot be enabled | — |

Every source starts **disabled** except `manual_csv`. Enabling an unverified source requires `signed_off_by` (your name), stored with the time. A disabled source's
observations vanish from prices, charts, coverage and statistics (they stay in the table).

## Resolution (`resolve.get_price`)
airport → country → region → global (observed only), then a labelled **estimate** (regional/global scheduled benchmark + a country adjustment you added in
`fuel_adjustments`, confidence 0.3, formula shown). The answer always carries `geo_level_requested` and `geo_level_used`. `non_scheduled` never falls back to a wholesale
price: it answers `no_retail_data` (the scheduled price appears only as a separate `scheduled_reference`).

## Statistics (`stats/`)
descriptive, volatility (weekly log-returns, rolling, calm vs shock), seasonality, decomposition (jet = Brent + crack), regression on Brent, lagged correlations
(-4..8 weeks), crack half-life (AR(1)), crack vs inventories (needs a loaded driver series), pass-through (spot → BTS, lags 0..6 months), retail premium, event windows.
Each result has n, date range and quality mix; thin data returns `{"status": "refused", "reason": ...}`.

## How to
- **Add a source:** add a row to `SEED_SOURCES` in `sources/__init__.py`; for an automatic one write an adapter (`fetch(since) -> list[Observation]`, no DB access, secrets only
  from env vars) and register it in `ADAPTERS`; add a parser test with a saved fixture.
- **Import CSV:** `POST /api/fuel/import/csv {"text": "..."}`; columns are listed at the top of `sources/csv_import.py`. The whole file is validated first; re-importing is a no-op.
  Non-USD units (`local_per_litre`, `local_per_gal`) need an `fx_to_usd` column, which is stored with the row.
- **Add an event:** `POST /api/fuel/events` (seeded: 2026-02-28 Strait of Hormuz closure, per EIA — as you stated; no URL recorded).

## Known gaps / assumptions (not verified)
- No free official country- or airport-level jet price outside the US exists in any source verified; those places show region/global, an estimate, or "no data".
- `BBL_PER_METRIC_TON = 7.9` (config, env `FUEL_BBL_PER_MT`) is an assumption to confirm against IATA's published pairs (the IATA importer reports the implied value).
- The country → IATA region mapping (`geo.py`) is my placement, not IATA's list.
- BTS P-12(a) column names were not verifiable; the importer detects `…GALLONS`/`…COST` columns with SCHED/NONSCHED in the name, or take `column_map`.
- EIA inventory/refinery series (jet stocks, utilization, exports) are **not wired** (need the EIA API key and confirmed series IDs); the inventory statistic refuses until a driver
  series `jet_stocks` etc. exists. The jet crack spread is jet − Brent, not a refinery margin.
- FX: no dated FX table yet — rates are supplied per row (`fx_to_usd`) and stored.
- Airports: OurAirports (public domain), trimmed to rows with an IATA code, bundled in `data/airports.csv`.
- If the app becomes multi-user, check each source's redistribution terms first.
