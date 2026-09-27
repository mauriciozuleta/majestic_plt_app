# Market Sizing Methodology (SAM / TAM)

This document explains, in plain terms, how every market-sizing number in **Market Analysis ▸ Market Size** is
produced, so that a reader who did not build these features can tell, for any number on screen, whether it is real
reported trade data or a model's output, and why.

## Why this document was renamed, and why the tab was relabeled

The feature originally built here (and originally documented as `TAM_METHODOLOGY.md`) was labeled "TAM" — but what
it actually computes is **Comtrade import demand summed across only the countries and categories this app
actively tracks in Commercial Structure**. That is not TAM. By definition:

- **TAM (Total Addressable Market)** is the *total* demand that exists everywhere — every country in the world,
  whether or not this app (or the business it supports) has any presence or plan to address it.
- **SAM (Serviceable Available Market)** is the slice of that total demand you've actually chosen, or are able, to
  address — in this app's case, the countries and categories tracked in Commercial Structure.

What this app had built and called "TAM" is, by that definition, actually **SAM**: it was already scoped to this
app's own tracked countries, never claiming to cover global demand. The tab has been relabeled accordingly — the
estimation layer and every underlying calculation are unchanged; only the label moved from TAM to SAM. A **new,
separate TAM tab** now sits where the mislabeled one used to be conceptually — real TAM (unscoped, worldwide import
demand for a category, summed across every UN Comtrade reporting country — the method already verified: omit
`reporterCode`, `partnerCode=0`, sum `primaryValue` across every returned row) is now built too, see Part 2.

Both tabs originally had their own Overview/Custom sub-tabs; Custom was always a stub on both, and has since been
**removed entirely** (see Part 3) — with only one real sub-tab left on either, both tabs now render their Overview
content directly, no nested tab bar.

---

## Part 1 — SAM (built)

There are exactly three families of number shown on **Market Size ▸ SAM ▸ Overview**, and they are never blended
into one figure without saying so:

1. **Confirmed** — a real, reported UN Comtrade (or discovered fallback-source) import total.
2. **Bilateral** (a subset of Confirmed) — a real reported figure, but only covering trade with one partner
   country, not the country's total trade with the world.
3. **Estimated** (opt-in, off by default) — a modeled prediction, never a reported figure, shown only when a
   viewer explicitly turns on "Include estimated values (modeled)".

### 1.1 Which categories qualify ("green" categories)

