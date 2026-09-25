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
