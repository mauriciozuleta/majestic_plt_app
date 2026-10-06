# Majestic P.L.T. — project diary



A progress wiki for whoever picks the project up next, **with no memory of earlier sessions**.

Read this file first; it is cheaper than re-reading the code. Newest entry on top.



**Rule for every prompt that changes something:** add an entry at the top of "Entries" with the date, the

user's prompt (verbatim, trimmed only if very long), and a summary of what changed and why. Keep the

"At a glance" section true. Do not paste code here — name files instead.



## Handout — start here (written 2026-10-06, after the calculator rework and the tax multipliers)

> **How this works.** This block exists so a new or changed session can pick up in one read. When you start a session:
> read it, do the work, add your entries under "Entries", then **delete this block**. As the very last step of the session
> (or of every prompt that changes something) write a fresh handout in its place, describing the state *then*. Never leave
> a stale handout behind. (`CLAUDE.md` makes reading this diary and the graphify files mandatory at session start — say in the
> first reply that you read them.)

**State of the code**
- Committed so far: up to `72ff4c4` (diary handout) / `f154581` (the 2026-10-05 work). **Uncommitted since then: the Tax Calculator** (see below:
  `backend/tax_calc/`, `routers/tax_calculator.py`, `main.py` registration, `tests/test_tax_calc.py`, `src/components/taxCalculator/`,
  `src/services/taxCalculator.js`, `App.jsx` route, `Sidebar.jsx` item, `.gitignore`) and this diary. Previous commit: `f154581` ("Add RAG Files, local Ollama models in the chat, tax-cost reports and Commercial Guide reader") on `main`,
  on top of `f3953d6`. It holds everything from the long 2026-10-05 session: the Commercial Guide reader (`backend/trade_gov/`) and
  profile changes; the RAG Files module (`backend/rag_files/`, `routers/rag_files.py`, `src/components/ragFiles/`,
  `src/services/ragFiles.js`, `ragDataFiles.js`, `knowledge_base/embed.py` thread cap, one line in `knowledge_base/rag.py`);
  local models (`backend/local_models/` — `ollama_client.py`, `reports.py`, `tax_report.py`, `import_tax.py`, `agent.py`;
  `routers/local_models.py`; `src/components/chatbox/`, `src/services/localModels.js`; bench scripts `backend/scripts/agent_*.py`);
  the sidebar; `CLAUDE.md`; this diary; the rebuilt Jamaica profile and `majestic_plt.db`. The graph was refreshed after the commit.
- Deliberately NOT committed: the ~50 modified/new `__pycache__/*.pyc` files (tracked by an old commit but never part of this work —
  consider `git rm --cached` + a `.gitignore` entry for `__pycache__/` if the user wants them out of status).
- `backend/documents/rag_files/` is gitignored on purpose (user documents, JSON conversions, baked RAG files, saved reports).
- Services running now (may be gone tomorrow): `npm run dev` (backend 8012, frontend `http://127.0.0.1:5173/`) and `ollama serve`.
  If the backend doesn't serve a NEW route after an edit, restart fully (stop python `uvicorn|multiprocessing` + node `vite|concurrently|npm-cli`
  + the `cmd.exe /c npm run dev`, then start `npm run dev` again) — `--reload` missed new routes several times today.

