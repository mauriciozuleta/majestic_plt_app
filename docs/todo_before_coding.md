# To-do list before coding

*Written for: the project owner, to answer the numbered questions before any code is written. Each question has my recommendation; answer with the number (for example "T1.2: 6 digits only") and anything you want to change. Nothing here is built yet.*

Status key: **recommended** = my proposal unless you say otherwise · **open** = needs your decision · **blocked** = cannot be tested yet.

## IMPLEMENTED 2026-11-10 (uncommitted)

**T1 (HS assignment in the normalization module) and T2 option B (market access brief) are built.** Where: `backend/catalog_normalization/hs.py` (parse/pad, per-country lookup, validation, suggestion tiers), `hs_store.py` (save, queue, status, history), `data/hs_item_rules.json` (curated rules, empty), table `product_hs_assignments`, API `/api/hs-codes/*` (`routers/hs_codes.py`); `backend/country_profile/access_pack.py` + new prompt in `claude_client.py`; UI: `HsCodeCell` (labels), `HsCodesModal` + the "N need HS" pill, Country Information ▸ "Market access brief". 62 new tests (362 in total) and a browser run on a throwaway copy of the database.

**Answers I applied by default (your recommended column) because you asked to implement what was discussed — tell me which to change:** T1.4 free-first order (rule → same product in another country → local model → Claude → person); T1.6 existing 6,744 name-only codes kept and read as "AI-suggested, not reviewed"; T1.7 an old name-only code applies to every country until a person saves one for that country; T1.8 review in a popup like the weights one (plus the pill); T1.9 opening a page or storing a source never starts a classification (both automatic triggers removed); T1.10 anyone can confirm, every change records the name (`saved_by`, currently "user"); T1.2b a padded heading keeps its real level (4) and is labelled "Heading only" (when the padded code is itself a real subheading, e.g. 0702.00, it is level 6); T1.3b labels "No HS code" (red), "Heading only" (amber), small neutral "AI" mark; T2.0 = B; T2.10 web search in the brief is off unless asked for.

