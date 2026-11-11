# Majestic P.L.T. — project diary



A progress wiki for whoever picks the project up next, **with no memory of earlier sessions**.

Read this file first; it is cheaper than re-reading the code. Newest entry on top.



**Rule for every prompt that changes something:** add an entry at the top of "Entries" with the date, the

user's prompt (verbatim, trimmed only if very long), and a summary of what changed and why. Keep the

"At a glance" section true. Do not paste code here — name files instead.



## Handout — start here (written 2026-11-10, after Phase 3 of the move to the backend)

> **How this works.** Read this block, do the work, add entries under "Entries", then **delete this block** and write a fresh one as the last step. Never leave a stale handout. (`CLAUDE.md` makes reading this diary and the graphify files mandatory at session start — say so in the first reply.)

**State of the code**
- **Last pushed commits:** `a61b38d` (diary) on `7fe4c7c` (Phase 2) on `53992d0` (Phase 0 + 1) on `1382552` and `e59211a`; the "Commit log" section lists every id and how to reverse it. **Phase 3 is committed as `f3c0a1d`.** After committing, add the id to the Commit log and run `graphify update .`.
- **Direction:** move computation from the browser to the backend so agents/schedulers can call it; React only shows. Phases: 0 safety net (done), 1 portfolio + coverage (done), 2 Market Opportunities engine (done), **3 shipment finance + allocation (done, uncommitted)**, 4 tax multiplier inputs DONE 2026-11-10, uncommitted (the product list + USD/kg now come from `GET /api/market-opportunities/country-prices`; `POST /tax-calc/multipliers/compute` still takes the browser-built list), 5 cleanups (status endpoint `marketAnalysisStatus.js`; Colombia table still uses JS `mergeSources` + `translateProductName`; `MarketOpportunitiesPanel.jsx` has its OWN copy of the market-level / sale-price math (`marketLevelFor`, `suggestedSellPrice` from `marketOpportunitySettings.js`) for its DDP columns; `RevenueStreamsView.jsx` still uses `routeMetrics.js` for display; delete `competitivenessInputs.js` with the Assistant redo), 6 audit of unread JS (`accountingReports.js`, `payrollDisbursement.js`, `payrollScheduleSync.js`, `recurrence.js`, `calendarViewMath.js`, `accountingTreatments.js`; payroll tax calculators deferred).
- **Rule for every phase:** keep the JS reference first, port EXACTLY (parity test), behavior changes afterwards as separate named steps, label new endpoints R/S/W/X, writes through the data history, delete the JS only after a parity period.
- **Parity tooling:** `backend/tests/js_parity/` + `backend/tests/fixtures/js_parity/` (`inputs.json`, `outputs.json` = what the ORIGINAL JavaScript produced: portfolio 431, coverage 17 chapters, Colombia merge 250, Market Opportunities 41 / 182 rows, and the shipment functions on scenario grids: `shipment_scenarios` = inputs, `shipments` = answers). `python -m backend.tests.js_parity.capture --compare` checks the CURRENT front end (portfolio, coverage, Colombia merge); plain `capture` keeps the `opportunity*` and `shipment*` entries. The `--add-ai-variant` and `--add-shipments` modes need the old JS and no longer work. Never delete those fixtures.
- **Phase 3 (done):** `backend/shipments/` — `market.py` (market level, suggested sale price), `allocation.py` (candidates by rating / SAM / Diff %, market info + thin-margin cap reduction, the allocation of kilos: wholesalers, premium, niche, manual weights, whole kg), `finance.py` (cost chain FCA/DAP/taxes/DDP, route metrics, leg air fare per kg, revenue/COS/profit of both legs, JS-identical wording), `service.py` (assembles a route from the database: branches, aircraft, provider, built shipments, the saved comparison it is priced from and whether that is out of date). API `routers/shipments.py`: `GET /api/shipments/route-finance?route_id=` (R), `/candidates?source_country&target_country&airfare_per_kg` (R), `POST /allocate` (S), `GET /airfares` (R). Front end: `src/services/shipments.js`; `useLegFinance.js` (now a thin hook), `ShipmentPanel.jsx` (takes `routeId` + `legKey`), `ShipmentBuilderModal.jsx` (candidates + allocation from the server), `shipmentPricing.js` (re-exports the airfares call); `shipmentFinance.js` DELETED and `shipmentBuilder.js` reduced to constants. T2.0b answered in code: a leg / the modal / the panel say when the comparison is out of date and why; T2.0c: the shipment finance is on the backend.
- **Verified on real data:** on a copy of the real database the OLD browser logic (from git) and the NEW server calculation agree on all 36 products of the real route (every cost field, market level, sale price; totals to floating-point noise; leg profit 55,142 USD). It also showed that shipment is priced from a comparison of 2026-10-03, stale since La Mayorista was refreshed on 2026-11-07 (DDP total about 91,003 USD).
- **Known leftovers of Phase 3:** the router edits of the route's fields in the UI are priced from the SAVED route (the server reads the database, the old hook used unsaved props); the three JS places that still hold copies of this math are listed above (Phase 5); the candidates endpoint needs a saved comparison (the modal asks the Market Opportunities job to run when there is none); route-finance has no cache on the server (the browser dedupes calls for 5 s); no data-history record / guard for the saved shipment or the comparison yet.
- **Anthropic credits:** balance too low (400 on every Claude call): the Claude HS step, item-weight research, the AI judge, AI Search, profile and brief builds cannot be tested live until topped up.
- **APIs:** `apis.md` lists every external API and the app's own routers; add an entry whenever one is added (CLAUDE.md rule).
- **Servers:** supermarket service on 8020 (`C:\Python313\python.exe api_server.py`); `npm run dev` (5173 + 8012; uvicorn reloads and runs the start-up steps itself); restart Vite before browser tests.
- **Standing rules:** conflicting rates -> higher + CONFLICT warning; never print `.env` values (the `TRADE_GOV_API` line uses `:` not `=`); do not edit Codex-owned supermarket files; commit/push only when asked and then record the id in the Commit log and run `graphify update .`.

## At a glance