**Tax Calculator (new, 2026-10-06; the user decided NOT to test a 14B model — "if it fails at reading rag, no point" — and asked for
a deterministic calculator per country instead).** Sidebar ▸ **Tax Calculator** (`/tax-calculator`). Backend `backend/tax_calc/`: one adapter
per country (`base.py` interface + helpers, `jamaica.py`, `usa.py`, registry in `__init__.py`); API `routers/tax_calculator.py`:
`GET /tax-calc/countries`, `GET /tax-calc/{country}/search?q=` (words or code prefix), `POST /tax-calc/{country}/calculate`,
`POST /tax-calc/{country}/refresh`. No AI anywhere: every result lists each tax with its rate, base and formula, plus assumptions
(`notes`), things not computed (`warnings`) and `complete` (false when a charge couldn't be computed). Data lives in
`backend/documents/tax_data/<Country>/` (gitignored; recreate with the page's "Update tariff data"):
- **Jamaica**: `tariff.csv` = copy of the printable tariff uploaded in RAG Files. Charges on the CIF value (goods + freight +
  insurance): import duty (ID), additional stamp duty (ASD), excise, special consumption taxes, SCF levy, environmental levy, cess, CAF;
  GCT on CIF + duties (cumulative). CARICOM-origin goods: import duty waived (ASD kept, flagged to verify). Optional advance GCT 5% for
  registered commercial importers (shown, not counted). Text charges ("J$ 1,400 per LPA", "US$1 per litre") are reported, not guessed.
- **United States**: `hts_full.json` = USITC export (13,802 rate lines), downloaded from hts.usitc.gov — the `2026_hts.md` in RAG Files is a
  PDF dump with scrambled columns and can't be parsed. Duty from the General (MFN) rate, a Special program the origin qualifies for
  (curated `PROGRAMS` map: CO, E=CBERA, S=USMCA, P=CAFTA-DR, …), or Column 2 (Cuba, North Korea, Russia, Belarus); ad valorem, specific
  (¢/kg, $/unit) and compound rates; customs value excludes freight; MPF 0.3464% (min 33.58, max 651.50 — FY2026 figures, verify each Oct 1),
  HMF 0.125% for sea. NOT computed: Section 232/301/IEEPA ("reciprocal") duties and AD/CVD — warned on every result; informal entries
  (<= USD 2,500) get no MPF. GSP/ATPA programs are deliberately not mapped (expired).
- Verified by hand + `backend/tests/test_tax_calc.py` (8 tests, `.venv/Scripts/python.exe -m unittest backend.tests.test_tax_calc`): Jamaica
  fresh tomatoes, 1,000 kg at USD 1.51 → USD 3,369.57 total = USD 3.37/kg (223.15%); US tomatoes 0702.00.20 from China 2,000 kg → 78.00 duty + 33.58 MPF.
- **Calculator page (reworked 2026-10-06 per the user):** state persists (zustand `useTaxCalcStore`, localStorage `majestic-tax-calculator`: countries, product,
  line, form, last result, and a history of the last 30 calculations that can be reopened/removed). Step 1 = **Buying from (origin)** select + **Importing
  into (destination)** tabs; step 2 = the origin's **product portfolio** (`fetchCountryProductPrices` in `services/marketOpportunities.js`: every product
  with USD/kg, HS code and its tax multiplier) plus the tariff search (any product, not limited to the portfolio); choosing a portfolio product fills the
  price per kg and auto-selects the tariff line (`GET /tax-calc/{country}/suggest`, same rule as the multipliers); choosing a searched line fills the price
  from the portfolio product with the same HS6 (or offers a picker when several). Step 3 = price per kg, quantity, registered commercial importer —
  **freight, insurance and transport were removed** (the logistics module does them). The result headline shows the cost with import taxes paid and the
  tax multiplier.
- **Tax multiplier (new):** `tax_multiplier = import taxes / goods value` (Colombia → Jamaica tomatoes = x2.23, i.e. taxes of 223%; `landed_multiplier = 1 +` that,
  x3.23), computed for 1 kg at the product's price by the destination's calculator (fixed fees excluded). Table `product_tax_multipliers`
  (destination, origin, product_key) filled by `POST /tax-calc/multipliers/compute` for EVERY product of the origin's portfolio — matched in the
  target market or not — and read with `GET /tax-calc/multipliers?destination=&origin=`. Product → tariff line (`backend/tax_calc/mapping.py`): the
  lines under the product's HS code; one line / identical rates → ok; a unique word of the name → ok; else the single catch-all "Other" line or the
  highest-tax line → status `review` (marked * in the UI); no HS code or no line → `no_line`; fixed per-kg charges without a price → `needs_price`; text
  charges the calculator can't compute → `incomplete`. Market Opportunities (`MarketOpportunitiesPanel.jsx`) has a **Tax ×** column (tooltip = tariff
  line, taxes, how it was chosen) and a "taxes x0.62" chip on every product of the "No match found in target market" list; it (re)computes on every
  run for each target that has a calculator (Jamaica, United States). Colombia → Jamaica: 241 portfolio products — 169 ok, 59 review, 9 incomplete
  (cheeses/milk: a Cess charge written as text "$16.541 per kg"), 4 no_line (HS codes in the cache that don't exist in the tariff, e.g. 020710 whole chicken,
  110421, 030419).