**T1.5 measured (free, 40 random existing names, agreement with Claude's unreviewed codes):** qwen2.5:3b 8% same heading / 0% same 6-digit; gemma3:12b 35% / 30% overall — 52% / 43% on fresh food (chapters 01-14) and 16% / 16% on processed goods. Not good enough to trust: the local model is offered only as a low-confidence suggestion the person checks.

**Not done / still open:** the Claude suggestion step is built and unit-tested with a mock but NOT run live (no credits); the curated rules file is empty (rules need a person to add them); T2.0b (stale comparison in the shipment builder) and T2.0c (move shipment finance to the backend) are unanswered; the Assistant's own `build_competitiveness_analysis` tool and `chat.js` still send a (now ignored) summary and still say "competitiveness" — left for the Assistant redo; `competitivenessInputs.js` is now only used by that Assistant path.

Related: `docs/agent_tool_inventory.md` (what exists today), diary entry "Data history" (the version/undo system the items below use).

---

## T1 — HS code assignment inside the normalization module

**Goal.** Every catalog product carries an `hs` block next to its `norm` block. The code shown for a product is always `<origin country ISO2><6-digit HS code>` (for example `JM070200`). No placeholder or fallback codes. A product without a confirmed code has no code, is marked "needs HS code" and cannot be traded. Testing of the AI step waits until Claude credits are available.

**What exists today (verified).**
- Comtrade's full HS reference is cached at `backend/comtrade/hs_reference_cache.json`: 8,261 codes (98 chapters, 1,266 headings, 6,897 subheadings; 1,159 six-digit codes in food chapters 01–23). Free, refreshed weekly.
- 6,744 of 6,894 cached names have a code; 150 have none; 42 codes are only 4 digits; 138 of 217 USA built-in names were never classified.
- The code table (`product_hs_codes`) stores only the code and description: no confidence, no "a person checked this", no way to correct a wrong code except editing the database.
- The cache key is the lowercased product name only (no country).
- Fallback codes use the product's position in a sorted list, so adding a product renumbers them.
- The classification starts by itself when the portfolio page opens (spends credits).

**Proposed design.**
1. Lookup order, free first, no web call when a catalog is stored: a person's confirmed code → curated rules for common products → the same product already classified elsewhere (checked) → a local Ollama model restricted to the HS list → Claude → a person.
2. The AI step becomes an explicit job (`suggest` → `validate` → `save`), like weight research. Opening a page never starts it.
3. Automatic validation from the reference list: the code exists, is 6 digits (or is flagged incomplete), its chapter agrees with the product's category, and the same product in two countries does not silently get two codes.
4. Provenance on every code: AI-suggested / confirmed by a person / corrected, with the reference description and date. Changes are recorded in the data history so they can be undone.
5. A review queue ordered by importance (priority list and saved comparisons first, then products with no code or a 4-digit code, then flagged ones), using the same red "need data" pill and popup that missing weights use.
6. The cache key becomes country + product name. The 6,744 existing codes are kept, labelled "AI-suggested, not yet reviewed".

**Questions.**

| # | Question | Recommended | Your answer |
| --- | --- | --- | --- |
| T1.1 | One row per country and product (`JM070200` and `CO070200` for the same tomato), instead of one merged row with the first country's prefix? | Yes | **Answered:** option A, one row per country and product. |
| T1.2 | Is a 4-digit code acceptable for trade, or must every product reach 6 digits? | 6 digits required; a 4-digit code is "incomplete" and stays in the queue | **Answered:** minimum 6 digits shown. If a heading has no subcategories, 4 digits is accepted and filled with zeros, e.g. `CO020100`. *Follow-up T1.2b below.* |
| T1.3 | Products with no confirmed code: leave out of comparisons and SAM/TAM, or include with a warning? | Leave out (they still show in the catalog tables, marked "No HS code") | **Answered:** do NOT leave out; include them with a warning label. *Follow-up T1.3b below.* |
| T1.2b | Padding with zeros can create a code that is not a real HS code (0201.00 does not exist; Comtrade has 0201.10 / .20 / .30) or one that equals a real code (0702.00 is real). OK to store the real level (4 or 6) next to the padded display, label a padded code "heading only", and use only the 4-digit heading when matching against 6-digit Comtrade data? | Yes | |
| T1.3b | Warning labels: "No HS code" (red) and "HS heading only" (amber). A small neutral "AI-suggested" mark on unreviewed codes, not a warning (otherwise nearly every product would carry one). OK? | Yes | |
| T1.4 | Approve the free-first order (confirmed → curated rules → same product elsewhere → local model → Claude → person)? | Yes | |
| T1.5 | May I test the local model now (it is free) against the 6,744 existing codes, to see whether Claude is needed at all? Those codes are Claude's answers, not verified truth, so this measures agreement only. | Yes | |
| T1.6 | Keep the existing 6,744 codes as "AI-suggested, not yet reviewed" and review by priority, instead of re-classifying everything? | Yes | |
| T1.7 | The old name-only codes: apply to every country until a conflict is flagged? | Yes, flag conflicts (same name, different country context) | |
| T1.8 | Where does the review happen: extend the existing "need data" popup, or a separate screen in Settings next to Data history? | Extend the popup (same pattern as weights), plus a count in Settings | |
| T1.9 | Opening the portfolio must never start classification. Confirm. | Confirm | |
| T1.10 | Who can confirm or change a code: anyone using the app, or restricted? | Anyone, every change recorded with the name | |

**Blocked until credits:** testing the Claude step and classifying the 138 USA names. Everything else (rules, validation, review form, the local-model test) can be built and tested now.

---

## T2 — Competitiveness: compare both sides in USD/kg and keep the original quotes

**REVISED 2026-11-10 after the owner's answers — read this first.**
- The competitiveness analysis (Claude document) has **no button**: `CountryCompetitivenessAnalysis.jsx` is imported by no file (the import was removed in commit `ebcc225`; not traced further). It can only be started from the Assistant chat (`chat.js`, `build_competitiveness`).
- The real, numeric competitiveness is in the **Shipment Builder / Revenue routes** (`shipmentFinance.js`, JavaScript): cost, market level and suggested sale price from the **saved Market Opportunities rows**, the tax multipliers, the air fare and the destination market levels. Claude's document adds none of those numbers; what it adds is bans, seasonal restrictions, protected products and agreements from the target's profile.
- The stale-rows problem (T2.2) therefore matters most for the shipment finance: e.g. Colombia→Jamaica was saved 2026-10-03, La Mayorista was refreshed 2026-11-07.
- Multi-source rule today: Colombia → La Mayorista's price wins when both sources have a product (stated on the row); target side → median USD/kg of the matched products/sources; repeated listings in one source → median listing. Never an average.

| # | Question | Recommended | Your answer |
| --- | --- | --- | --- |
| T2.0 | Role of the competitiveness analysis: **A** retire it (remove the orphaned button and the Assistant tool; old documents stay readable); **B** keep it as a narrower "market access brief" (bans, seasonal restrictions, protected products, agreements, per HS heading of the portfolio; numbers shown as read-only facts; Claude reads the profile, no price verdict, no averages); **C** keep it as it is with fixed averages (the original plan below). | B | |
| T2.0b | Shipment finance when the saved comparison is older than the catalogs: show a stale warning in the builder, or refresh the comparison automatically (needs the comparison engine on the backend first)? | Warning now, automatic refresh after the engine is ported | |
| T2.0c | Move the shipment finance math (`shipmentFinance.js`) to the backend so an agent can price a shipment? New todo after T2. | Yes, as T6 | |

If the answer to T2.0 is **A** or **B**, questions T2.3–T2.12 below mostly fall away (they only apply to option C). T2.1, T2.2 and T2.13 still matter in a smaller form.

---

**Original goal (option C).** The competitiveness analysis compares our source-country products against the target country's own prices, both turned into USD per kg, and shows the original quote next to each figure. Example: Colombia apples "USD 2.00 per kg" against Jamaica apples "USD 5.00 per 3 lb bag" becomes 2.00 against 3.68 USD/kg, and the document still shows "USD 5.00 per 3 lb bag" as the original.

**What exists today (verified).**
- The prompt (`country_profile/claude_client.py`, `_build_competitiveness_prompt`) receives only: our source country's per-category average price and unit, the product count and up to 5 examples, plus the target's profile text. **It receives no target-country prices.** Claude is told it may web-search for target price benchmarks.
- The category averages are built in the browser (`competitivenessInputs.js`) from raw prices with no conversion: 14 of 122 La Mayorista and 60 of 172 Corabastos rows are not priced per kg, and the Colombia summary labels everything "COP". USA categories mix pack sizes (Produce CA mixes 19 lb containers, 6 oz cup flats and 1 lb container flats) under the first row's unit.
- The parser you describe already exists: the normalization module turns "USD 5 per 3 lb bag" into a price per kg using `parse_unit` and keeps the original text and price. Its price per kg is in the product's own currency; the conversion to USD happens in the Market Opportunities step with a stored exchange rate and date (`/api/market-opportunities/exchange-rate`).
- Market Opportunities already stores matched source/target rows with both original quotes and both USD/kg figures, the tax multiplier and a rating, but the competitiveness analysis does not read them.

**Proposed design.**
1. The backend builds the data pack (no browser): per category, for the source and for the target, the median USD/kg, the low–high range and how many products were priced, plus the matched-product gap from the comparison rows.
2. Each figure carries its original quote and the exchange rate and date used, for example "USD 5.00 per 3 lb bag → USD 3.68/kg (rate date shown)". Products that cannot be converted to kg are excluded from the statistics and counted ("22 of 130 not comparable").
3. Wholesale and retail are never mixed in one statistic; the pack states the level of each side.
4. Median and range, not averages, matching the app's rule of using one real recorded price and never a blended figure.
5. The numeric gap, and a landed-cost estimate where the tax multiplier (and freight, if a shipment is built) exists, are computed in code. Claude explains the numbers and applies the profile's rules; it no longer guesses the figures.
6. Categories are grouped by HS heading so the two countries line up (their own category names differ). This depends on T1.
7. The analysis document gets a numeric price table section; old analyses stay and are labelled as built with the previous method.

**Questions.**

| # | Question | Recommended | Your answer |
| --- | --- | --- | --- |
| T2.1 | Use our own target-country catalogs (Jamaica etc.) as the target side? When the target has no catalog, say "no local price data" and keep the profile-only analysis? | Yes | |
| T2.2 | Build the pack from the saved Market Opportunities rows, or from the catalogs directly? Saved rows are quick but can be stale; the catalogs are always current but redo the matching. | Saved rows when they are newer than the catalogs, otherwise recompute (after the engine is ported) | |
| T2.3 | Replace the averages with median + range + count? | Yes | |
| T2.4 | How many original quotes per category go into the document: lowest, median and highest of each side (3 per side), or more? | 3 per side | |
| T2.5 | Products that cannot be converted to kg (a dozen eggs with no known weight, bunches): exclude and count, or show in a separate "per unit" line? | Exclude and count | |
| T2.6 | Split statistics by wholesale and retail, or compare only like with like and show the rest as a note? | Compare like with like; mismatches shown as a note | |
| T2.7 | Include a landed-cost estimate now (source price × tax multiplier), and add freight per kg only when a shipment is built? | Tax now, freight when a shipment exists | |
| T2.8 | Who gives the verdict per category: a rule computed in code (for example "landed cost below target median = competitive") with Claude explaining, or Claude as today? | Code computes the numbers and the rating; Claude explains | |
| T2.9 | If the rule in T2.8 is wanted, which thresholds? For example competitive below −10% of target median, caveats within ±10%, not competitive above +10%. | Your numbers | |
| T2.10 | Keep Claude's web search in the build, or turn it off now that we pass our own target prices? | Keep it optional (off by default), fewer credits | |
| T2.11 | Group by HS heading (needs T1), or keep the sources' own category names and match them by hand? | HS heading, with the category name shown for reading | |
| T2.12 | Keep old analyses and mark them "built with the previous method"? | Yes (the data history keeps their versions too) | |
| T2.13 | May the Assistant call this build directly (no browser hand-off) once the data pack is on the backend? | Yes | |

**Depends on:** T1 (HS grouping), the Phase 1 collectors (English names, Colombia merge), and the exchange-rate function. Tax multipliers (TX-08) are needed for T2.7.

---

## Not yet detailed (to be turned into todos after T1 and T2)

- T3 — Product portfolio and category coverage on the backend (also gives SAM/TAM a server-side scope). **DONE 2026-11-10 (Phase 0 + 1, uncommitted until the next commit):** `backend/portfolio/`, `routers/portfolio.py`, parity fixtures in `backend/tests/fixtures/js_parity/`.
- T4 — Market Opportunities engine on the backend (matching, comparison rows, job, staleness fingerprint).
- T5 — Tax multiplier inputs on the backend (a country instead of a browser-built product list).
- T6 — Market Analysis status endpoint; shipment airfares.
- T7 — Payroll tax calculators (decide whether an agent ever needs them).
- Before any port: save the current JavaScript outputs as test fixtures (Phase 0), because there are no JavaScript tests today.
