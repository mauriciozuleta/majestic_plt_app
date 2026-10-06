# Majestic P.L.T. — project diary



A progress wiki for whoever picks the project up next, **with no memory of earlier sessions**.

Read this file first; it is cheaper than re-reading the code. Newest entry on top.



**Rule for every prompt that changes something:** add an entry at the top of "Entries" with the date, the

user's prompt (verbatim, trimmed only if very long), and a summary of what changed and why. Keep the

"At a glance" section true. Do not paste code here — name files instead.



## Handout — start here (written 2026-10-05, end of day; next session starts 2026-10-06)

> **How this works.** This block exists so a new or changed session can pick up in one read. When you start a session:
> read it, do the work, add your entries under "Entries", then **delete this block**. As the very last step of the session
> (or of every prompt that changes something) write a fresh handout in its place, describing the state *then*. Never leave
> a stale handout behind. (`CLAUDE.md` makes reading this diary and the graphify files mandatory at session start — say in the
> first reply that you read them.)

**State of the code**
- Last commit: `f3953d6`. **Everything from this long session is uncommitted** (the user hasn't asked for a commit — don't commit unless
  asked; after any commit run `graphify update .`): the Country Commercial Guide reader (`backend/trade_gov/`) and profile changes
  (`country_profile/claude_client.py`, `routers/country_profile.py`); the **RAG Files** module (`backend/rag_files/`,
  `routers/rag_files.py`, `src/components/ragFiles/`, `src/services/ragFiles.js`, `src/services/ragDataFiles.js`, one line in
  `knowledge_base/rag.py`, thread cap in `knowledge_base/embed.py`); **local models** (`backend/local_models/` — `ollama_client.py`,
  `reports.py`, `tax_report.py`, `import_tax.py`, `agent.py`; `routers/local_models.py`; `src/components/chatbox/`,
  `src/services/localModels.js`); the sidebar changes (`layout/Sidebar/`); `src/App.jsx`; `backend/main.py`; `.gitignore`;
  `CLAUDE.md`; this diary; the rebuilt Jamaica profile (`backend/documents/knowledge_base/62c74da6…md`) and `majestic_plt.db`.
- `backend/documents/rag_files/` is gitignored on purpose (user documents, JSON conversions, baked RAG files, saved reports).
- Services running now (may be gone tomorrow): `npm run dev` (backend 8012, frontend `http://127.0.0.1:5173/`) and `ollama serve`.
  If the backend doesn't serve a NEW route after an edit, restart fully (stop python `uvicorn|multiprocessing` + node `vite|concurrently|npm-cli`
  + the `cmd.exe /c npm run dev`, then start `npm run dev` again) — `--reload` missed new routes several times today.

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

**The open question (where we stopped):** the user does NOT want hardcoded solutions — they want to establish whether a local model can
navigate the RAG files and answer by itself. `backend/local_models/agent.py` (generic tools search/grep/read/calc, JSON actions, optional
self-review and think mode; NOT wired into the chat) was benchmarked on the tomato question in 4 wordings: gemma3:12b 0/4, qwen3:8b 0/4,
qwen3:8b with thinking 0–1/4. They find the tariff row but misread it (drop the `ID 01` import-duty column, treat fractions as money or
as %, add wrongly); the column codes are never explained in the documents. Offered, not yet decided: run the same harness with a bigger
model (`qwen3:14b`, fits 12 GB, ~9 GB download — ask before downloading); or accept the hybrid (code reads rows, model explains). The chat
currently uses the hybrid. Bench scripts: `backend/scripts/agent_trial.py <model> "<question>" "Jamaica,United States"` (prints the tool trace)
and `backend/scripts/agent_bench.py "<model>|<on|off>|<review|noreview>" …` (4 wordings of the tomato question; needs Jamaica baked —
snapshot/restore it). Run with `.venv/Scripts/python.exe`.

**Open questions / loose ends**
- Decide the agent question above; if a bigger model works, consider replacing `import_tax.py`/row-reading with the agent.
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

