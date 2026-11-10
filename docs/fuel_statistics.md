# Fuel Statistics — aviation fuel price tracker

*Where to find it:* Company ▸ Financial ▸ COS/Expenses ▸ **Fuel Statistics** (works under any company, including Majestic Cargo).
*Code:* backend `backend/fuel_prices/` (own package, own `fuel_*` tables), API `backend/routers/fuel_prices.py` (`/api/fuel/*`), frontend `src/components/fuelStatistics/` and `src/services/fuelPrices.js`.
Technical detail and the full list of assumptions are in `backend/fuel_prices/README.md`; this document is the overview.

*Implementation reviewed: 2026-11-09.* This overview describes the current code; source licensing statements and historical events require their own supporting evidence.

## 1. What it does

- Tracks **jet-fuel prices** in USD per US gallon, split by **operator class**: *scheduled* (regular carriers, wholesale/contract-type prices) and *non-scheduled* (charter/general aviation, retail-type prices).
- Looks a price up by **country**, **airport (IATA code)**, region or global, and always says **which level it actually used** (for example "asked for airport MIA, answered with the US country series").
- Explains price behaviour with a **statistics layer**: descriptive statistics, volatility, seasonality, crude vs crack-spread decomposition, regression on Brent, lagged correlations, mean reversion of the crack spread, relation to EIA stocks / refinery utilization / production / exports, pass-through to airline-paid prices, retail premium and event windows.
- Never invents data: a place without observed data shows the regional/global index, a **labelled estimate** (only if you supplied an adjustment), or an explicit "no data". Non-scheduled never falls back to a wholesale price ("no retail data" instead). Statistics **refuse** (with the reason) when the data are too thin.

## 2. Requirements to work

| Requirement | Detail |
| --- | --- |
| Backend | The normal app backend (`npm run dev`, port 8012). Packages already in `requirements.txt`: `httpx`, `python-dotenv`, `APScheduler`, SQLAlchemy. No new installs. |
| Frontend | The normal Vite app (port 5173). No chart library: the chart is plain SVG. |
| EIA API key | `EIA_API_KEY=` in the backend `.env` (gitignored). Free registration at https://www.eia.gov/opendata/. Never printed, logged or committed; errors are sanitised. |
| Network | Outbound HTTPS to `api.eia.gov`, `data.bts.gov`, and `www.transtats.bts.gov`. BTS monthly requires no API key. |
| Database | Tables are created automatically at startup (`fuel_sources`, `fuel_observations`, `fuel_driver_points`, `fuel_job_runs`, `fuel_airports`, `fuel_countries`, `fuel_events`, `fuel_adjustments`). Reference data (≈8,800 airports from OurAirports, public domain; countries → IATA regions) is seeded on first start. |
| **Your sign-off** | External sources start **disabled** until you enable them in *Data coverage & sources*. Manual CSV is enabled by default. Unverified sources ask for your name, stored with the sign-off time; this does not automatically change the terms status to `verified_ok`. Restricted sources cannot be enabled. |

**First-time setup:** put the key in `.env` → restart the backend → Fuel Statistics ▸ *Data coverage & sources* ▸ **Enable…** on *U.S. Energy Information Administration (API v2)* (type your name) ▸ **Download data** (about 20 s for the full history). After that the app keeps it current by itself.

**BTS monthly setup:** enable *BTS P-12(a) monthly fuel (TranStats)*, then click **Download data** (or **Refresh** if data already exists). Alternatively, wait for the next scheduler tick. Return to *Prices & statistics* to load the monthly card. EIA credentials are not needed for BTS.

## 3. Sources