- **Next ideas:** compute the Cess/specific text charges (needs JMD→USD at the day's rate); fix the outdated HS codes in the cache (020710→020711 …); wire the chat's import-tax answers to the calculator (replace `import_tax.py`/`rates_from_rows` row-reading); add countries —
  Trinidad and Tobago and Saint Lucia (CARICOM CET + 12.5% VAT; needs their tariff/VAT data), Colombia (DIAN tariff), Bahamas, Barbados;
  prefill price/quantity from the Product Portfolio / saved opportunities; show Jamaican-dollar rate date.

**RAG Files (what exists)**
- Per-country folder `backend/documents/rag_files/<Country>/{source,json,reports,<Country>.rag.json,bake.json,state.json}`. Status chain
  Uploaded → Loaded (JSON) → Baked. One global **queue** with one worker for every Load/Bake (queue strip, Cancel, **Bake all (n)**,
  chunk progress + ETA, per-document commits; the queue is in memory — a backend restart drops jobs). Embedding is batched (32) and capped
  to half the cores (`EMBED_THREADS`); baking ~3,000 chunks now takes seconds. Don't call `POST /rag-files/queue/bake-pending` casually —
  it bakes EVERY country with loaded files.
- Toolbar button **+ Portfolios & opportunities** adds `<Country> - Product Portfolio.md` and `<Country> - Product Opportunities.md`
  to every country (from `buildProductPortfolio()` + saved Market Opportunities; `diff_pct` = source price as % of target price,
  lower = bigger margin: Very High < 20, High < 30, Challenging < 50, Complex < 65, Difficult <= 100, Not Viable > 100).
- **Current data state:** each country folder has its Commercial Profile copy; Colombia, Jamaica, Saint Lucia, Trinidad and Tobago and
  the United States also have the portfolio + opportunities files — all "Uploaded" except: **United States is baked** (profile + 6.3 MB
  `2026_hts.md`, 8,711 chunks) and **Jamaica is Loaded but not baked** (profile + 2.5 MB tariff CSV loaded; the two new files uploaded).
  `Jamaica/reports/` holds the 45-product tax-cost PDF from the Gemma test. The user wants to run Load/Bake themselves — don't bake
  for them; if a test needs a baked country, snapshot its folder first, restore it afterwards, and delete test chat messages from
  `assistant_messages` (`majestic_plt.db`).

**Local models (Ollama) in the chat** — a local model only works from baked RAG files; Claude stays the default assistant.
Installed: gemma3:12b (best quality, ~10 GB on the RTX 3060 12 GB), gemma3:4b, qwen3:8b, qwen2.5:3b-instruct, qwen2.5-coder:7b, llava-phi3,
codellama 7b/13b. Three request kinds in local mode:
1. **Plain report** (`reports.py`): request → top semantic passages of the SELECTED country → cited Markdown report; "Open report" window.
2. **Import-tax question** (`import_tax.py`, hooked in `reports._run`): tax words + "import" (no "opportunit") → destination/origin
   countries from the wording, product → HS code (`product_hs_codes` cache), the DESTINATION's baked tariff rows for that HS code,
   rates read **by code** (`tax_report.rates_from_rows`: words that single out one row, else the catch-all "Other" line, else the model
   picks), per-USD and per-kg tax computed in code (origin price from saved Market Opportunities), model writes the answer from FACTS.
   Correct for the tomato question (Jamaica: 100% duty + 80% stamp duty + 15% GCT + 0.3% SCF + 0.85% environmental levy → 223.3% of
   customs value = USD 3.37/kg at the saved Colombian price of USD 1.51/kg; assumes GCT compounds on value+duty+stamp+levies).
3. **Tax-cost PDF** (`tax_report.py`): "tax cost of the very high opportunity products …" → per product the tariff row is read, Gemma
   writes the summary, reportlab lays out the PDF (saved in `<Country>/reports/`, "Open PDF" link in the chat, `GET /local-models/reports/file`).
   Only Jamaica's tariff-table format is converted to named percentages (`TARIFF_COLUMNS`); other countries get semantic passages only.

**(Resolved by the user, kept for context) The agent experiment:** the user does NOT want hardcoded solutions — they want to establish whether a local model can
navigate the RAG files and answer by itself. `backend/local_models/agent.py` (generic tools search/grep/read/calc, JSON actions, optional
self-review and think mode; NOT wired into the chat) was benchmarked on the tomato question in 4 wordings: gemma3:12b 0/4, qwen3:8b 0/4,
qwen3:8b with thinking 0–1/4. They find the tariff row but misread it (drop the `ID 01` import-duty column, treat fractions as money or
as %, add wrongly); the column codes are never explained in the documents. The user declined to try a bigger model and chose to build the deterministic Tax Calculator (above). The chat
still uses the hybrid (`import_tax.py`) until it is pointed at the calculator. Bench scripts: `backend/scripts/agent_trial.py <model> "<question>" "Jamaica,United States"` (prints the tool trace)
and `backend/scripts/agent_bench.py "<model>|<on|off>|<review|noreview>" …` (4 wordings of the tomato question; needs Jamaica baked —
snapshot/restore it). Run with `.venv/Scripts/python.exe`.

**Open questions / loose ends**
- Point the chat's import-tax answers at the Tax Calculator (and drop the row-reading code in `tax_report.py`/`import_tax.py`), then add more countries.
- Chicken backs: Jamaica's profile says backs/necks enter duty-free, the tariff only has an "Other poultry cuts" line (40%) — conflict between documents.
- Local reports are plain text (no Markdown rendering).
- Shipment builder fills the aircraft's max payload (27,000 kg); should it fill the outbound leg's Available cargo (Target Cargo % × payload)? Should
  destination prices prefer Jamaica's Wholesale level?
- A second supermarket download from the same store replaces its products — should it add instead? Ask Codex for an images on/off option?
- `.env` has `TRADE_GOV_API:` (colon) — should be `=`; that key's value was once printed in a session, consider rotating it.
- The Barbados Country Commercial Guide is from 2021; Saint Lucia, Saint Martin and United States profiles come from web research only.
- Not tested: reading legacy `.xls` in RAG Files. No ESLint config exists in the project (only `vite build` as a check).
- The supermarket catalog API (`launch_api.bat` in `Supermarket_data_fetch`, port 8020) is not running unless the user starts it.

**Habits worth keeping:** read this diary and the graphify files first; never print `.env` values; Codex owns
`Supermarket_data_fetch/api_server.py`; restart uvicorn/vite fully after backend changes; run `graphify update .` after code
changes; don't commit unless asked; write complex edits as script files (the shell heredocs broke repeatedly); wait for running
Load/Bake jobs before editing backend `.py` files; tell the user plainly when a test failed or a model was wrong.

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



## Entries

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

