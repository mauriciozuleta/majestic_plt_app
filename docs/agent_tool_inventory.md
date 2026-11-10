# Agent tool inventory — what the app can already do

*Written for: the project owner, to review with Claude and decide which capabilities become agent tools. Research only — nothing was built, changed, called or scheduled.*

- **Date / basis:** 2026-11-09, last commit `6e161e5` plus uncommitted work (Agents tab, `backend/fuel_prices/`). Everything below comes from reading code (routers, packages, services, `diary.md`, the 8020 service's header). The only calls made were `GET /health` and `GET /stores` on `127.0.0.1:8020` (the CLAUDE.md start-up check; both answered 200, the service was already running). No paid API, external site or data-changing endpoint was called; no `.env` value is reproduced here (variable *names* only).
- **Background plan:** `agent_development.md`. **Design recap:** a TOOL is one small action with typed inputs, a TASK is a saved list of tool steps, a SCHEDULE is when a task runs; the model only picks tools and explains results.
- **Cells marked `unverified`** were not confirmed by reading the code path; the section "Open questions" says where to look.
- **Credit state (from the diary):** the Anthropic balance is too low (HTTP 400 on every Claude call), so every row marked `credits` currently fails until it is topped up. Local Ollama models still work.

## Legend

| Term | Meaning |
| --- | --- |
| **Tier** | **R** read · **S** simulate (computes, saves nothing) · **W** reversible write · **X** sensitive (deletes of substantive data, money, accounting, licence sign-offs, printed labels). Rule used: create/update of small settings = W; a delete is X when it destroys real data (a company, a source, a document, an account, an accounting entry), otherwise W. |
| **runs: instant** | Answers inside the HTTP request. |
| **runs: job** | Background task / thread; the caller polls a status endpoint or marker file. |
| **runs: browser** | The input (or the whole logic) is built by the React app; the endpoint alone cannot do it. |
| **runs: 8020** | Needs the Supermarket_data_fetch service on `127.0.0.1:8020`. |
| **runs: key:NAME / credits** | Needs that API key in `.env` / spends paid Anthropic credits. |
| **Restorable: No** | Overwritten or deleted in place. Verified: `snapshot_store.save_snapshot` keeps ONE row per source (no history); a search of `backend/` for backup / restore / undo / history code found none. The only copy is `majestic_plt.db` as tracked in git (whole file, last commit only) and any OneDrive file history — neither is per-item. |
| **Restorable: Rerun** | The data is derived; running the same action again rebuilds it. |
| **Restorable: Yes** | A setting that can be set back with the same call. |
| **Fit** | **yes** / **cond** (only with conditions, stated) / **no**. |
| **Decision** | Left blank for you. |

Important finding that affects every "W" row below: **a snapshot overwrite is not restorable**, so a W that replaces a snapshot, a SAM/TAM figure, a tariff file or a generated profile behaves like X for recovery purposes. Until some history exists, treat those rows as "W, not undoable".

**Also important:** several endpoints that look like reads change data. Tier below follows what they really do: `GET /market-analysis/colombia/*` and `/usa/*` (fetch and overwrite a snapshot), `GET /api/trade/sam-overview` and `/tam-global-overview` (compute and persist on first call), `GET /api/trade/categories|products|subheadings` (write the Comtrade cache on a miss, spend a Comtrade call), `GET /supermarket-catalog/jobs/{id}` (imports a finished job), `GET /tourism/compare?refresh=true` (calls providers).

---

## 1. Summary

**146 capability rows in 23 module tables.** A row is a capability, not an endpoint: grouped rows cover several endpoints (BI-04 is seven USDA reports, FN-09 a whole record set). Counts were produced by a script reading the tables below.

**Per tier**

| Tier | Rows | What they are |
| --- | --- | --- |
| R read | 45 | lists, statuses, stored snapshots, searches, exports |
| S simulate | 16 | tax calculation, packing, conversions, validation, AI Search (no save) |
| W reversible write | 72 | refreshes, imports, settings, job starts — **many are not undoable** (see Legend) |
| X sensitive | 12 | deletes of real data, money and ledger entries, licence sign-off, released box IDs |
| unverified | 1 | SX-03 (script not read) |

**Per module**

| Module | Rows | R | S | W | X | | Module | Rows | R | S | W | X |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BI Built-in price sources | 7 | 1 | 0 | 6 | 0 | | FU Fuel prices | 10 | 4 | 1 | 4 | 1 |
| PS Product analysis sources | 9 | 2 | 0 | 5 | 2 | | TO Tourism | 5 | 1 | 0 | 4 | 0 |
| SC Supermarket catalog (8020) | 7 | 1 | 1 | 5 | 0 | | KB Knowledge base | 6 | 3 | 0 | 2 | 1 |
| CN Catalog normalization | 11 | 3 | 5 | 3 | 0 | | RG RAG Files | 6 | 1 | 0 | 5 | 0 |
| PC Classification / matching | 4 | 1 | 0 | 3 | 0 | | LM Local models | 3 | 1 | 0 | 2 | 0 |
| MO Market Opportunities | 6 | 2 | 1 | 3 | 0 | | RA Risk analysis | 4 | 1 | 0 | 2 | 1 |
| TX Tax calculators | 11 | 3 | 3 | 5 | 0 | | PK Packer / air logistics | 9 | 3 | 3 | 1 | 2 |
| CT Comtrade / SAM / TAM | 9 | 6 | 0 | 3 | 0 | | FN Finance / accounting | 11 | 3 | 0 | 5 | 3 |
| CP Profiles / competitiveness | 4 | 2 | 0 | 2 | 0 | | CO Structure / PR Payroll | 4 / 3 | 1 / 1 | 0 | 2 / 2 | 1 / 0 |
| SG Species gallery | 5 | 1 | 1 | 3 | 0 | | AS Assistant tools | 8 | 3 | 0 | 5 | 0 |
| CU Currency | 1 | 1 | 0 | 0 | 0 | | SX Scripts | 3 | 0 | 1 | 0 | 1 + 1 unverified |

**Automation fit (all rows):** yes 65 · only with conditions 42 · no 38 · already automated 1 (FU-10).

**Things to know before choosing**

- Only two things run on a timer today (accounting audit, fuel prices). No product source, SAM/TAM figure, tariff file, profile or catalog refreshes by itself (section 5).
- Refreshes overwrite one stored copy; nothing can be rolled back (Legend). Three refreshes can also overwrite good data with worse data: an empty USDA parse (BI-04), a rate-limited SAM/TAM run (CT-06/07), and a custom site that returns fewer products (PS-06). These need a "do not save if it got worse" guard before they are scheduled.
- Everything marked `credits` fails right now (Anthropic balance), and everything marked `browser` cannot run without the React app.
- Several "reads" write (list at the top of the Legend).
- Three cheap, key-free health tools exist or are trivial: `FU-07` coverage, `CT-08` SAM/TAM summary, `BI-01` snapshot ages; together with `CN-01` they could power a "what is stale?" digest.

**Ten most promising candidates**

| # | Rows | Why |
| --- | --- | --- |
| 1 | BI-04, BI-05 — USDA reports (8 sources) | Public PDFs or one keyed JSON API, no credits, independent endpoints, failure keeps old data; only needs an "empty result" guard. Weekly. |
| 2 | BI-02 (+ BI-03 on bulletin days) — Colombia prices | Plain GETs with no key or credits; the Colombia catalog feeds Market Opportunities. |
| 3 | PS-06 — refresh custom sites | The Assistant already does this by hand; automate only sources whose last note is not the AI-extracted one, and block the overwrite when the product count drops. |
| 4 | CT-06, CT-07 + CT-08 — SAM / TAM refresh | Monthly or quarterly; before/after totals already exist (the Assistant reports them). Needs the partial-failure guard first. |
| 5 | TX-06 — USA HTS refresh | Downloads to a temp file and validates before replacing; low frequency, safe pattern. |
| 6 | RG-05 — bake pending RAG files | One call, local embeddings, free, idempotent, queue already exists. |
| 7 | CN-07 → CN-08 → CN-09 — re-annotate, preview, research with a limit | The natural step after any refresh; deterministic first, paid research only after a dry run and while credits exist. |
| 8 | SC-04 (+ SC-05) — supermarket catalog re-download | Highest data value, but only with conditions: store the category list, check 8020 with SC-01 first, and allow for multi-hour runs. |
| 9 | FU-07 / FU-03 — fuel health digest | The module already schedules itself; an agent adds the plain-language "what is stale and why" report from the coverage endpoint. |
| 10 | FN-02 (+ FN-01) — accounting audit digest | The audit already runs on a schedule; an agent can summarise new findings per company instead of someone opening the settings card. Read-only. |

---

## 2. Capability tables

### BI — Built-in price sources (Colombia and USDA)  `routers/price_comparison.py`, `routers/usa_sourcing.py`, `price_sources/`, `usa_sources/`

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BI-01 | Read stored Colombia / USA snapshots | `GET /market-analysis/colombia/snapshot`, `GET /market-analysis/usa/snapshot` → `snapshot_store.list_snapshots` | Last fetched products per source + `fetched_at` | none → list of {source, products, fetched_at} | R · none | instant | none | n/a | yes — cheap freshness check (`fetched_at`) | |
| BI-02 | Fetch + store La Mayorista | `GET /market-analysis/colombia/la-mayorista` → `fetch_la_mayorista_products`, `save_snapshot` | Finds the sheet id on the homepage, downloads the Google-Sheet xlsx, parses, overwrites snapshot `la_mayorista` (re-normalizes weights with stored research only) | none → products | W · overwrites snapshot; deterministic `norm` recomputed; no HS classification | instant (HTTP 15 s + 30 s timeouts), no key | Any exception → HTTP 502 and `save_snapshot` is not reached, so the old data stays (verified). Depends on the homepage still exposing the sheet link | No | cond — plain GET, no key/credits; guard against page-layout change (compare product count with last run) | |
| BI-03 | Fetch + store Corabastos bulletin | `GET /market-analysis/colombia/corabastos` → `fetch_corabastos_products` | Downloads today's dated PDF bulletin, parses, overwrites snapshot `corabastos` | none → products | W · same as BI-02 | instant (30 s timeout), no key | Only TODAY's file name (`Boletin_diario_YYYYMMDD.pdf`) is tried; no fallback to an earlier day (verified) — expect failure on days without a bulletin (live behaviour unverified). Failure keeps the old data | No | cond — run only on days a bulletin exists / after publication time | |
| BI-04 | Fetch + store USDA AMS PDF reports (beef, pork, poultry, eggs, grains, produce-FL, produce-CA) | `GET /market-analysis/usa/{beef,pork,poultry,eggs,grains,produce-fl,produce-ca}` → `usa_sources/*`, `common.download_pdf` | Downloads each public report PDF (pdfplumber), parses with report-specific regexes, overwrites that source's snapshot | none → products (7 independent endpoints) | W · overwrites one snapshot each | instant each (30 s timeout), no key | Fetch/parse exception → 502, old data kept (verified). **No empty-result guard in `beef.py` (verified): a layout change that matches nothing would save an empty list over good data**; the other six parsers unverified | No | cond — add a "refuse to save if empty or far fewer rows" check first | |
| BI-05 | Fetch + store USDA retail produce (MARS FVWRETAIL) | `GET /market-analysis/usa/retail-produce` → `usa_sources/retail_produce.py`, `mars.py` | Pulls the latest week of national conventional retail rows from the USDA My Market News API | none → products (detail rows) | W · overwrites snapshot `usa_retail_produce` | instant (90 s timeout), `key:USDA_MYMARKETNEWS_API_KEY` | Raises (502) if no national rows in the last 3 weeks; 401 and non-200 give readable errors; old data kept. API rate limits: unverified | No | yes — keyed, structured JSON, empty result raises | |
| BI-06 | Colombia product-name translations (list / set) | `GET/PUT /market-analysis/colombia/translations` | Reads / upserts a confirmed English name for a Spanish product key | key, `translation_en` → override row | W · upsert one override | instant | empty text → 400 | Yes (set it back) | cond — decisions are human judgements | |
| BI-07 | Translation suggestions: list / start job / confirm / reject | `GET/POST /market-analysis/colombia/translation-suggestions`, `POST …/{key}/confirm`, `DELETE …/{key}` → `translation/resolve.py` | Tier 3 local Ollama model, tier 4 Google web search; suggestions wait for a person to confirm | list of {product_key, name_es} → suggestions; confirm → override | W (start, confirm) · writes suggestion/override rows; reject = W | job (start); `key:GOOGLE_SEARCH_API_KEY` + `GOOGLE_SEARCH_CX`; local Ollama | Marker file; a restart kills the job (`is_building` clears stale markers). Quality is flagged "lower confidence" | Confirm: Yes (PUT again); reject: No | cond — start is safe; confirm should stay human | |

### PS — Settings ▸ Product analysis sources  `routers/product_sources.py`, `routers/catalog_products.py`, `custom_sources/extract.py`

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PS-01 | List sources (built-in + custom) | `GET /product-sources` | Built-in list is a constant in code (10 entries: 2 Colombia, 8 USDA) with snapshot status; custom rows from `product_sources` | none → {built_in[], custom[]} with status, product_count, last_loaded_at | R · none | instant | none | n/a | yes | |
| PS-02 | Read one source's / all custom sources' products | `GET /product-sources/{id}/products`, `GET /product-sources/products` | Stored products as the portfolio and comparisons use them | id → products | R · none | instant | none | n/a | yes | |
| PS-03 | Create a custom source | `POST /product-sources` → `_analyze` | Saves the source row; with a web address it analyses the site immediately (see PS-06 steps) and stores the products | country, name, url?, currency?, analysis_type → source row | W · new row + snapshot `custom_<id>` + HS classification thread | instant for the row, but the site read runs inside the request (40 s per download); classification = job, `credits` | Failure leaves an empty source with a status message ("needs_file"); never raises on site errors | Delete (PS-09) removes it | cond — rarely repeated | |
| PS-04 | Edit source fields | `PUT /product-sources/{id}` | Renames / changes country, currency, label; **a changed URL re-analyses and replaces the products**; a changed currency re-stamps every stored product | same as create → source row | W · may overwrite the snapshot | instant (site read inline on URL change) | On failed re-read it keeps products and writes the reason | No (if the URL changed) | no — config edit, human | |
| PS-05 | Set Wholesaler / Retail label | `PUT /product-sources/{id}/analysis-type` | Built-in sources via `BuiltInProductSourceOverride`, custom via the column; Market Opportunities flags wholesale-vs-retail pairs from it | id, analysis_type → label | W · one value | instant | other values → 400 | Yes | no — a judgement, rarely changes | |
| PS-06 | **Refresh a custom source from its web address** | `POST /product-sources/{id}/refresh` → `_analyze` → `custom_sources.extract.analyze_url` | Escalating read: (1) the URL is a data file, (2) the page links to xlsx/csv/pdf/Google Sheet files, (3) HTML table with product + price columns, (4) Claude reads the page text. Special reader for `moa_jamaica`. Overwrites the snapshot, re-normalizes, queues HS classification | source id → source row (status, product_count, note) | W · overwrites snapshot `custom_<id>`; status/last_loaded_at; HS classification thread | instant (40 s per download, inline); step 4 `credits`; classification job `credits` | Rejected with 400 when the source has no URL or `origin = catalog`. Site error → keeps products (status message updated; `needs_file` only if it had none). Sites needing JavaScript or a login yield "No product prices could be found". Step 4 products are labelled "Extracted … with AI — worth a quick check". **A source whose products were loaded from a file but which also has a URL is re-read from the URL and the file data is replaced (verified: `_analyze` only skips `origin = catalog`)** | No | cond — only for sources whose last note is NOT the AI one; add count-drop guard | |
| PS-07 | Load a products file | `POST /product-sources/{id}/file` → `parse_file` | Parses csv / xlsx / xls / pdf (finds header row with a name and a price column), replaces the snapshot | filename + base64 content (≤ 15 MB) → source row | W · overwrites snapshot; HS classification thread | instant; classification `credits` | Unreadable file → 400 and the reason is stored in `status_message`; products kept (status `needs_file` only if empty) | No | cond — needs a file path the tool can read; there is no watch folder for product files (verified) | |
| PS-08 | Delete a source | `DELETE /product-sources/{id}` | Deletes the snapshot and the source row | id → ok | X · destroys products of that source | instant | none | No | no | |
| PS-09 | Delete selected catalog products | `POST /catalog-products/delete` → `modification_reports` | Rewrites the affected snapshots without the chosen products, updates `product_count`, writes a .md report into Documentation ▸ Modification Reports | list of {source, product keys} → counts + report path | X · removes products; writes a report document | instant | A later source refresh can bring the products back (the dialog says so) | No — the report records what was removed; whether it is complete enough to rebuild is unverified | no | |

**Source kinds — how each refreshes today and whether it can run unattended**

| Kind | Examples | How it refreshes today | What triggers it | Can it run unattended today? |
| --- | --- | --- | --- | --- |
| **Built-in Colombia** | La Mayorista, Corabastos | `GET` fetch endpoints BI-02 / BI-03 (public sites, no key). The Settings card says "Updated from the Country Product Portfolio tab's Update button" (`ColombiaProductAnalysisView.handleUpdate`, which also fetches the COP→USD rate). | Only that browser button. No scheduler, no job. | **Yes technically** — the endpoints work without a browser. Conditions: Corabastos only has today's file; La Mayorista depends on the homepage link; failures keep old data. After a fetch nothing else runs by itself: no HS classification (only the browser-built portfolio queues it, `productPortfolio.js`), no translation suggestions, no weight research. |
| **Built-in USDA** | AMS Beef, Pork, Poultry, Eggs, Grains, Produce FL, Produce CA (PDFs); Retail Produce (MARS API) | Eight `GET` endpoints BI-04 / BI-05, called by `USASourcingView.handleUpdate` with `Promise.allSettled` so one failure never blocks the others. | Only that browser button. | **Yes** — public PDFs need no key; MARS needs `USDA_MYMARKETNEWS_API_KEY`. Condition: add a guard against saving an empty parse (BI-04). |
| **Custom with a web address** | Added in Settings, e.g. a government price site | PS-06 (the four-step read above). | The row's "Refresh" button, or the Assistant tool `refresh_product_source` (AS-06). | **Yes, with conditions** — no scheduler exists; sites needing JavaScript/login fail; step 4 uses credits and its output needs a human check; a drop in product count should block the overwrite. |
| **Supermarket catalog** (`origin = catalog`) | Jamaica, Bahamas, Barbados, Trinidad, Sint Maarten catalogs under `backend/supermarket_catalogs/` | "Rebuild catalog" opens the catalog modal, where a person re-ticks categories (`selected` is React state; the backend stores only a category *count* in `client_data`) and starts SC-04. `POST /product-sources/{id}/refresh` refuses it (400). | Browser modal only. | **Only with conditions** — needs (a) the service on 8020 running (started by hand, not by Majestic), (b) a stored category list (does not exist today), (c) a long run (watcher limit 6 h). A cancelled or partly failed download still replaces the products. |
| **File-only** | Sources with no URL, or `status = needs_file` | PS-07: a person loads a new file. | Browser upload. | **No today** — nothing to fetch and no watch folder. Would need a drop-folder tool (the fuel module already has one: `fuel_prices/drop/`). |

### SC — Supermarket catalog service (port 8020)  `routers/supermarket_catalog.py` → separate app `Supermarket_data_fetch/api_server.py` (Codex-owned, read only here)

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-01 | Service status | `GET /supermarket-catalog/status` → 8020 `GET /health` + `GET /stores` | Reports whether the service is up and lists its saved store setups | none → {available, stores[]} | R · none | instant, 8020 | Unreachable → `available:false` with the "start launch_api.bat" hint. CLAUDE.md: `/stores` must also answer 200 (global Python, not the bat) | n/a | yes — mandatory precheck for any SC step | |
| SC-02 | Prepare a store (find categories) | `POST /supermarket-catalog/prepare` → 8020 `POST /catalog/prepare` | Prepares a website setup and lists its categories | url, country → job/categories | W · may save a store setup inside the other app (unverified) | job on 8020 | Unreachable → 503 | unknown | cond | |
| SC-03 | Find subcategories | `POST /supermarket-catalog/subcategories` → `POST /catalog/subcategories` | Checks one category page for hidden sections, returns the merged list | store_id, category, current list → merged list | S · returns a list, nothing saved here | job on 8020 | as SC-02 | n/a | cond | |
| SC-04 | **Download a catalog** | `POST /supermarket-catalog/download` → `POST /catalog/download` | Starts a crawl of the chosen categories into `backend/supermarket_catalogs/<country>/` and starts a watcher thread that imports it when done (SC-05) | url, store_id, country, categories[{name,url}], source_name → job | W · files on disk; later overwrites the source's snapshot | job on 8020, long (minutes–hours); no key on this side | At least one category required (400). Per-category errors are listed in the import note ("Incomplete — N categories failed"). Throttling / site blocking: handled inside the other app, unverified | No (files on disk are overwritten per country folder; unverified whether old exports are kept) | cond — needs stored categories + 8020 | |
| SC-05 | Import a finished download (automatic) | `_watch` thread + `_import` (also called from SC-06) | Parses the export with the same parser as a manual file, finds or creates the Retail source for country+URL, `_store` (snapshot, status, HS classification thread) | finished job → source row, product count, image summary | W · overwrites snapshot; HS classification thread (`credits`) | job (thread polls every 2 s, gives up after 6 h) | `done` and `cancelled` jobs are both imported (cancelled = partial). The "already imported" set is an in-memory dict, lost on restart (verified) | No | cond | |
| SC-06 | Job status | `GET /supermarket-catalog/jobs/{id}` → 8020 `GET /jobs/{id}` | Returns progress; **if the job finished it also runs the import** | job id → job (+ import result) | W (looks like a read) · import side effect | instant, 8020 | 404 if the service restarted | No | yes for polling | |
| SC-07 | Cancel a download | `POST /supermarket-catalog/jobs/{id}/cancel` | Stops the job; the service still exports what it had | id → job | W | instant, 8020 | — | n/a | cond | |

### CN — Catalog normalization (unit and weight conversion)  `routers/catalog_normalization.py`, `catalog_normalization/`

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CN-01 | Normalization status | `GET /api/catalog-normalization/status` | Per catalog: counts by conversion method, pending-research count, whether research is running, last error | none → status | R · none | instant | none | n/a | yes — shows what needs attention | |
| CN-02 | Convert one price | `GET /api/catalog-normalization/convert` | $/kg, pack weight, items per pack for one row | name, unit, price → norm | S · none | instant | needs researched weight otherwise "needs_research" | n/a | yes | |
| CN-03 | Items ↔ weight | `GET /api/catalog-normalization/items` | Items in N kg or weight of N items for a researched product | product, kg or count → number | S · none | instant | 404 if the weight has not been researched | n/a | yes | |
| CN-04 | List researched weights | `GET /api/catalog-normalization/weights` | All stored item weights with confidence and sources | none → list | R · none | instant | none | n/a | yes | |
| CN-05 | Missing-data summary / list | `GET …/missing-summary`, `GET …/missing?country=` | Per country count (the red pill) and the rows needing a weight | country → rows | R · none | instant | none | n/a | yes | |
| CN-06 | Validate typed / suggested weights | `POST /api/catalog-normalization/validate` | Range per unit, USDA band, price per kg against the same product's other listings | items → verdicts | S · none | instant | none | n/a | yes | |
| CN-07 | **Re-annotate all catalogs** | `POST /api/catalog-normalization/reannotate` | Copies weights to English names, imports legacy estimates, recomputes `norm` on every stored catalog | none → counts | W · rewrites `data_json` of every catalog snapshot (derived field) | instant to seconds; no web, no credits | Whether raw fields (price, name) can ever be altered is unverified | Rerun (derived); raw fields unverified | yes — natural step after any refresh | |
| CN-08 | Research queue preview | `POST /api/catalog-normalization/research` with `dry_run:true` | Counts pending products and shows a sample, no call | limit, names? → counts | S · none | instant | none | n/a | yes | |
| CN-09 | **Research item weights** | `POST /api/catalog-normalization/research` | Claude web search of one item's weight per product, 12 per call (`MAX_ITEMS_PER_BATCH`), then re-annotates all catalogs | limit (default 48), names? → started | W · writes `catalog_item_weights` rows; rewrites catalog `data_json` | job (marker file), `credits` | Error stored as marker `.error` and shown by CN-01. Colombia sources are researched first. Whether weights from earlier batches survive a later batch failing depends on `DbStore.put` commit behaviour — unverified | New weights: No (a user-typed weight wins over them, `confidence = user`) | cond — run with a limit, after CN-08, only when credits exist | |
| CN-10 | AI Search for missing weights | `POST /api/catalog-normalization/suggest` | Same research, validated, **not saved** | ≤ 12 products → suggestions + validation | S · none | instant-ish (up to 900 s timeout), `credits` | 502 with the real reason on failure | n/a | yes as a drafting step; saving stays human | |
| CN-11 | Save weights | `POST /api/catalog-normalization/weights` | Stores accepted weights and converts every catalog again | items → saved + counts | W · rows + catalog rewrite | instant | none | No for the old value (upsert) | cond — human-reviewed values only | |

### PC — Product classification, matching and overrides  `routers/product_classification.py`, `product_matches.py`, `product_overrides.py`

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PC-01 | List HS classifications | `GET /api/product-hs-codes` | Every classified product + whether a job is running + last error | none → {building, error, results} | R · none | instant | none | n/a | yes | |
| PC-02 | **Classify products to HS codes** | `POST /api/product-hs-codes`; also started automatically after every `_store` (custom source, file, catalog) by `classify_source_products_in_background` | Claude picks from a Comtrade shortlist per product, cached by lowercased name | [{key,name,context}] → started | W · writes classification cache rows | job (marker file), `credits` | One job at a time; ~500 names took 5+ minutes in testing. The automatic path waits up to 30 min for a running job. Built-in Colombia/USDA sources are NOT classified automatically | Cached rows overwritten: No | cond | |
| PC-03 | Product matching (cross-country) | `POST /api/product-matches` → `product_matching/claude_client.py` | Claude proposes matches per product, with a cache flag | keys/names → matches + note | W · cache rows (details unverified) | instant-ish, `credits` | unverified | unknown | cond | |
| PC-04 | Custom match overrides | `GET/POST /product-custom-overrides`, `POST …/clear` | A person's manual product-match decisions | override → row | W · one row | instant | none | Yes (clear) | no — human decisions | |

### MO — Market Opportunities  `routers/market_opportunities.py`, `routers/market_opportunity_settings.py`, `src/services/marketOpportunities.js`

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MO-01 | Read saved comparisons / pairs / priority list | `GET …/comparisons`, `…/comparisons/pairs`, `…/priority` | Stored comparison rows per source→target country | countries → rows | R · none | instant | none | n/a | yes | |
| MO-02 | **Compute a comparison** | **no backend function** — `computeMarketOpportunity`, `getOrComputeComparison` (JS) | Joins both countries' price snapshots (curated overrides, translated names, HS fallback), normalizes units/currency through the CN module, adds tax multipliers and built-shipment airfares | source, targets → rows | S · none (until MO-03) | **browser** | Logic exists only in JavaScript — see Gaps | n/a | no — blocked until ported to the backend | |
| MO-03 | Save comparisons | `POST /api/market-opportunities/comparisons` | Server computes `diff_pct` and `opportunity_rating`, replaces the pair's rows and unmatched list | rows from the browser → ok | W · deletes and re-inserts the pair's rows | instant | rows must come from MO-02 | No | no (depends on MO-02) | |
| MO-04 | Priority list add / remove | `POST …/priority`, `POST …/priority/remove` | Marks products as priority | items → ok | W · small | instant | none | Yes | cond | |
| MO-05 | Exchange rate to USD | `GET …/exchange-rate` (same source as CU-01) | Rate used as common basis | currency → rate | R · none | instant, `key:EXCHANGERATE_API_KEY` | 4-hour in-memory cache | n/a | yes | |
| MO-06 | Opportunity settings | `GET/PUT /market-opportunity-settings` | Thresholds / options for ratings | settings → settings | W · one row | instant | none | Yes | no | |

### TX — Tax calculators  `routers/tax_calculator.py`, `tax_calc/`

Countries with a calculator (`tax_calc/__init__.py`): Jamaica, USA, Trinidad, Bahamas, Saint Lucia, Grenada, Barbados, Turks and Caicos, Sint Maarten. Colombia works through DIAN (TX-09). Standing rule (CLAUDE.md): when two parts of a document give different rates for one line, the calculators use the **higher** rate (`higher_rate()` in `tax_calc/base.py`) and still show the "CONFLICT IN THE FILE" warning.

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TX-01 | List calculators + data status | `GET /tax-calc/countries` | Per country: ready flag, source file, loaded time | none → list | R · none | instant | none | n/a | yes — staleness check | |
| TX-02 | Search tariff lines | `GET /tax-calc/{country}/search` | Matches words or code prefixes | q, limit → lines | R · none | instant | 409 if tariff data not loaded | n/a | yes | |
| TX-03 | Suggest the tariff line for a product | `GET /tax-calc/{country}/suggest` → `mapping.lines_for_hs`, `multiplier_for` | Candidate lines + computed multiplier for a product | name, hs_code?, origin?, price → candidates | S · none | instant | whether it ever calls an AI model: unverified | n/a | yes | |
| TX-04 | **Calculate import taxes** | `POST /tax-calc/{country}/calculate` | Duties, levies, VAT for one line and shipment, with conflict handling | code, goods value or price×kg, freight, insurance, origin, transport → result | S · none | instant | 404 for an unknown code; 400 if value missing | n/a | yes — best pure tool in the app | |
| TX-05 | Refresh tariff data from documents | `POST /tax-calc/{country}/refresh` (Jamaica, Trinidad, Bahamas, Saint Lucia, Grenada, Barbados, Turks and Caicos) | Re-parses the customs schedule document already in the knowledge base / RAG Files and rewrites the country's `tariff.json` (Jamaica copies a `*TARIFF*.csv`) | none → info | W · replaces the tariff file | instant, no network, no key | Missing source document → error (502 with text); overwrite is not validated first | No | cond — only after a new document is uploaded | |
| TX-06 | Refresh USA HTS | same endpoint, USA | Downloads the current HTS JSON from USITC to a temp file, checks it parses, then replaces the working copy | none → info | W · replaces `hts_full.json` | instant-ish (300 s timeout), no key | Invalid JSON never replaces the old file (verified) | No | yes — safe pattern, low frequency | |
| TX-07 | Sint Maarten refresh | same endpoint | No-op (returns info) | — | R · none | instant | — | n/a | no | |
| TX-08 | **Compute multipliers for a portfolio** | `POST /tax-calc/multipliers/compute` | For each product, computes and stores the tax multiplier origin→destination; skips rows a person saved from the calculator | destination, origin, products[{name,hs_code,price}] → counts by status | W · upserts `ProductTaxMultiplier` rows | instant | 409 if the destination data is not loaded. The product list is assembled by the browser (portfolio is JS) | No for the old value | cond — a tool could accept a product list | |
| TX-09 | Colombia DIAN lookup (single / batch) | `POST /tax-calc/colombia/dian/lookups`, `/batch`, `GET …/jobs/{id}`, `GET …/{hs_code}` → `tax_calc/colombia_dian/` | Playwright drives DIAN WebArancel to read Gravamen + IVA | HS code, date, forceRefresh → job → rates | W · writes `dian_tariff_cache` | job, Chromium must be installed (`BROWSER_NOT_INSTALLED` otherwise), 5–20 s per code, `DIAN_MAX_SESSIONS` 1–2 | Errors: `DIAN_UNAVAILABLE`, `DIAN_TIMEOUT`, `HS_CODE_NOT_FOUND`, `PAGE_STRUCTURE_CHANGED`. **Several valid rows → the result needs a human choice (`needsInput`)** | Cache rows: Rerun (forceRefresh) | cond — only unambiguous results | |
| TX-10 | DIAN calculate | `POST /tax-calc/colombia/dian/calculate` | Pure calculator from the two DIAN values | values + shipment → taxes | S · none | instant | needs the chosen row when ambiguous | n/a | yes | |
| TX-11 | Save / delete / list saved multipliers | `POST /tax-calc/multipliers/save`, `DELETE …/multipliers`, `GET …/multipliers` | A person's calculator result becomes the multiplier Market Opportunities reads | destination, origin, product, multiplier → row | W · upsert / delete one row | instant | status must be ok/review/incomplete | Yes (save again) | no — human-confirmed values | |

### CT — Comtrade, SAM / TAM, trade-source discovery  `routers/comtrade.py`, `comtrade/`, `trade_sources/`, `market_size_store.py`

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CT-01 | Reference lists (countries, HS products) | `GET /api/trade/countries`, `/hs-products` | Country catalog and HS reference | none → lists | R · none | instant | none | n/a | yes | |
| CT-02 | Comtrade category / product / subheading data | `GET /api/trade/categories`, `/products`, `/subheadings` → `comtrade/client.py` | Annual trade values per chapter / product / heading | country, year, flow, chapter → rows | R · writes the Comtrade cache on a miss (successful results cached indefinitely) | instant, `key:COMTRADE_API_KEY` | Free tier: 500 calls/day; 429 → "daily call limit reached"; failed calls are not cached | n/a | cond — respect the daily budget | |
| CT-03 | Source status per country | `GET /api/trade/countries/{code}/source-status` | Which source (Comtrade or a fallback tier) a country uses, whether discovery is running | code → status | R · none | instant | none | n/a | yes | |
| CT-04 | **Recheck a country's trade-data source** | `POST /api/trade/countries/{code}/recheck-source` → `trade_sources/discovery.py` | Re-runs the full chain (Comtrade check, then statistics office, parent-country office, FRED/US Census bilateral) and overwrites the stored fields | code → started | W · overwrites `trade_data_source`, coverage fields | job (marker file); external sites + FRED (`key:FRED_API_KEY`) | robots.txt check before using a discovered source. Also runs automatically once when a country is created (see Chains) | No | cond — occasional | |
| CT-05 | Read SAM / TAM overview | `GET /api/trade/sam-overview`, `/tam-global-overview` | Returns the stored aggregate; **the first call computes and persists it** | chapters, flow → regions/categories | R after first run (W the first time) | instant after first run; Comtrade calls on first | Chapters passed later are ignored once a snapshot exists | n/a | yes for reading | |
| CT-06 | **Refresh SAM** | `POST /api/trade/sam-overview/refresh` | Recomputes SAM with the last stored chapter scope and overwrites the single stored row | optional chapters → new snapshot | W · overwrites `market_size_snapshots` kind `sam` | instant-seconds (many Comtrade calls; cached rows are free), `key:COMTRADE_API_KEY` | 400 if never computed. **A per-country `ComtradeError` is swallowed and the country is skipped (`routers/comtrade.py` around lines 385 / 583 / 757), so a rate-limit mid-run can overwrite a good snapshot with smaller totals** (code-reading; not seen live) | No | cond — needs a guard (compare totals / refuse on any country error) | |
| CT-07 | **Refresh TAM** | `POST /api/trade/tam-global-overview/refresh` | Same for TAM | same → snapshot | W · overwrites kind `tam` | same | same | No | cond | |
| CT-08 | SAM / TAM summary | `GET …/sam-overview/summary`, `…/tam-global-overview/summary` | Total value, category count, `computed_at` | none → summary | R · none | instant | none | n/a | yes — before/after check | |
| CT-09 | Product-level SAM and SAM estimates | `GET /api/trade/product-sam`, `/sam-overview-estimates` (uses `estimation/regression.py`) | Per-HS6 import values by region; regression-based estimates | region, hs_codes → figures | R · Comtrade cache writes | instant, `key:COMTRADE_API_KEY` | Countries with no report are left out, not counted as 0. Estimates: details unverified | n/a | cond | |

### CP — Country profiles, competitiveness, trade.gov guides  `routers/country_profile.py`, `routers/competitiveness.py`, `country_profile/`, `trade_gov/`

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CP-01 | List / read country profiles | `GET …/commercial-countries/profiles`, `…/{country_id}/profile` | Profiles (markdown) already built | company, country → text | R · none | instant | none | n/a | yes | |
| CP-02 | **Build a Country Commercial Profile** | `POST /companies/{c}/commercial-countries/{id}/profile` | Reads the trade.gov Country Commercial Guide (no key; if unreachable it carries on from web research), adds our best-rated products and the uploaded business documents, asks Claude, writes `backend/country_profiles/<id>.md` | ids → started | W · overwrites the profile file (header says "AI-generated — date") | job (marker file), `credits` | The file is written only at the end, so a failure keeps the old one (verified) and stores the error. `country_profiles/` has no tracked files in git (verified: 0) | No | cond — costs credits; overwrites a reviewed profile | |
| CP-03 | List / read competitiveness analyses | `GET …/competitiveness-analyses`, `…/{target}/competitiveness` | Saved source→target analyses | ids → text | R · none | instant | none | n/a | yes | |
| CP-04 | **Build a Competitiveness Analysis** | `POST /companies/{c}/commercial-countries/{target}/competitiveness` | Claude compares the source country's category summary with the target's profile | source country name + `category_summary` → started | W · overwrites the analysis file | job, `credits`, **browser** (the summary is built in `competitivenessInputs.js`) | 400 if the target has no profile or the summary is empty; old file kept on failure | No | no — blocked until the summary is a backend function | |

### FU — Aviation fuel prices (uncommitted)  `routers/fuel_prices.py`, `fuel_prices/`

README: `backend/fuel_prices/README.md`. All sources start disabled except `manual_csv`; enabling an unverified source needs a person's name as sign-off.

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FU-01 | List sources | `GET /api/fuel/sources` | Terms status, enabled flag, sign-off | none → list | R · none | instant | none | n/a | yes | |
| FU-02 | **Enable / disable a source (licence sign-off)** | `POST /api/fuel/sources/{id}/enable` | Turns a source on; an `unverified` source needs `signed_off_by` | enabled, signed_off_by → ok | X · records a legal sign-off; disabled sources vanish from prices/stats | instant | stubs cannot be enabled | Yes (disable) but the sign-off record is the point | no — humans only | |
| FU-03 | **Refresh a source now** | `POST /api/fuel/sources/{id}/refresh?full=` → `service.refresh_source` | EIA API v2 (jet, Brent, stocks, utilization, production, exports) or BTS: backfill or incremental, idempotent upserts | source id, full → run result | W · upserts observations / driver points; writes `fuel_job_runs` | instant to minutes (full backfill ≈ 33,735 rows, 5000/page, 0.6 s pause), `key:EIA_API_KEY` | Errors are sanitised (key scrubbed) and stored; failed jobs retry ≥ 6 h later; no numeric EIA limit published | Upsert: previous revisions are not kept (unverified) | yes — already automated by FU-10 | |
| FU-04 | Resolve a price | `GET /api/fuel/price` | Airport → country → region → global observed, else a labelled estimate | country or airport, class → price + level used | R · none | instant | non-scheduled never falls back to wholesale | n/a | yes | |
| FU-05 | Series and statistics | `GET /api/fuel/series`, `/stats/{kind}`, `/bts/monthly` | Chart data and statistics (volatility, crack, regressions, lags, pass-through) | place, class, dates → data | S · none | instant | Thin data returns `{"status":"refused"}` | n/a | yes | |
| FU-06 | Search airports / countries | `GET /api/fuel/airports/search`, `/countries`, `/search` | Lookup of IATA codes and countries | q → matches | R · none | instant | none | n/a | yes | |
| FU-07 | **Coverage and job health** | `GET /api/fuel/coverage` | Per job: ok / stale / error / never_run / disabled, newest data date, BTS reminder | none → status | R · none | instant | none | n/a | yes — ideal monitoring tool | |
| FU-08 | Events and adjustments | `GET/POST /api/fuel/events`, `GET/POST/DELETE /api/fuel/adjustments` | Chart event markers; per-country add-on to estimates | event or adjustment → ok | W · small rows (adjustment delete = W) | instant | duplicates ignored | Yes | cond | |
| FU-09 | Import CSV / IATA / BTS text | `POST /api/fuel/import/csv`, `/iata`, `/import/bts` | Parses pasted file text into observations | text, column_map → counts | W · inserts / upserts | instant | 409 if the source is disabled; 422 with reasons | No | cond — needs the file text | |
| FU-10 | Scheduled refresh (automatic) | `fuel_prices/scheduler.py` → `service.refresh_due` | See "Existing schedulers" | — | W · as FU-03 | automatic, hourly tick + start-up catch-up | see section 5 | as FU-03 | already automated | |

### TO — Tourism indicators  `routers/tourism.py`, `tourism/`

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TO-01 | Read stored values, history, compare, providers status, imports, export | `GET /tourism/countries`, `/countries/{code}`, `/stored`, `/history`, `/providers/status`, `/imports`, `/export`; `GET /compare` | Indicators per country/year built from the database, each with source and edition; export as csv/xlsx/json | countries, year → rows/file | R · none (`compare?refresh=true` and `providers/status?check=true` call providers) | instant | a missing value is reported missing with a reason, never estimated | n/a | yes | |
| TO-02 | **Refresh stored values** | `POST /tourism/refresh` | Calls the providers (World Bank, IDB, UN SDG API; Statista if keyed) and stores observations | countries, year → stored rows | W · inserts observations | instant, no key for World Bank/UNSD; `key:STATISTA_API_KEY` for Statista | Max countries per call (`MAX_COUNTRIES`); provider errors per indicator | Observations keep source/edition/time and "sources never overwrite each other" (docstring); whether re-fetching duplicates or replaces: unverified | yes — free, annual cadence | |
| TO-03 | Provider enable / sync | `PUT /tourism/providers/{id}`, `POST …/{id}/sync` | Switch a provider on/off; force a UNSD or registered-dataset sync | id → ok / counts | W · flag; observations | instant | `not_syncable` 422 | Flag: Yes | cond | |
| TO-04 | Import a licensed WTTC file | `POST /tourism/import` | Parses a WTTC export into observations | file name, base64 (≤ 15 MB), edition, unit → import job | W · inserts observations | instant, **needs a file** | invalid → 422 | unknown | no — licensed file, human | |
| TO-05 | Add a country | `POST /tourism/countries` | Adds to the country registry | code → row | W · one row | instant | none | Yes | cond | |

### KB / RG / LM — Knowledge base, RAG Files, local models  `routers/knowledge_base.py`, `routers/rag_files.py`, `routers/local_models.py`

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KB-01 | List / download / view documents | `GET /documents`, `/documents/{id}/download`, `/view` | Company documents, generated reports, Modification Reports | id → file | R · none | instant | none | n/a | yes | |
| KB-02 | Upload a document | `POST /documents` | Stores a file | file → document row | W · new file + row | instant | needs file bytes | Delete (KB-04) | cond | |
| KB-03 | Add to knowledge base | `POST /documents/{id}/add-to-knowledge-base` | Chunks and embeds with the local ONNX model (offline, no credits) | id → ok | W · writes embeddings | instant–seconds | none | Rerun | cond | |
| KB-04 | **Delete a document** | `DELETE /documents/{id}` | Removes the document | id → ok | X · destroys the file/row | instant | none | No | no | |
| KB-05 | Search knowledge base | `POST /knowledge-base/search` | Semantic + keyword passages | query, top_k → passages | R · none | instant, local | none | n/a | yes | |
| KB-06 | Ask knowledge base | `POST /knowledge-base/ask` | Retrieves 6 passages and has Claude answer | question → answer + sources | R · none | instant, `credits` | 502 on failure | n/a | yes | |
| RG-01 | List countries / files / read converted JSON | `GET /rag-files/countries`, `…/{name}`, `…/files/{f}/json`, `GET /rag-files/queue` | Per-country document folders and queue state | name → status | R · none | instant | none | n/a | yes | |
| RG-02 | Upload / delete a country file | `POST …/files`, `DELETE …/files/{f}` | Adds or removes a source document | filename + base64 → ok | W (upload); delete = W | instant | needs file bytes; supported extensions only | Upload: delete; delete: No | cond | |
| RG-03 | **Load (convert to JSON)** | `POST /rag-files/countries/{name}/load` | Queues conversion of the country's documents | name → queue state | W · writes converted JSON | job (single worker thread, queue) | `cancel` available; thread dies on restart | Rerun | yes | |
| RG-04 | **Bake (embed)** | `POST …/{name}/bake` | Queues embedding into the country's one RAG file; unchanged documents keep their chunks | name → queue state | W · rewrites the baked file | job, local embeddings, no credits | as RG-03 | Rerun | yes | |
| RG-05 | **Bake everything pending** | `POST /rag-files/queue/bake-pending` | Queues a bake for every country whose loaded documents are not yet baked | none → queued list | W · as RG-04 | job | none | Rerun | yes — one call, free, idempotent | |
| RG-06 | Cancel a queued job / search a country | `POST …/queue/{id}/cancel`, `POST …/{name}/search` | Cancels; keyword + embedding search | job id / query → job / passages | W (cancel) / R | instant | none | n/a | yes | |
| LM-01 | List local models | `GET /local-models` | Installed Ollama models that can write text | none → models | R · none | instant, Ollama at `OLLAMA_HOST` | reports why none are available | n/a | yes | |
| LM-02 | Local report (start / poll / cancel / save) | `POST /local-models/report`, `GET …/report/{job}`, `…/cancel`, `POST …/reports/save`, `GET …/reports/file` | A local model navigates baked RAG files (`local_models/agent.py`: search, grep, read, calc; max 10 steps) and writes a report | model, country, question → job → text | W (start; save writes a markdown file in the country's `reports` folder) | job, local Ollama, no credits | bounded loop; trace shown with the answer; answer must come from tool results | Saved report: delete | cond | |
| LM-03 | Local tax-cost report (PDF) | `POST /local-models/tax-report`, `GET …/tax-report/{job}`, `…/cancel`, `…/pdf` | PDF of a country's opportunities of one rating with tax cost | country, rating → job → PDF | W · job output | job, local Ollama | requires the country's baked RAG file (checked) | Rerun | cond | |

### RA — Risk analysis  `routers/risk_analysis.py`, `risk_analysis/`

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RA-01 | Read risk analysis / a plan | `GET /companies/{c}/risk-analysis`, `…/risk-categories/{id}/plan` | Categories, risks, mechanisms, scores; generated plans | company → tree | R · none | instant | none | n/a | yes | |
| RA-02 | Create / update category, risk, mechanism | `POST/PUT` on `/risk-categories`, `/risks`, `/mechanisms` | Edits the register | fields → row | W · rows | instant | none | Yes (edit back) | no — human register | |
| RA-03 | Delete category / risk / mechanism | `DELETE` on the same three | Removes register entries | id → ok | X · destroys entries | instant | none | No | no | |
| RA-04 | **Generate a risk plan** | `POST …/risk-categories/{id}/generate-plan` | Claude writes a plan for the qualifying risks | ids → started | W · overwrites the plan | job, `credits` | unverified failure handling | No | cond | |

### PK — Cargo load operations and air logistics  `routers/packer.py`, `routers/air_logistics.py`, `packer/`

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PK-01 | Read aircraft, plans, boxes, events | `GET /api/packer/aircraft`, `/aircraft/{id}`, `/plans`, `/plans/{id}`, `/boxes/{id}`, `/events` | Stored aircraft, plans, released boxes, release events | id → record | R · none (`aircraft` list calls `ensure_seed`) | instant | none | n/a | yes | |
| PK-02 | **Pack a plan (compute)** | `POST /api/packer/pack` | Calculates the layout, weights, door exclusions for a plan | plan → layout | S · none | instant | deterministic | n/a | yes | |
| PK-03 | Suggest box sizes | `POST /api/packer/suggest` | Size suggestions for an aircraft | plan → suggestions | S · none | instant | 422 on bad input | n/a | yes | |
| PK-04 | AI-draft an aircraft | `POST /api/packer/aircraft/draft` | Claude drafts geometry from a text query | query → aircraft draft | S · none | instant, `credits`, `key:ANTHROPIC_API_KEY` (a different name from the `CLAUDE_API_KEY` used elsewhere) | 503 if the variable is missing; the `.env` variable list has no such name (see Open questions) | n/a | no | |
| PK-05 | Save plan / aircraft | `POST /api/packer/plans`, `POST /plans/{id}`, `PUT/POST /aircraft` | Stores a plan (optimistic version check, 409 on conflict) or an aircraft | plan → plan | W · rows | instant | 409 if changed elsewhere | Version number only; no history | cond | |
| PK-06 | **Release a plan (assign box IDs)** | `POST /api/packer/plans/{id}/release` | Re-packs, deletes the plan's box slots, inserts new ones, records a release event | plan id, confirm_reassign → ids | X · box IDs that may already be printed on labels | instant | 409 if IDs would change without `confirm_reassign`, or an ID belongs to another plan | No (previous slots deleted) | no | |
| PK-07 | Labels / work order / boxes CSV / barcodes | `GET …/plans/{id}/labels.pdf`, `/workorder.pdf`, `/boxes.csv`, `POST /workorder/preview`, `POST /barcodes` | Documents for the floor | plan id → file | R · none | instant | none | n/a | yes | |
| PK-08 | Delete aircraft | `DELETE /api/packer/aircraft/{id}` | Removes (or hides) an aircraft | id → ok | X | instant | unverified whether hard delete | No | no | |
| PK-09 | Air logistics fleet, charter providers, aircraft catalogue | `/companies/{c}/air-logistics/*` (list, create/update, delete) | Company fleet and charter provider records | fields → rows | R (lists) / W (create, update) / delete = W | instant | none | Yes (edit back); delete: No | no | |

### FN — Finance, accounting and revenue  `routers/accounting_audit.py`, `commercial_operations.py`, `bank_accounts.py`, `general_ledger.py`, `startup_investment.py`, `expense_*.py`, `revenue_streams.py`

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FN-01 | **Run the accounting audit now** | `POST /accounting-audit/run-now` → `accounting_auditor.run_audit` | Independent check of every commercial-operation entry: field completeness, bank transaction, journal postings, company cash balance; stores a run and findings | scope company? → run | W · adds `AccountingAuditRun` / findings rows (that it changes no other table is unverified) | instant (runs inline) | no external call, no credits | Findings can be re-run | yes — already scheduled (see section 5) | |
| FN-02 | Read audit settings / runs / findings | `GET /accounting-audit/settings`, `/runs`, `/runs/{id}` | Enabled flag, interval days (1–90), scope, last run; runs and their findings | none → data | R · none | instant | none | n/a | yes — a digest tool | |
| FN-03 | Change audit settings | `PATCH /accounting-audit/settings` | Turn the scheduled check on/off, change interval and scope | enabled, interval_days, scope → settings | W · one row | instant | `enabled` must be boolean | Yes | no | |
| FN-04 | Read ledger | `GET /companies/{c}/gl/accounts`, `/gl/journal-entries` | Chart of accounts and journal entries | company → rows | R · none | instant | none | n/a | yes | |
| FN-05 | Read operations, bank accounts, transactions, expenses | `GET …/commercial-operations`, `…/bank-accounts`, `/bank-accounts/{id}/transactions`, `…/expenses`, `/expense-categories`, `…/expense-providers` | Operational and bank data | company → rows | R · none | instant | none | n/a | yes | |
| FN-06 | **Create / update a commercial operation entry** | `POST/PUT /companies/{c}/commercial-operations[/{id}]` → `gl_engine.post_commercial_operation_entry` | Records revenue/cost entries and posts journal and bank legs | entry fields → entry | X · accounting and cash postings | instant | settlement-date and treatment rules | the update un-posts and re-posts; no history | no | |
| FN-07 | **Delete a commercial operation entry** | `DELETE …/commercial-operations/{id}` → `unpost_commercial_operation_entry` | Removes the entry and its postings | id → ok | X | instant | none | No | no | |
| FN-08 | **Bank transfer / create / delete bank account** | `POST /bank-accounts/transfer`, `POST …/bank-accounts`, `DELETE /bank-accounts/{id}` | Moves cash between accounts; manages accounts (a Main account cannot be deleted; one Main per bank) | accounts, amount → transactions | X · money | instant | amount > 0; different accounts | No | no | |
| FN-09 | Start-up investment plan and records | `GET/POST/PUT/PATCH/DELETE /companies/{c}/startup-investment/*` | Planning records; Main-account opening balance syncs from the plan (`sync_opening_balance`) | plan/records → rows | W (delete of a record = W) · may add the opening-balance bank transaction | instant | none | Edit back; delete: No | no | |
| FN-10 | Expense categories, provider, company expense settings | `/expense-categories*`, `/expense-category-company-settings`, `…/expenses/{category}`, `…/expense-providers` | Category list and per-company amounts | fields → rows | W · rows | instant | none | Yes (edit back) | no | |
| FN-11 | Revenue streams, routes, shipment save | `/companies/{c}/revenue-streams*` | Streams, route legs, saved outbound/return shipments (Shipment builder output) | fields → rows | W · rows (route delete = W) | instant | the allocation itself is computed in the browser | Edit back | no | |

### CO / PR — Company structure, payroll, settings  `companies.py`, `commercial_structure.py`, `org_chart.py`, `payroll*.py`, `roadmap.py`, `settings.py`, `sim_parameters.py`

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CO-01 | Read companies, regions, countries, branches, org chart, roadmap, sim parameters, reference countries, airport lookup | `GET` on the corresponding routes | Portfolio structure | ids → rows | R · none | instant | none | n/a | yes | |
| CO-02 | Create / update structure (company, region, country, branch, org node/edge, roadmap task, sim parameter) | `POST/PUT/PATCH` on those routes | Edits the structure. **Creating a commercial country starts the trade-source discovery chain automatically** (CT-04 path) | fields → row | W · rows; country create starts a job | instant (+ job) | validation per route | Edit back | no | |
| CO-03 | **Delete a company** | `DELETE /companies/{id}` | Removes a company | id → ok | X · destroys a company | instant | unverified whether it cascades | No | no | |
| CO-04 | Delete other structure items | `DELETE` region / country / branch / org node / edge / roadmap task / sim parameter | Removes items | id → ok | W (small; org node delete = W) | instant | none | No | no | |
| PR-01 | Read payroll rows, areas, template, levels, schedule settings, portfolio settings, country inflation | `GET /companies/{c}/payroll`, `/payroll-areas`, `/payroll-template`, `/payroll-levels`, `…/payroll-schedule-settings`, `/settings`, `/countries/{code}/inflation` | Payroll and settings | company → rows | R · none | instant | none | n/a | yes | |
| PR-02 | Edit payroll positions / employees; levels; schedule; apply or clear a growth rate for all | `POST/PATCH/DELETE /payroll-*`, `PUT /payroll-levels`, `PATCH …/payroll-schedule-settings`, `POST …/apply-growth-rate-all`, `…/clear-growth-rate` | Payroll roster and projection settings | fields → rows | W (employee delete = W) · apply-growth rewrites every row | instant | none | apply/clear: No | no | |
| PR-03 | Portfolio settings (FX rate, reference figures, benefits, inflation, US state, phases, schedule, time projection, calendar, start date) | `PATCH /settings/*`, `PATCH /countries/{code}/inflation`, `POST /settings/assign-start-date` | Portfolio-wide parameters; **inflation re-derives Year 2..N salaries**; phases replace the single start date | values → settings | W · some recompute payroll | instant | none | Set back; recomputed salaries are derived | no | |

### SG — Species gallery and variety matching  `routers/species_gallery.py`, `species_gallery/`

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SG-01 | Read species / varieties / review queue / config status | `GET /api/species-gallery/species`, `…/varieties`, `/admin/varieties/{id}`, `/review-queue`, `/config-status` | Stored gallery; which optional services are configured | name → rows | R · none | instant | none | n/a | yes | |
| SG-02 | Resolve a species | `POST /api/species-gallery/resolve` | Maps a product to a scientific name via GBIF (free, keyless) | name → species | W · cache row (details unverified) | instant, external GBIF | unverified | unknown | cond | |
| SG-03 | **Bootstrap a variety** | `POST /api/species-gallery/varieties/bootstrap` | Cache-first: GBIF + Wikimedia Commons + LangSearch (`key:LANGSEARCH_API_KEY`, free tier) + keyword characteristics; never repeated for the same variety | species, variety → variety record | W · new records, queued for review | instant-ish, external sites | Docstring: "zero paid-API spend"; unset LangSearch key degrades silently | Reject = delete | yes | |
| SG-04 | Confirm / reject a queued variety | `POST …/review-queue/{id}/confirm`, `DELETE …/review-queue/{id}` | Human review of bootstrapped varieties | id → record | W (confirm) / X (reject deletes) | instant | none | confirm: Yes; reject: No | no — human review | |
| SG-05 | Match varieties across countries / cost guardrail | `POST /api/species-gallery/match`, `/cost-guardrail` | Plain point-scoring (no AI); counts what a bootstrap would cost | products → scores / counts | S · none | instant | none | n/a | yes | |

### AS — The Assistant's current tools (the 7 tools in `routers/assistant.py`)

`POST /assistant/chat` runs a Claude loop (model from `knowledge_base/claude_client.py`, max 6 tool rounds, 30 turns of history, `credits`). Tools never run unattended: the chat is a browser feature.

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AS-01 | `search_knowledge_base` | `_run_tool` → `rag.search` | Top 6 passages from documents and generated reports | query → passages with source names | R · none | instant, local | none | n/a | yes (same as KB-05) | |
| AS-02 | `list_countries` | `_country_rows` | Commercial countries with ids and "has profile" | none → JSON | R · none | instant | none | n/a | yes | |
| AS-03 | `build_country_profile` | `_run_tool` | Validates and returns an `action`; **the chat window runs the real endpoint** (CP-02) | country_id → "started" | W · via CP-02 | **browser**, job, `credits` | unknown id → message | No | cond — an agent should call CP-02 directly | |
| AS-04 | `build_competitiveness_analysis` | `_run_tool` | Same pattern for CP-04; checks the target has a profile and the source has product data | target id, source name → "started" | W · via CP-04 | **browser**, job, `credits` | needs the browser-built summary | No | no (see CP-04) | |
| AS-05 | `list_product_sources` | `_run_tool` | Custom sources only (built-in ones excluded) | none → JSON | R · none | instant | none | n/a | yes | |
| AS-06 | `refresh_product_source` | `_run_tool` → `product_sources._analyze` | Re-reads a source's site and replaces its products | source id → text | W · as PS-06 | instant (inline), `credits` for step 4 | **Quirk (verified): for a `catalog`-origin source `_analyze` returns early without doing anything, status stays `ok`, and the tool still replies "Refreshed … N products."** A source with no URL gets a refusal message | No | cond — fix the catalog case first | |
| AS-07 | `refresh_market_size` | `_run_tool` → `comtrade.refresh_sam_overview` / `refresh_tam_overview` | Recomputes SAM and/or TAM, reports before/after totals | which: sam/tam/both → text | W · as CT-06/07 | instant, Comtrade key | as CT-06 | No | cond (same guard) | |
| AS-08 | Chat history | `GET/POST /assistant/messages`, `POST /assistant/messages/clear` | Stores the conversation; **clear** writes the whole chat to Documentation ▸ Modification Reports, then deletes the rows | messages → rows / report path | W · rows; clear = W (a copy is kept) | instant | none | Yes (the report holds the full chat) | no | |

### CU — Currency  `routers/currency.py`, `currency/exchange_rate.py`

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CU-01 | Exchange rate | `GET /api/exchange-rate/` | Rate for a currency pair | from, to → rate | R · in-memory cache only | instant, `key:EXCHANGERATE_API_KEY` | 4-hour cache (verified); failure behaviour unverified | n/a | yes | |

### SX — Scripts and developer tools (not tools for the agent)

| ID | Capability | Where | What it does | Inputs → output | Tier · side effects | How it runs | Limits · failure behavior | Restorable? | Automation fit | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SX-01 | Local-agent benchmark and trial | `backend/scripts/agent_bench.py`, `agent_trial.py` | Run the local RAG-navigating model on tax questions and score the answers | model, question, countries → printed trace | S · none | command line, local Ollama | dev use | n/a | no | |
| SX-02 | F24 payroll import test | `backend/scripts/import_f24_payroll.py` | One-off: **deletes and recreates** the test company `f24-import-test` and imports a payroll plan | none → test company | X · deletes/recreates a company | command line | verification script only | No | no | |
| SX-03 | Aircraft database import | `backend/import_aircraft_database.py` (`AIRCRAFT_IMPORT.md`) | Imports an aircraft catalogue | unverified | unverified | command line | not read | unknown | no | |

---

## 3. Chains that already exist

Order and what is automatic. "Auto" = happens without a person clicking the next step.

1. **Custom source add / refresh / file load** → read site or parse file → `save_snapshot` (deterministic normalization with already-researched weights) → source row status → **auto:** HS classification thread (Claude, `credits`). *Not automatic:* item-weight research (CN-09), Market Opportunities recompute, tax multipliers, translations.
2. **Supermarket catalog** → prepare (SC-02) → a person selects categories → download job on 8020 (SC-04) → **auto:** watcher thread polls every 2 s and imports the export (SC-05) even if the modal is closed → same as chain 1. The import is also triggered by anyone polling the job (SC-06).
3. **Built-in Update click (Colombia / USA)** → fetch (BI-02…05) → `save_snapshot`. *Not automatic:* HS classification (only queued when the browser builds the portfolio, `productPortfolio.js`), translation suggestions, weight research.
4. **Item weights** → research job (CN-09) → store weights → **auto:** re-annotate every catalog. Manual variant: AI Search (CN-10) → validate → a person saves (CN-11) → **auto:** all catalogs re-converted. A weight typed by a person (`confidence = user`) beats USDA and research.
5. **Catalog product deletion** → PS-09 → snapshot rewritten → `product_count` updated → **auto:** markdown report written and mirrored into Documentation ▸ Modification Reports.
6. **Creating a commercial country** → **auto:** `discovery.trigger` — quick Comtrade check (synchronous); if Comtrade has nothing, a background job walks the territory's statistics office → parent country office → FRED/US Census; stops at the first success; checks robots.txt.
7. **Country profile → competitiveness** → CP-02 must exist before CP-04 (400 otherwise); CP-04's category summary is built by the browser.
8. **Assistant build request** → tool validates and returns an `action` → **browser** runs the endpoint → `backgroundJobs.js` polls every 5 s → result posted into the chat store.
9. **Market Opportunities** → (browser) compute from snapshots + CN + tax multipliers + airfares → `POST comparisons` → server computes `diff_pct` and rating → priority list.
10. **RAG Files** → upload → Load (convert) → Bake (embed); `bake-pending` queues all stale countries; one worker thread processes the queue.
11. **Fuel** → start-up seed (refreshes source metadata, purges restricted FRED rows) → hourly tick `refresh_due` → drop-folder scan → `fuel_job_runs` → coverage page shows stale/error.
12. **Accounting audit** → hourly tick → if enabled and interval elapsed → `run_audit` → run + findings → `audit_last_run_at`.
13. **Commercial operation entry** → create/update → **auto:** journal postings and bank transaction (`gl_engine`); Main bank account creation and start-up investment edits **auto:** `sync_opening_balance`.
14. **Clear chat** → write the whole chat to a Modification Report → delete rows.

## 4. Gaps

**Logic that exists only in JavaScript (no callable backend function)**

- `src/services/marketOpportunities.js` — `computeMarketOpportunity`, `getOrComputeComparison`: the whole comparison engine (product matching, translations, unit/currency normalization, tax multipliers, airfares). The backend only stores results (MO-03).
- `src/services/productPortfolio.js` — `buildProductPortfolio`, `buildProductCodeIndex`, `buildCategoryCoverage`: the deduplicated English product list, reference codes, and the "qualifying categories" that define SAM/TAM chapter scope. SAM/TAM first compute and `product-sam` depend on it.
- `src/services/competitivenessInputs.js` — `getCategorySummary` (input of CP-04).
- `src/services/shipmentPricing.js` — `fetchBuiltShipmentAirfares`; and the Shipment builder allocation itself (route leg cards under Financial ▸ Revenue).
- Product-name translation tiers 1–2 (`productTranslations.js`, `priceComparisonData.js` `mergeSources`), `unitConversion.js` overrides/signatures, `catalogNorm.js`.
- `src/services/marketAnalysisStatus.js` — the Market Analysis table's per-country status join (no backend endpoint).
- Payroll/benefit calculators: `colombiaPayrollTax.js`, `usPayrollTax.js`, `usBenefits.js`, `stMaartenPayrollTax.js` (whether a backend twin exists: unverified), plus `excelImport.js`, `calendarDates.js`.

**Done only by clicking, or with inputs only the UI holds**

- Supermarket "Rebuild catalog": the category selection lives in React state; nothing stores it server-side.
- Built-in source refresh is wired to the Update buttons; the endpoints exist but nothing calls them on a schedule.
- Loading a products file, uploading WTTC/RAG/knowledge-base documents: need file bytes from the browser (the APIs accept base64, but there is no watch folder except the fuel BTS one).
- DIAN rows needing a choice (`selection_required`, `multiple_valid_rows`).
- Fuel licence sign-off (FU-02), weight/translation confirmations, variety review: deliberately human.
- The Assistant's build tools hand an `action` to the chat window instead of running anything.

**Missing plumbing an agent would want**

- No snapshot history or undo anywhere (see Restorable legend). Only `accounting_audit_runs` and `fuel_job_runs` keep run history; product-source refreshes keep only the last `fetched_at`.
- No cross-module "what is stale?" endpoint (only fuel `coverage` and per-source `last_loaded_at`).
- No generic job registry: each feature has its own marker files (`*.building`, `*.error`) or an in-memory dict; markers older than the server start are discarded (a restart kills BackgroundTasks jobs).
- No guard against saving empty or much smaller results (BI-04 `beef.py`, CT-06/07, PS-06).

## 5. Existing schedulers and background jobs

| What | Trigger | Configuration | Notes |
| --- | --- | --- | --- |
| **Accounting audit scheduler** (`accounting_audit_scheduler.py`) | In-process APScheduler `BackgroundScheduler`, started in `main.py` `_on_startup`; ticks every 60 min, first tick at start-up | Portfolio settings row: `audit_enabled`, `audit_interval_days` (default 7, allowed 1–90), `audit_scope_company_id`, `audit_last_run_at`; edited via `PATCH /accounting-audit/settings` (Settings ▸ Accounting Health Check). Takes effect at the next tick, no restart | Default of `audit_enabled`: unverified. Does nothing while the backend is not running |
| **Fuel refresh scheduler** (`fuel_prices/scheduler.py`) | `start()` at start-up (seeds sources, then APScheduler hourly tick, first tick immediately = catch-up after downtime) | Per source `enabled` flag (+ sign-off for unverified sources), `EIA_API_KEY`, job frequency table `INTERVAL_DAYS` (daily / weekly / monthly series), last runs persisted in `fuel_job_runs` | Failed job retried ≥ 6 h later; BTS drop folder `fuel_prices/drop/bts_p12/` scanned every tick. Module is uncommitted |
| **Thread / BackgroundTask jobs started by a request** (not schedules) | Request | Marker files next to the output (`background_jobs.py`) or in-memory | Country profile, competitiveness, risk plan, HS classification, weight research, translation suggestions, trade-source discovery (BackgroundTasks); RAG Files worker, local reports, tax reports, catalog watcher, HS-classify-when-free (threads). All die on a backend restart |
| **Frontend polling** (`src/services/backgroundJobs.js`) | A browser tab started the job | 5 s poll, posts the result into the chat store | The backend job continues if the tab closes, but the chat notice needs a browser |
| **Supermarket service (8020)** | Started by hand (`launch_api.bat`, or the global-Python command in CLAUDE.md) | `SUPERMARKET_API_URL` | Not started or supervised by Majestic; keeps its own jobs in memory |
| **OS-level schedules / cron** | none found in the repository | — | A Windows Task Scheduler entry outside the repo cannot be excluded (unverified) |

Nothing else runs by itself: **no product source, SAM/TAM figure, tariff file, profile, tourism value or catalog refreshes on a timer today.**

## 6. Open questions

| # | Question | Where to look |
| --- | --- | --- |
| 1 | `TRADE_GOV_API` is in `.env` but no backend code reads that name (grep of `*.py`); `trade_gov/commercial_guides.py` fetches public HTML with no key. Is the entry unused? Also its line uses `NAME: value`, not `NAME=value`, which `python-dotenv` may not parse. (While listing variable names I accidentally printed that line's value into this session's tool output — it is not in any file; consider rotating it if session logs are shared.) | `.env` (names only), `backend/main.py` `load_dotenv()`, `trade_gov/` |
| 2 | Packer AI draft needs `ANTHROPIC_API_KEY`; the `.env` variable list has no such name (only `claude_api_key`, which every other module uses). Is `/aircraft/draft` simply unavailable? | `backend/packer/ai_draft.py` lines 19–21 |
| 3 | Do the other six USDA parsers save an empty list on a layout change? (`beef.py` has no guard.) | `usa_sources/{pork,poultry,eggs,grains,produce_fl,produce_ca}.py`, `routers/usa_sourcing.py` `_endpoint` |
| 4 | Does a SAM/TAM refresh really overwrite with partial totals when Comtrade rate-limits mid-run? Needs a controlled test on a copy of the DB. | `routers/comtrade.py` ~385, ~583, ~757; `market_size_store.save_snapshot` |
| 5 | Does `DbStore.put` commit per weight, so earlier research batches survive a later failure? | `catalog_normalization/store.py`, `routers/catalog_normalization.py` `_run_research` |
| 6 | BTS monthly: the fuel README says an automatic daily check of the TranStats history table (`sources/bts_monthly.py`), while the 2026-11-09 diary entry says it is not automated. Which is current? | `fuel_prices/sources/bts_monthly.py`, `fuel_prices/service.py` (`ADAPTERS`, `INTERVAL_DAYS`) |
| 7 | Corabastos on days without a bulletin, and La Mayorista after a homepage change — real failure messages. Needs a live call, so it was not run. | `price_sources/corabastos.py`, `la_mayorista.py` |
| 8 | Is there any OS-level backup of `majestic_plt.db` (OneDrive version history, a copy job) that could serve as a restore point? | OneDrive settings (outside the repo), `git log -- majestic_plt.db` |
| 9 | What does the 8020 service's `prepare` persist (saved store setups), does it throttle or honour robots.txt, and could it return a saved category list for a store? Read-only; the app is Codex-owned. | `D:\OneDrive\0. software Lab\Supermarket_data_fetch\api_server.py`, `app/worker.py` |
| 10 | Default of `audit_enabled`, and whether `run_audit` touches any non-audit table. | `backend/models.py` `PortfolioSettings`, `accounting_auditor.run_audit` |
| 11 | Tourism: does a second refresh replace or append observations (history)? | `tourism/service.py` upsert, `models.TourismObservation` |
| 12 | Do payroll/benefit calculators have a backend twin? | `backend/routers/payroll.py`, `settings.py`; `src/services/*PayrollTax.js` |
| 13 | Does deleting a company cascade (CO-03), and does aircraft delete hide or remove (PK-08)? | `routers/companies.py`, `routers/packer.py` `aircraft_delete` |
| 14 | Which Ollama models are installed and is `OLLAMA_HOST` reachable (LM rows, BI-07 tier 3)? | `GET /local-models` (not called), `local_models/ollama_client.py` |
| 15 | `POST /api/product-matches` and `POST /species-gallery/resolve`: exact cache writes and failure behaviour. | `routers/product_matches.py`, `product_matching/claude_client.py`, `species_gallery/resolver.py` |
| 16 | Graphify: `wiki/index.md` is a generic overview and `GRAPH_REPORT.md` lists only community hubs, so no module boundaries came from them; this inventory is built from router/AST and file reads. The graph was built from `6e161e54` and does not cover the uncommitted fuel/Agents code until `graphify update .` runs. | `graphify-out/` |

---

## Addendum 2026-11-10 — capabilities added after this inventory was written

Same columns as above in short form (all backend functions; none needs the browser). Counts in the summary above were not updated.

| ID | Capability | Where | Tier · side effects | Runs | Notes |
| --- | --- | --- | --- | --- | --- |
| DH-01 | List datasets / versions / diff | `GET /api/data-history/datasets`, `/log`, `/diff` | R | instant | |
| DH-02 | Restore a version | `POST /api/data-history/restore` | W · becomes a new version | instant | restorable by restoring again |
| DH-03 | Approve / reject a held refresh | `POST /api/data-history/held/{id}/approve|reject`, `GET /held` | W · approve saves the held data | instant | a refresh that is empty or loses 50%+ of the rows (SAM/TAM -25%) waits here |
| DH-04 | Pin a version | `POST /api/data-history/pin` | W | instant | |
| HC-01 | HS status / review queue / lookup | `GET /api/hs-codes/status`, `/queue`, `/lookup` | R | instant | |
| HC-02 | Validate HS codes | `POST /api/hs-codes/validate` | S | instant | against Comtrade's HS reference + category + other countries |
| HC-03 | Suggest HS codes | `POST /api/hs-codes/suggest` | S · saves nothing | instant; local model slow; Claude needs credits | rule, same product elsewhere, local model, Claude (each only when allowed) |
| HC-04 | Save HS codes | `POST /api/hs-codes/save` | W · rewrites every catalog, versioned (`hs:assignments`) | instant | confirmed / corrected by a person |
| PF-01 | Product directory | `GET /api/portfolio/directory` | R | instant | one row per country and product with its HS code |
| PF-02 | Category coverage / qualifying chapters | `GET /api/portfolio/category-coverage`, `/qualifying-chapters` | R | instant | the chapters SAM and TAM cover |
| PF-03 | Products of one country / merged Colombia table | `GET /api/portfolio/products?country=`, `/colombia` | R | instant | English names, HS blocks, comparison fields |
| MB-01 | Build a market access brief | `POST /companies/{c}/commercial-countries/{target}/competitiveness` | W · overwrites the brief file (versioned) | job, `credits` | only the source country name is needed; replaces the browser-built summary |
| MO-07 | Compute a comparison (simulation) | `POST /api/market-opportunities/compute` with `save:false` | S · saves nothing | instant with `allow_ai:false, allow_research:false` (free, deterministic) | replaces the browser-only engine (old MO-02) |
| MO-08 | Compute and save a comparison | `POST /api/market-opportunities/compute` (`wait:true` or poll `GET /compute/status`) | W · replaces the pair's saved rows, records what it was built from | job; `allow_ai` / `allow_research` spend credits only when true | not yet versioned in the data history |
| MO-09 | Is a saved comparison out of date | `GET /api/market-opportunities/comparisons/pairs` (`stale`, `stale_reasons`) | R | instant | names the catalog / HS / weight / translation change |
| MO-10 | A country's prices in USD/kg | `GET /api/market-opportunities/country-prices?country=` | R | instant | the prices the tax-multiplier and shipment screens use |