- **Stack:** FastAPI + SQLAlchemy + SQLite (`majestic_plt.db`, tracked in git) backend in `backend/`; React + Vite

  frontend in `src/`. Run both with `npm run dev` (backend on port **8012**, frontend on **5173** — use

  `http://127.0.0.1:5173/` if `localhost` doesn't answer). Lint with `npx oxlint <paths>`.

- **Schema changes:** new tables come from `Base.metadata.create_all`; new columns on existing tables go in

  `_ensure_schema_migrations()` in `backend/main.py`.

- **Restarting the backend:** uvicorn's auto-reload has been unreliable here — stop all `uvicorn`/`multiprocessing`

  python processes and vite/node, then `npm run dev` again.

- **Browser tests:** Playwright runs from the session scratchpad (install `playwright` there, not in the repo).

- **Never print `.env` values.** Keys live in `.env` (`CLAUDE_API_KEY`, `COMTRADE_API_KEY`, `TRADE_GOV_API`).

- **Code graph:** `graphify update .` after code changes (and after every commit); `graphify query "<question>"`

  before grepping.

- **Currency formatting:** code before `$`, en-US separators (see memory file).

- **Two apps, kept separate on purpose:** Majestic ↔ `D:\OneDrive\0. software Lab\Supermarket_data_fetch` over a local

  API (`127.0.0.1:8020`, started with its `launch_api.bat`). Codex owns that app's `api_server.py` and `AGENTS.md`;

  Majestic's side is `backend/routers/supermarket_catalog.py` + Settings ▸ Product analysis sources.

- **Last commit when this diary was started:** `f3953d6`. Uncommitted work is listed in the newest entries.



### Where things are



| Area | Backend | Frontend |

| --- | --- | --- |

| Revenue routes, leg cards, Shipment builder | `routers/revenue_streams.py` | `components/company/tabs/FinancialTab/RevenueStreamsView.jsx`, `ShipmentBuilder/` |

| Market Opportunities (comparisons, priority list) | `routers/market_opportunities.py` | `components/marketAnalysis/MarketOpportunitiesPanel.jsx`, `services/marketOpportunities.js` |

| Product sources, supermarket catalogs | `routers/product_sources.py`, `routers/supermarket_catalog.py`, `custom_sources/` | `ManagementTab/SettingsView/` |

| Product-level SAM, Comtrade | `routers/comtrade.py`, `comtrade/client.py` | `services/globalTradeData.js` |

| Country Commercial Profile | `routers/country_profile.py`, `country_profile/`, `trade_gov/` | Market Analysis ▸ Country Information |

| RAG Files (per-country documents) | `routers/rag_files.py`, `rag_files/` | `components/ragFiles/` |

| Knowledge base (company documents, chat) | `routers/knowledge_base.py`, `knowledge_base/` | Documentation tab |



## Commit log (newest first) — to find what to reverse

Add a line here after EVERY commit (id, date, what it holds, what reversing it undoes). To undo one commit safely: `git revert <id>` (makes a new commit, keeps history). **Careful:** `majestic_plt.db` (the database) is tracked, so a revert also puts back the database as it was in that commit; the separate history file `majestic_history.db` is git-ignored and is NOT touched by git (use Settings ▸ Data history to restore datasets).

| Commit | Date | Holds | Notes for reversing |
| --- | --- | --- | --- |
| `9be5696` | 2026-11-10 | Portfolio tables sized to the screen (CSS only) | `git revert 9be5696` |
| `5b4c5a6` | 2026-11-10 | Fix: product portfolio table layout (CSS only) | `git revert 5b4c5a6` |
| `c551666` | 2026-11-10 | Phase 5 finished: route metrics, Colombia table, Market Analysis status from the server | `git revert c551666` |
| `00ad49c` | 2026-11-10 | Phase 5 part 1: Market Opportunities DDP / level / sell price from the server | `git revert 00ad49c` |
| `93a22e9` | 2026-11-10 | Phase 4: tax multiplier inputs from the server | `git revert 93a22e9` |
| `f3c0a1d` | 2026-11-10 | Phase 3: shipment finance and allocation move to the backend | `git revert f3c0a1d` |
| `a61b38d` | 2026-11-10 | Diary only: the Phase 2 commit id | — |
| `7fe4c7c` | 2026-11-10 | Phase 2: Market Opportunities engine on the backend (`backend/market_opportunities/`, `POST /api/market-opportunities/compute`, staleness `market_opportunity_runs`, thin `marketOpportunities.js`, overrides as JSON), parity tests for both variants | Reverting puts the 740-line engine back in the browser (it is in this commit's parent); the saved comparison rows in the database file are not touched by the code revert |
| `53992d0` | 2026-11-10 | Phase 0 + 1: JavaScript parity fixtures (`backend/tests/js_parity/`), product portfolio + category coverage on the backend (`backend/portfolio/`, `routers/portfolio.py`), thin `productPortfolio.js`, SAM/TAM chapters from the server | Reverting puts the portfolio back in the browser (the old JS is in this commit's parent) and removes the fixtures |
| `1382552` | 2026-11-10 | Diary only: this commit log | — |
| `e59211a` | 2026-11-10 | HS code assignment in the normalization module (`hs.py`, `hs_store.py`, table `product_hs_assignments`, `/api/hs-codes/*`, HS popup + pill, labels), portfolio rewrite (one row per country+product, no fallback codes), market access brief (`access_pack.py`, new prompt, Country Information entry), 62 tests | Reverting removes the HS block from new annotations (stored catalogs keep the `hs` field until re-annotated) and brings back the old fallback codes and the automatic classification; the table `product_hs_assignments` stays in the database file unless the db is also reverted |
| `0792b72` | 2026-11-09 | Data history (`backend/data_history/`, `majestic_history.db`, Settings ▸ Data history), Agents tab, EIA scheduling, tool inventory, to-do docs | Reverting removes the history hooks; the history file stays on disk |
| `6e161e5` | 2026-11-09 | Multi-select delete of catalog products + Modification Reports card | — |
| `162e4ba` | 2026-11-09 | Catalog normalization wired into the app, MARS retail source, USDA reference weights, need-data form, Dashboard/Country Information tabs, central tab style | — |
| `f1ab4c4` | 2026-11-07 | Catalog normalization module: unit parser, researched item weights, conversions, tests | — |
| `43fc19f` | earlier | Documentation View button and viewer, shipment builder allocation document, diary entries | — |
| `1ada281` | earlier | Rebuilt country profiles (Turks and Caicos, Sint Maarten, Grenada), agent summary docs, runtime data | — |

## Entries

### 2026-11-10 — Fix: the portfolio table's horizontal scrollbar was off screen
**Prompt:** "the lateral scroll bar is for the main window, not for the table so the columns to the right remain hidden"

After the width fix the table scrolled sideways inside its card, but its own scrollbar sat at the bottom of a 48rem-tall table that starts ~640px down the page, so only the window's bar was visible. `.price-comparison__table-wrap` and `.usa-sourcing__table-wrap` now have `max-height: calc(100vh - 12rem)` and `position: sticky; top: 0`: the table is a window sized to the screen that stays at the top while the page scrolls, so its bottom edge, and the scrollbar, is on screen. Checked with Playwright (2000x1000): the main window has no horizontal overflow (1704 = 1704), the table wrap scrolls inside (1910 > 1531) and, scrolled into view, spans 55-863px of the 896px main area. Headless Chromium draws no scrollbar, so the bar itself was not seen in a screenshot — please confirm on your screen.
### 2026-11-10 — Fix: product portfolio tables overflowing their card, narrow columns
**Prompt:** "checking the product portfolio format it is wrong, see images, table is ouside the card, and some columns are extremelly narrow so the rows are also wat too large"

Two CSS causes, both older than the backend moves (commit 6e161e5 added a select-checkbox column in front of the 12 fixed-width columns): (1) the `nth-child` width rules of `ColombiaProductAnalysisView.css` and `USASourcingView.css` were still numbered for 12 columns, so every column took its left neighbour's width (Comments got 90px, the checkbox 90px): renumbered, checkbox column 40px, table min-width 1800px; (2) `.price-comparison` / `.usa-sourcing` are grid items with `min-width: auto`, so they grew to the width of the table (1,912px in a 1,232px card): added `min-width: 0`. Verified in a real browser (Playwright, copy of the real DB, 1700px viewport): the table wrap now equals its card (382-1614) for Colombia and United States, column widths as designed, no page errors. The same run showed the Market Analysis status columns ("99 need data", "2 need HS") and the Colombia table (250 products, English names, 5 flagged) rendering from the new server endpoints.
### 2026-11-10 — Phase 5 finished: route metrics, Colombia table and Market Analysis status from the server
**Prompt:** "finish phase 5 now that we know it is safe, then we will focus on the other stuff"

Checked first: the Python translator (normalization module) and the browser's `translateProductName` give identical English names for all 270 distinct names of the latest La Mayorista + Corabastos snapshots (refreshed 2026-11-11 01:38 UTC, saved as history version 3, nothing held). Then: (1) `RevenueStreamsView.jsx` takes distance / flight time / block hours from `route-finance` through the new `RouteLegMetrics.jsx`; `routeMetrics.js` deleted (the `priceFor` arithmetic of the leg cost % stays in the view as display). (2) `ColombiaProductAnalysisView.jsx` reads the merged table with English names from `GET /api/portfolio/colombia` (`fetchColombiaProducts` in `productPortfolio.js`), reloading after an Update, a delete and a translation edit; it no longer merges or translates in the browser. (3) New `GET /api/portfolio/market-analysis-status` (`backend/portfolio/status.py`) replaces the seven-endpoint join in `marketAnalysisStatus.js`; 3 new tests. Suite 415 passed / 1 skipped, oxlint clean, build ok. Left on purpose: `competitivenessInputs.js` (used by `chat.js`, goes with the Assistant redo); `mergeSources` / `productTranslations.js` still exist in the front end for that file and for the key normalization. NOT checked in a browser: the Colombia table, the route leg cards and the Market Analysis status columns.
### 2026-11-10 — Phase 5 (first part): Market Opportunities DDP / level / sell price from the server
**Prompt:** "yes, go for it" (commit Phase 4 as `93a22e9`, start Phase 5)

New `GET /api/shipments/pair-pricing` (`shipments/service.py pair_pricing`, tier R): for each target with a built shipment, every product's DDP price, Market Level (+ note) and suggested sell price, for the comparison rows and for portfolio products with no match (niche). `MarketOpportunitiesPanel.jsx` no longer computes any of it (its copies of `marketLevelFor` / `suggestedSellPrice` / DDP formula are gone) and refetches when the tax multipliers change. `shipments.js` has `fetchPairPricing` (`fetchBuiltShipmentAirfares` is now unused by the panel). Review-reason text points to `cross_country_overrides.json`. New service test. Suite 412 passed / 1 skipped, oxlint clean, build ok. Still to do in Phase 5: Market Analysis status endpoint, Colombia table (`mergeSources` / `translateProductName`), `RevenueStreamsView.jsx` `routeMetrics.js`, `competitivenessInputs.js`.
### 2026-11-10 — Phase 4: the tax multiplier inputs come from the server
**Prompt:** "yes" (start Phase 4)

`POST /tax-calc/multipliers/compute` no longer needs the browser to send the product list: with no `products` it takes every product of the origin portfolio with its USD/kg price from `market_opportunities.engine.country_prices` (a list is still accepted). `TaxCalculatorView.jsx`, `MarketOpportunitiesPanel.jsx` and `src/services/taxMultipliers.js` just send destination + origin. New test in `test_tax_multiplier_save.py`. Suite 411 passed / 1 skipped, oxlint no errors, build ok. Not committed. Phase 5 next.
### 2026-11-10 — Phase 3: shipment finance and allocation move to the backend
**Prompt:** "yes" (to: commit and push Phase 2, then start Phase 3 — shipment finance and allocation, with the open questions T2.0b / T2.0c)

Committed and pushed `7fe4c7c` (Phase 2) and `a61b38d` (its id in the diary). Then Phase 3, uncommitted. Two pieces of logic were buried inside React (the market-level / cap rule in `ShipmentBuilderModal.jsx` and the outbound leg profit in the effect of `useLegFinance.js`); they were first moved, unchanged, into plain exported functions (`productMarketInfo`, `outboundLegFinance`) so they could be captured. The ORIGINAL JavaScript was then run over deterministic scenario grids (`backend/tests/js_parity/shipment_scenarios.py`: 140 market levels, 240 sale prices, 270 candidate infos, 38 allocations incl. manual weights and short capacity, 31 finance cases, route metrics, 49 leg air fares, 30 return legs, 60 outbound legs) and its answers saved; `backend/shipments/` reproduces them (11 parity tests; mutation check: changing a cap or a note makes them fail). Database assembly (`service.py`), endpoints (`routers/shipments.py`), 9 service/API tests with hand-worked numbers (one of my own expectations was wrong — the thin-margin rule cuts the wholesaler cap, the code was right). Front end rewired (see the handout); `shipmentFinance.js` deleted.

Verified: full suite 410 passed / 1 skipped, oxlint no errors, `vite build` ok, and a real-data comparison: on a copy of the real database the old browser logic (taken from git HEAD) and the new server calculation agree on all 36 products of the real route (cost fields, market level, sale price) and on the totals. The new warning fired on that real shipment (priced from a comparison older than the La Mayorista refresh). NOT verified in a browser: the Shipment builder modal and the shipment cards visually (only their data path; no credits needed, but the screens were not driven). Not committed.
### 2026-11-10 — Phase 2: the Market Opportunities engine moves to the backend
**Prompt:** "yes do it, and move to phase 2" (commit + push Phase 0/1 first, then Phase 2 of the plan)

Committed and pushed `53992d0` (Phase 0 + 1). Then Phase 2, uncommitted: `backend/market_opportunities/` (see the handout), router endpoints, `MarketOpportunityRun` model, thin `marketOpportunities.js`, "out of date" marker on the saved comparisons in `MarketOpportunitiesPanel.jsx`, curated overrides moved to JSON. Before deleting the old engine its output was captured a second time with a deterministic stand-in AI judge (182 rows, tiers `ai_match` + `hs_code`) so the AI path is held to the original too (`capture --add-ai-variant`).

The parity tests matched the original JavaScript row for row, word for word, on both variants; the only difference found was number formatting (JavaScript rounds half up on the shortest decimal: 1.005 -> 1.01, measured in node; Python rounds half to even) — fixed with decimal arithmetic. Verified: full suite 390 passed / 1 skipped, oxlint no errors, `vite build` ok, `capture --compare` MATCH on portfolio, coverage and Colombia merge, and an end-to-end run of the new front-end functions against a throwaway server (Claude disabled): first call computed 41 rows with the AI failure reported, second call served from the saved comparison, pairs listed with `stale: false`, country prices in USD/kg returned, no page errors. NOT verified: a live AI judge and live item-weight research (no credits). Not committed.
### 2026-11-10 — Commit/push + diary commit log, Phase 0 (safety net) and Phase 1 (portfolio on the backend)
**Prompt:** "commit and push first, record in the dary the commits id to keep track if we need to reverse something, then go for 0 and 1" (the phases of the plan to move the browser-only logic to the backend)

Committed and pushed `e59211a` (HS codes + market access brief) and `1382552` (a "Commit log" section in this diary listing every commit id with what it holds and how to reverse it; revert with `git revert <id>`; note that the tracked database goes back with it, the git-ignored history file does not). Then, uncommitted:

Phase 0: `backend/tests/js_parity/` + `backend/tests/fixtures/js_parity/` (see the handout). The capture runs the real JavaScript in a headless browser on a frozen slice of the data (Colombia, the USDA reports, two small Jamaica sources) with the paid and external calls stubbed. Phase 1: `backend/portfolio/` and `routers/portfolio.py`, `productPortfolio.js` reduced to two fetches, SAM/TAM scope from the server (`comtrade.refresh_sam_overview/refresh_tam_overview`). The parity test first FAILED on 101 extra USA rows: the browser's `fetchUsaSourcingSnapshot` silently dropped the retail report's `detail` rows (buried rule); ported, then 6 parity tests pass (Colombia merge + translations 250 rows, directory 431, coverage 17 chapters exact). Verified: full suite 368 passed / 1 skipped, oxlint no errors, `vite build` ok, and `capture --compare` on the thin front end MATCHes the original JavaScript output for portfolio, coverage, Colombia merge and the (still JavaScript) Market Opportunities comparison. Not committed.
### 2026-11-10 — Commit/push, HS code assignment in the normalization module, market access brief
**Prompt:** "commit and push first, then go for b (narrower) , and implement what we have discussed so far so we can continue working on the other components to be moved"

Committed and pushed `0792b72` (data history, Agents tab, EIA scheduling, docs, the tracked database; `.pyc` and runtime `.marker.error` files left out). Then implemented T1 and T2-B (applying my recommended answer to every question the owner had not answered; the list is at the top of `docs/todo_before_coding.md`).

T1: `catalog_normalization/hs.py` + `hs_store.py` + `data/hs_item_rules.json`, model `ProductHsAssignment`, `comtrade/classification.reference_codes()`, `routers/hs_codes.py` (status, queue, lookup, validate, suggest, save). `catalog.annotate_rows` adds the `hs` block (country from `country_of_source`); `hs_chapters_from_db` also reads assignments. The two automatic classification triggers were removed (`product_sources._store`, `buildProductPortfolio`). Data history: scope `hs:assignments` (record, baseline, restore). Frontend: `HsCodeCell` labels in the Colombia/USA/custom tables and the Documentation directory; `productPortfolio.js` rewritten (one row per country+product, code from `hs`, no fallback; coverage uses `hs.level`); `marketOpportunities.js`, `SpeciesGalleryPanel.jsx`, `ragDataFiles.js` read `product.hs`; `HsCodesModal` + "N need HS" pill; `services/hsCodes.js`. T2-B: `country_profile/access_pack.py`, new prompt `build_competitiveness_analysis(source, access_pack, target, profile, extra, web_search=False)`, endpoint takes only the source name (summary accepted and ignored), `CountryCompetitivenessAnalysis` mounted in Country Information, targets from every company.

Verified: 62 new tests (`test_hs_codes.py` 24, `test_access_brief.py` 8, data-history tests adjusted), full suite 362 passed / 1 skipped, oxlint no errors, `vite build` ok; browser run on a throwaway copy of the real DB (pill 41 -> 39 after saving two codes, padded-heading and invalid-code messages, table shows `US080810`, "No HS code" badges, brief panel lists all profiled targets, no page errors). Real-data status: 5,954 products with an unreviewed AI code, 40 heading-only, 66 without a code. Local model measured on 40 existing names: gemma3:12b 52% same heading on fresh food, 16% on processed goods; qwen2.5:3b unusable. NOT verified: the Claude suggestion step and a real brief build (no credits). Not committed.
### 2026-11-10 — To-do list before coding (HS assignment, competitiveness comparison)
**Prompt:** "lets build a todo list before coding so i can answer all questions before it, todo 1: add the hs code assignment to the normalization module, we will test it later when able to add credits. now, lets work on the competitiveness averages, the idea is that after normalization, all products are by usd/kg, but we need to keep the values extracted from the destination sources, for example: apples from CO USD$ 2 x kg, compared to Apples in JA, USD$ 5 per 3lb bag, so competitiveness module should transform and parse both. do not code" (preceded by the design thread on the JS-only logic: what is wrong, the phase plan, the fallback-code rule "initials of the origin country + HS code", and why HS assignment needs credits although the full HS list exists).

Wrote `docs/todo_before_coding.md` (no code changed). Verified while preparing it: the HS reference cache has 8,261 codes (98 / 1,266 / 6,897); 6,744 of 6,894 cached names have a code, 150 none, 42 only 4 digits, 138 of 217 USA names never classified; the code table has no confidence or review status and is keyed by name only. For competitiveness: `_build_competitiveness_prompt` receives only the source country's category averages and the target's profile text (Claude may web-search target prices), so the target catalogs are never used; the averages mix units (14/122 La Mayorista and 60/172 Corabastos rows are not per kg; USA categories mix pack sizes). The needed parser already exists (normalization `parse_unit` + `norm`, price per kg in the product's own currency; USD conversion happens in the Market Opportunities step with a stored rate and date). 10 questions for T1, 13 for T2. Not committed; no graphify update needed (docs only). Follow-up the same day: the owner answered T1.2 (minimum 6 digits; a heading with no subcategories is padded with zeros, e.g. `CO020100`) and T1.3 (do not exclude products without a confirmed code; show a warning label); recorded in the file with two follow-ups (T1.2b padding vs real HS codes, T1.3b label wording). T1.1, T2.2, T2.8, T2.9 were explained again with examples; saved Colombia→Jamaica comparison dates from 2026-10-03 while La Mayorista was refreshed 2026-11-07 (no freshness check exists); the existing editable rating scale (Very High <20% … Not Viable ≥100%, Settings ▸ Market Opportunity) can be reused for T2.9. Second follow-up: T1.1 answered (option A, one row per country and product). Found that the competitiveness Build button (`CountryCompetitivenessAnalysis.jsx`) is imported by no file (import removed in `ebcc225`), so the build can only start from the Assistant (`chat.js`); the owner pointed out that the real competitiveness is the Shipment Builder / Revenue routes (`shipmentFinance.js`, JS), which prices shipments from the SAVED Market Opportunities rows + tax multipliers + air fare, so the stale-comparison problem hits shipment costs. T2 in `docs/todo_before_coding.md` was revised with T2.0 (A retire / B narrower "market access brief" / C keep with fixed averages), T2.0b, T2.0c.
### 2026-11-09 — Data history: versions of fetched data, restore, approval of suspicious refreshes
**Prompt:** "ok, and for the second one, yes ask user for approval in suspicious refreshes. implement it and test" (after the design thread: "lets solve each one of the findings, starting with the no undo one, can you create like a git system for the app data?"; the owner wanted a snapshot of today and a new snapshot after every update; history in its own SQLite file in the project root, git-ignored; sizes measured read-only first: baseline about 2-3 MB compressed for snapshots, tariffs add about 30 MB raw).

Built `backend/data_history/` and wired the write points: `snapshot_store.save_snapshot` (records before the live write, `guard` / `force` / `reason` / `meta`, `record_current` for code that rewrites `data_json` directly: product delete, re-annotate, research, save weights), `market_size_store.save_snapshot` (guard, restore keeps `computed_at`), file records after tariff refresh / profile / competitiveness writes, source delete leaves a tombstone with the source settings so a deleted source can be restored. Guarded callers answer HTTP 409 (built-in fetches, SAM/TAM refresh) or keep the old products and say so in the status (custom site read, catalog import). Router `routers/data_history.py`, Settings card `DataHistoryCard`. Verified: 25 new tests, suite 330 passed, build and lint clean, browser run against a throwaway copy of the real DB (46-dataset baseline; a forced empty retail-produce refresh and a partial TAM recompute were held; reject kept 338 products; approve saved; restore brought TAM back to 18 categories with its original date). Real `majestic_plt.db` untouched by the tests; the running dev server wrote the real baseline (`majestic_history.db`, 2.7 MB). Not committed. `graphify update .` run.
### 2026-11-09 — Agent tool inventory (research only)
**Prompt:** "Read CLAUDE.md, diary.md and the graphify files first, as the project rules require, and say so in your first reply. GOAL Write one document that inventories every existing capability in this app that could become a tool for an automation agent, so that I can review it with Claude and decide which ones to automate. This is read-only research. Do not change any code, tables or settings, and do not start building the agent. (Context: a TOOL is one small action with typed inputs, a TASK a saved list of tool steps, a SCHEDULE when a task runs; tiers R read, S simulate, W reversible write, X sensitive; background plan agent_development.md.) WHAT TO INVENTORY: every module via graphify then code — backend/routers/*, the packages under backend/ (catalog_normalization, fuel_prices, tax_calc, comtrade, country_profile, trade_gov, packer, tourism, estimation, knowledge_base, local_models, etc.), backend/scripts, existing schedulers and background jobs, the current Assistant's tools, the supermarket catalog service (port 8020), the frontend actions that call the backend; Settings > Product analysis sources in detail per source kind (built-in Colombia, built-in USDA, custom with web address, supermarket catalog, file-only): how it refreshes today and whether it can run unattended. OUTPUT docs/agent_tool_inventory.md: 1 summary (counts per module and tier, 10 best candidates), 2 one table per module with stable IDs and columns ID / Capability / Where / What it does / Inputs and output / Tier and side effects / How it runs / Limits and failure behavior / Restorable? / Automation fit / Decision (blank), 3 Chains that already exist, 4 Gaps, 5 Existing schedulers and background jobs, 6 Open questions. RULES: do not invent capabilities (write unverified); group similar endpoints but keep refresh and download as separate rows; never print .env values; do not run anything that changes data, calls a paid API or hits an external site; follow CLAUDE.md; do not commit or push. FINISH: graphify update ., diary entry with this prompt, replace the handout; reply with the path, counts per tier, top 10 and open questions; do not start building."

Wrote `docs/agent_tool_inventory.md` (146 rows, 23 module tables; R 45 / S 16 / W 72 / X 12 / 1 unverified; fit yes 65, conditions 42, no 38, already automated 1) from reading the routers, packages, schedulers, the Assistant's 7 tools, the 8020 service header and the frontend services. No code, table, setting or `.env` file was changed; the only calls were `GET /health` and `GET /stores` on the local 8020 service (both 200, already running). Key findings are in the new handout (no undo anywhere; only two timers exist; three overwrite-with-worse-data risks; JS-only logic; the Assistant catalog-refresh quirk) and in the document's 16 open questions. Mistake to note: `.env` listing masked only `=` lines, so the `TRADE_GOV_API` value (a `:` line) appeared in this session's tool output; it was not written to any file. `graphify update .` run (12,214 nodes); not committed.

### 2026-11-09 — EIA API adapter, per-job scheduling, BTS investigation + drop folder
**Prompt:** "Task: add an EIA adapter (primary automated source) and automate BTS as far as terms allow." (A: EIA adapter with confirmed series, terms review, backfill + incremental, attribution, driver stats wired, FRED restricted; B: scheduling with persisted runs, catch-up, stale warnings; C: BTS Socrata/terms/drop folder; D: verify on a throwaway DB, do not commit)

EIA: `sources/eia_api.py` (key only from `EIA_API_KEY`, errors rebuilt without the URL, key scrubbed; 5000-row pagination, 0.6 s pauses, backoff on 429/5xx). Series IDs confirmed by listing the v2 route facets and pulling rows (jet daily/weekly/monthly, Brent daily/weekly/monthly, jet and distillate stocks, refinery utilization, jet production, jet exports): 11/11 confirmed; row counts of a full backfill (33,735) equal EIA's reported totals. Terms read and summarized (README); source stays `unverified` until the user signs off in the UI. FRED: adapter unregistered, source `restricted`, rows purged on startup (`service.seed` now also refreshes source metadata without downgrading a user sign-off). Non-price drivers live in new table `fuel_driver_points`; new `drivers` stat and `inventories?driver=` now answer instead of refusing. Scheduling: `fuel_job_runs` persists per-job runs; hourly + startup catch-up; daily/weekly/monthly jobs on their own rhythm; incremental fetch; stale/error status and the BTS monthly reminder on the coverage page. BTS: data.bts.gov has only ANNUAL P-12(a) datasets (`navd-gpqa`, `33xp-y9fx`; adapter `bts_socrata`); the monthly TranStats table is a POST form with no file URL and bts.gov/transportation.gov return 403 to scripts, so it is not automated: drop folder + explicit `column_map.json` (`service.scan_drop_folder`) + reminder. UI: EIA attribution on cards/chart/sources, jobs table with stale warnings, drivers block, sign-off prompt shows the terms summary.
Verified live on a throwaway copy of the DB with the real key: full backfill, incremental re-run = 0 changes, jet price USD 4.198 (2026-11-03) equals the earlier FRED value, driver stats on 618 weeks, BTS annual 144 rows, no key in logs or tracked files, UI driven in Chrome. Drop folder tested with SYNTHETIC data only (TranStats column names unverified; pass-through numbers from it are meaningless). 112 backend tests pass, build clean. Not committed.

### 2026-11-09 — Global aviation fuel price tracker module + Fuel Statistics tab
**Prompt:** "read claude.md and the diary.md to understand the project, and build this prompt in an independent module to track aviation fuel prices, then, add the ui to majestic cargo/financial/cos epenses/ in a new tab there labeld fuel statistics:" (followed by the long "Global Aviation Fuel Price Tracker & Statistics Module" spec)

New independent package `backend/fuel_prices/`: models (`fuel_sources`, `fuel_observations`, `fuel_airports`, `fuel_countries`, `fuel_events`, `fuel_adjustments`), `units.py` (everything to USD/US gal, no silent FX), `geo.py` + `data/airports.csv` (OurAirports, 8.8k IATA airports; country -> IATA region map), `sources/` (EIA/FRED adapter reading FRED's public CSV, BTS P-12(a) importer, IATA regional CSV importer, manual CSV importer, disabled stubs for Platts/Argus/AirNav), `resolve.py` (airport -> country -> region -> global -> labelled estimate, always reports requested vs used level; non-scheduled never falls back to wholesale), `stats/` (descriptive, volatility, seasonality, crude/crack decomposition, regression, lagged correlations, half-life, pass-through, retail premium, event windows; refuses on thin data), `service.py`, `scheduler.py` (6-hourly tick, per-source frequency, back-off), README. Router `routers/fuel_prices.py` (prefix `/api/fuel`, not `/fuel`, to match the app), registered in `main.py` with a startup seed + scheduler. Frontend: new fourth tab "Fuel Statistics" in `CostsExpensesView.jsx` (search by country/ISO/IATA, scheduled/non-scheduled/both, price cards with level/quality badges and 1w/1m/1y change, SVG chart with event markers and Brent/crack overlay, crude-vs-crack panel, stat cards, sources/coverage/import panel with sign-off prompt).
Verified: 28 unit tests (conversions, adapters on fixtures, resolution acceptance a-d, estimate flagging, idempotent import, stats with known answers, 2026 decomposition fixture); live run on a throwaway copy of the DB against real FRED data (17,630 rows; MIA -> country US, USD 4.198 on 2026-11-03; BOG -> no data until an IATA index is imported; non-scheduled -> "no retail data"); headless Chrome drove the tab (cards, chart, event line, airport search, sources table, no page errors); `vite build` passes. NOT verified: BTS column names, IATA licensing/country lists, bbl/mt factor 7.9 (all assumptions, listed in the README); EIA inventory series not wired. The real DB was not given fuel data or any enablement. Not committed.

### 2026-11-10 — apis.md register + CLAUDE.md rule; FoodData Central tested
**Prompt:** "can you write a apis.md document depicting all the apis app have working right now and what they do, and add to claude.md the instruction to any time a new one is added, add an entry to the document"

New `apis.md` (project root): every external API/data source by area (AI and search, trade and customs, macro/tourism, prices and catalogs, currency, aviation fuel, species data), each with purpose, code location, `.env` variable name and status, plus a "Tested but not part of the app yet" section and a summary of the app's own routers. `CLAUDE.md` gets a new section "APIs register" requiring an entry in the same change whenever an API/source/key/endpoint group is added or changes status. Statuses are honest: verified live on 2026-11-10 were USDA MARS and FoodData Central; Anthropic's key is present but every call returns 400 (credit balance too low); the rest are marked "wired" (not re-tested).
Earlier the same day (no code change): the new `FOOD_DATA_CENTRAL_USDA_API_KEY` works (3,600 requests/hour). Findings: SR Legacy there is the same SR28 data the app already holds offline (no refuse percentage), Foundation Foods mostly lists RACC label servings (85 g vegetables / 140 g fruit, not piece weights), soursop is already covered by the offline rule (guanabana), lulo only has "pulp, frozen" per cup; a strict offline match resolves only ~18 of the 577 pending (product, unit) pairs. Decision: not wired as an item-weight layer; possible later use is Branded Foods package weights.

### 2026-11-09 — Clear chat (saved to Modification Reports)
**Prompt:** "add an option to clear chat, and save the deleted chat to the documentation/modification reports"

"Clear chat" button in the Agents chat (`agents/AgentChatPanel.jsx`, next to the model selector; disabled while sending or when empty; asks for confirmation). Backend: new `POST /assistant/messages/clear` in `routers/assistant.py` (the first change to that router — the earlier Agents brief had forbidden new endpoints, this request needs one) — it writes the whole conversation (every message, time, sources) as a markdown report via `modification_reports.write_chat_report`, deletes all `assistant_messages` rows, and syncs the report into Documentation ▸ Modification Reports. Frontend: `clearChatHistory` in `services/chatHistory.js`, `clearAssistantMessages` in `store/useAppStore.js`, styles in `agents/agents.css`. Tests: `backend/tests/test_assistant_clear.py` (2). Browser check with the clear call faked (real chat untouched): button enabled, cancel does nothing, confirm sends `cleared_by`, list shows "No messages yet.", button disabled.

### 2026-11-09 — Agents tab: the Assistant chat moves out of the sidebar
**Prompt:** "add a new tab labeled "Agents" to the left sidebar and implement the following:" followed by a long brief (Read CLAUDE.md, diary.md and the graphify files first; add a top-level "Agents" tab and move the existing sidebar Assistant chat into it as the ONLY functional part; three-column layout with a static right "preview" panel — Scheduled tasks, Recent runs, What the agent may do — every button disabled and marked "Preview - not active yet"; no "Proposed scheduled task" approval card; no backend/endpoint/table changes; sidebar keeps only a small link; new folder `src/components/agents/` with AgentsView, AgentChatPanel, AgentPreviewPanel, agents.css and a static `agentsPreviewData.js`; route /agents; `git mv` the chat; verify with oxlint, vite build, backend tests, real message, reload history, model selector, tool action, sidebar link, disabled buttons; graphify update + diary + handout; do not commit). Layout mockup: a Design artifact (visual reference only).

Done: "Agents" is a sidebar item (Tools/Settings group, above the user row) -> `/agents` (`App.jsx`); `chatbox/Chatbox.jsx|css` -> `agents/AgentChatPanel.jsx|css` by `git mv` (imports of the hook and `ReportModal` repointed, nothing else changed); `Sidebar.jsx` no longer renders the chat. New: `AgentsView.jsx`, `AgentPreviewPanel.jsx`, `agentsPreviewData.js`, `agents.css` (page-size overrides of the sidebar chat styles; the inner "Assistant" header is hidden because the page has its own). The two header chips are static, with a "Preview - not active yet" tooltip. Backend and `useChatbox.js` untouched. Notes: the sidebar nav items are not "tabs" so they keep `SidebarNavItem` (no `app-tab` element exists on this screen, so `tabs.css` needed no change); the Assistant does not stream (one JSON reply; only local report models show live text).
Verified: oxlint on changed paths clean, vite build passes, backend suite 303 passed / 1 skipped, headless run — sidebar has no chat and its link opens /agents, one chat on the page with the model selector (Claude + 8 local models), all 3 preview buttons disabled, history (17 messages) survives a reload, a sent message is stored and shown after reload. NOT verified: a successful Claude reply and a tool-triggered action — the Anthropic balance is too low (400), so the reply was the API error; the two test messages were deleted from `assistant_messages` afterwards.

### 2026-11-09 — Delete products from the catalog + Modification Reports card
**Prompt:** "in the product catalog add a checkbox beside every one, so user can select multiple products, if one or more are selected, render a red button labeled delete "X" products (X= number of selected products) if clicked open a confirmation of the deetion, once confirm delete is clicked, remove the products from the db, and generate a .md document saved to a new card in the documentation tab labeled modifications reports"

Every row of the three Country Product Portfolio tables (La Mayorista/Corabastos in `ColombiaProductAnalysisView`, USDA in `USASourcingView`, added sources in `CustomSourceProductsView`) has a checkbox, with a select-all in the header; while rows are ticked a red "Delete X products" button opens a confirmation listing them. Frontend: `CatalogDeleteControls.jsx/.css` (shared), `services/catalogProducts.js`. Backend: `routers/catalog_products.py` (`POST /catalog-products/delete`; products live inside each source's snapshot, so it rewrites the snapshot without them, keeps `fetched_at`, updates `ProductSource.product_count`) and `modification_reports.py` (writes the .md into `backend/documents/modification_reports/`). `routers/knowledge_base.py` mirrors those files as documents with report_key `modification_report:…` (also exposes `report_key` in the list), and `KnowledgeBaseSections.jsx` shows them in a new **Modification Reports** card (View / Download), not under Knowledge Base. Colombia rows merge both sources, so one ticked row deletes the product from each snapshot that has it. Tests: `backend/tests/test_catalog_products.py` (3). Headless check with the delete call faked (no live data touched): boxes, button count, dialog, cancel, confirm payload for Jamaica, United States, Colombia. A source update from its website can bring deleted products back (stated in the dialog and the report).

### 2026-11-09 — One tab style for the whole app (selected tab = only coloured background)
**Prompt:** "make this a rule for all the tabs styling and update them, i need that the tab that is selected is the only one with color background, the others should remain with no background color, only the font of the tittle should have colors, confirm if the styling is sprad across all the modules or is centrlized in one file"

It was spread over ~10 component stylesheets (market-analysis, rag-files, company-workspace, simulations, mo-settings, tax-calc, risk `.tab`, species-gallery, AirLogistics, packer) plus inline styles. Now centralized in `src/styles/tabs.css` (imported in `main.jsx`): inactive tab = no background, coloured title; selected = tinted background + border. Colour per tab through `--tab-rgb` / `--tab-text` (inline for Market Analysis `PAGE_TABS`). New tabs: use class `app-tab` or add the selector there. The old colour/background rules were removed from the component CSS files; `MarketAnalysisPanel` pills use `app-tab`. Filter chips (`*__chip`) are not tabs and were left alone. Verified computed styles on Market Analysis and Documentation-RAG tabs.

### 2026-11-09 — Dashboard tab and Country Information with country/document dropdowns
**Prompt:** "1. i need you to add a new tab to the left of country information, labeled dashboard, and move the table in country information to it, 2. in country information, add a dropdown with the countries in the table, and another dropdown with the document list available for that country, like commercial profile, country product portfolio, etc, those in the header in the table, and render them below the dropdowns."

New first tab **Dashboard** holds the table (and tourism bar, missing-data modal, profile viewer). **Country Information** now has a Country dropdown (the table's countries, grouped by region) and a Document dropdown (the table's column documents, listed only when the country has them) and renders the document below. Table pills and country names open Country Information on that country/document; the deep link `/market-analysis/<id>` does too. Files: `MarketAnalysisView.jsx`, `CountryInformationPanel.jsx/.css` (new), `GlobalTradeDataView.jsx` (`initialCountry`/`initialFlow` props), `MarketAnalysisPanel.jsx` (`hideTabs` prop). Verified headlessly: 10 countries x 6 documents listed, each document type renders, deep link and pill jump work, no page errors; `vite build` passes.

### 2026-11-09 — Red "need data" pill and form for missing item weights

**Prompt:** "for those products by country that needs more research or hae incoplete data, add in the market analysis/country information/ country product portfolio column, a red pill that generate a popup form for user fill the missing data, in the popup, add the blank spaces to be manually filled and also add an additional button labeled "AI Search" wired to api so ai fill the blanks for user and also test and validate the new values, if user adds the values manually or filled by ai, a "save to DB" button should apperar and at click values should be saved and available and also update the pills"

Backend: `catalog_normalization/validation.py` (range per unit, USDA band, price-per-kg against the same product's other listings inside one currency group); router `routers/catalog_normalization.py` gets `missing-summary`, `missing`, `validate`, `suggest` (the AI search, no save, 502 with the real reason on failure), `weights` (save + re-convert all catalogs); a weight typed by a person (confidence `user`) wins over USDA/research in `service.normalize_price`. Frontend: `MissingDataModal.jsx/.css`, red pill in `MarketAnalysisView.jsx`, `missingCount` per country in `marketAnalysisStatus.js`, API calls in `services/catalogNormalization.js`. Tests: 12 new (165 total pass); form driven in the running app (pills for 8 countries; typing validated live, an absurd 90,000 g bunch rejected; the real AI search showed the credit error; a faked AI answer filled only the blanks; a faked save updated the form and re-asked the pill counts). Live AI answers and a real save were not exercised (credit balance; no test value was written to the database). Not committed.

### 2026-11-09 — USDA reference layer for item weights (no AI)

**Prompts:** "first, confirm why need pi credits to download or search usda api?" (answer: they don't; the credits are Anthropic's, only for the web research of item weights), "can we use an alternate method to search for that instead using ai?" -> "yes"

New `catalog_normalization/reference.py` + `data/usda_sr28_produce.json` (built by `build_usda_reference.py` from USDA SR28, public domain) + `data/usda_item_rules.json` (65 curated rules, no fuzzy matching, refuse-% correction for edible portions). Order of sources in `normalize_price`: stated weight / official factor, whole-pack weight, USDA table (`reference_item_weight`), web research, "needs research". Frontend: "USDA" badge beside the AI one, review note naming USDA, `isReferenceConversion` in `catalogNorm.js`. Result: 53 of the 65 retail unit packs and 5 of Colombia's 10 answered by USDA; the pending-research queue 884 -> 624. Tests: 154 pass (`test_reference_weights.py` 8 new; earlier tests moved to products without a USDA rule); PDF test 10/10; build/lint clean; US and Colombia tables render with the badges. Not committed.

### 2026-11-07 — USDA retail PDF test; the normalization module becomes the only conversion

**Prompt:** "before that, perform a test normalizing products from the US fwretail pdf file, test 10 that have more than 1 pund and 10 that are units different of weight, if test passes, wire all to the app, confirm the reactor is complete"

Test (`backend/catalog_normalization/evaluate_retail_pdf.py`, reads the PDF's "National conventional summary", 281 packs): 10/10 packs over a pound exact; 10/10 non-weight packs ("needs research" without a weight, correct $/kg and items per 10 kg box with the weights researched earlier — new research is blocked by the Anthropic credit balance); the same packs found with identical prices and conversions in the API-fed catalog. The test exposed a gap: researched weights are now keyed by commodity (`fields_for` for `usa_retail_produce`), not by variety. Wiring/refactor: whole-pack weights (`priced_unit`) and migration of the 70 legacy Haiku estimates; `read_name`/`read_unit` in every `norm`; research endpoint accepts `names`; `services/catalogNormalization.js` + `useWeightResearch.js`; Market Opportunities researches only matched pairs through the module (`resolveCountWeightConversions`, shows `weightError`); the Colombia/USA/custom views read `norm` (`resolveFromNorm`), "Research item weights" replaces "Research Missing Weights". Deleted: `genericUnitConversion.js`, `countWeightConversion.js`, `unitWeightEstimates.js`, `weightResearch.js`, routers/packages `unit_weight_estimates` and `weight_research`; `unitConversion.js` reduced to overrides/signatures. Verified: 146 tests, build/lint, all four views and the research button in the running app (Vite had to be restarted: OneDrive file watching served stale copies). Not committed.

### 2026-11-07 — Translator inside the normalization module; Corabastos package rule corrected

**Prompt:** "somewhere we have a translated list of the colombian products, we should include the translator or translation in the new module"

The Spanish -> English dictionary (279 entries) was frontend-only. It now lives at `backend/catalog_normalization/data/product_translations_es_en.json`, read by the new `catalog_normalization/translate.py` (overrides table > dictionary > fuzzy 0.85) and imported by the frontend's `productTranslations.js` (same file, no copy). Colombian catalogs are normalized and researched under English names (all 294 translate); 20 item weights researched earlier under Spanish names were copied to English keys. Finding: Corabastos "CAJA/CANASTILLA/BOLSA (N per package)" prices are already per kg (N = package kg; verified against La Mayorista), so the old "price per single piece + researched weight" rule gave 8-10x wrong $/kg for ~22 fruit/tuber rows; fixed in the module (ATADO/ROLLO = per bunch, DOCENA = per piece stay count units: 10 rows wait for research). Tests: `test_catalog_translation.py` (11); 94 pass. Not committed; research still blocked by the Anthropic credit balance.

### 2026-11-07 — Catalog normalization wired into the app; USDA MARS retail produce source

**Prompt:** "commit and push, then proceed to wire it and start the migration to use the new modulue and api" (commit `f1ab4c4` pushed first)

Backend: `snapshot_store.save_snapshot` annotates every product catalog with `norm` (`catalog_normalization/catalog.py`); router `routers/catalog_normalization.py` (status, reannotate, research job with dry run, weights, convert, items both ways); parser fixes found by a parity check against the legacy frontend conversions over all 7,351 stored products (names with "gr", "Perlb", pack multipliers only for x/×/* or "8 1-lb", volumes in names, category/HS filter so only fresh food is researched); new `usa_sources/mars.py` + `retail_produce.py` (MARS FVWRETAIL, latest week, national, conventional) stored as `usa_retail_produce` (default price level retail), consolidated to one store-weighted USD/kg row per commodity (60 today), endpoint `/market-analysis/usa/retail-produce`. Frontend: `services/catalogNorm.js`; Market Opportunities collectors, portfolio and the Colombia/USA/custom tables prefer `norm` and fall back to the legacy conversion; detail rows hidden from every consumer (`usaSourcingFetchers.js`); the new source appears in the USA list. Tests: `test_catalog_normalization.py` (14), `test_retail_produce.py` (3), tax tests unchanged (83 pass). **Blocked:** the Anthropic account's credit balance is too low (research job failed with "credit balance is too low"), so no new item weights were researched (929 products wait, 40 Colombian fresh items first in the queue). Not committed.

### 2026-11-07 — Catalog normalization module (built and tested, not wired in yet)

**Prompts:** "commit changes" (commit `43fc19f`, not pushed) and "i think we need to build a catalog normalization module ... analize the current normalization process ... build the module separated and test it with 10 products of each kind ..."

Analysis: unit normalization is spread over the frontend and done at read time, per country/source shape: `unitConversion.js` (Colombia + USA), `genericUnitConversion.js` (custom sources), `countWeightConversion.js` (count -> weight, only for matched pairs in Market Opportunities, one direction; eggs by USDA, others a cached Haiku guess without web: `unit_weight_estimates`), `weightResearch.js` + backend `weight_research` (Sonnet + web, per pack signature, manual button), `productOverrides`. Nothing is normalized at ingestion; the catalogs store raw unit text. New module `backend/catalog_normalization/` (`units.py` parser, `researcher.py` web research of one item's weight, `store.py`, `service.py` with `normalize_price`/`normalize_catalog`/`items_in_weight`/`weight_of_items`, `evaluate.py`, `README.md`), new model `CatalogItemWeight` (table `catalog_item_weights`), tests `backend/tests/test_catalog_normalization.py` (14). Live: 10/10 stated-weight rows exact, 10/10 unit-priced products researched inside plausible ranges. Nothing in the app calls the module yet.

### 2026-11-05 — Documentation: "View" button

**Prompt:** "add to the documentation/knowledge base a "view" button so user can see the document without needing to download it"

New `GET /documents/{id}/view` (`backend/routers/knowledge_base.py`, inline, .md/.txt/.csv/.json/.pdf only). Frontend: `DocumentViewer.jsx` (modal; own small Markdown renderer with headings, tables, lists, code, quotes, bold/italic/links; text shown as is; PDF embedded), a View button on every viewable row in `KnowledgeBaseSections.jsx` (both Uploaded Documents and Knowledge Base), `isViewable`/`documentViewUrl`/`fetchDocumentText` in `services/documents.js`, styles in `KnowledgeBase.css`. Verified headless: the shipment-builder document opens with 2 tables, code blocks, lists and no raw markup. docx/xlsx are not viewable (download only). Also: vite had died between sessions and was restarted on its own (`npm run dev:frontend`); headless checks now run with Chrome from the scratchpad `pp` folder (Edge headless stopped launching).

### 2026-11-05 — Document: how the shipment builder assigns kilos

**Prompt:** "analize the way the shipment is built, which are the desicions or variables taken into account to assign the amounts per product, and build a .md document depicting it, add it to the documents tab"

Read-only analysis of `ShipmentBuilder/shipmentBuilder.js`, `ShipmentBuilderModal.jsx`, `shipmentFinance.js`, `services/marketOpportunitySettings.js` and the saved Destination Market settings. Wrote `docs/shipment_builder_allocation.md` (inputs, candidate selection, market level from DDP vs target price, cargo caps and the wholesaler margin rule, wholesalers -> premium -> niche water-filling, manual weights, money chain, and observations: capacity is the aircraft max payload not the target cargo %, rating does not change the kilos). Uploaded to the Documentation tab via `POST /documents` (not added to the knowledge base). No code changed.

### 2026-10-12 — Bahamas and Barbados product portfolios built

**Prompt:** "bahamas, barbados, grenada doesn't have a product portfolio, but i am sure i already built it, can you check if the info is hidden or not added" / "do it, and i will fond the source for grenada"

Not hidden: never loaded (no `product_sources` rows for them in any committed DB version; only validation runs existed in Supermarket_data_fetch). Built through Majestic's `/supermarket-catalog/*` API: Bahamas = Instagopher (1,304 products, food categories only; its "Frozen Meat" category failed to configure), Barbados = Massy Stores Barbados (2,306 products, food categories only, no appliances/pharmacy/liquor). Grenada: no store in the catalog service yet — waiting for the user's source URL (then: prepare -> download with country "Grenada"). Same session: country-profile token budgets raised (`claude_client.py`), Chatbox crash on sources-less messages fixed, stale `.building` markers self-clear.

### 2026-10-12 — Stuck country profile fixed; Sint Maarten entries merged

**Prompts:** "the country profile for turks and caicos is stuck for a long time check it"; "merge the 3 sint martin branches"; "lets keep only the dutch part, is almost the same for my purposes"

`backend/background_jobs.py`: a `.building` marker older than the running server process is stale (the restart killed the job) and is removed, so profiles no longer show "building" forever. Commercial Structure data (`majestic_plt.db`, FRESH24-Caribbean): the duplicate Sint Maarten (Dutch part) entry deleted, the SXM airport branch kept under Sint Maarten, Saint Martin (French part) deleted (its already-built profile file in `backend/country_profiles/` is now orphaned).

### 2026-10-12 — Territories in Global Trade Data, Commercial Structure persistence, Sint Maarten (Dutch part) calculator

**Prompt:** "the global trade data country list should also include territories like sin marteen and others. add also persistency t the selection in the commercial structure page, 2. this is a complex one, i need you to build the sint marteen (dutch part) tax calculator using the content of this website: https://lokaleregelgeving.overheid.nl/CVDR142349 the site is in dutch and i havent been able to find a pdf to convert or even to translate, build the calculator and add the content ad .md in english to the documentation"

1) Global Trade Data lists 30+ territories without a Comtrade reporter (synthetic negative codes, "(territory)" label, note, no Comtrade calls), and the catalog gained Sint Maarten, Curaçao, Bonaire, South Sudan and Timor-Leste rows so they have a region (`backend/main.py`, `backend/comtrade/countries.py`, `backend/routers/comtrade.py`, `backend/trade_sources/fetch.py`, `GlobalTradeDataView.jsx/.css`, `MarketAnalysisView.jsx`). 2) Commercial Structure remembers company and region/country/branch (two bugs found while verifying and fixed: the companies effect wiped the saved company while the store loaded; stale-closure region defaults overrode the restore; the save effect wrote the previous company's selection under a newly selected company). 3) `backend/tax_calc/sint_maarten.py`: the law sets duty at NAf 0, so one uniform line; `mapping.py` uniform hook; registered; tests (`SintMaartenTests`); duty blurb in `importDutyStructures.js`. 4) Full English translation of the 170-article law (unofficial) in `docs/sint_maarten_import_duties_en.md` and uploaded to the knowledge base (173 chunks).

### 2026-10-12 — Tourism values stored and read from the database; update button

**Prompt:** "the tourism and economy values in that table are being built everytime app is loaded, they should be saved to the db nd fetched from there, and updated as uer request, add a button for that. delete the tourism gdp (total) and tourism employement columns as they have no data"

Added `service.stored_rows` / `refresh_rows`, `GET /tourism/stored`, `POST /tourism/refresh`; Market Analysis now loads the stored values and has the 'Update tourism data' button with a last-updated note; removed the two empty columns from that table; made the World Bank fetch parallel (a refresh was taking minutes when the API was slow). Verified in the running app (on load only /tourism/stored is requested; the click posts /tourism/refresh and the timestamp advances).

### 2026-10-12 — Turks and Caicos tax calculator (tariff uploaded)

**Prompt:** "i just added tariffs-duties 2010 turks aand Caicos, check it for the mising information"

The new file is the Customs Tariff (General) Order 2010 with the full tariff table. Checked what it fills (import rates for 5,315 codes, units, landed-cost vehicles, specific alcohol/tobacco/fuel duties, Part IV exemptions) and what is still missing (amendments L.N. 16/2010 / 38/2011, 12 unrated lines, export column empty, freight/insurance and fuel definition). Built `turks_caicos.py`, registered it, `TurksCaicosTests`, rewrote `TURKS_AND_CAICOS_RULES.md`, added the structure line in `importDutyStructures.js`.

### 2026-10-10 — Turks and Caicos: file checked, tariff missing

**Prompt:** "do turks and caicos calculator please"

Read the uploaded `turks and caicos customs ordinance.md` (260 pages): it is the Ordinance and its subsidiary legislation; Part III, the Customs Tariff with the import duty rates, is "(Omitted)". No code written (a fees-only calculator would give no duty and no total). Wrote `backend/tax_calc/TURKS_AND_CAICOS_RULES.md` with every rule the file does contain and what to upload next.

### 2026-10-10 — Standing rule: conflicting rates use the higher one

**Prompt:** "as a rule, if a disagreement like the one on the pork, always go for the higher tariff or tax, leaving the \"conflict\" msg"

Added `rate_pct`/`higher_rate` to `backend/tax_calc/base.py` and applied it to Barbados, Grenada (also the rum/whisky Orders vs the CET: both computed when the gallons are given, the higher used) and Saint Lucia; summaries and `signature()` show the rate actually used; docs (`BARBADOS_RULES.md`, `GRENADA_FILE_REVIEW.md`) updated; rule written into CLAUDE.md and saved as a memory. 5 new tests (`HigherRateRuleTests`).

### 2026-10-10 — Barbados tax calculator

**Prompt:** "read claude.md and diary.md and implement the tax calculator for barbados, i uploaded its document"

Read CLAUDE.md, the diary and graphify first; checked the supermarket service (healthy). Mapped the 1,097-page Barbados file, wrote `backend/tax_calc/barbados.py` (Section A parser with per-page meaning of the middle column, Section B 60% list, Section C safeguard formula, Lists cross-check), registered it,
`BarbadosTests`, `BARBADOS_RULES.md`, and the one-line structure in `src/components/marketAnalysis/importDutyStructures.js` (Barbados now has the green Import duties pill). Verified through the API and Market Analysis; Market Opportunities multipliers work (tomato x1.99, chicken wings x1.86 for Colombia).

### 2026-10-09 — Commit + tourism data-acquisition document

**Prompt:** "yes commit and write a .md document explaining the process to get that data"

Wrote `docs/tourism_data_acquisition.md` (where each indicator comes from, the exact calls, what was verified against the live UN and World Bank APIs, the ISO-to-M49 mapping, the dependency formula, the WTTC licensed-file process, IDB/Statista setup, how to check a value by hand) and committed everything as `ebbae87`. Left out on purpose: `majestic_plt.db`, `__pycache__`, `backend/comtrade/_classification_job.marker.building`, `docs/agent_development/agent_summary.*` (from an earlier session, untracked). The four customs source documents in `backend/documents/knowledge_base/` (about 18 MB) WERE committed, because the calculators rebuild their `tax_data` from them.

### 2026-10-09 — Tourism module: UN SDG API provider for DIRECT tourism GDP

**Prompt:** "Update the existing Global Tourism & Economic Dependency module to correct its missing Tourism GDP data … Implement the official United Nations Statistics Division (UNSD) SDG API as an additional provider … ST_GDP_ZS … add TOURISM_GDP_DIRECT_PCT as a separate indicator, retain TOURISM_GDP_TOTAL_PCT for WTTC … never substitute direct for total … verify the API response format and actual available countries before building the full import pipeline …" (full text trimmed)

Verified the live API first (bulk endpoint, pageSize/page, DataSlice, empty/500/200 behaviours, 149 areas, no ISO codes in GeoArea/List). Added `backend/tourism/unsd.py`, M49 assignment in `registry.py` (+ `M49_OVERRIDES`, UN-name aliases), `service.sync_unsd`/`sync_all`, renamed the WTTC code to `TOURISM_GDP_TOTAL_PCT` (existing rows migrated), `TOURISM_GDP_DIRECT_PCT` source priority = UNSD only, UI columns/chart/sync button. 16 new tests (45 in the module).

### 2026-10-09 — Global Tourism & Economic Dependency module + Market Analysis columns

**Prompt:** "check and implement this prompt adding the columns to the market analysis table" (the long 'VS Code Implementation Prompt — Global Tourism & Economic Dependency Module': five indicators, World Bank / IDB / WTTC / Statista providers, global country registry, calculation engine, data model, UI, charts, exports, API, quality labels, tests, docs).

Phase 1 inspection (stack, conventions, no chart library, no auth layer, no multipart lib) then built: backend package + router + models + 29 tests + README; the Tools page (selector, year modes, sortable/filterable/paginated table, details with provenance, SVG charts, CSV/XLSX/JSON exports, providers panel with WTTC import); and the new column group in the Market Analysis table. Verified with headless Edge/puppeteer (`%TEMP%/pp/chk_tourism.mjs`) and `vite build`.

### 2026-10-09 — Grenada: tax calculator, file review, pending row + Add to Commercial Structure

**Prompt:** "i added \"Grenada custom duties\" to the documentation, create the tax calculator, but also check the file for inconsistencies,  grenada is currrently not created in the commercial structure, so, add it to the market analysis table, and in the company column add a pill \"Add to Commercial Structure\" and redirect user to that page so it create the respective subsidiary and branch"

Built `grenada.py` (+ `GrenadaTests`, `GRENADA_FILE_REVIEW.md`), registered it, restarted the backend. Market Analysis shows Grenada as a pending Caribbean row (Import duties pill green) with the Add to Commercial Structure pill; the redirect prefills the editor. Verified with headless Edge/puppeteer (`%TEMP%/pp/chk_add.mjs`, read-only: it clicks the pill and reads the form, it does not create anything). `vite build` passes.

### 2026-10-09 — Market Analysis: 'Import duties structure' column

**Prompt:** "good day, please read claude.md and diary.md for context, and after that, add to the market analysis/country information table, a new column labeled \"Import duties structire\" and add there all the countries we have created a tax calculator."

Added the column (label spelled 'Import duties structure') to the Country Information table: `src/components/marketAnalysis/MarketAnalysisView.jsx`, `importDutyStructures.js` (new), `MarketAnalysisView.css`. Verified in the running app with a headless render: Bahamas, Jamaica, Saint Lucia, Trinidad and Tobago, United States, Colombia are green; Barbados and Saint Martin '—'. `vite build` passes.

### 2026-10-08 — Saint Lucia: Lists A and C spliced in and loaded

**Prompt:** "here are list a and c path for you to add it to the .md document and replace the current content so it complemnt the calculator: C:\Users\donre\Downloads\Saint_Lucia_orientation_review\pages-599-627.md"

Replaced pages 599-627 of the knowledge-base Saint Lucia .md with the clean extraction (730 pages kept, order intact), and taught `saint_lucia.py` to read the List A/C rows (Saint Lucia column) and use them over the CET rate. Validated against the schedule (0 disagreements). Tests updated.

### 2026-10-08 — Saint Lucia tax calculator

**Prompt:** "check saint lucia customs duties.md that i uploaded to documents and build the calculator for it"

Added `backend/tax_calc/saint_lucia.py` (parser of the CET 2012 text + EPA phase-down table + adapter), registered it, `SaintLuciaTests`. Lists A/C/D (national rates) could not be read reliably — flagged, not guessed (see handout).

### 2026-10-08 — Bahamas tax calculator

**Prompt:** "good, build the calculator for bahamas"

Added `backend/tax_calc/bahamas.py` (schedule text parser classifying tokens by content + adapter), registered in `tax_calc/__init__.py`, `BahamasTests` in `backend/tests/test_tax_calc.py`. Bahamas now appears in Tools ▸ Tax Calculator (backend restarted). Design in the handout.

### 2026-10-08 — Bahamas: rules extracted from the "customs duties explanation" document

**Prompt:** "ok, now analize the new bahamas-customs-1 duties explanation added to documents, to reference what is relevant to build the tax calculator for bahamas, i will load later the actual schedule, in this one i need the rues for the variable rates or any other rule that might apply for it"

The uploaded .md (knowledge base, 3 MB) is the Tariff Bill 2018 **plus its full schedule** (845 pages, plain-text columns). Wrote `backend/tax_calc/BAHAMAS_RULES.md`: charge of duty, the variable-rate mechanism
(Minister's Order up to the 300% ceiling, replaces the general rate, 5-day gazette notice), EPA preferential column, Chapter 98 exemptions, 1% bonded-warehouse duty, excise chapters, units (pound, UK gallon,
"unpackaged" = over 20 lb), what is NOT in the document (VAT, fees, Orders in force, EPA Second Schedule, Excise Act) and how the schedule text must be parsed. No code yet; no adapter registered.

### 2026-10-08 — Trinidad and Tobago tax calculator

**Prompt:** "good morning, read claude.md diary.md for context and get ready to develop the tax calculator for trinidad and tobago. i added to the documentations tab the trinidad-tobago-customs that is the complete duty schedule, check its structure and build the calculator"

Inspected the uploaded schedule (a scanned 596-page PDF, OCR'd into HTML tables; ~6,600 tariff lines, duty rates Free / n% / TT$ per litre, a few rotated pages come out as garbage). Added `backend/tax_calc/trinidad.py`
(parser + adapter, same interface as Jamaica/USA), registered it in `backend/tax_calc/__init__.py`, added `TrinidadTests` to `backend/tests/test_tax_calc.py`, and extended the hint text in `MarketOpportunitiesPanel.jsx`.
Design and numbers are in the handout above. Checked: tomatoes 0702.00.00 = 40% of CIF; chicken wings 0207.14.20 = 40%; CARICOM origin = 0; API `/tax-calc/Trinidad and Tobago/*` answers; 18 tests pass.

### 2026-10-07 — Agent plan: simulations as branches of a `main` baseline, and three model lanes

**Prompt:** "so, simulations will start with a defined baseline, that will be the "main" branch if we compare to github, for each simulation, a new branch is open, and agent play with the values of the new branch. yes update it, but also add which tasks can be performed by locl agent, which ones by api and wich ones done by local and tested by api"

**What changed (documentation only):** `agent_development.md` now describes (a) **branches** — a pinned baseline `main`, one copy of the DB per simulation, an edit log, diff / measure / compare, three-way merge into live as a change set (conflicts listed, never auto-resolved), rebase, discard, a branch-aware `get_db()` via an `X-Agent-Branch` header, network/jobs blocked in branches (§6.1, §6.3, §11.6); (b) **three model lanes** (§8): local only, API only, and local-drafts + API-checks, with a task matrix, the check protocol, a typed local contract, evaluation gates and economics. Also updated: one-page summary, non-goals, constraints, data model (`agent_baselines`, `agent_branches`, `agent_branch_edits`, `agent_model_stats`), API, UI (branch switcher, banner, lane tags), roadmap (≈ 9 weeks human, branches in phase 2, merge in phase 3, local lane in phase 5), tests, risks, decisions 8–10, appendices. New mockups `mockup_branches.png` and `mockup_model_lanes.png`; `mockup_architecture.png` updated. No application code changed. Not committed.

### 2026-10-06 — Air Logistics Builder: layout fixed per screenshot (third pass)

**Prompt:** "check image, there shoul be 2 rows, outbound and return cards, beside each one should be the following cards 1. air logiscs builder 2. shipment builder. air logistic builder should display the type of return, distance, flight time, block hours, block hours cost, that should be shown in user clicks the view route button. the view route button. remove the build route button."

**What changed:** each leg row is now: leg card, **Air Logistics Builder** (only a **View route / Hide route** button; Update/Build route removed), **Shipment builder** (moved out of the leg's ▸ sub-row, always visible; "—" placeholders on the return row), then — on View route — Type of return, Distance, Flight time, Block hours, Block hours cost. Grid is 8 columns. The ▸ sub-row keeps Leg cost %, Leg cost, Target Cargo %, Available cargo, Price x Kg. Frontend only (`RevenueStreamsView.jsx/.css`). Not committed.

### 2026-10-07 — Agent development plan (documentation only)

**Prompt:** "read the graphify files, and the claude.md and diary.md and draft a plan to code an agent for this app, where it can run simulations, update the values and others you can identify in the app modules. also add a description on how will be the ui, if possible with images, all written in an "agent_development.md" document"

**What was done:** read `CLAUDE.md`, the diary, `graphify-out/GRAPH_REPORT.md` / `wiki/index.md` (the wiki index is stale/generic; `graphify query` was used for specifics) and the code the plan relies on (`routers/assistant.py` = the existing Claude tool-use loop with 7 tools and browser "actions"; `routers/sim_parameters.py` whose docstring says its flagged entries are "values a future simulation agent should be able to manipulate"; `gl_engine.py`, `packer/`, `tax_calc/`, the JS money logic in `routeMetrics.js` / `shipmentBuilder.js` / `shipmentFinance.js` / `marketOpportunitySettings.js`; the Simulator, Drivers and Financial Modeling tabs are placeholders). Wrote **`agent_development.md`** (project root): goals/non-goals, module evidence table, principles, tool catalogue by module and tier (read / simulate / reversible write / sensitive), simulation design (Python engine ports with Node parity fixtures + a client bridge for browser-only work + a sandbox copy of the 10 MB DB), change sets with snapshots and undo, modes and guard rules, prompt design, 7 new tables, API, UI, 6-phase roadmap (~7 weeks), testing/evaluation, risks, 7 decisions for the owner, appendices. Pictures in `docs/agent_development/images/` (4 screenshots of the running app + 5 mockup PNGs); mockup sources in `docs/agent_development/mockups/` (`_theme.css` = the app's tokens). No application code changed. Not committed.

### 2026-10-07 — Tax Calculator results saved into the Market Opportunities analysis

**Prompt:** "i need the results of the calculator to be saved into the respective market opportunity analysis, check how the Colombia jamaica is built, so you can identify where to place the values and calculations"

**How Colombia → Jamaica is built (what was found):** Market Opportunities reads ONE stored number per product and pair, `product_tax_multipliers` (destination, origin, product_key → `tax_multiplier` = import taxes / goods value for 1 kg, `landed_multiplier`, tariff line, `detail` = the taxes behind it, `status`, `method`, `note`), through `GET /tax-calc/multipliers`. That number feeds the **Tax ×** column (matched and no-match tables), the **DDP price** = (FCA + air fare) x (1 + multiplier), **Market Level**, the **suggested sell price** and the shipment cost chain (`ShipmentPanel` / `shipmentFinance.js`). Jamaica and the USA are filled automatically (`POST …/multipliers/compute` over the whole portfolio on every Market Opportunities run); Colombia has no automatic calculator (DIAN needs a live lookup per product), so its rows never existed.
**What changed:** (1) `POST /tax-calc/multipliers/save` (router `tax_calculator.py`) upserts a row with `method = 'tax_calculator'` for ANY destination (`DELETE /tax-calc/multipliers` removes it); `compute` now SKIPS rows with that method, so a value the user calculated is not overwritten by the automatic run. (2) The Tax Calculator saves every fresh calculation (per kg, USD) automatically (`toSavedMultiplier` in `taxResult.js`; status `ok`, `review` when the tariff line was a judgement call / the user's choice or DIAN rows were chosen, `incomplete` when a charge couldn't be computed) and shows "Saved to the Market Opportunities analysis of origin → destination: tax multiplier xN" with **Open that analysis** and **Remove the saved value**. Only calculations made in the session are saved — restoring one from the history does not re-save. (3) `MarketOpportunitiesPanel.jsx` now reads the stored multipliers even for targets with no automatic calculator (it used to skip a target when the compute call failed), and its Tax × tooltip explains where a missing value comes from. Verified live: United States → Colombia (a real comparison, 37 rows): calculating Beef Primal Flank/Brisket in the calculator (DIAN: Gravamen 80 %, IVA 0 %) saved x0.80, and the analysis showed x0.80 in the matched table and in the no-match table with the tariff line and rates in the tooltip; the two test values were then removed. 5 new tests (`backend/tests/test_tax_multiplier_save.py`: save/list for Colombia, replace, validation, delete, automatic computation not overwriting a saved value). Not done on purpose: no bulk DIAN lookup of a whole portfolio (hundreds of products x ~5 requests each) — Colombia values are saved as products are calculated. Not committed.

### 2026-10-07 — Tax Calculator: one flow for every country, always per 1 kg in USD

**Prompt:** "lets updte the tax calculator ui, all the countries should ahve the same flow, export country (dropdown) import country (dropdown with the dutestaxes structure built in this case only jamaica, colombia and usa) the exporter country product list to search and select a product, and then the calculation per 1 kg in usd always"

**What changed:** `TaxCalculatorView.jsx` rewritten. Flow: **1 · Countries** (Export country select = the countries with portfolios; Import country select = Colombia, Jamaica, United States — the export country is disabled in it) → **2 · Product** (the exporter's portfolio list with a search box over name/category/HS code, the selected product's details, its price per kg in USD (editable) and, for Jamaica, the commercial-importer tick) → the **result**, calculated automatically, ALWAYS for 1 kg in USD (no quantity field, no free tariff search, no "Calculate" button, no dual currency). Jamaica/USA: the product's tariff line is suggested from its HS code (a select offers the other candidate lines) and `POST /tax-calc/{country}/calculate` runs with `quantity_kg = 1`; Colombia: the product's HS code goes to DIAN (`useDianFlow.js`, `DianLookupPanel.jsx`) — progress steps, a picker when the code covers several DIAN lines (the pick is remembered per product in the store, `dianLines`), a row picker when DIAN lists several valid Gravamen/IVA rows, raw data/Copy JSON/Export JSON — and the rates are applied to the price of 1 kg. One result shape for all (`taxResult.js`: `fromTariffResult`, `fromDianCalculation`). History ("Products calculated") is one entry per origin|destination|product. Store `useTaxCalcStore` bumped to version 2 (only the countries survive the migration). The separate "Colombia (DIAN)" tab and `ColombiaDianPanel.jsx` are gone (its CSS file is reused). Also: DIAN's own listing has double-encoded text ("elaboraciÃ³n"); `fix_mojibake` (parsers) repairs the usual accented sequences, with a test. Verified with puppeteer: Colombia → Jamaica tomato (taxes USD 3.49/kg, x2.23), → United States (duty-free from Colombia), Jamaica → Colombia apples (HS 080810: Gravamen 15 %, IVA EXCLUIDO, taxes 1.34/kg) and beef mince (HS 020130 covers 6 DIAN lines → pick 0201300010 → Gravamen 80 %, 9.03/kg; the pick survives a reload). Not committed.

### 2026-10-07 — Colombia (DIAN) tax calculator: Phase 3–4 (implementation, tests, docs)

**Prompt:** "yes" (approving the Phase 1 plan with its decisions, then the "choose a row when DIAN lists several valid Gravamen rows" behaviour).

**What was built** (all in `backend/tax_calc/colombia_dian/`, README.md there has the full design): `dian_types.py` (result contract + `BROWSER_NOT_INSTALLED`), `selectors.py`, `parsers/` (`dates_numbers`, `tax_table`, `pages` = profile/listing/not-found, `generic_table`), `browser.py` (Playwright in a dedicated worker thread pool = the global session limit, `DIAN_MAX_SESSIONS` 1–2), `navigation.py` (the user workflow, bounded retries, no fixed sleeps), `provider.py` (`DianProvider`), `cache.py` (+ models `DianTariffCache`, `DianCodeAlias` in `models.py`), `service.py` (registry, in-flight sharing, batch, background jobs polled by the UI), `import_taxes.py` (pure Decimal calculator; `iva_base_for_imports` = customs value + Gravamen, unverified), `RECON.md`, `fixtures/` (14 real sanitized pages + 3 `SYNTHETIC_*` for cases DIAN never produced). API (`routers/tax_calculator.py`): `POST /tax-calc/colombia/dian/lookups` → job, `GET …/jobs/{id}`, `GET …/{hsCode}` (waits), `POST …/batch`, `POST …/calculate`. UI: `components/taxCalculator/ColombiaDianPanel.jsx/.css` + `services/dianTax.js`, shown as a **Colombia (DIAN)** tab in Tools ▸ Tax Calculator (`TaxCalculatorView.jsx`; mode kept in localStorage). `requirements.txt` pins `playwright==1.63.0` and `beautifulsoup4==4.15.0`; `.gitignore` has the `debug/` folder; `package.json` has `npm run test:dian-live`.
**Decisions implemented (user-approved):** partial codes resolved through DIAN's "Por código de nomenclatura" listing (0 lines → `HS_CODE_NOT_FOUND`, 1 → profile, >1 → `selection_required`); IVA "EXCLUIDO"/"EXENTO" = `rate: 0` + `classification` tag + DIAN's wording (never legal interpretation); several valid Gravamen rows (e.g. ARANCEL VARIABLE) or a conditional IVA → `gravamen`/`iva` null + `needsInput`, the UI shows radio pickers and calculates with the chosen row; `ivaStatus: "not_listed"` only if the page was recognized, the Gravamen found and the IVA icon absent/disabled or its popup table empty — a failed IVA popup is an error (tested); no date input on DIAN → warning for a non-today date.
**Tests:** 76 offline tests for this module + the old ones = 81 across `backend/tests` (`python -m unittest backend.tests.test_aircraft_catalog … backend.tests.test_dian_provider backend.tests.test_dian_live`; unittest discovery needs explicit module names here); live: `npm run test:dian-live` (calls DIAN once, ~14 s, excluded from the default run). Verified through the real UI with puppeteer: 0702000000 (15 % / 0 % EXCLUIDO), 6109100000 (40 % / 19 %, 1,000 → 666 taxes), lard 1501100000 (row picker; choosing the variable row gives 0 % Gravamen), `0901` (7-line picker → coffee 15 % / 5 %), invalid code (`HS_CODE_NOT_FOUND`).
**Gotchas worth remembering:** (1) uvicorn `--reload` on Windows installs the Selector event-loop policy, which can't spawn subprocesses — Playwright then fails with `NotImplementedError`; `browser.py` switches to the Proactor policy inside the worker thread. (2) The `--reload` watcher said "Reloading…" but didn't restart the server — restart it fully after backend edits. (3) The harness halves backslashes typed in shell commands: when writing Windows paths into JSON use `chr(92)`. (4) npm scripts run in cmd.exe, so `package.json` needs `.venv\\Scripts\\python.exe`. Not wired into Market Opportunities' Tax × column / `product_tax_multipliers` (Colombia is not a `Calculator` adapter yet). Not committed.

### 2026-10-07 — Colombia (DIAN) tax calculator: Phase 0–2 (repo inspection, plan, live-site reconnaissance) — NO code yet

**Prompt:** the user pasted a long spec ("Task: Tax Calculator module (Colombia / DIAN, Gravamen + IVA only)", Playwright against MUISCA WebArancel, provider-based, phased with stops for approval after Phase 1 and 2), then asked for "full interaction with dian page" and to re-read CLAUDE.md/diary.md to understand what the tax calculator is for.

**What was done:** Phase 0/1 — repo is React+JS / FastAPI+SQLAlchemy+SQLite (no Electron, no TS), so the spec was adapted to Python inside `backend/tax_calc/` (plan + 6 questions given to the user; no official DIAN API/open data found, terms page not explicit about automation; Decreto 1881/2021 is the static alternative for Gravamen). Phase 2 — drove the real DIAN site with Playwright (Python 1.63, headless, one session, ~100 lookups, no CAPTCHA). Findings are in `backend/tax_calc/colombia_dian/RECON.md`, sanitized snapshots in `backend/tax_calc/colombia_dian/fixtures/` (14 HTML files). Key surprises vs the spec: (1) no date input — historical lookups unsupported; (2) partial codes silently return the FIRST line under the prefix on the "General" page, but the "Por código de nomenclatura" page lists all lines (basis for `selection_required`); (3) IVA is never missing — exclusion/exemption are explicit rows ("0 % - EXCLUIDO"/"EXENTO"), plus conditional multi-row IVA (phones etc.); (4) Gravamen can have an extra time-limited "ARANCEL VARIABLE" row; (5) popups are real new pages with clean `<table class="consulta">` markup. Throwaway scripts live in `%TEMP%/dian` (not in the repo). Nothing in the app changed; not committed. Waiting for the user's approval/decisions before Phase 3.

### 2026-10-06 — Wholesalers: Min profit margin and Cap reduction

**Prompt:** "add 2 new input % cell for the wholesalers row in the market opportunity settings/destination market, one labeled "min profit margin" to enter the % of difference in the cost/profit margin, and the second labeled "Capreduction" reduction of the max payload cap for products between that range. example "nevada potato" cos is 4620, and revenue is 4664, the profit margin is only 0.95% if the min profit margin is set at 10% and the cap reduction is 500 kg, the max amount of that product should be only 700 kg. the idea is to ship less products that doesnt leave that much margin, but still keep variety on the portfolio."

**What changed:** the Wholesalers row of Settings ▸ Market Opportunity settings ▸ Destination Market has two more inputs, **Min profit margin** (%) and **Cap reduction** (kg) (`min_margin_pct`, `cap_reduction_kg` in the stored JSON; `routers/market_opportunity_settings.py`, `MarketOpportunitySettingsCard.jsx/.css` — the row is now a wrapping flex row). Rule in the Shipment builder (`ShipmentBuilderModal.jsx`, `levelFor`): for a wholesale product, margin % = (suggested sale price per kg − DDP per kg) / DDP per kg (the user's example: 4,664 vs 4,620 = 0.95 %; the sale price already has the "never below cost" floor, so floored products have 0 %); if margin < Min profit margin, its cap (the wholesalers' Cargo Cap, or the 1,500 / 200 kg default) loses the Cap reduction (1,200 − 500 = 700 kg), floor 0. Allocation is unchanged (`allocateShipment` just sees the lower `capKg`), so the freed cargo flows on to premium/niche and nobody is dropped. The builder table marks such products with "↓" next to the market level (tooltip: margin % and the new cap) and shows the margin % in the tooltip of the others. The user's label "Capreduction" was written as "Cap reduction". Both inputs are empty by default (rule off) — the user must fill them; settings were not touched. Backend restarted (new fields). Verified headless: the Wholesalers row shows 6 inputs; the builder modal loads without errors (no product reduced since the values are empty). Not committed.

### 2026-10-06 — Bug fix: sale price below cost

**Prompt:** "i see a bug, the sale price is lower than the cost that for logic cannot be happening" (screenshot: Green Onion cost USD 4,318, sale USD 4,081, Market level Wholesalers).

**What changed:** cause — the wholesale rule sells at `sell_pct` % (60) of the TARGET price, while a product is "Wholesalers" whenever its DDP is up to 70 % of the target price (the user's saved range 0–70), so every product with DDP between 60 % and 70 % of the target sold below cost. `suggestedSellPrice` (`services/marketOpportunitySettings.js`) now never returns less than the DDP price: when the rule gives less, the product sells at cost and the tooltip says so ("… is below the cost (DDP price), so it sells at cost"). Applies everywhere it is used (cards, Details, route/leg Revenue/Profit, Market Opportunities column). Verified headless on route 1: 36 products, 0 below cost, 5 at cost. The settings were NOT touched (saved: wholesalers 60 %, niche 20 %, premium 30 %). Open question for the user: if wholesalers should earn a margin, the rule needs changing (e.g. sell at the range top, 70 %, or DDP + a profit %), since 60 % of the target is below the top of the 0–70 % range. Not committed.

### 2026-10-06 — Return COS x Kg, per-leg Revenue / COS / Profit cards, route totals = both legs

**Prompt:** "add ti the return "shipment builder" beside the GSA proce X kg, another input card labeled COS X Kg. 2) update the shipment revenue, cos and profit to be the sum between the 2 routes, and add an individual card for each one of the legs beside the shipment builder cards, for the return leg, if the type of return in the outbound is selected Full, it should be for the total revenue, the multiplication of the gsa price x kg x available cargo, for the cos card, the cos x kg * available cargo and the profit the difference beween them. if the selection is compensated, the calculation is between the return route price x kg * available cargo, the cos, same as the other one and same for profit"

**What changed:** (1) New route field `return_cos_per_kg` (backend: `models.py`, `main.py` migration, `routers/revenue_streams.py` out/settings models + validation) and a **COS x Kg** input card next to **GSA price x Kg** in the return "GSA terms" panel; for a *compensated* return the Shipment builder card also gets an **Add COS / Update COS / Hide COS** button opening a "Return terms" panel (return route Price x Kg read-only + the COS x Kg input). (2) New `ShipmentBuilder/useLegFinance.js` (`returnLegFinance` + the hook), `LegFinanceCards.jsx` (three cards **Shipment Revenue / COS (red) / Profit** beside each leg's Shipment builder card) and a rewritten `RouteFinanceCells.jsx` (route table cells = sum of both legs; the tooltip lists the legs counted; a leg with no figure adds nothing). **Outbound** leg = as before (sale prices of its shipment; COS = DDP; profit also less the empty-payload cost). **Return** leg: full → revenue = GSA price x Kg x available cargo; compensated → revenue = the return route's own Price x Kg x available cargo; both → COS = COS x Kg x available cargo, profit = revenue − COS (no empty-payload discount on the return). "Available cargo" = return target cargo % x the aircraft's max payload. The return shipment's products (compensated) no longer feed the money figures. Verified headless (no console errors): route 1 — outbound revenue 128,147 / COS 95,891 / profit 32,256, return revenue 4,725 (COS not entered yet → "—"), route totals revenue 132,872. Backend restarted (new column; also added by importing `backend.main`). Not committed.

### 2026-10-06 — Builder order: wholesalers, then premium, then niche share the rest

**Prompt:** "confirm that the math follows this process: the top cap should be given to the wholesaler level products, so all of them should get the 1200 kg of space, then the premium products should get the top cap, 200 kg, and then the remaining space should be divided by the remaining niche products. lets try it like that"

**What changed:** the previous allocation did NOT follow that (niche and premium shared the leftover under one common cap). `allocateShipment` (`ShipmentBuilder/shipmentBuilder.js`) now: (1) every wholesaler gets its full cap, (2) every premium product its full cap, (3) the niche products (and any with no market level) split what is left evenly, none above its own cap; cargo left after every cap is the Available P/L. If the full caps don't fit: premium and niche share what the wholesalers leave evenly (nobody dropped); if the wholesalers alone exceed the aircraft, everyone comes down to one common cap. `MARKET_PRIORITY` is now `['wholesalers','premium','niche']`. Checked with `%TEMP%/pp/t2.mjs` at 27,000 kg: 15 wholesalers (1,200) + 6 premium (200) + 10 niche → 1,200 / 200 / 780 each, 31 products, 27,000 kg; niche capped at 400 → 19,000 kg left free; premium squeezed → premium and niche 60 each; wholesalers too big → common cap; manual weight kept. Existing shipments change only after **Update shipment**. Not committed.

### 2026-10-06 — Bug fix: the builder dropped products instead of reducing amounts

**Prompt:** "i found a bug, the builder is removing products from the list instead of reducing the amount of the niche or premium products amounts, if the total weight is above the 27000 kg then for example the niche or premium market products should be capped at 400 kg, the idea is that all the products on the selection are shipped"

**What changed:** `allocateShipment` (`ShipmentBuilder/shipmentBuilder.js`) was greedy (each product up to its cap in priority order), so once the aircraft was full the later products got 0 kg and vanished. Now every selected product ships: if the caps fit, each gets its cap; if not, the non-wholesalers (niche, premium, no level) share what the wholesalers leave under ONE common reduced cap (`waterFill`: products with a smaller cap keep it, the rest is split evenly — e.g. "niche/premium at 400 kg"); only if the wholesalers alone exceed the aircraft do they come down to a common cap too. Manual weights stay fixed; kilos lost to rounding go to the highest-priority product under its cap. The modal's explanation text was updated. Checked with a node harness (`%TEMP%/pp/t.mjs`): 27 products over 27,000 kg → all 27 ship, 27,000 kg; caps that fit → leftover stays as Available P/L; wholesalers alone too big → common cap with the 400 kg niche kept; manual weight respected. Existing shipments are unchanged until **Update shipment** is pressed. Not committed.

### 2026-10-06 — Available P/L pill is a link; source price for the no-match products

**Prompt:** "make the "available P/L" pill a button that redirects user to the respective market opportunities page. 2) check why the products in the market opportunity do not have the origin or source price"

**What changed:** (1) The green **Available P/L** pill is now a `<button>` (`RevenueStreamsView.jsx/.css`) that opens `/market-analysis?tab=market-opportunities&source=<origin country>&target=<destination country>` of that leg (country names from `fetchMarketAnalysisRegions`, loaded once in the view). Verified with puppeteer: MDE → KIN lands on Colombia → Jamaica. (2) **Cause of the missing source price:** all 78 matched rows have `source_price_normalized`; the blanks were in the "No match found in target market" table — 22 of its 171 products (vegetable oil bottles/jugs, liquid milk, coffee 500 g…) have prices that aren't per kg, and the count/volume → kg conversion only runs on MATCHED pairs (`marketOpportunities.js`), so `fetchCountryProductPrices` returns `priceUsdPerKg: null` for them. Fix: `fetchCountryProductPrices` now also returns `original` (value / unit / currency), and the no-match table shows the original price (e.g. "COP 12,000 / bottle") under the USD/kg figure, with "—" + a tooltip for USD/kg when it can't be converted. All 171 rows now show a source price. DDP / sell price for those still need USD/kg, so they stay blank for the 22. Verified headless (no console errors). Not committed.

### 2026-10-06 — Cost (red) / sale (green) on product cards; Shipment Revenue, COS, Profit in the route table

**Prompt:** "it seems to be working, now in the fresh 24 revenue product cards, make the product cost in red and the product sale price in green, and place them side by side, remove the "sale price" text. add to the route tabl, 3 columns beside aircraft the first one labeled "Shipment Revenue" with the sum of all products sales prices, then othr labeled COS (in red) with the sum of all product cost, and the third labeled Profit with the differene between the total and cos columns. if the total payload is less than the total available, like in the mde-kin outbound route, then the difference of the unused space should be discounted of the profit."

**What changed:** (1) Shipment product cards (`ShipmentBuilder/ShipmentPanel.jsx/.css`): `1,000 kg` then the cost (DDP total, red) and the sale price (green) side by side, no "Sale price" text (tooltips explain); cards widened to 11.5rem so each USD value stays on one line. (2) New `ShipmentBuilder/shipmentFinance.js` (shared by the cards and the route table: `loadShipmentContext` with a 30 s cache, `costsFor`, `financeForShipment`) and `ShipmentBuilder/RouteFinanceCells.jsx`; the route table (`RevenueStreamsView.jsx`) has **Shipment Revenue** (sum of the suggested sale prices), **COS** (red, sum of DDP totals) and **Profit** after Aircraft. Profit = revenue − COS − the cost of the payload that flies empty = (aircraft max payload − kg carried) x the leg's air fare per kg (Price x Kg); hover for the breakdown. Both legs count when the return is compensated and its shipment is built. "—" until a shipment is built or while any product lacks a price. `legPricePerKg` (routeMetrics.js, covers both legs; `outboundPricePerKg` kept as a wrapper). Verified with headless Edge + puppeteer-core (installed in `%TEMP%/pp`, not in the project): route 1 shows revenue USD 87,836, COS USD 64,284, profit USD 15,222 (23,552 − 8,330 for the 8,400 kg unallocated), no console errors. Interpretation: "the unused space" is valued at the leg's air fare per kg; the return leg's GSA-terms case (return type full) is not counted. Not committed.

### 2026-10-06 — Bug fix: black screen on Colombia → Jamaica Market Opportunities

**Prompt:** "there is a bug, when i try to reach the colombia jamaica market opportunities the screen goes black"

**What changed:** `MarketOpportunitiesPanel.jsx`: the local `marketLevelFor` returned `key` but destructured only `{ level, share, configured }` from `destinationLevelFor`, so `key` was undefined — a ReferenceError (React unmounted the app = black screen) as soon as a rating group with a built shipment's DDP values rendered (also on the `?product=` link). Added `key` to the destructuring. Reproduced and verified with headless Edge (`msedge --headless=new --enable-logging=stderr --dump-dom <url>` prints the console errors — handy for checking a page for crashes without a browser). Lesson: I had not rendered the expanded table after adding the sell price column; always load the page after UI edits. Not committed.

### 2026-10-06 — Suggested sell price (Market Opportunities column + shipment sale price)

**Prompt:** "now, add a new colum to the market opportunities table, and build a tool that calculate the suggeted sell price to be matching the top % of the category, for wholesaler is 60% for the niche market add 20% of profit over the price and for premium also 20%. then in the shipment builder, beside the product totla cost add the product total sale price"

**What changed:** `suggestedSellPrice(marketKey, ddpPerKg, targetPrice, markets)` in `services/marketOpportunitySettings.js`: **wholesalers** = `sell_pct`% of the TARGET price (default 60); **niche / premium** = the DDP price + `sell_pct`% profit (default 20 each). The percentages are editable in Settings ▸ Market Opportunity settings ▸ Destination Market (a new "Sell at (% of target price)" / "Profit over DDP" input per category; stored as `sell_pct` in the JSON; `routers/market_opportunity_settings.py` fills the defaults for rows saved before it existed). Market Opportunities: new **Suggested sell price** column after Market Level (also for the no-match products, always niche: DDP + 20 %; shown with the DDP / Market Level columns, i.e. when a shipment is built for the pair). Shipment cards (`ShipmentPanel.jsx`): a green "Sale price USD …" line (suggested sell price per kg x weight) under `kg / DDP total`, a "sale total" in the shipment header, and a "Suggested sale price" section in the Details popup. Interpretation: "matching the top % of the category" was read as wholesalers = 60 % of the target price (an in-range value under the 0–70 % wholesaler range), not the range's own top (70). Frontend + settings JSON only; backend restarted (the reloader missed the edit). Not committed; not checked in the browser.

### 2026-10-06 — Market-first shipment allocation, Cargo Caps, manual weights, Available P/L, no-match checkboxes

**Prompt:** "add the checkbox for each product in that category too, but automatically assign the nichemarkets level 2) add to the settings/market opportunity settings/destination markets, a new input cell labeled "Cargo Caps" 3) the shipment builder is gving priority to products with higher country sam, now first priority to assign the max weight is the market, whole saler first, niche market second and premium third, then by sam, and update the builder to use the just added value for market cap in settings 4) in the details popup, add an "Edit" button that enables an input cell to modify the assigned weight, and once modified, a save button will save the new value and a "manual" small pill just beside the product name should appear. 5) in the shipment builder card, if total products weight is below the max cargo of the aircraft, a green background pill labeled "Available P/L" should appear"

**What changed:** (1) `MarketOpportunitiesPanel.jsx`: each no-match product has a priority checkbox (they count in `rowKeys`), and the Market Level cell of the no-match table shows **Niche Markets** (`UNMATCHED_MARKET_KEY = 'niche'`). In the Shipment builder such a product is a niche product too: it is built from the source portfolio (price, HS code, SAM by its HS code) and listed under "Unrated". (2) Settings ▸ Market Opportunity settings ▸ Destination Market: a **Cargo Caps** input (kg) per category (`cargo_cap_kg` in the stored JSON; `routers/market_opportunity_settings.py`, `MarketOpportunitySettingsCard.jsx/.css`) — the most kg of ONE product of that category per shipment. (3) `shipmentBuilder.js` `allocateShipment` rewritten: greedy fill product by product up to its cap, ordered wholesalers, niche, premium, no level, then Country SAM desc, then Diff % asc (`MARKET_PRIORITY` in `services/marketOpportunitySettings.js`); a product's cap = its market's Cargo Cap, else the old 1,500 kg (200 kg without SAM); cargo no cap can take stays unallocated (it used to be spread proportionally). The market level of a product in the builder = DDP per kg (needs the route's air fare, now passed to the modal as `airfarePerKg`, plus the tax multiplier) as a % of the target price against the Destination Market ranges; the modal table has a Market level column. `marketLevelFor` now also returns the category `key` and `cargoCapKg`. (4) `ShipmentPanel.jsx`: Details popup has **Edit** (weight input, Save/Cancel; max = free payload + the product's own weight) — saving stores the item with `manual: true` (backend `ShipmentItemIn.manual`), flags a small **manual** pill beside the product name (card and popup), and `RevenueStreamsView.jsx` `handleSaveShipment` persists it. Updating a shipment keeps manual weights fixed and allocates only the rest. (5) The Shipment builder card in the leg row shows a green **Available P/L** pill when the shipment weighs less than the aircraft's max payload (tooltip: kg free). Not committed; not checked in the browser.

**Incident (mine):** while testing the settings endpoint I PUT a payload that overwrote the saved Destination Market ranges; I restored them at once from the values read just before (Premium 100–2000, Niche 70–100, Wholesalers 0–70), but the margin ranges were overwritten with the defaults in the same call — if the user had edited those, they must re-enter them. Lesson: never PUT to a settings endpoint to test; read-only checks only. The backend was restarted again (the Cargo Cap field needed it).

### 2026-10-06 — Region SAM and Country SAM for the no-match products

**Prompt:** "make sure the region sam and country sam are also updated in the no match category"

**What changed:** `MarketOpportunitiesPanel.jsx`: the no-match tables now show **Region SAM** and **Country SAM** (same lookups and tooltips as the matched rows, by the product's own 6-digit HS code from the source portfolio). The SAM request (`hsKey`) now includes the HS codes of the unmatched products as well as the matched rows, so they are fetched with the same call; `sourcePrices` state moved above it. Products without a 6-digit HS code stay blank. Not committed; not checked in the browser.

### 2026-10-06 — Unmatched products as a table; Market level on shipment cards

**Prompt:** "in the market opportunities, give the no match found in target market the same table structure as the other categories, leaving out the values and calculations that are not available. 2) in the shipment builder,products card, add to the main card the market level of the correspondent product,"

**What changed:** (1) `MarketOpportunitiesPanel.jsx`: each "No match found in target market" group now opens a table with the same header as the rating tables (the header is the shared `tableHead` const). Only what is known is filled in: product (+ category), HS code and source USD/kg (from the source portfolio, `fetchCountryProductPrices`, kept in `sourcePrices`), Tax × and — when a shipment is built for the pair — DDP price; target product/price, SAM, Diff %, Opportunity, Market Level and Confidence are left blank. (2) `ShipmentBuilder/ShipmentPanel.jsx`: each product card shows **Market level: <category>** (DDP per kg as a % of the comparison's target price vs the Destination Market ranges; tooltip gives the %). The rule is now shared: `marketLevelFor` in `services/marketOpportunitySettings.js`, used by both pages. Like the column, it shows "—" until the Destination Market ranges are filled in Settings. Not committed; not checked in the browser.

### 2026-10-06 — Active sidebar tab gradient; DDP price + Market Level columns

**Prompt:** "1)give some degraded background coloring with transparency to the actibe tab in the lateral tab. 2) if a shipment has been built for the a specific market opportunities comparison, e.g. Colombia Jamaica, add a new column named DDP price beside the Opportunity one, and calculate the final ddp price for all the products using the formula in the build shipment module. then beside that column add another one labeled "Market Level" and comparing the target price and the ddp price, using the market opportunity settings/destination market, assign the correspondent level"

**What changed:** (1) `SidebarNavItem.css`: the active item has a left-to-right sky-blue gradient fading to transparent, with a soft border. (2) `MarketOpportunitiesPanel.jsx`: when a route has a built outbound shipment from the comparison's source country to a target country, two columns appear after **Opportunity**: **DDP price** (USD/kg = (FCA price + air fare) x (1 + tax multiplier), for every product of the comparison — FCA = `source_price_normalized`, tax multiplier = the Tax × column, air fare = that route's outbound Price x Kg) and **Market Level** (DDP as a % of the target price, matched against the Settings ▸ Market Opportunity settings ▸ Destination Market ranges; first category whose from/to contains it, an empty end = open). New `services/shipmentPricing.js` (`fetchBuiltShipmentAirfares`: loads every company's routes/branches/providers/aircraft, finds routes with a built shipment between the two countries) and `outboundPricePerKg` in `FinancialTab/routeMetrics.js` (a copy of `priceFor` in `RevenueStreamsView.jsx` for pages without a route card — keep the two in step). Cells show "—" with a tooltip explaining what is missing (route has no air fare yet — set type of return, leg cost % and target cargo % —, no tax multiplier). **Market Level stays "—" until the Destination Market ranges are filled in** (they are empty by default; the tooltip shows the DDP/target %). Interpretation: level compares DDP as a % of the target price (same orientation as Diff %). Not committed; not checked in the browser.

### 2026-10-06 — Accounting Health Check to Tools, collapsible Tax Calculator, Market Opportunity settings

**Prompt:** "1) move to the tools tab, the "accounting health check" pannel from settings. 2) make the tax calculator panel also collapsible, 3) add a new card in settings labeled "Market Opportunity settings and inside it add 2 tabs, 1 labeled Market opportunity margin" and import the market opportunities categories and its values, make the values editable in 2 cells, like "Very high" between: 0% and 20%, so they are no longer hardcoded, but set from this panel. and also wire the the values for being fetched form here for the market opportunities calculations. the second tab is labeled "Destination Market" an inside create the following categories also with the 2 input cells a. Premiun Market b. Niche Markets and c. Wholesalers."

**What changed:** (1) `AccountingHealthCheckCard` removed from `SettingsView.jsx`; it is now the third Tools tab, `/tools/accounting-health-check` (`App.jsx`, `ToolsView.jsx`). (2) `TaxCalculatorView.jsx`: the header is a chevron toggle that folds the whole panel (state remembered via `usePersistentSet('tax-calculator:collapsed')`). (3) New Settings card **Market Opportunity settings** (`SettingsView/MarketOpportunitySettingsCard.jsx/.css`, collapsible, two tabs). **Market opportunity margin:** the six ratings with a from/to % pair each (Very High 0–20, High 20–30, Challenging 30–50, Complex 50–65, Difficult 65–100, Not Viable 100+); each range starts where the previous ends, so editing one end moves its neighbour; first starts at 0, last has no limit. **Destination Market:** Premium Market / Niche Markets / Wholesalers, each with a from/to % pair — stored only, NOT used by any calculation yet (the user didn't say what they drive; units assumed %, empty by default). Backend: table `market_opportunity_settings` (model `MarketOpportunitySettings`), `routers/market_opportunity_settings.py` (`GET/PUT /market-opportunity-settings`, validation, `get_margin_tiers`, `rating_for`), registered in `main.py`; `routers/market_opportunities.py` no longer hardcodes the scale — `save_comparisons` rates with `rating_for(diff_pct, get_margin_tiers(db))`. Saving the settings **re-rates every saved comparison** from its stored `diff_pct` (the rating is stored per row). Boundary note: a tier is min <= diff < max, so a diff of exactly 100% is now "Not Viable" (was "Difficult"). Frontend service `services/marketOpportunitySettings.js`. The backend had to be restarted for the new route (auto-reload missed it). Not committed; not checked in the browser.

### 2026-10-06 — Product link lands on the product, persistent route panels, Tools tab

**Prompt:** "perfect, 1) if the product name is clicked, take user as close as it is to the product info, for example if it is located in the very high category, expand it and position the screen where user can see it and navigate the less possible. 2) the routes keep collapsing after tab changes, it should be persistent to keep the opened tabs. 3) in the lateral tab below settings, add a new tab labeled tools, and move in there the tax calculator and rag tabs"

**What changed:** (1) `MarketOpportunitiesPanel.jsx` reads `?product=` (passed down as `focusProduct`): once the comparison's rows are in it expands that product's rating group, clears the search / target filter (and leaves the priority-only sort), scrolls the row (`id="mo-row-<id>"`) to the middle of the screen and highlights it for 6 s (`tr.is-focused` in `MarketAnalysisView.css`). The Shipment builder card link already carries the product name. (2) New `utils/usePersistentSet.js` (a Set in state mirrored to localStorage); `RevenueStreamsView.jsx` uses it for the expanded routes, the open route panels, the shown shipments and the GSA cards (keys `revenue-routes:*`), so they survive tab changes and reloads. (3) New sidebar item **Tools** (below Settings) → `/tools` (`components/tools/ToolsView.jsx/.css`, pill sub-nav + `Outlet`) with **Tax Calculator** (`/tools/tax-calculator`) and **RAG Files** (`/tools/rag-files`); the two sidebar items are gone and the old `/tax-calculator` and `/rag-files` paths redirect (`App.jsx`, `Sidebar.jsx`). Not committed; not checked in the browser.

### 2026-10-06 — Product name links to Market Opportunities; FCA price fixed (Perolera Pineapple)

**Prompt:** "it was a typo 1)make the product name in the card also a link to the market opportunities, so user can navigate direct to it and investigate why for example the "perolera pineapple" does not have a FCA cost, but in th market opprtinities it is present."

**What changed:** In `ShipmentBuilder/ShipmentPanel.jsx` the product name on each shipment card is now a router `Link` to `/market-analysis?tab=market-opportunities&source=&target=&product=` (the panel reads source/target; the `product` param is passed but Market Opportunities doesn't use it yet). **Root cause of the missing FCA:** the panel took the origin price from the portfolio collectors (`fetchCountryProductPrices`), which can't convert count-based units like Perolera Pineapple's "CAJA DE MADERA (32 per package)" (the comparison converts it with a cached AI pack-weight estimate, USD 0.59/kg). The FCA price now comes from the saved comparison's `source_price_normalized` (`fetchMarketOpportunityComparisons`), i.e. exactly the price Market Opportunities shows; the red "no price" note now says it is missing from that comparison. Not committed; not checked in the browser.

### 2026-10-06 — Shipment product cards: Details popup with FCA / DAP / DDP, 50 % builder cards

**Prompt:** "perfect, 1) change the cards color background to have 50% transparency, also outbound should be different blue shades and return different shades of yellow. 2) to each product card in the shipment builder i need you to add the following a. remove from card the market opportunity information, but keep it as a tooltip b. add a "details" button to open a popup product expanded card, with the following information FCA cost, and multiply the product amount by the product origin country cost like 1 kg = USD$1, total = USD$1500, below it, DAP cost displaying the multiplication between the product amount in kg x the price per kg(air fare) like Price x kg = USD$ 1 Total = USD$1500,, and below it the DAP subtotal liketotal DAP = USD$3000. below it add "DDP at Terminal", and multiplly the total dap cost by the product tax multiplier that is in the market opportunities origin/destination countries comparison, if no comparison exists then flagg it in red and pop a window to redirect usr to build it in the market opportunities tab like TAX X = 1, total = USD$3000. below it add the DAP total = USD$6000. display the DAP total beside the product amount in the product card like 1,500 Kg / USD$6,000"

**What changed:** (1) Builder cards (Air Logistics Builder, Shipment builder) are 50 % transparent: outbound = dark blue (#1d4ed8) + sky blue (#38bdf8), return = dark amber (#b45309) + amber (#fbbf24) (`RevenueStreamsView.css`). (2) New `ShipmentBuilder/ShipmentPanel.jsx/.css` replaces `renderShipment`: the leg's built shipment as cards showing `1,500 kg / USD$ <DDP total>`, the old SAM/Diff/share/HS/rating line now a tooltip, and a **Details** button opening a popup: FCA (kg x the origin portfolio price per kg, `fetchCountryProductPrices`, matched by product name), DAP (kg x the leg's Price x Kg = air fare, passed from the route panel's `priceFor(leg)`), Total DAP = FCA + DAP, DDP at Terminal = Total DAP x the product's tax multiplier (`fetchTaxMultipliers(destination, origin)`, the `tax_multiplier` = taxes / goods value), DDP total = Total DAP + those taxes. A product with no multiplier gets a red alert with a "Go to Market Opportunities" button (`/market-analysis?tab=market-opportunities&source=&target=`); a missing FCA price or air fare is flagged red too and the totals show "—". The shipment header also shows the whole DDP total once every product has one. Interpretation notes: the user wrote "DAP total" for the last line — I labelled it **DDP total**; "TAX x = 1, total = 3000" was read as taxes = Total DAP x multiplier, added to Total DAP. Frontend only. Not committed; not checked in the browser.

### 2026-10-06 — Blue-background bug, GSA terms and return shipment builder

**Prompt:** "remove the blue baackground from the outbound, return and return's leg shipment builder. 2) in the return shipment builder if the outbound route type of return "full" is selected then the shhipment builder should render a button labeled "add GSA terms" and once it is clicked, a carfor user input a $ value. if the selection is "compensated, then the same process for the outbound route should be followed. 3) check that you are updating the diary.md as instructed after finish every prompt"

**What changed:** (1) The blue fill was my own CSS bug: an earlier insert of the `--air` rule landed inside an existing selector in `RevenueStreamsView.css` and painted the value of every Outbound/Return card blue (and dropped their text colour). Fixed; the Air Logistics Builder card keeps its own darker blue. (2) The Return leg's **Shipment builder** now follows the Type of return: none chosen → "—"; **full** → an **Add GSA terms** button (Update/Hide GSA terms afterwards) that opens a card under the Return row with a USD price-per-kg input, stored in the existing `return_price_per_kg` (the return panel's Price x Kg now just shows it); **compensated** → Build/Update/View shipment exactly like outbound, using the ShipmentBuilderModal with origin = outbound destination and destination = return airport. New backend: column `revenue_stream_routes.return_shipment` (migration in `backend/main.py`, `models.py`), `PUT …/routes/{id}/return-shipment` in `routers/revenue_streams.py` (shared `_save_shipment` helper), `saveRouteReturnShipment` in `services/revenueStreams.js`. Shown-shipment state is now keyed `routeId:leg`. (3) Diary: rewrote the Handout block (it had gone stale) and added this entry. Not committed; not checked in the browser.

### 2026-10-06 — Independent route panels per leg, ▸ toggle removed

**Prompt:** "correct, structure is the same but they should be independent, and should have the same buttons, and also move from the outbound and return cards the available cargo and price x kg to the air logistics builder card. and remove the dropdown arrow as it no longers have any function" — each leg's Air Logistics Builder card now has its own **View route / Hide route** (state `shownRoutes` keyed `routeId:leg`); the ▸ leg toggle and its sub-row are gone, and everything that was in it (Leg cost %, Leg cost, Target Cargo %, Available cargo, Price x Kg) moved into the leg's route panel next to Type, Distance, Flight time, Block hours, Block hours cost. Return's Shipment builder stays a "—" placeholder (no return shipment exists). `RevenueStreamsView.jsx/.css`. Not committed.

### 2026-10-06 — Route details as shipment-style panels

**Prompt:** "the route cards are being rendered in line with the outbound row … i need them to be rendered below the card, organized as the shipment are … make the route cards to match the shipment cards style" — **View route** now opens a full-width panel under each leg's row (Outbound route, then Return route in amber) using the shipment panel/card classes: Type of return (select, outbound) / Type, Distance, Flight time, Block hours, Block hours cost. The inline cards are gone; grid back to 6 columns. `RevenueStreamsView.jsx/.css`. Not committed.

### 2026-10-06 — Return row starts on its own line

**Prompt:** "now move the return, and the return air logistics and shipment builder below the outbound row" — the Return leg card now starts at grid column 1 (inline `gridColumnStart` in `RevenueStreamsView.jsx`), so Return + its Air Logistics Builder + Shipment builder sit under the whole Outbound row instead of flowing after its cards. Not committed.

### (earlier pass) Air Logistics Builder card on route legs

**Prompt:** "no, you did it all wrong, i needed you to group the cards under the new one, the type of return, distance, flight time etc., those must be under the air logistic builder card, and should be displayed if the view route button is clicked if a route is already built as this one is" (first prompt: add an "Air Logistics Builder" card in a different blue than the shipment builder with a "Build Route" button that displays the other cards, copying the shipment builder's update/view button behavior.)

**What changed:** In Financial ▸ Revenue Streams, each route leg row is now: leg card, **Air Logistics Builder** card (darker blue, `--air` class; a "—" placeholder on the return leg), then — only after **View route** — Type of return, Distance, Flight time, Block hours, Block hours cost. Existing routes count as already built, so the card shows **Update route** (opens the route edit modal) and **View route / Hide route** (per-route `shownRoutes` state, hidden by default). The leg's opened sub-row (Shipment builder, Leg cost %, …) is unchanged. No backend change (an earlier `air_route_built_at` attempt was reverted). Files: `RevenueStreamsView.jsx/.css` (grid is 7 columns). Not committed; not checked in the browser.

### 2026-10-06 (later) — Calculator persistence + country-first flow + tax multipliers for all portfolio products

**Prompt:** "add persistency to the calculations performed , the calculator resets the values if i change tabs, 2) in the calculator, move the country selection to be the first step, then list the products from the selected country but keep the search tool, so the calculation is not restricted to that specific product list, once product is selected and if it exists in the product portfolio then fetch also the cost x kg and place it in the calculator 3) the the freight, insurance and type are calculated in another module so here is not neccesary 4) now that we have the calculator and the tax table, i need to add a multiplier column for each category of the products available in the market opportunities, for example in the colombia jamaica tomatoes, should have a x2.23 multiplier, and i need agent to do it to all the products in the portfolio, even those with no match in the target market"

**Done:** (1) zustand-persisted calculator + history of calculations; (2) origin/destination first, origin's portfolio list with price and multiplier, tariff search kept, price auto-fill both ways; (3) freight/insurance/transport removed; (4) multiplier engine (`tax_calc/mapping.py`, table `product_tax_multipliers`, endpoints `compute`/`list`/`suggest`), a **Tax ×** column in Market Opportunities and a multiplier chip on the unmatched products. Interpretation notes for the user: "x2.23" is the taxes as a multiple of the goods value (landed x3.23 also stored); "agent" was built as an automatic batch step (deterministic mapping + calculator, no AI) that runs for the whole portfolio each time a comparison loads; "category" was read as per product row inside the opportunity groups (no category-level aggregate). 14 unit tests (`backend/tests/test_tax_calc.py`). Browser-tested: list/auto-fill/persistence across navigation and reload; the Colombia → Jamaica column and unmatched chips.

### 2026-10-06 — Tax Calculator for every country (Jamaica + United States so far)

**Prompt:** "no, i dont see the point on trying a 14b model, if it fails at a simple task as reading rag, so i want yo build a tax calculator for every country, s far usa have the 2026 hts and jamaica also have the tax file"

**Built** a deterministic, per-country import-tax calculator — see the handout for the design, rules and data. Backend `backend/tax_calc/` (+ `routers/tax_calculator.py`, 8 unit tests), frontend page `src/components/taxCalculator/TaxCalculatorView.jsx` (destination tabs, product search by name or code, shipment form, result with total in local + USD per the currency convention, formula per tax, notes and warnings), sidebar item, route. The US `2026_hts.md` could not be parsed (PDF dump with scrambled columns), so the US adapter uses the official USITC JSON export of the same schedule (downloaded to `backend/documents/tax_data/`). Browser-tested on both countries; `.gitignore` excludes the data folder.

**Follow-up (same day):** the user, testing Jamaica, couldn't see the final cost of the goods (landed cost was only a small grey line). The result now opens with two headline figures — **Final cost of the goods (landed, taxes paid)** with its per-kg value, and Import taxes — and ends with a "Final cost" table: goods + freight + insurance + import taxes = landed cost, plus landed cost per kg and the recoverable advance payments shown separately. Excludes broker/handling/inland costs (stated on screen). Assumptions that need the user's confirmation are listed in the handout (CARICOM origin keeps ASD; GCT base = CIF + duties; MPF figures are FY2026; US additional/reciprocal duties not computed).

### 2026-10-05 (late night) — Can a local model navigate the RAG files by itself? (agent experiment)

**Prompt:** "but the question was clear, so i need solutions not to be hardcoded i need to establish if a local model can do that, as all the information is there and should navigate the rag files"

**Built** `backend/local_models/agent.py` (NOT wired into the chat): a generic tool loop with no tax/tariff/HS knowledge — tools `search` (semantic), `grep` (regex, falls back to all-words, spread over documents), `read` (document passages), `calc`; the model writes one JSON action per turn (gemma3 has no native tool calling); bounded to 10 steps; optional completeness self-review and `think` mode (`ollama_client.stream_chat(..., think=)`).

**Result** (Jamaica baked, the tomato question in 4 wordings, temperature 0; scripts in the session scratchpad, not the repo): gemma3:12b 0/4 in every variant, qwen3:8b (thinking off) 0/4, qwen3:8b (thinking on) 0-1/4 "rates right". What happened: after fixing grep (multi-word, spread across documents) the models DO find the tariff row (`0702000000 … ID 01: 1; ASD05: 0.8; GCT 06: 0.15 …`) but then misread it: they drop the first rate column (ID 01 = import duty, never explained anywhere in the documents), treat fractions as money (JMD 0.80) or as percent (0.8%), and add wrongly. Adding a column-guide document to the folder (a test file, removed again) and a "expand every column" instruction did not fix it. Conclusion: at 8-12B the local models can navigate but are not dependable on tabular numeric derivation; the dependable answer (223.3% / USD 3.37 per kg) came from `import_tax.py` + `tax_report.rates_from_rows`, which read the numbers by code. Next options for the user: try a bigger model with the same harness (qwen3:14b fits 12 GB, ~9 GB download), or accept the hybrid (code reads table rows, model writes/explains). Jamaica restored to "loaded, not baked".

### 2026-10-05 (night, final) — Wrong answer to "how much tax per kg to import tomatoes from Colombia to Jamaica"

**Prompt:** the user pasted gemma3:12b's answer (it described COLOMBIA's tariffs/VAT and said it couldn't find a per-kg cost) — "the answer is far from correct".

**Cause.** (1) The chat answers from the country selected in the dropdown, not the destination named in the question; (2) plain questions only did a semantic top-10 search, never the exact tariff row (Jamaica's row 0702000000 = 100% duty, 80% stamp duty, 15% GCT, 0.3% SCF, 0.85% environmental levy).

**Change.** New `backend/local_models/import_tax.py` + hook in `local_models/reports.py`: a question about import taxes (tax words + "import", no "opportunit") finds destination/origin countries ("to/into X", "from Y"), the product and its HS code (`product_hs_codes` cache), uses the DESTINATION's baked documents, reads the product's tariff row(s), and computes taxes per USD 1 and per kg (origin price from saved Market Opportunities) in code; Gemma writes the answer from those FACTS. `tax_report.rates_from_rows` now reads rates from the tariff row by code (Gemma only breaks ties between rows; words that single out one row decide first, otherwise the catch-all "Other" line) — Gemma had mis-added levies when it read the numbers itself. Also used by the tax PDF. Result for the tomato question: 223.3% of customs value = USD 3.371/kg at the saved Colombian price of USD 1.51/kg (assumes duty/stamp/levies on the customs value and GCT on value+duty+stamp+levies; freight/insurance not included). The destination country must be baked; Jamaica restored to "loaded, not baked" after testing.

### 2026-10-05 (night, last) — Tax PDF moved into the chat

**Prompt:** "no, my idea is to do it from the chatbox, not a specific panel, so gemma is not reliable to build the document?"

Removed the RAG Files panel; the chat now routes tax-on-opportunities requests to the tax report job (see handout). Answer given: Gemma
is reliable at reading evidence and writing text, not at producing a PDF file, unit conversion, arithmetic or choosing between similar
tariff rows — so code builds the file/sums. Tested through the browser chat on Trinidad and Tobago (8 products, snapshot restored).

### 2026-10-05 (night, later) — Portfolio and opportunity files per country, and a Gemma tax-cost PDF

**Prompt:** "add the product portfolios of each country as files to be baked to each country, also the product opportunities, the idea is to run a test for gemma finding the tax cost for the very high opportunity category, and return a pdf with the results, but generated by gemma"

**Changes.** `src/services/ragDataFiles.js` + a toolbar button in `RagFilesView.jsx` add each country's portfolio and opportunities as
Markdown files (not baked). `backend/local_models/tax_report.py`, endpoints in `routers/local_models.py`, `TaxReportPanel.jsx` and
`services/localModels.js`: a local model builds a tax-cost PDF for one opportunity category from the country's baked documents.
"Generated by Gemma" = Gemma reads the evidence, extracts the rates and writes the summary; a model cannot emit a PDF file, so
the layout/arithmetic is code (reportlab).

**Findings during the test.** First run Gemma mixed fractions and percentages (0.4 vs 40) and added totals wrongly, so tariff
rows are now converted to named percentages in code, totals are computed in code, and the summary gets pre-computed FACTS.
After that the 45-product Jamaica run matched the tariff rows. Opportunity wording fixed (the saved `diff_pct` is the source price
as a % of the target price, not a gap). uvicorn `--reload` did not register new routes — a full restart was needed (twice).

### 2026-10-05 (night) — "the chat window is blocked… check if user can create a queue of embedding files"

**Prompt:** "the chat window is blocked, i can't use it. check if user can create a queue of embeding files."

**Diagnosis.** Baking the United States folder (6.3 MB `2026_hts.md`, 8,711 chunks) saturated the 20-core CPU: ONNX used every
core, the old Bake embedded the whole document in one call (so the screen sat at "0 of 1" with no progress and no cancel), jobs
for different countries ran in parallel, and country summaries re-parsed the 6 MB RAG file on every poll. The chat endpoints
themselves answered normally (Claude reply 1.6 s), so it was the machine and the missing feedback, not a hung backend.

**Changes.** Single FIFO queue + worker for Load/Bake with chunk progress, estimate, cancel and per-document commits
(`backend/rag_files/store.py`); queue endpoints and enqueue semantics (`backend/routers/rag_files.py`); embedder thread cap
(`backend/knowledge_base/embed.py`); `bake.json` sidecar; queue UI (`RagFilesView.jsx/.css`, `services/ragFiles.js`); chat
hardening in `useChatbox.js` (a local report is abandoned after 15 min; Stop works before the job id is known).

**Tested** with sample files in two countries (queued Bake showed "Running" + "#1 in line", Cancel dropped the queued one);
both countries restored from snapshots afterwards. Slip: a first API test called `bake-pending`, which briefly baked Jamaica's
profile (43 chunks) — cancelled and reverted; Jamaica is back to "loaded, not baked" and Saint Lucia to "uploaded".

### 2026-10-05 (evening) — Mandatory reads; local Ollama models in the chat, for RAG reports only

**Prompt:**
> make mandatory to read it and also read the graphify files always. 2. i need you yo check and wire ollama son I can run
> local models from the chat window, add a dropdown with the available models that user can select. 3. the local model is
> only to build repprts based on the rag files,

- **CLAUDE.md:** new top section "Session start — MANDATORY": always read `diary.md` (handout, at a glance, newest entries)
  and `graphify-out/GRAPH_REPORT.md` + `graphify-out/wiki/index.md` before anything else (~66 KB of reading), and say so in the
  first reply. The older "read GRAPH_REPORT only when needed" line was changed to match.
- **Ollama check:** v0.20.3 is installed (`C:/Users/donre/AppData/Local/Programs/Ollama`), was not running; models present:
  qwen3:8b, qwen2.5:3b-instruct, qwen2.5-coder:7b, gemma3:4b, llava-phi3, codellama 7b/13b, nomic-embed-text (embedding only,
  filtered out of the dropdown via `/api/show` capabilities).
- **Backend:** `backend/local_models/ollama_client.py` (list models, streaming chat; `think` is turned off for reasoning models),
  `backend/local_models/reports.py` (request → `rag_files.store.search_country` top 10 passages → system prompt that allows
  only those excerpts, cites `[n]`, says "Not covered in the documents." where they don't answer; runs as a polled background
  job with partial text and cancel), `routers/local_models.py`: `GET /local-models`, `POST /local-models/report`,
  `GET|POST /local-models/report/{id}[/cancel]`. There is deliberately **no** general chat endpoint for local models.
- **Frontend:** the Assistant has a **Model** dropdown (Claude — assistant / Local · reports from RAG files: each model, or a
  disabled "Ollama not running"), and for a local model a **Country** dropdown (only countries with a baked RAG file). The report
  streams into the chat; the send button becomes Stop; the choice is remembered in `localStorage`. Local messages are not sent to
  Claude as context. Files: `components/chatbox/Chatbox.jsx`, `useChatbox.js`, `Chatbox.css`, `services/localModels.js`.
- **Tested in the browser** (temporarily baking Saint Lucia's profile copy, then restoring the folder to "Uploaded" and deleting
  the two test chat messages): a 3-line request produced a cited report in ~14 s with qwen2.5:3b-instruct, the selection and the
  report survived a reload, and switching back to Claude restored the normal chat.
- **Follow-up prompt:** "do the button, how large model can 12gb of vram run? as it is for this simple task of writing reports?"
  Added **Open report** on each finished local report (`chatbox/ReportModal.jsx`): larger window, **Copy**, and **Save to
  <Country> folder** (`POST /local-models/reports/save` → `backend/documents/rag_files/<Country>/reports/<timestamp> <slug>.md`
  with a comment header: model, date, request). Tested the same way (Saint Lucia re-baked temporarily, then restored; test chat
  messages removed). Advice given: 12 GB VRAM runs up to ~14B models at 4-bit with an 8k context; 12–14B is the sweet spot for
  grounded report writing.
- **Follow-up prompt:** "try gemma3 12 b" — pulled `gemma3:12b` (8.1 GB) and ran one report request through gemma3:12b, qwen3:8b
  and qwen2.5:3b-instruct (numbers in the handout). Saint Lucia's folder was restored to "Uploaded" afterwards.
- **Not committed.**

### 2026-10-05 (later) — Commercial profiles copied into the country RAG folders; diary handout

**Prompt:**
> add a copy of the available commercial reports to the country rag folder, do not bake them i will test the process.
> 2) i need you to add also to the diary.md a handout in case i have to change or start a new session, and remove it once
> the diary is updated after new entries and also updated at the end

- Copied each of the 8 countries' Country Commercial Profile (`backend/country_profiles/<country id>.md`, the AI-built
  "Commercial Import/Export Profile") to `backend/documents/rag_files/<Country>/source/<Country> - Commercial Profile.md`.
  They show as **Uploaded** on the RAG Files page — not loaded, not baked, so the user can test Load/Bake. Jamaica's is the
  new Country-Commercial-Guide-based one; the others are the older web-research profiles. The Colombia competitiveness
  analysis (`backend/competitiveness_analyses/`) was not copied (it belongs to a country id that no longer exists).
- Added the "Handout — start here" block at the top of this diary with the rules for keeping it current (read it, add
  entries, delete it, write a fresh one last), and the same rule in `CLAUDE.md`.
- **Not committed.**



### 2026-10-05 — RAG Files, scrollable sidebar, this diary



**Prompt:**

> 1) create a diary.md file, where you will save my prompt, and the summary of the fixes, and before spending any

> token on cache or the regular process you can go and get updated like a progress wiki 2) make the lateral bar

> sections scrollable, and only show 4 tabs per section. 3) add above the settings tab, another labeled "RAG Files"

> and inside it add a tab for every country created in the commercial structure. 4) to the rag files add a "Add

> file" button and a dropdown listing the available countres. 5) i need you to import and improve the file in this

> path: D:\OneDrive\0. software Lab\PDF to RAG intgrating a modified version of the ui for app layout consistency,

> and destination folder should be a folder linked or named after the country being added to. i need the module be

> able to accept not only pdf, also csv, .md, excel, word. 6) once user load the documents, a button labeled "load"

> should transform the files into .json files, and once added t the flder as json, then a "Bake" button in each

> country card that have files that has not been processed into embeded files should be in red background, so at

> click, it update the country file adding the new documents



**Changes:**



- **Diary:** this file, plus a rule in `CLAUDE.md` to read it first and add an entry per prompt.

- **Sidebar** (`layout/Sidebar/Sidebar.jsx/.css`): the main nav and the company list are each a scrollable section showing

  four rows (nav rows now a fixed 2.7rem; company rows are 3.325rem); the bottom block (RAG Files, Settings, user,

  assistant) is pinned to the bottom with `margin-top: auto`.

- **RAG Files page** (`/rag-files`, sidebar item above Settings): `components/ragFiles/RagFilesView.jsx/.css`,

  `services/ragFiles.js`. One tab per distinct commercial-structure country (red dot = needs bake), a country dropdown +

  **+ Add file** (also drag-and-drop onto the card), a per-country card with **Load (n)** and **Bake** (red while loaded

  documents aren't baked yet; "Baked ✓" and disabled otherwise), a file table (status chip, sections, remove) and an

  expandable section list per loaded file.

- **Converter** `backend/rag_files/convert.py`, ported from `D:\OneDrive\0. software Lab\PDF to RAG\pdf_to_rag.py`

  (that tool is untouched): its cleaning and heading detection kept; made generic (no FAA chapters/glossary), plus Word,

  Excel (.xlsx/.xlsm/.xls), CSV/TSV, Markdown and text, numbered and Spanish headings, heading paths/levels, spreadsheet rows

  as "Column: value", scan/legacy-format detection. Output JSON: `{country, title, source{file,format,sha256}, sections[

  {id,title,path,level,content,tags}]}`. Not supported: legacy `.doc`, PowerPoint, scanned PDFs (need OCR). The `.xls` path

  was not tested (no sample could be generated). `pdfminer.six` is already installed (a pdfplumber dependency) — no new

  dependency.

- **Storage** `backend/rag_files/store.py`: `backend/documents/rag_files/<Country>/` with `source/` (originals), `json/`

  (Load output), `<Country>.rag.json` (Bake output) and `state.json` (hashes, errors). Statuses are derived from hashes:

  uploaded → loaded → baked; re-adding changed content resets it. Load/Bake run as background jobs polled by the page.

  The folder is **gitignored**.

- **Bake** chunks each document's sections (heading path prepended), embeds them with the knowledge base's local MiniLM model

  and updates the country's RAG file **incrementally** (unchanged documents keep their vectors, removed/changed ones are

  dropped). The file has the knowledge base's own shape, so `knowledge_base/rag.search` was changed (one line) to accept a

  file path; `POST /rag-files/countries/{name}/search` queries it. Nothing in chat/profiles uses these files yet.

- **API:** `routers/rag_files.py` — `GET /rag-files/countries`, `GET|…/countries/{name}`, `POST …/files`, `DELETE

  …/files/{file}`, `GET …/files/{file}/json`, `POST …/load`, `POST …/bake`, `POST …/search`.

- **Tested in the browser** with a PDF, CSV, Excel, Word, Markdown and text sample (a scan-like PDF reports its error, `.doc`

  is refused with a hint): Load → Bake (red → "Baked ✓"), a second round only embedded the new documents, removing a file

  and re-baking dropped its chunks, and search found the right passages. Test data was deleted afterwards.

- **Not committed.**



### 2026-10-05 (earlier) — Country Commercial Guides feed the Country Commercial Profile



**Prompt:** "I added a new api key to navigate trade.gov, i am specially looking to search data from the country

opportunities profiles, check if that is the correct api" → then "i need some way to interact with this site and build

or extract the analysis there: https://www.trade.gov/country-commercial-guides".



- trade.gov's data API (key via `subscription-key` header) works for Consolidated Screening List, Trade Events, Trade

  Leads, etc. It does **not** serve Country Commercial Guides or Market Intelligence any more (paths 404).

- New `backend/trade_gov/commercial_guides.py` reads the public guide chapter pages (no key): chapters matched by

  page-name prefix (names differ per country, typos included). Guides exist for Jamaica, Colombia, Bahamas, Barbados,

  Trinidad and Tobago; none for Saint Lucia, Saint Martin, United States.

- The Country Commercial Profile build (`country_profile/claude_client.py`, `routers/country_profile.py`) now takes the

  guide as its primary source, adds "Opportunities for Our Products" (from the priority list / best-rated matches) and an

  "Import Rules for Food" section; token budget raised to 32k for guide builds.

- `.env` has `TRADE_GOV_API:` with a colon — should be `=` (not needed by this feature). The key value was accidentally

  printed once in a session; consider regenerating it.

- **Not committed.**



### 2026-10-04 / 10-03 — Priority list, shipment building, product lists, Jamaica fix (commit `f3953d6`)



- Market Opportunities: priority list per source→target comparison (checkboxes, Add/Remove, "Priority list" sort filter,

  saved in DB by product name); the "Add to priority list" button is teal when active.

- Shipment builder: opens the route's priority list (or a pop-up leading to Market Opportunities); every product ticked;

  **Build** distributes the aircraft's max payload (27,000 kg for the A321F) by country SAM and Diff % (≤1,500 kg each,

  ≤200 kg without SAM), saves it on the route; **Update/View shipment** cards. The route "Add Products" form is FRESH24-only

  (`FinancialTab/companyRevenueForms.js`).

- Settings ▸ Product sources: product count opens the source's products; supermarket catalog pop-up has a bounded list and

  live product list; products are queued for HS classification as soon as a source stores them.

- Jamaica Ministry of Agriculture reader (`custom_sources/moa_jamaica.py`): stacked per-parish tables merged — 680 rows → 313

  products, with per-market prices.



### 2026-10-02 — Supermarket catalogs, directional comparisons, product-level SAM (commits `6fbfbe8`, `417f0af`)



- Comparisons are directional: one row per **source** product found in the target (median matched target price); repeated

  listings collapsed; all 7 saved comparisons recomputed. Saved comparisons list + Recompute; a saved run reopens without

  recomputing.

- Product-level (6-digit HS) region and country SAM from one cached Comtrade call per country.

- Supermarket catalogs: Settings builds a country source through the separate Supermarket_data_fetch app's API

  (categories + subcategories, download, import as a Retail source, images saved with the export).

- AI product matching tolerates Claude wrapping its JSON in an object.



### 2026-10-01 — Revenue routes



- Route form (origin, destination, return, provider, aircraft); expandable card with one coloured row per leg; type of

  return (Full: GSA-operated return, outbound carries the whole flight; Compensated: legs split 100%); leg cost, target

  cargo %, available cargo, price per kg; route calculations ported from AI_FRESH24 (haversine, block hours).

- Providers ▸ Air Logistics and Expenses; COS/Expenses sub-tabs.



### Earlier (before 2026-10-01)



- Product price/HS classification and matching made general-purpose (prompts, not per-product rules); eggs use the most

  traded size; exchange rates shown as "1 USD = X"; percent-of-profit expenses fixed; chat history persisted; product

  portfolio tables standardized to the Colombia layout.