| Source | What it provides | Terms status | How it gets in |
| --- | --- | --- | --- |
| **EIA API v2** (`eia_api`) — primary | Gulf Coast jet spot (daily, weekly, monthly), Brent spot (daily, weekly, monthly), U.S. jet and distillate stocks, refinery utilization, jet production, jet exports. All 11 series IDs were confirmed against the live API. | `unverified` until you sign off. EIA's terms allow retrieving, storing and displaying the data; attribution required; no implied endorsement; no logo; do not alter content and still call it EIA's; calls may be limited (no number published). Data are public domain. | Automatic |
| **BTS annual** (`bts_socrata`) | Airline-paid fuel price per year by carrier group (cost ÷ gallons), 1990 → latest year, from data.bts.gov datasets `navd-gpqa` and `33xp-y9fx` (public domain U.S. Government). Annual only; scheduled vs non-scheduled not stated. | `unverified` until you sign off | Automatic (weekly poll) |
| **BTS monthly** (`bts_p12`) | Published monthly average price for U.S. scheduled carriers, domestic + international operations, from January 2000 onward. | Starts `unverified`; enablement records sign-off | **Automatic public HTML-table fetch**, checked daily; CSV/drop-folder fallback (see §5) |
| **IATA regional** (`iata_regional`) | Weekly regional indices (Global + 6 regions). | `unverified` — licensing not confirmed | CSV import |
| **Manual CSV** (`manual_csv`) | Any country / airport / region price you hold (including non-scheduled retail). | `verified_ok` (your data) | CSV import |
| FRED (`eia_fred`) | Copy of the EIA series. | **`restricted`** — FRED's terms bar storing its content; never used, rows purged | — |
| Platts, Argus (stubs), AirNav | Interface only / no terms found. | disabled; AirNav `restricted` (not scraped) | — |

## 4. How data stays current

- An in-process scheduler ticks hourly and once at startup, running only due jobs. Normal intervals are daily, weekly, or 28 days for monthly jobs. BTS monthly data is checked **daily**, despite its monthly reporting period.
- **The backend must be running.** Closing the browser does not stop a running backend; stopping the backend stops downloads. There is no independent background worker or Windows scheduled task in this module.
- Last-run times are saved in the database, so after downtime everything overdue runs at the next start (catch-up).
- EIA first downloads paginated history, then uses incremental requests with revision overlaps. BTS monthly fetches the entire public history table on every run to reconcile revisions. Upserts avoid duplicates; changed values replace stored values rather than creating revision-history records.
- Failed jobs record an error and scheduled retries wait at least 6 hours. Manual **Refresh** runs immediately and can bypass that scheduling delay. EIA adapter errors redact the API key.
- The *Data coverage* page shows **ok / stale / error / never run / disabled**. A job is stale after more than twice its interval plus one day without success, or when its newest point exceeds the data-age limit: 7 / 16 / 75 days for daily / weekly / monthly data. BTS uses the **75-day monthly data limit** with a daily job-health interval.
- Status is persisted as the latest state per job in `fuel_job_runs`, not a complete run history. The UI does not continuously poll for changes: reopen the view to refresh general coverage; the BTS card reloads when returning to *Prices & statistics*.

## 5. Monthly BTS automatic feed and file fallback

Once BTS monthly fuel is enabled, the scheduler checks the public `fuel.asp` history table daily. It imports published total-system USD/US gallon prices for U.S. scheduled carriers (domestic + international), reconciling the full history for revisions. The separate **BTS monthly airline-paid fuel** card shows the latest reporting month regardless of the selected location; it is a U.S. carrier benchmark, not a local or retail quote. Refresh is also available on the source row. Automatic checks require the backend to be running.

The adapter validates monthly rows and fails without importing if the page structure or values are invalid. Costs/gallons in the history table are rounded to millions, so the adapter retains the published price instead of recalculating it from rounded totals. Monthly data freshness is evaluated separately from the daily polling interval.

The implemented flow is:

1. `sources/bts_monthly.py` makes one HTTPS GET to `https://www.transtats.bts.gov/fuel.asp`. It reads the public HTML table; it does **not** download an Excel file or drive the export form.
2. Validate the scheduled-carrier heading, 11-column monthly rows, finite positive numbers, unique months, and agreement between system cost/gallons and published price within USD 0.02/gal. Annual totals, YTD and percentage-change rows are excluded.
3. Store series `bts_p12:US:scheduled` with `period_type=month`, `price_basis=airline_paid`, `quality=observed`, and country `US`. Dates use the first day of the reporting month; this is not the publication date. Provenance retains the source URL, scope, rounded cost/gallons and calculation description.
4. `GET /api/fuel/bts/monthly` returns the latest enabled monthly observation, or an explicit disabled/no-data response. The separate card is unaffected by location, class or chart-range selections.