SAM Overview only ever shows HS 2-digit chapters that have **real product data** behind them — chapters this
company actually has classified products in, not the full HS reference tree. This is computed on the frontend by
`buildCategoryCoverage()` (`src/services/productPortfolio.js`): every product across every source (Colombia and
USA's built-in pipelines, plus any custom source added in Settings ▸ Product analysis sources) that has been
confidently classified to a real HS code rolls up to its 2-digit chapter. Only chapters with at least one such
classified product qualify — these are the "green" categories elsewhere in the app (Available Categories), and
`Object.keys(coverage)` from that function is exactly the chapter list SAM Overview asks the backend about.

A product that hasn't been classified yet (background classification is still running) simply doesn't count yet —
it'll appear once classification catches up. This chapter-qualification step has nothing to do with trade data;
it only decides *which* chapters SAM Overview bothers asking Comtrade about at all — and it is exactly what makes
this SAM rather than TAM: it's scoped to what this app's own tracked portfolio actually deals in, not to every HS
chapter that exists.

### 1.2 Confirmed figures — how they're pulled and summed

For every qualifying chapter, in every region (`GET /api/trade/sam-overview`, `backend/routers/comtrade.py`'s
`sam_overview`):

- For each active country in that region, the backend resolves that **country's own** most-recently-reported year
  (tried newest-first, walked backward up to 6 years — `_resolve_year_and_rows`) and fetches its HS 2-digit chapter
  totals for that year (`backend/trade_sources/fetch.py`'s `fetch_categories`, which dispatches to either UN
  Comtrade directly or a discovered fallback source per country — see `CountryReferenceCatalog.trade_data_source`).
- If a country has **no data at all** for a chapter (never reported it, or Comtrade has no data for that country in
  any of the probed years), that country is **excluded from that chapter's total entirely** — it is never counted
  as a zero. This matters: a category's total is the sum of only the countries that actually had something to
  report, not "should have reported but didn't."
- If **every** country in a region has nothing for a chapter, that chapter simply doesn't appear for that region at
  all in the confirmed view — an empty category is left out, never shown as a hollow $0 row.
- A country whose only available data is **bilateral** (only trade with one specific partner, not its total trade
  with the world — flagged via `CountryReferenceCatalog.trade_data_coverage == 'bilateral'`, set once by this
  app's own source-discovery process) still contributes its figure to the total, but that figure — and the total
  it feeds — is tagged with the amber "Bilateral" badge, both on the category's own total row and on that
  country's own breakdown row. A mixed-source total (some countries total coverage, one bilateral) is never shown
  with the same unqualified confidence as an all-total-coverage one.
- A country sourced from the US Census/FRED fallback tier (`us_census_fred`) returns a single pseudo-row
  (`hs_code: 'TOTAL'`) that never matches a real 2-digit chapter code, so it never contributes to any chapter total
  here — a known, documented limitation of that fallback tier, not a bug.
- Every real Comtrade figure quoted anywhere in this app (SAM's own confirmed figures included) passes through
  the shared duplicate-row guard described in full in §2.6 (Part 2) below — a bug found and fixed while building
  Global TAM, not something specific to it. If you're only reading Part 1, the short version: it was already
  correct for every country tested against it before this fix, but wasn't guaranteed to be for every country in
  general (see §2.6) — this has since been closed.

**In short: Confirmed = a real, reported figure for a real country, for a real year, from either UN Comtrade or a
discovered fallback source — summed only across the countries this app tracks that actually had one. This is the
"serviceable" scope, not the whole world — see Part 2 for what would make it TAM instead.**

### 1.3 Estimated figures — the opt-in layer

Turned on only via the "Include estimated values (modeled)" checkbox on the Overview tab, off by default. Fetches
a **separate** endpoint (`GET /api/trade/sam-overview-estimates`) only when switched on — the default page load
never calls the World Bank API or runs a regression.

#### 1.3.1 What "confirmed" means for training data (stricter than what's shown above)

For fitting a model, a country only counts as "confirmed" if it has a **true UN Comtrade figure, with total
(non-bilateral) coverage** for that specific chapter — `trade_data_source in (None, 'comtrade')` and
`trade_data_coverage != 'bilateral'`. A bilateral-coverage country, even though it's shown as a real (badged)
number in the confirmed view above, is deliberately **excluded from training data** — it's a real number, but a
partial one, and letting a model learn from a partial figure as if it were a complete one would compound one
uncertainty (missing coverage) on top of another (a modeled fit). This is a stricter set than "has any SAM figure"
on purpose.

#### 1.3.2 Which countries can be estimated (the "gap" set)

A country is only ever a candidate for estimation if it has **no existing row at all** for that chapter — not a
true-Comtrade figure, and not even a bilateral one. Whether or not UN Comtrade tracks the country at all does not
matter; a country UN Comtrade has never covered is exactly the kind of gap this feature exists to estimate for.

**A country that already has any real figure — confirmed or bilateral — is never estimated, never overridden, and
never second-guessed.** Estimation only ever fills a genuine gap.

#### 1.3.3 Predictors: population and GDP per capita

For every country in every region (regardless of whether it has confirmed data), the backend fetches from the
World Bank Indicators API (free, no key required):

- **Population** — indicator `SP.POP.TOTL`
- **GDP per capita (current US$)** — indicator `NY.GDP.PCAP.CD`

Request shape (confirmed against the live API): `GET https://api.worldbank.org/v2/country/{ISO2}/indicator/{indicator}?format=json&mrnev=1`
— the World Bank API accepts **ISO alpha-2** country codes directly (e.g. `US`, `PH`, `CO`), which is exactly what
this app's own `CountryReferenceCatalog.country_code` already stores, so no ISO2→ISO3 translation is needed
anywhere in this pipeline. Several countries can be requested in one call by joining codes with a semicolon
(e.g. `US;PH;CO`), which this app uses to batch requests.

`mrnev=1` asks for each country's **most recent non-empty value** — population and GDP per capita are resolved
**independently**: a country can have a newer population figure than GDP-per-capita figure, or vice versa (seen
live: Saint Martin's population resolved to 2025 while its GDP per capita resolved to 2021). Every figure shown in
this app carries the actual year it came from for exactly this reason.

These are per-country, category-independent facts — fetched **once** per set of countries and reused across every
category's regression, never refetched per category. Each `(indicator, country)` result is cached indefinitely
(`backend/trade_sources/worldbank.py`, via the same `snapshot_store` mechanism `backend/comtrade/client.py`
already uses), on the same "a published figure doesn't change" reasoning — a real network failure is never
cached, only a genuine "no data for this country" result is.

#### 1.3.4 The regression itself

Implemented in `backend/estimation/regression.py` with plain `numpy` least-squares — no new ML dependency (numpy
is already a dependency of this project).

For a given category, once the confirmed (§1.3.1) training set is gathered:

1. **Minimum sample guardrail: at least 5 confirmed countries required.** Two predictors (population, GDP per
   capita) need enough rows to mean anything. Below 5, **no model is fit at all** — the category instead reports:
   *"Not enough confirmed data points to estimate this category (X of 5 minimum)."* — shown in place of an
   estimate, never as a silently missing row, whenever the toggle is on.
2. If the minimum is met, **both** forms are fit and compared:
   - **Linear:** `import_value ~ 1 + population + gdp_per_capita`
   - **Log-log:** `log(import_value) ~ 1 + log(population) + log(gdp_per_capita)` (skipped only if any training
     value, population, or GDP-per-capita is non-positive — never the case for real trade/population/GDP figures)
   - Both are fit via ordinary least squares (`numpy.linalg.lstsq` against the normal equations — no external
     solver).
3. **R² is computed for both forms on their own scale**, and whichever fits better is kept. The category's result
   records which form ("linear" or "log-log") was actually used, alongside its R².
4. **Fit-quality guardrail: R² < 0.5 → every estimate from that model is marked "low confidence."** The model is
   still applied and its estimates are still shown when the viewer has opted in, but every one of those estimates
   carries a visually distinct treatment (a different badge color, "Estimated · Low Confidence", not merely a
   tooltip) from a normal-confidence model's estimates.
5. The fitted model is applied only to the **gap** set (§1.3.2) — never to a country already in the training set,
   never to a country with any existing confirmed or bilateral figure — using that specific country's own real
   population and GDP-per-capita. A prediction is clamped at $0 (never shown as a negative market).

#### 1.3.5 What's shown on screen when the toggle is on

- **Category total:** two numbers, always side by side, never combined into one: **"Confirmed: $X"** (exactly the
  figure from §1.2, unchanged) and **"Confirmed + Estimated: $Y"** (§1.2's figure plus the sum of every gap
  country's prediction for that category). The second number carries a "Modeled" (or "Modeled · Low Confidence")
  badge.
- **Per-country breakdown:** confirmed and bilateral countries appear exactly as in the confirmed-only view.
  Estimated countries appear as additional rows, tagged "Estimated" (blue) or "Estimated · Low Confidence" (red,
  dashed outline) — a genuinely different color per state, not a shared badge with different text. Clicking an
  estimated row expands a detail panel with **full transparency**: the model's method and R², the exact list of
  countries whose confirmed data trained it, and that specific country's own population/GDP-per-capita inputs
  (with each input's own year).
- **Guardrail categories:** a qualifying chapter that fails the minimum-sample guardrail (§1.3.4 step 1) — whether
  or not it already has a confirmed total — shows the guardrail explanation next to whatever confirmed figure
  exists (or a $0 confirmed figure, if the chapter had zero confirmed contributors anywhere in that region), never
  a missing row.

#### 1.3.6 Four visual states, not three

| State | Badge | Color |
|---|---|---|
| Confirmed (total coverage) | none | plain text |
| Confirmed (bilateral-only) | "Bilateral" | amber |
| Estimated, normal confidence (R² ≥ 0.5) | "Estimated" / "Modeled" | blue |
| Estimated, low confidence (R² < 0.5) | "Estimated · Low Confidence" / "Modeled · Low Confidence" | red, dashed outline |

### 1.4 What SAM explicitly does not do

- SOM is untouched — unaffected by any of the above (TAM's Overview tab is now built, see Part 2; both tabs'
  Custom sub-tab has been removed, see Part 3).
- An estimate is never written to the database or persisted as if it were confirmed data. It exists only in the
  API response of `/api/trade/sam-overview-estimates`, computed fresh on every call (subject only to the World
  Bank indicator cache in §1.3.3, which caches inputs, never predictions), and only ever rendered inside SAM
  Overview. This is still true after Part 3's persistence build: the CONFIRMED figures (§1.2) are what gets
  persisted, never the estimated layer — see §3.4.
- Nothing outside SAM Overview reads or depends on an estimate. A future SOM build — or the real TAM build in
  Part 2 — must not silently consume an estimated figure as if it were confirmed; it would need to carry the same
  confirmed-vs-estimated distinction forward explicitly.
- A country/category pair that already has confirmed (or bilateral) data is never estimated, under any
  circumstance.
- The "Include estimated values (modeled)" checkbox now defaults to **checked** (previously unchecked) — the
  estimates fetch (`sam-overview-estimates`) now kicks off automatically on the Overview tab's first render
  instead of waiting for a click. Nothing else about how the estimation layer works changed; see §3.4 for why this
  doesn't affect what gets persisted.

### 1.5 Where the SAM code lives

- `backend/trade_sources/worldbank.py` — World Bank API client (population + GDP per capita, batched, cached).
- `backend/estimation/regression.py` — the regression itself (fit + predict), pure numpy.
- `backend/routers/comtrade.py` — `sam_overview` (confirmed, §1.2, now persisted — see Part 3) and
  `sam_overview_estimates` (estimated, §1.3, never persisted), plus the shared `_region_chapter_country_data`
  helper that computes each chapter's confirmed/gap country sets.
- `src/services/globalTradeData.js` — `fetchSamOverview` / `fetchSamOverviewEstimates` / `fetchSamOverviewSummary`.
- `src/components/marketAnalysis/SamPanel.jsx` — the SAM tab's Overview content (no more Custom sub-tab, no nested
  tab bar — see Part 3), including the toggle (now checked by default) and the merge logic that combines the
  confirmed and estimated responses without ever blending their numbers.
- `src/components/marketAnalysis/MarketAnalysisView.css` — the four badge states (`.market-analysis__bilateral-badge`,
  `.market-analysis__estimated-badge`, `.market-analysis__estimated-badge--low-confidence`) and the dual-total layout
  (`.sam-overview__dual-total`).

---

## Part 2 — TAM ▸ Overview (built)

**TAM = total global import demand for a category, unscoped to any particular tracked country set** — i.e. every
country UN Comtrade has a reporter for, not just the countries active in this app's Commercial Structure. This is
the "Overview" sub-tab under **Market Size ▸ TAM**; "Custom" is still a stub, same modular approach SAM's own
Custom tab already uses.

### 2.1 Same qualifying-category filter as SAM, reused rather than re-derived

TAM Overview pulls a global figure only for the same "green" 2-digit chapters SAM already qualifies — chapters
with at least one Wholesaler/Retail-linked sub-code in Available Categories (`Object.keys(await
buildCategoryCoverage())`, `src/services/productPortfolio.js` — see §1.1). No separate qualification logic exists
for TAM; the frontend computes this list once and passes it to both `/api/trade/sam-overview` and
`/api/trade/tam-global-overview`. The rationale is the same as SAM's: stay scoped to categories actually relevant
to this business, not all 97 HS chapters — "global" describes the *country* scope (every reporter, not just
tracked ones), not the *category* scope, which stays exactly as narrow as SAM's.

### 2.2 The query mechanism

For one HS 2-digit chapter/year/flow, `backend/comtrade/client.py`'s `fetch_global_total` calls Comtrade with
`reporterCode` **omitted from the request entirely** — not set to `0`. This distinction was verified empirically,
not assumed:

- **`reporterCode=0` does not mean "World."** Tested live across three different years (2023, 2022, 2020): every
  call returned `HTTP 200, count: 0, data: []`. A parallel sanity-check call for a real reporter (Jamaica, same
  params otherwise) returned real data in the same call shape, confirming this wasn't a broken test harness —
  Comtrade genuinely has no concept of reporter code `0`. Separately, Comtrade's own reference file
  (`Reporters.json`) was fetched live and inspected: it has exactly 3 `isGroup` aggregate entries (ASEAN, European
  Union, "Other Asia, nes") and **no "World" entry at all**.
- **Omitting `reporterCode` entirely** returns one row per country that actually reported that chapter/year/flow —
  confirmed live (242 raw rows for HS chapter 02, 2023, before the duplicate-row fix in §2.6 below narrowed that
  to 166 genuinely distinct reporters).
- **`partnerCode=0` is a different axis and must never be confused with a "World reporter."** It means "every
  partner country combined" — so each reporting country's row is *that country's* total trade with the world, not
  broken out by individual partner. It says nothing about which countries report; it's applied on top of the
  omitted-`reporterCode` call for exactly the same reason SAM's own per-country queries already use it (so each
  country's own row is its total, not split per partner). Confusing this for a "World reporter" mechanism was
  tested directly and confirmed wrong — see §2.2's first bullet.

Comtrade offers **no single-call server-side "world aggregate"** — this app fetches every reporter's own row and
sums them itself, the same way SAM sums its own tracked-country subset, just without a region/Commercial-Structure
filter narrowing which countries are asked about.

### 2.3 Year resolution

Resolved once per chapter (not shared globally across all chapters, and not per-country — there's no per-country
axis here at all), newest-first, walked backward the same `YEAR_PROBE_ATTEMPTS` depth SAM's own per-country
resolution uses (`backend/routers/comtrade.py`'s `_resolve_global_year_and_rows`). A chapter with no country
reporting it in any probed year is left out entirely — never a hollow zero row, the same exclusion convention
Part 1 already uses.

### 2.4 What's shown on screen

One card per qualifying category (never per region — a global figure isn't scoped to any one region by
definition). Each card shows **"Global TAM: $X (based on N reporting countries, `<year>`)"** — the reporting-country
count is never omitted, because not every country reports every category every year, and a bare dollar figure
without that context would misrepresent how complete the underlying data actually is. Expanding a card reveals
the full per-country breakdown, sorted by value (descending) by default, with a country-name search box and a
name/value sort toggle — the same expand/collapse interaction language as SAM's own breakdown rows, adapted for a
list that can run into the hundreds of countries rather than a handful of tracked ones.

**No bilateral/partial-coverage badge appears here.** That concept is specific to the fallback-source discovery
system built for SAM's own tracked countries (a country UN Comtrade doesn't cover getting a best-effort substitute
source). At global scale, a country either reported to Comtrade for that category/year or it didn't — there is no
fallback tier in play — and the "N reporting countries" count already discloses that completeness honestly.

### 2.5 What TAM Overview explicitly does not do (this pass)

- No comparison to SAM is shown on this screen (e.g. "SAM is X% of Global TAM") — a natural next step, but its own
  deliberate addition once both figures are independently verified correct, not bundled into this pass.
- The origin-country supply-capacity ratio (Colombia+USA production vs. demand) is not part of this — still an
  open decision (fold into SOM, or keep separate) from an earlier conversation, out of scope here.
- Custom (TAM's second sub-tab) has been removed — it was always a stub; see Part 3.
- Beyond §2.7's per-row Comtrade cache, the AGGREGATE itself (every category's total + per-country breakdown) is
  now also cached — see Part 3, which persists it so a normal tab view never recomputes it live.

### 2.6 The duplicate-row guard — and a real bug this build found and fixed

Comtrade's response for an unfiltered global chapter/year/flow query isn't broken down only by mode of transport
(`motCode`) and secondary partner (`partner2Code`) — the two dimensions this app's shared `_call()` helper
(`backend/comtrade/client.py`) already pinned to their "total" values (`0` for both) before this build. It's also
broken down by **customs procedure** (`customsCode`) — and this third dimension was *not* being pinned, anywhere
in this app, before this build.

This was caught empirically, exactly as it should be — **verified before trusting any sum, not after**:

- An unfiltered global pull for HS chapter 02, 2023 returned **5,155 raw rows** — not 242. `customsCode` alone
  had 9 distinct values (`C00` "TOTAL CPC" plus `C01`–`C07`, `C20`), and `motCode`/`partner2Code` were each far
  more varied too when nothing was pinned.
- With `motCode=0` and `partner2Code=0` requested as actual parameters (the pre-existing fix) but `customsCode`
  still unconstrained, the same query returned exactly 242 rows — but **37 of the underlying 166 distinct
  reporting countries were duplicated 2–3× each**, once per `customsCode` value they happened to report under.
  Concretely: reporter 100's chapter-27 rows were `C00: 5.97B`, `C01: 5.14B`, `C20: 0.83B` — summing all three as
  if additive would have overstated that one country's contribution by roughly 2×.
- Adding `customsCode='C00'` as an explicit request parameter (mirroring exactly how `motCode=0`/`partner2Code=0`
  already worked) collapsed the same query to **exactly 166 rows — zero duplicate reporters** — and a direct
  check confirmed **every one of the 166 real reporters has a `C00` row**, so requesting it loses no country's
  data; `C00` is Comtrade's own "all customs procedures combined" total, the same kind of pre-aggregated total
  `motCode=0`/`partner2Code=0` already represent for their own dimensions, not a partial procedure.
- This fix was made in the **shared** `_TOTALS_ONLY` dict every Comtrade data call in this app funnels through
  (`backend/comtrade/client.py`) — so it applies to SAM's per-country `fetch_categories`/`fetch_products`/
  `fetch_subheadings` calls too, not just TAM's global one. A direct check found the same `customsCode`
  duplication in real per-country queries (e.g. reporter 8 had 97 of its own chapters duplicated 2–3× before this
  fix, reporter 28 had 97, reporter 100 had 96) — meaning **some of SAM's own confirmed figures, for countries
  with multi-procedure reporting, were silently affected by exactly this bug before this fix.** Jamaica (the
  country used in Part 1's own cross-check example) happened to have zero duplication, which is why that
  cross-check passed — it was not evidence the bug didn't exist elsewhere. Every existing cached Comtrade
  category/product/subheading snapshot (77 rows across `PriceComparisonSnapshot`) was cleared after this fix so
  the app never continues serving a pre-fix, potentially-inflated cached figure — the next view of any affected
  country refetches cleanly with the corrected query.

### 2.7 Caching (raw rows)

A global pull is meaningfully larger than one of SAM's per-country queries (up to ~250 raw rows per category/year
before dedup, vs. a handful of tracked countries) — `fetch_global_total` caches per `(flow, chapter, year)`
combination indefinitely, the same "a published figure doesn't change" convention every other Comtrade fetch in
this app already uses (`snapshot_store`), specifically so a normal session never re-fetches the same global total
for the same chapter/year more than once, and so repeated use doesn't burn through the API's daily call limit
faster than necessary. This is the RAW-ROW cache — see Part 3 for the separate AGGREGATE cache added on top of it.

### 2.8 Where the TAM code lives

- `backend/comtrade/client.py` — `fetch_global_total` (the global pull itself) and the shared, now-3-dimension
  `_TOTALS_ONLY` guard (§2.6) every Comtrade call in this app uses.
- `backend/routers/comtrade.py` — `tam_global_overview` / `_compute_tam_overview_data` and its own
  `_resolve_global_year_and_rows` (§2.3); `refresh_tam_overview` and `tam_global_overview_summary` (Part 3).
- `src/services/globalTradeData.js` — `fetchTamGlobalOverview` / `fetchTamGlobalOverviewSummary`.
- `src/components/marketAnalysis/GlobalTamPanel.jsx` — TAM's Overview content (no more Custom sub-tab, no nested
  tab bar — see Part 3), the per-category cards, and the per-country search/sort within each expanded breakdown.
- `src/components/marketAnalysis/MarketAnalysisView.css` — the `.global-tam__*` card/table styles.

---

## Part 3 — Persistence, the Home page cards, and the chatbox refresh (built)

Before this pass, both `sam_overview` and `tam_global_overview` recomputed their ENTIRE aggregate — resolving
qualifying chapters, walking every country's own year, summing — on every single GET, even though the underlying
per-country/global Comtrade ROWS were already cached indefinitely (§2.7 above, and `comtrade/client.py`'s own
module docstring). The aggregate itself (region/category totals, per-country breakdown) was never persisted. This
part closes that gap.

### 3.1 What's persisted, and where

A new table, `market_size_snapshots` (`backend/models.py`'s `MarketSizeSnapshot`, no migration needed — it's a
brand-new table, picked up automatically by `Base.metadata.create_all` the same way every other new table in this
app is), one row per `kind` (`'sam'` | `'tam'`):

- `data_json` — the exact response body the endpoint already returned before this pass (regions/categories/etc.),
  with `computed_at` folded into it.
- `chapters_json` — the qualifying-category scope (frontend `buildCategoryCoverage()` output) the snapshot was
  last computed with. Kept for display/debugging and so a chatbox-triggered recompute — which has no browser to
  ask for a fresh chapter list — can reuse the same scope. **Never compared against a later request's own chapters
  to auto-invalidate the row** — by design, see §3.2.
- `flow` / `computed_at` — self-explanatory; `computed_at` is also the one shown on screen (§3.5).

Persistence logic lives in `backend/market_size_store.py` (`get_snapshot`/`save_snapshot`), a sibling to
`snapshot_store.py` but deliberately a separate module/table: `snapshot_store.py` caches raw Comtrade ROWS
(per-country/per-chapter/per-year), this caches the computed AGGREGATE built from them — two different things
that happen to use the same "persist indefinitely, overwrite only on an explicit refresh" convention.

### 3.2 How the GET endpoints behave now

`GET /api/trade/sam-overview` and `GET /api/trade/tam-global-overview` (same request shape as before — `chapters`
still required): if a stored snapshot exists for that kind, it's returned **immediately, as-is** — no Comtrade
call, no chapter re-resolution, nothing. The `chapters` passed in the request are read only to validate the
request isn't empty; they are **never compared against the stored snapshot's own scope**, so a newly-qualifying
category (a product that only just got classified into a chapter nothing was tracking before) will **not**
automatically appear until an explicit recompute happens. This is a deliberate trade-off — the alternative
(diffing chapters on every view to decide whether to recompute) would silently reintroduce a live Comtrade call on
some views, defeating the point. The trade-off is disclosed on screen (§3.5) and in the tool description used by
the chatbox tool (§3.4).

If no snapshot exists yet (first-ever view of that tab, or after some future "clear cache" action that doesn't
exist yet), the endpoint computes live via `_compute_sam_overview_data` / `_compute_tam_overview_data` (the same
computation that existed before this pass, just pulled into its own function) and persists the result in the same
call — so the very next view, by anyone, is instant.

### 3.3 Manual recompute: the refresh endpoints

`POST /api/trade/sam-overview/refresh` and `POST /api/trade/tam-global-overview/refresh` unconditionally
recompute and overwrite the stored snapshot, regardless of whether one already existed. `chapters` is **optional**
on these — pass it to recompute with an explicit scope, or omit it to reuse the last stored snapshot's own scope
(the normal case: Comtrade's published figures change over time even for the same categories, which is the actual
reason to ask for a refresh, not a change in which categories qualify). Calling this before anything has ever been
computed, with no chapters given, returns a 400 explaining there's no scope to recompute with yet.

The same logic is exposed as plain Python functions (`refresh_sam_overview` / `refresh_tam_overview` in
`backend/routers/comtrade.py`) so it can be called in-process — no HTTP round trip — by the chatbox tool (§3.4).

### 3.4 The chatbox tool: `refresh_market_size`

Added to `backend/routers/assistant.py`'s `TOOLS`. A user typing "update SAM", "refresh the TAM numbers", or
similar triggers `refresh_market_size` (`which: 'sam' | 'tam' | 'both'`, defaults to `'both'`), which calls
`refresh_sam_overview`/`refresh_tam_overview` directly (no chapters — reusing each tab's own last scope, §3.3) and
reports back the new total + category count, or explicitly says "no change" if the recomputed numbers matched the
previous ones exactly (compares the before/after summary, §3.6). If a tab has never been computed yet, the tool
returns that explanation in plain language instead of a stack trace.

**Sync, not async-action.** This was an empirical decision, not a guess (per this repo's own convention for this
kind of choice — see `refresh_product_source` for the sync precedent and `build_country_profile` for the
async-action one). Measured live, on a normal warm cache (the ordinary case, since raw Comtrade rows are cached
indefinitely per §2.7): a full SAM recompute (18 categories, 3 regions) took **~0.4s end to end**, and a full TAM
recompute (18 categories, ~105 reporting countries each) took **~0.37s end to end** — both comfortably inside
`refresh_product_source`'s own "a few seconds, not a background job" characterization, so `refresh_market_size`
follows the same synchronous pattern: it does the real work inline and returns the result as the tool's own return
string, reported straight back in the same chat reply, exactly like `refresh_product_source`. (A fully cold cache
— every underlying Comtrade row a miss — would take longer, bounded by however many countries/chapters need a real
network call; this wasn't hit in testing since this app's Comtrade cache is already warm from ordinary use, and a
genuinely cold first-ever compute already happens inline in the GET endpoint itself, §3.2, with no different
timeout concern than the live compute this endpoint already did before this pass.)

### 3.5 What's shown on screen

Both `SamPanel.jsx` and `GlobalTamPanel.jsx`'s Overview now show a second hint line under the existing description:
**"Last updated: `<computed_at>`. Ask the assistant to \"refresh SAM/TAM\" to recompute this with the latest UN
Comtrade data."** — using the real `computed_at` from the stored snapshot, same `.market-analysis__hint` visual
register as every other hint text in this module. Nothing is shown here before the very first compute finishes
(the initial GET call itself still returns fresh data synchronously, same as before — there's just no separate
"empty" state to render).

### 3.6 Home page cards (TAM / SAM / SOM)

Two new lightweight, DB-only endpoints back the Home page's cards, deliberately separate from the full
Overview endpoints so opening Home never triggers Comtrade work even indirectly:

- `GET /api/trade/sam-overview/summary` → `{ computed_at, total_value, category_count }` — `total_value` is the
  grand total summed across every region's every category (confirmed figures, bilateral included — same
  convention as the category totals themselves); `category_count` is the number of distinct qualifying chapters
  that contributed anywhere, across all regions (a chapter appearing in 3 regions counts once). Comes back with
  `computed_at: null`, zeroed totals if SAM has never been computed.
- `GET /api/trade/tam-global-overview/summary` → same shape; TAM has no regions, so `total_value` is just the sum
  of every category's own global value and `category_count` is simply how many categories qualified.

`src/components/home/HomeView.jsx` fetches both on mount and renders two `MetricCard`s — **TAM** and **SAM** —
value formatted compactly (`$1.3B`, `$420M`, `$85K` — a local `formatCompactUsd` helper, deliberately different
from this app's usual code-before-$ dual-currency convention in `utils/currencyFormat.js`, which is for real
per-transaction amounts, not order-of-magnitude portfolio totals) with a second line ("in N categories") via
`MetricCard`'s new optional `sub` prop (backward-compatible — every existing caller that doesn't pass `sub` is
unaffected). Before either summary has ever been computed, the card shows "—" and a prompt to view that tab. A
third card, **SOM**, is a plain `PlaceholderMetricCard` (the same "Coming soon" component already used for
ROI/Valuation) — there's no real SOM calculation yet; this is explicitly a placeholder.

### 3.7 Custom sub-tabs removed

Both SAM's and TAM's `Custom` sub-tab (always a stub) have been removed, along with the now-pointless single-item
nested tab bar that used to switch between it and Overview — `SamPanel.jsx` and `GlobalTamPanel.jsx` now render
their Overview content directly. SOM has no sub-tabs and was never touched by this.

---

## Part 4 — Market Opportunities (built)

**Market Opportunities is a different question from SAM/TAM.** Where SAM/TAM answer "how big is this category's
import demand," Market Opportunities answers "for one real product this app already has a wholesale price for in a
SOURCE country, is it actually cheaper to sell into a given TARGET market than that market's own price?" — a
per-product, per-country-pair price comparison and opportunity score, not a category aggregate. It replaces
`MarketOpportunitiesPanel.jsx`'s original "Selection saved — opportunity analysis for this pairing is coming soon"
placeholder that sat under its cascading Source ▸ Target ▸ Region ▸ Country selector.

### 4.1 Scope: one source, one or many targets

Target = "By Country" runs exactly one source→target pair. Target = "By Region" is the natural, non-inventive
extension of the same logic: every qualifying country already listed in that region (the same "has a linked
Wholesaler or Retail source with real products" filter the selector itself already applies) is run as its own
independent source→target pair — never blended into one figure, grouped and filterable by target country in the
results table.

### 4.2 Step 1 — product matching: composing three existing pieces, not a fourth mechanism

This app already had relevant, independently-built pieces, and Market Opportunities composes them rather than
inventing a new matching mechanism:

1. **`backend/price_sources/match_table.py`** — a curated, human-verified name-override dict, checked before a
   plain normalized-name match, explicitly *not* a fuzzy-string algorithm. Built for one same-language pair
   (Corabastos ↔ La Mayorista, both Colombia/Spanish).
2. **`src/services/productPortfolio.js`** — already establishes cross-country product identity today: every
   country's products get translated to English (Colombia via `productTranslations.js`, Spanish→English, frontend-
   only by design) and deduplicated onto one canonical name.
3. **`backend/comtrade/product_classification.py`'s HS-code cache** (`GET /api/product-hs-codes`) — the same
   classification `buildProductPortfolio()`/`buildCategoryCoverage()`/Available Categories/SAM/TAM already read,
   reused here as a third, lower-confidence matching tier (§4.2.1).

**Decision, made after inspecting real data from all three live custom sources (Jamaica, Saint Lucia, Trinidad and
Tobago) and Colombia's own catalog: translate-then-normalize is the primary join, with a curated override as a
refinement on top — not a replacement for it.** `src/services/marketOpportunities.js` translates a Colombia source
product's Spanish name to English the same way `productPortfolio.js` already does, then joins on
`normalizeProductName()` (accent-strip, lowercase, parenthetical-qualifier-strip — already used for exactly this
purpose elsewhere in this app). A source/target pair whose translated names still don't align (e.g. Colombia's
"Pimentón" → "Bell Pepper" vs. Jamaica's own "Sweet Pepper") falls back to a new curated override table,
**`src/data/crossCountryMatchOverrides.js`** — `match_table.py`'s exact pattern (a human comparing both real
product lists), generalized from one hardcoded same-language pair to arbitrary `"<Source>|<Target>"` country pairs.
Every Colombia product with no Jamaica counterpart (e.g. Hass Avocado — Jamaica's bulletin has no avocado at all)
and every Jamaica-only product (e.g. Callaloo, Scotch Bonnet Pepper) is listed separately as "no match found in
target market," never dropped — the same full-outer-join discipline `priceComparisonData.js`'s `mergeSources()`
already established, just scoped to what this feature actually needs (a source product with no target match; a
target-only product isn't a sourcing opportunity and isn't shown as a second unmatched list).

#### 4.2.1 A real gap found after shipping tiers 1–2, and the HS-code tier that closes it

A user reported real Colombia/Jamaica tomato products missing from the table despite both countries clearly
selling tomatoes. Confirmed live: many product variants on both sides share the exact same already-classified HS
code (`070200`, "Vegetables; tomatoes, fresh or chilled") under completely different display names — Colombia's
"Chonto Tomato"/"Milano Tomato"/"Long-Life Tomato"/`"Kidney" Tomato` and Jamaica's "Tomato [Plummy] (Local)"/
"Tomatoes(Plummy) (Local)"/"Tomato [Salad ] (Local)" — none of which are identical strings even after translation
and normalization, so tiers 1–2 correctly excluded every one of them. This is a real, disclosed gap in name-based
matching, not a bug in tiers 1–2 themselves.

**Tier 3: matched by shared HS code**, added as a fallback — never a replacement for tiers 1–2, only reached when
a source product has no name/override match. Reuses the exact classification cache every other product-identity
feature in this app already reads (`fetchProductHsCodes()`), keyed by the product's plain display name, trimmed
and lowercased — the same key format the classification pipeline itself uses (**not** `normalizeProductName()`,
which additionally strips parentheses/accents for the name-join above and would miss real cache entries like
`"tomato (deli) (a)"`, cached under that exact string). A product not yet classified (background classification
still running, or it failed) simply isn't eligible for this tier yet — same "no invented data" discipline as every
other unresolved case in this app.

**Multi-candidate handling — an explicit product decision, not a silent default**: an HS code very often groups
*several* real variants per side (as above), so a naive one-to-one join would have to pick a winner among several
equally-real candidates. Asked directly, and the answer was: **show every source × target combination as its own
row, never silently pick one** — nothing hidden, even though a widely-shared code (like tomatoes) can now produce
many rows for one source product. A `hs_code`-tier row is always `match_confidence: 'review'`, tagged with the same
amber "HS Code Match" badge treatment as a curated-override match (a real match, just not a name match), and its
review reason names the exact HS code and description used, plus that other variants may share it. Confirmed live:
Colombia → Jamaica went from 12 matched products (tiers 1–2 only) to 205 after adding tier 3 — including all 27
real tomato-pair combinations across Colombia's 4 variants and Jamaica's 3, each independently priced and scored,
each correctly tagged. The results table gained a "Target Product" column specifically because of this tier — two
rows for the same source product previously looked identical except for price; now which specific target product
each row compares against is always visible, not just inferable from the number.

### 4.3 Step 2 — unit normalization

**Colombia and USA** reuse `unitConversion.js`'s existing `colombiaPricePerKg`/`usaPricePerKg` unchanged. **Every
other country's custom source** uses a new sibling module, `genericUnitConversion.js`, built only after reading the
real product rows from all three live custom sources (`GET /product-sources/products`), not guessed:

- Jamaica (moa.gov.jm) and Saint Lucia (Massy Stores) already report a clean `kg` / `g` / `each` / `unit` value —
  a simple official kg/g/lb/oz lookup covers them.
- Trinidad and Tobago (namdevco) has the same "real weight embedded in unstructured unit text" shape Colombia's own
  parser already solved for `"bulto de 50 kilos"` — just in English (`"45kg bag"`, `"100lb bag"`, `"22.68kg bag"`,
  `"5lb bundle"`) — so `genericUnitConversion.js` reuses that exact regex-extraction approach, generalized to the
  real wording found, rather than re-deriving it. A count/package unit with no stated weight anywhere (e.g. Trinidad's
  `"100's"`, `"Bundle"`) returns `null` with a plain-language comment, same discipline as every other conversion
  path in this app — never an invented number. The existing AI-research fallback (`weightResearch.js`) is wired up
  as the same tier-2 fallback signature shape (`genericWeightResearchItem`) for a future pass; this build's own
  verification did not need it (Colombia/Jamaica's real matched products all resolved via tier 1).

#### 4.3.1 Count-based vs. weight-based units — the conversion §4.3 deliberately didn't attempt

§4.3's two conversion modules (`unitConversion.js`, `genericUnitConversion.js`) both deliberately return `null` for
a count-based unit (Colombia's `"unidad"`/`"docena"`/`"30 UNIDADES (1 per package)"`; a custom source's `"each"`/
`"unit"`/`"100's"`/a bare `"Bag"`/`"Bundle"`/`"Head"`) — correct, since neither module has a safe universal
per-item weight, and an invented one would silently corrupt every downstream $/kg figure. That was the end of the
line for both modules **by design**. The real gap this closes: a matched cross-country pair where Colombia sells
eggs "por unidad" (per egg, count-based) and the target market prices them per kg (weight-based) — the comparison
correctly came back unresolved, but this app already holds the exact reference data needed to convert the count
side to a real $/kg figure and wasn't using it.

A new module, `countWeightConversion.js`, activates ONLY when a matched pair has exactly one side still `null`
because it's count-based **and** the other side is already weight-resolved — never speculatively on every
count-based product regardless of whether it's part of a real comparison. Two tiers:

**Tier A — eggs, deterministic, zero cost.** USDA AMS's own official minimum net-weight-per-dozen standard
(`unitConversion.js`'s `EGG_DOZEN_OZ` — Jumbo 30oz/Extra Large 27oz/Large 24oz/Medium 21oz/Small 18oz/Peewee
15oz — cross-checked against two independent sources, the AMS PDF itself and Maryland's Dept. of Agriculture's
copy of the same standard, before writing any code) is reused verbatim, never redeclared, converting
price-per-egg → price-per-dozen → price-per-kg. Colombia's own grading scales (La Mayorista's A/AA/AAA;
Corabastos' A/AA/B/Extra) have **no established correspondence** to USDA's Jumbo/Extra Large/Large/Medium/Small/
Peewee size classes — confirmed by checking `productTranslations.js`'s own `huevo-*` entries and the rest of the
app for any such mapping; none exists. Every non-USDA-graded egg therefore maps to USDA "Large" as an explicit,
disclosed default (never silently treated as a confirmed grade match) — the dozen-weight figure itself is a real
official standard, so a row converted this way is still eligible for `match_confidence: 'confirmed'` if everything
else about it is clean, but the grade-default ASSUMPTION is independently flagged as a review reason regardless,
since it's the assumption that's uncertain, not the reference table.

**Tier B — everything else (e.g. Trinidad's "papaya, box of 18" style packaging) — a single cached Haiku call per
distinct product, no web search, no tools.** Deliberately **not** the existing `ProductWeightResearch`/
`weight_research.py` pipeline — that's `claude-sonnet-5` **with** the server-side `web_search` tool, batched, a
real research call already wired up for a different purpose (USA produce cartons / Colombia's own single-country
$/kg table via `usaWeightResearchItem`/`colombiaWeightResearchItem`). Reusing it here would defeat the point: this
is a plain "what's the typical weight of one X" estimate from the model's own general knowledge — its own new,
separate table (`product_unit_weight_estimates`), its own new endpoint (`backend/routers/unit_weight_estimates.py`),
pointed at `claude-haiku-4-5` (no web search, no tools). Cached forever per distinct product, keyed by the
product's own display name trimmed/lowercased — the same convention §4.2.1's HS-code cache already uses,
deliberately **not** `normalizeProductName()` (which strips parentheticals — `"Pimento (S)"` and
`"Pimento (S)(20lb)"` are genuinely different pack sizes with genuinely different real weights, and collapsing
them into one signature would silently apply the wrong pack's estimate to the other). Paid **at most once** per
distinct product for the whole app: the endpoint checks the cache before ever calling Haiku, and a second request
for an already-cached signature returns the stored value with no new API call — confirmed live (see below). A
Haiku-estimated row is always `match_confidence: 'review'`, tagged with a new "Estimated Unit Weight" badge
(`.market-analysis__estimated-badge`, the same blue treatment §4.6 already uses for "not a clean match," never the
same badge as a real official conversion) — reusing `reviewBadges()`'s existing vocabulary, not inventing a color.
Genuinely uncertain — the model can decline: confirmed live against a real ambiguous case (Trinidad's `"100's"`
corn count), where Haiku correctly returned `weight_grams: null` with a note explaining the ambiguity rather than
guessing, and the row correctly stayed unresolved.

**A new `conversion_note` field** (both `MarketOpportunityComparison.conversion_note` and the API contract) records
which method was used and the exact factor/weight, in plain language, on any row where a count↔weight conversion
was applied — empty/null on a row that needed none, unchanged from before this existed.

**Cost guardrail, checked before any real spend**: a dry-run mode on the new endpoint (`dry_run: true` — checks the
cache and reports hit/miss counts without calling Haiku or writing anything) found **30 distinct non-egg products**
with a real count-vs-weight mismatch across this app's currently tracked countries (Colombia/USA/Jamaica/Trinidad
and Tobago/Saint Lucia), found by grouping every product by its already-classified HS code and flagging any
cross-country group mixing a count-based and a weight-based unit — confirmed reachable today only for the subset
whose group also contains a Colombia or USA member (the only two source-eligible countries in the UI today); the
rest would surface only if a retail-only country (Jamaica/Trinidad/Saint Lucia) were ever promoted to a wholesale
source. Verified end-to-end, not just unit-tested: Colombia → Jamaica's egg rows (11 real rows, La Mayorista's
A/AA/AAA and Corabastos' A/AA/B/Extra, `"unidad"` and `"30 UNIDADES (1 per package)"` alike) all now resolve to a
real USD/kg figure (~$2.25–$3.35/kg) instead of staying unresolved, each correctly tagged `review` with the
grade-default caveat; USA → Saint Lucia's "Cab Fresh Beff Kebabs" (`"unit"`, no stated weight) resolved via a fresh
Haiku call (400g, cached on the next request — confirmed by a repeat call returning the identical `estimated_at`
timestamp and `cached: true`, no second Haiku call); and three real Colombia papaya varieties → Jamaica resolved
via Haiku correctly reasoning about their own stated crate counts (`"Melona"`/`"Round"` papaya: 18/crate ≈ 9000g;
`"Tainung"`: 10/crate ≈ 7500g) — the exact "papaya, box of 18" scenario this mechanism was built for, working on
real data.

### 4.4 Step 2 — currency normalization: every currency to a common USD basis

Every currency converts **independently to USD** — never source-currency straight to target-currency. With N
currencies in play, a common USD basis needs only N rates total (each currency → USD), not one per pair; adding a
new country later needs just one new rate, not one per existing country; and every comparison, regardless of which
two countries, ends up on the same common basis (USD/kg).

Built as `backend/currency/usd_rates.py`, wrapping the free, keyless
[open.er-api.com](https://open.er-api.com/v6/latest/USD) — deliberately not `currency/exchange_rate.py` (a
separate, paid, 4-hour-cached service with no rate date, left untouched). One bulk call returns every one of its
~166 supported currencies' rate against USD at once — confirmed live: `GET /v6/latest/USD` →
`200 {"result":"success","time_last_update_utc":"...","rates":{"JMD":158.03,"COP":3264.54,"XCD":2.70,"TTD":6.80,...}}`,
no API key needed. Cached per currency, keyed against this app's own clock so any currency already fetched today
is served with no outbound call (`usd_exchange_rate_cache`, a new table — not `exchange_rate.py`'s existing 4-hour
in-memory cache). USD itself, and XCD (a fixed 2.70-per-USD peg the Eastern Caribbean Central Bank has held since
1976 — independently confirmed against this same API's own live value for it, also exactly 2.70), never need a
network call at all.

**Direction, confirmed empirically and worth restating since getting it backwards produces a plausible-looking but
wrong number**: the API's `rate` for a currency is how many units of it equal 1 USD (e.g. `JMD: 158.03` means
1 USD = 158.03 JMD) — stored in exactly this raw form (not inverted) so it stays checkable against a real-world
quote by eye. Converting a LOCAL price to USD is therefore `usd_value = local_value / rate` — a **division**, never
a multiplication. Sanity-checked against real magnitudes before trusting this at scale: a Colombia wholesale
vegetable price around 2,000–5,000 COP/kg divides to roughly $0.6–1.5/kg, and a Jamaica retail price around
150–300 JMD/kg divides to roughly $1–2/kg — both plausible, neither wildly off.

**This supersedes an earlier version of this module that wrapped Frankfurter/ECB** (`backend/currency/frankfurter.py`,
since removed) — confirmed live that Frankfurter covers only its own ~30 ECB-tracked currencies, and specifically
does **not** include COP, JMD, XCD, or TTD, exactly the currencies behind this app's real tracked product data
(Colombia, Jamaica, Saint Lucia, Trinidad and Tobago), so no real comparison could ever reach `'confirmed'` — every
real row came back `review` for a currency reason, disclosed rather than papered over at the time. open.er-api.com
covers all four, confirmed live, so a real comparison can now actually reach `'confirmed'` when everything else
about it (the match, both units) is also clean.

### 4.5 Step 3/4 — the comparison record and the opportunity-rating scale

A new table, `market_opportunity_comparisons` (`backend/models.py`, no migration — a brand-new table, same
`Base.metadata.create_all` pattern `MarketSizeSnapshot` already established), one row per matched product per
source→target pair: both sides' original (value, unit, currency) and normalized (USD/kg) prices, both sides'
exchange rate used + its own date, `diff_pct`, `opportunity_rating`, `match_tier`, `match_confidence`
(`'confirmed'` only when the match was an exact/translated-exact name join **and** both sides normalized via an
official factor and a resolved currency; anything less — a curated-override match, an unresolved unit, an
unavailable USD exchange rate — is `'review'`, with the specific reason(s) recorded), and `calculated_at`. Computed
and persisted by `POST /api/market-opportunities/comparisons` (`backend/routers/market_opportunities.py`), the one
place the rating scale itself lives:

```
diff_pct < 20%           → "Very High"
20% ≤ diff_pct < 30%      → "High"
30% ≤ diff_pct < 50%      → "Challenging"
50% ≤ diff_pct < 65%      → "Complex"
65% ≤ diff_pct ≤ 100%     → "Difficult"
diff_pct > 100%           → "Not Viable"
```

**The ">100% → Not Viable" tier is mathematically correct, not an arbitrary addition** — verified, not assumed:
`diff_pct = (source_price_normalized / target_price_normalized) × 100`. A low `diff_pct` means the source price is
a small fraction of the target market's own price (the largest possible margin, correctly "Very High"); as
`diff_pct` climbs toward 100 the two prices converge (a shrinking margin, correctly "Difficult" just under 100).
Past 100%, the source price actually *exceeds* the target market's own price — there is no margin at all, a
fundamentally different situation from a thin-but-positive one — so a distinct break exactly at 100 is the correct
place for "Not Viable," not a more extreme flavor of "Difficult." Confirmed with a direct boundary test at every
edge (19.9/20.0/29.9/30.0/49.9/50.0/64.9/65.0/100.0/100.1) — every value landed in exactly the tier above.

### 4.6 What's shown on screen

`MarketOpportunitiesPanel.jsx`'s results section: a sortable/filterable table (default sort: Opportunity Rating,
then `diff_pct` — the two options the spec calls out, via the same sort-dropdown language `GlobalTamPanel.jsx`
already uses), a search box (`AvailableCategoriesPanel.jsx`'s convention), and — only in a "By Region" run — a
target-country filter. The "no match found in target market" list is rendered as its own separate section, grouped
by target country in a region run, never mixed into the matched table. A row carrying a `review`-tier
`match_confidence` shows a badge drawn from this app's existing vocabulary, never a new color:
`.market-analysis__bilateral-badge` (amber) for a curated-override match, and
`.market-analysis__estimated-badge--low-confidence` (red) for anything that actually blocked the `diff_pct`
computation (an unresolved unit, an unavailable USD exchange rate, no currency at all) — confirmed live rendering
both badges together on the same row (Colombia's Bell Pepper → Jamaica's Sweet Pepper: a real curated match that is
*also* currency-unresolved, shown exactly as both).

### 4.7 Where the code lives

- `backend/currency/usd_rates.py` — the open.er-api.com client + its own daily persisted cache (§4.4).
- `backend/routers/market_opportunities.py` — the exchange-rate passthrough, and `POST`/`GET
  /api/market-opportunities/comparisons` (scoring + persistence, §4.5).
- `backend/models.py` — `UsdExchangeRateCache`, `MarketOpportunityComparison`, `ProductUnitWeightEstimate` (§4.3.1).
- `backend/unit_weight_estimates/claude_client.py` + `backend/routers/unit_weight_estimates.py` — the cached
  Haiku unit-weight-estimate endpoint (§4.3.1), deliberately separate from `weight_research/`.
- `src/components/company/tabs/OperationsTab/MarketAnalysis/genericUnitConversion.js` — custom-source unit
  conversion (§4.3).
- `src/components/company/tabs/OperationsTab/MarketAnalysis/countWeightConversion.js` — count-vs-weight
  conversion (§4.3.1), reusing `unitConversion.js`'s `EGG_DOZEN_OZ`/`OZ_TO_KG`.
- `src/services/unitWeightEstimates.js` — the frontend fetcher for the Haiku unit-weight-estimate endpoint (§4.3.1).
- `src/data/crossCountryMatchOverrides.js` — the generalized curated-match-override table (§4.2).
- `src/services/marketOpportunities.js` — the matching/normalization engine (§4.2–4.4) and the frontend fetchers
  for the backend endpoints.
- `src/components/marketAnalysis/MarketOpportunitiesPanel.jsx` — the selector (unchanged) plus the results
  table/unmatched-list UI (§4.6) and the "Estimated Unit Weight" badge (§4.3.1).
- `src/components/marketAnalysis/MarketAnalysisView.css` — the `.market-opportunities__*` results styles (badges
  reuse the existing SAM classes as-is, no new colors added).

### 4.8 Known limitations register

Issues found during development or later testing that are real, disclosed gaps — not fixed in the pass that found
them, recorded here so they aren't lost.

- **HS-code matching (§4.2.1) groups by broad commodity category, not by cut/sub-product.** Found in testing: a
  real row matched Colombia's "Chicken Breast" to a target market's "Chicken Neck (Best Dressed)" — both correctly
  share one HS code (poultry cuts, not further subdivided), so tier 3 correctly produced the pairing per its own
  design, but a breast and a neck are not a remotely substitutable product for a real sourcing decision. This is
  the same "an HS code can group several real variants" behavior §4.2.1 already discloses for tomatoes (where every
  variant genuinely IS the same product, just a different name) — the gap is that the same mechanism doesn't
  distinguish a same-product naming difference from a different-cut-entirely difference within one code. A fix
  likely needs sub-cut-level matching — parsing/comparing the specific cut name within a shared HS code, not just
  the code itself — which is its own separate design problem (what vocabulary of cuts to recognize, per category,
  across languages) and was deliberately not attempted in this pass.