The implementation check on 2026-11-09 returned **321 observations**, January 2000–September 2026, with September at **USD 3.86/US gal**. This is a dated verification result, not a fixed current value.

Only the scheduled total-system summary is fetched automatically. Non-scheduled airline-paid figures and individual-carrier downloads are not part of this adapter. The BTS card does not change the series selected for the main graph or add a separate monthly graph.

Manual fallback:

1. Obtain a BTS export and save/convert the relevant data to CSV; the importer accepts CSV, not Excel workbooks.
2. Put it in `backend/fuel_prices/drop/bts_p12/` together with a `column_map.json` naming its columns (copy `column_map.example.json`). Use either the aggregate rows or the individual carriers, never both (`carrier_exclude` removes aggregate rows).
3. Enable *BTS P-12(a) monthly fuel* (sign-off). Within the hour the file is imported and moved to `processed/`; an unreadable file goes to `failed/` with a `.error.txt`.
4. A **pending-data reminder** appears when the latest imported month is behind the month containing `today − 45 days`. This is an approximate expectation, not an official release calendar; automatic checks continue.

The automatic HTML-table adapter has been checked against live monthly rows. User-supplied CSV column names still require an explicit mapping.

CSV imports calculate `sum(cost) / sum(gallons)` and are labelled derived. Scheduled CSV rows share the automatic series identifier, so a subsequent automatic fetch can replace overlapping monthly values with BTS's published prices.

## 6. Importing your own prices (CSV)

`POST /api/fuel/import/csv` with `{"text": "<csv>"}` (also the *Import CSV* button on the source row). Columns: `obs_date, value, unit, geo_level, operator_class, price_basis` plus `country_iso2` / `airport_iata` / `region_code` as the level requires; optional `period_type, currency, fx_to_usd, quality, confidence`. Units: `usd_gal, usd_bbl, cts_gal, usd_mt, usd_litre, local_per_litre, local_per_gal`; local-currency units **require** `fx_to_usd`, which is stored. The whole file is validated first (one bad row rejects it, with line numbers); importing the same file twice changes nothing. IATA regional and BTS files have their own endpoints (`/import/iata`, `/import/bts`).

To get an **estimate** for a country with no observed data, add an adjustment (`POST /api/fuel/adjustments`, USD/gal added to the regional/global scheduled benchmark, with a note). The result is flagged *Estimated*, confidence 0.3, and shows its formula.

## 7. Reading the screen

- **Search** accepts a country name, ISO code or IATA code. **Scheduled / Non-scheduled / Both** toggle; range 1 year / 5 years / All.
- **Price card:** value in USD/gal (original unit shown when different), change vs 1 week / 1 month / 1 year, badges for the **level used** (Airport / Country / Region / Global) and **quality** (Observed / Estimated / Manual / Derived), source, price basis, age of the data and the source attribution.
- **BTS monthly card:** latest scheduled U.S. carrier airline-paid average, reporting month and attribution. This is a national carrier benchmark including international operations, not the selected airport's price.
- **Chart:** the main price history for the first selected class (scheduled when *Both* is selected), with an optional Brent or crack-spread line. The graph can show daily, weekly or monthly data; a BTS monthly card on screen does not mean the graph is plotting BTS.
- **Tooltip:** hover or tap to inspect the nearest original observation. Monthly series show month/year; other series show the observation date. Fuel price is displayed to three decimals in USD/US gal. The overlay value appears only when it has an observation on the same date. Focus the chart and use left/right arrows to move between observations; Escape dismisses the tooltip. The drawn line is thinned for long histories, but tooltip selection uses the original points. Daily observations are not converted into monthly averages.
- **Red dotted vertical lines:** stored event markers, not prices or forecasts. The seeded marker is labelled `2026-02-28 Strait of Hormuz closure (per EIA)`. **Its date/description remain unverified and no source URL is recorded**; the label is not evidence of verification or causation. Only events inside the chart's date range are drawn. Additional events can be stored through `POST /api/fuel/events` with date, title, category and source URL. The moving inspection cursor is separate from these event markers.
- **Statistic cards:** every card shows n, date range and quality mix, or says why it was not computed. The crude-vs-crack panel splits a price change into the Brent part and the crack-spread part (they add up exactly).
- **Data coverage & sources:** sources with terms status and sign-off, scheduled jobs with stale warnings, reminders, and which places hold observed data.

## 8. Current limits (be aware)

- Outside the US there is **no free official country or airport price** in any verified source: those places show a regional/global index, an estimate or "no data" until you import data (IATA regional, a licensed provider, or your own CSV).
- Non-scheduled (retail/FBO) prices exist only if you import them; AirNav is not scraped.
- Crack spread = Gulf Coast jet − Europe Brent (a simple spread, not a refinery margin). Driver correlations use levels of seasonal series: read the lag pattern, not one coefficient.
- Assumptions to confirm: 7.9 barrels per metric ton (`FUEL_BBL_PER_MT`), the country → IATA region mapping, BTS annual data scope, TranStats column names. No dated FX table yet (rates are given per CSV row).
- If the app becomes multi-user, review each source's redistribution terms first.

## 9. Tests and checks

Run `python -m pytest backend/tests/test_bts_monthly.py backend/tests/test_fuel_prices.py` for conversions, fixture adapters, pagination/key redaction, resolution, estimates, imports, scheduling, freshness and statistical known answers. The implementation validation on 2026-11-09 passed **52 tests**; this count is a dated result.

The monthly fixture covers August/September 2026. Tests cover published system price, invalid layouts/values, idempotence, source disabling and monthly freshness. The live monthly API returned September 2026 at USD 3.86/gal. `npm run build` passed after the card and tooltip changes; browser interaction checks are separate from the build.

## 10. How the module fits together

`backend/main.py` starts `scheduler.py` → `service.py` selects enabled/due jobs → source adapters fetch and validate observations → the service upserts `fuel_*` tables → API routes serve prices, series, statistics and coverage → React renders cards and the SVG chart.

The price resolver tries airport → country → region → global, then an explicitly configured estimate. Series selection is separate: it uses the requested geography and prefers the finest available period. Consequently a price card can show a geographic fallback while the main chart has no local series. Disabling a source hides its stored observations from normal queries without deleting them (restricted-source cleanup is a separate startup operation).

The statistics service reads enabled data and returns calculations with quality/sample metadata or a refusal reason. The UI shows descriptive statistics, volatility, seasonality, regression, lags, half-life, events and driver/decomposition panels; pass-through and retail-premium calculations are also available through the statistics API. No automatic forecast or purchasing decision is generated.

## 11. Troubleshooting

| Symptom | What to check |
| --- | --- |
| BTS card says disabled | Enable BTS monthly in *Data coverage & sources*; return to *Prices & statistics*. |
| BTS card has no data | Use **Download data/Refresh** and inspect the source/job error. Confirm backend and outbound network access. |
| Latest month is older than today | Data is monthly and published with a lag. Compare reporting month and job status; a successful fetch need not contain a new month. |
| BTS layout/validation error | Existing observations remain available. Inspect the official table and update the parser if its structure changed; mapped CSV is a fallback. |
| CSV remains in the drop folder | Confirm source enablement and valid `column_map.json`; a missing/invalid map prevents processing. Inspect `failed/` and `.error.txt` for rejected files. |
| Card updates but graph differs | The BTS card is independent. Check the graph's series ID, reporting period and selected class. |
| Scheduled updates stop | Keep the backend running. Overdue work resumes at startup; this module does not run while the backend is stopped. |
