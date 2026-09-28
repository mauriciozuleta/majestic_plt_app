# Variety Gallery Methodology

This document explains, in plain terms, how the **Variety Gallery** (Market Analysis ▸ Variety Gallery) anchors
every product to a real biological species, grows a persistent database of named varieties per country, and scores
cross-market variety matches — so a reader who didn't build this can tell, for any variety on screen, where its
data actually came from and how much to trust it.

**Hard constraint, honored throughout:** zero Claude/paid-API calls anywhere in this pipeline. Every other
AI-assisted feature in this app (translation fallback, HS classification, weight research, unit-weight estimates)
uses Claude/Haiku/Sonnet somewhere; this one deliberately does not. Every external call this subsystem makes is to
GBIF, Wikimedia Commons (both free and keyless) or LangSearch (free-tier, keyed, optional). Where a step would
normally reach for a model call — extracting structured traits from free-text search results, in particular — it
uses plain keyword matching instead, and says so.

---

## Part 1 — Scientific-name resolution (the species anchor)

### 1.1 Why GBIF alone can't do this

GBIF's Backbone Taxonomy (`api.gbif.org`) is free, keyless, and — for an actual scientific (binomial) name —
extremely reliable: `species/match?name=Solanum lycopersicum` returns an EXACT, SPECIES-rank, ACCEPTED match at 98%
confidence. The obvious design would be to hand it this app's own product/variety names directly and let it
resolve them. Confirmed live, that doesn't work:

- `name=tomato`, `name=chicken`, `name=onion`, `name=apple`, `name=peach`, `name=mango`, `name=cassava`,
  `name=chickpea`, `name=trout` — all return `matchType: NONE`. GBIF's own full-text `species/search` (with or
  without `qField=VERNACULAR`) is no better: real crop names are outranked by unrelated plant pathogens/viruses
  named after their host crop (searching "peach" ranks *Prunus andersonii* above the actual peach, *Prunus
  persica*).
- Worse, `name=papaya` returns an **EXACT** match — `"? papaya Olsson, 1922"`, an obscure DOUBTFUL fossil taxon
  under kingdom *Animalia* — a wrong, silently-plausible-looking answer if trusted at face value.

So GBIF is used here **only as a validator/confirmer** of a candidate scientific name this app already produced
some other way — never as the common-name discovery mechanism itself (`backend/species_gallery/gbif_client.py`).

### 1.2 How a candidate is actually found

`backend/species_gallery/resolver.py`, in priority order:

1. **A short curated list of well-known multi-word common names** (`VERNACULAR_PHRASES` in
   `commodity_dictionary.py`), checked against the product's own raw name first — needed because some HS
   descriptions bundle several congeneric species under one customs code (HS0302's trout heading literally reads
   "Trout (*Salmo trutta*, *Oncorhynchus mykiss*, ...)"), and only the raw product name says which one a specific
   product actually is ("Rainbow Trout" means *Oncorhynchus mykiss* specifically, not the first-listed species).
2. **An embedded Latin binomial inside the HS classification description itself.** This app's own HS classifier
   (`backend/comtrade/product_classification.py`, via `GET /api/product-hs-codes`) frequently already spells out
   the real scientific name for chapter-03 fish/seafood in parentheses. When present, the first listed binomial is
   taken as the best-effort anchor.
3. **A curated commodity-term dictionary** (`COMMODITY_TERMS`, ~130 entries), matched against the product's own HS
   classification description — a much cleaner signal than a raw variety name (e.g. "Vegetables; tomatoes, fresh or
   chilled" vs. "Chonto Tomato"). When an HS heading genuinely combines more than one commodity (e.g. HS0804.50
   covers guavas, mangoes **and** mangosteens together), the dictionary match is disambiguated by whichever term
   also appears in the product's own raw name — see 1.4 below for a real bug this caught.
4. **The same dictionary, against the raw product name** with qualifier words stripped ("local", "domestic",
   "grade", etc.) — used only when the product has no HS classification yet.
5. Otherwise: **unresolved.** Never a guess.

Every candidate produced by 1–4 is then passed to GBIF's `species/match` and only persisted (into the `Species`
table) if GBIF itself confirms it: matchType not `NONE`, rank one of SPECIES/SUBSPECIES/VARIETY/FORM, confidence
≥ 90, and status ACCEPTED or SYNONYM. A dictionary typo or a wrong embedded binomial still can't silently make it
through — this is a second, independent gate, not just trusting the dictionary.

**Why SYNONYM is accepted, not just ACCEPTED:** confirmed live that GBIF's backbone frequently files a real,
correct agricultural name as a SYNONYM of whichever name it currently prefers — *Citrus sinensis*, *Pisum sativum*,
*Litopenaeus vannamei*, and *Gallus gallus domesticus* (chicken) all confirm at 97–98% confidence but status
SYNONYM. Rejecting those would make the dictionary fail its own validation for entirely correct entries. DOUBTFUL
(papaya's wrong fossil-taxon match) is a different status and is deliberately excluded.

### 1.3 Real accuracy, measured against this app's own catalog

Run against every real classified product in `GET /api/product-hs-codes` (673 products with a real HS code, drawn
from `buildProductPortfolio()`'s actual cross-country catalog):

- **504 resolved (75%)** to a GBIF-confirmed species — spanning **67 distinct species**.
- **169 correctly refused (25%)** — margarine, cheese/curd/milk powder, hydrogenated lard, salted/smoked fish,
  tobacco, frogs' legs, generic "pepper of the genus piper or capsicum" (genuinely ambiguous between two genera,
  intentionally not guessed), and produce not yet in the dictionary (passion fruit, dragon fruit, granadilla) — a
  real coverage gap, not a wrong guess. Every dictionary entry itself re-validates against GBIF live with zero
  failures (`resolver.validate_dictionary()`).

### 1.4 A real bug this process caught, and the fix

The first pass resolved **"guava"** to *Mangifera indica* (mango) — wrong. Cause: HS0804.50's description
("Fruit, edible; guavas, mangoes and mangosteens, fresh or dried") matches both the `guavas` and `mangoes`
dictionary keys, and picking the longest match picked "mangoes". The fix checks whether either candidate's
scientific name has ANY dictionary key (singular or plural) present in the product's own raw name — "guava"
(singular) doesn't literal-string-match "guavas" (plural), so the first fix attempt (matching literal key strings)
still failed; the working fix checks by **scientific name**, not by literal key string. A second, related case
("Feijoa (pineapple guava)", a genuinely different genus, *Acca sellowiana*) needed its own `VERNACULAR_PHRASES`
entry since it isn't true guava at all, just named after it.

This is a standing limitation worth restating: a customs HS code that conflates several regionally distinct species
under one heading (common in chapter 03 fish/seafood, and in a handful of chapter 07/08 combined produce headings)
is a limitation of the classification itself, not something this resolver invents — the raw product name is the
best real signal available to disambiguate, and when it doesn't help, the result is a documented best-effort
default, never a black box.

---

## Part 2 — Species / Variety database

Two new tables (`backend/models.py`), picked up automatically by this repo's existing `Base.metadata.create_all` —
no migration:

- **`Species`** — one row per GBIF-confirmed scientific name. Carries `gbif_key`/`gbif_rank`/`kingdom`/`family` and
  which resolution path found it (`resolved_from`/`resolved_term`), for audit.
- **`Variety`** — one or more rows per species: `variety_name`, `source_country`, a schema-less
  `characteristics_json` blob (produce today: shape/firmness/primary_culinary_use/skin_flesh/ripening_type; a
  different category, e.g. meat/seafood, would add its own trait vocabulary here without a migration), two image
  tiers, and a `confidence_status` that starts `'auto-filled - unverified'` and only ever becomes `'confirmed'`
  through a human action.

### 2.1 Structural Tier A / Tier B separation

`image_tier_a` (broader, non-Commons sourcing, internal-only) and `image_tier_b` (Wikimedia Commons only, with
license/attribution) are stored side by side on the same row, but **no public response can return
`image_tier_a`** — not by convention, by construction. `schemas.VarietyPublicOut` has no field for it at all;
`schemas.VarietyAdminOut` (used by exactly one internal endpoint) is the only model that adds it. Confirmed live:
`GET /api/species-gallery/species/{name}/varieties` (the public read path) returns objects with no `image_tier_a`
key whatsoever, while `GET /api/species-gallery/admin/varieties/{id}` does carry it.

### 2.2 Cache-first, always

Every lookup checks the database first. `POST /api/species-gallery/varieties/bootstrap` returns an existing row
immediately (same `id`/`created_at` as the first call, confirmed live in well under 100ms — no network round trip)
if one already exists for the exact `(scientific_name, variety_name, source_country)` triple; bootstrap-specific
external calls (LangSearch, Commons) only ever run on a genuine miss, and only once, ever, per triple.

---

## Part 3 — Bootstrap on cache miss

Three independent sub-steps, each degrading gracefully on its own:

1. **One LangSearch web search** per bootstrap: `"{variety_name} {source_country} {species common name} variety
   characteristics"`. LangSearch (`langsearch.com`) is a real, free-tier web search API, but not keyless — it
   needs a real `LANGSEARCH_API_KEY`, wired exactly like this app's other optional keyed services
   (`COMTRADE_API_KEY`, `FRED_API_KEY`): unset means this step reports "not configured" and is skipped, never
   blocking anything else. **A real key is now configured** — confirmed live via `GET
   /api/species-gallery/config-status` returning `{"langsearch_configured": true}`, and a real bootstrap run now
   genuinely returns LangSearch-derived characteristics (e.g. bootstrapping "Tomate Chonto"/Colombia filled
   `shape: "oblong"` from a real search) rather than the earlier "LangSearch not configured" skip. (Earlier in this
   project's life no key was configured, and this section described that skip — kept only as history: unset still
   behaves exactly as described, degrading to a skip rather than blocking anything.)
2. **Tier A image** — best-effort, from the same LangSearch result set (a direct-looking image URL among the
   returned pages), internal-only. Not exercised in this environment (LangSearch unconfigured).
3. **Tier B image** — Wikimedia Commons, specifically, via `commons_client.py`. Confirmed live and working:
   bootstrapping "Roma Tomato" / United States returned a real photo
   (`upload.wikimedia.org/.../Roma_tomatoes_(509115549).jpg`) licensed CC BY-SA 2.0, attributed to "Simon Law from
   Montréal, QC, Canada". Two real fixes were needed to get here:
   - **User-Agent policy:** Commons silently 403s a request with no identifying User-Agent
     (`meta.wikimedia.org/wiki/User-Agent_policy`) — confirmed live before adding one.
   - **File-type filtering:** Commons' File namespace also holds PDFs, SVGs and other non-photo files. A plain
     text search for "Chonto Tomato Tomato" ranked an unrelated EU Official Journal PDF above any real photo —
     confirmed live. Fixed by restricting the search itself to `filetype:bitmap` and independently checking the
     fetched file's own reported MIME type starts with `image/` before ever accepting it (belt and suspenders,
     since this result can reach a public response).

**Characteristics extraction is plain keyword matching, not a model call** (`characteristics.py`) — deliberately,
per the $0 constraint. A trait vocabulary (round/oblong/..., firm/soft, fresh-eating/cooking/..., etc.) is scanned
against the search results' own text; a trait whose vocabulary doesn't appear anywhere is left `null` rather than
guessed. This is honest but limited: it will under-fill characteristics compared to what a model reading the same
text could infer — a known, accepted trade-off for staying at $0.

Every bootstrapped row is persisted as `confidence_status = 'auto-filled - unverified'`, `created_via =
'bootstrap_search'` — regardless of how much of steps 1–3 actually found something.

---

## Part 4 — Cross-market matching

Deterministic point-scoring (`matching.py`), never AI, never image similarity. One point per trait both sides have
a value for AND agree on; a trait missing on either side never scores for or against (so a sparse,
just-bootstrapped variety isn't penalized against a fixed denominator — the denominator itself is only the traits
both sides actually have). Ties (equal score) are broken by confirmed-over-unverified, then by earlier
`created_at` — confirmed live: matching an unverified Colombia tomato against two equally-unscored (empty
characteristics, since LangSearch is unconfigured here) US varieties correctly picked the one a human had already
confirmed over the one still auto-filled.

`POST /api/species-gallery/match` returns the full breakdown (`field_breakdown`) and every candidate's own score
(`all_candidates`), not just the winner — auditable by design.

### 4.1 Target-country discovery is now real (previously the real gap in this pipeline)

Earlier, a target country with nothing cached yet made `/match` stop dead: `"No variety ... is cached yet for
{target_country} — bootstrap one first."` There was no discovery mechanism anywhere in the codebase —
`bootstrap.py`'s `bootstrap_variety` only ever bootstraps a single variety it's ALREADY given the name of, so the
whole workflow was fully manual: "Find best match" only ever searched among whatever a human had already
bootstrapped one at a time.

This is now implemented (`backend/species_gallery/discovery.py`, wired into `match_variety` in
`routers/species_gallery.py`). On a genuine cache miss for `(scientific_name, target_country)`:

1. **One LangSearch web search**, `"common {common_name} varieties grown in {target_country}"`. The exact
   phrasing was chosen empirically, not assumed — several real query phrasings were run live against LangSearch
   for tomato/United States first. This one reliably surfaced seed-catalog / grower-reference pages
   (reimerseeds.com, gardenguides.com, ...) whose own text consistently spells a named variety as "`<Title Case
   Words> <common name>`" right next to the species' scientific name — a real result's text verbatim: `"72 days.
   Solanum lycopersicum. Open Pollinated. Bonny Best Tomato. ..."`, `"85 days. Solanum lycopersicum. Open
   Pollinated. Caribe Tomato. ..."`.
2. **Plain regex extraction** (no model call, same $0 discipline as `characteristics.py`) anchors on exactly that
   shape: 1-3 capitalized words immediately followed by the common name (singular or plural). A small blocklist
   filters out category/listing language that matches the same shape without being a real variety name (e.g.
   "Commercial Production Tomato", "Verticillium Wilt Resistant Tomatoes") — imperfect by design; a residual bad
   candidate still lands in the human review queue like everything else here, never presented as fact.
3. Results are capped (`discovery.MAX_DISCOVERY_CANDIDATES`, currently 6) and de-duplicated against variety names
   already cached for this exact `(scientific_name, target_country)` pair before a single bootstrap call runs — so
   a discovery run never re-bootstraps a variety a prior run already found, and one `/match` request can't trigger
   unbounded bootstrap calls.
4. Each surviving candidate name is bootstrapped via the **unchanged, existing** `bootstrap_variety` (the real
   LangSearch-characteristics + Wikimedia-Tier-B work per variety, exactly as Part 3 describes) and persisted the
   same way `/varieties/bootstrap` does — `confidence_status: 'auto-filled - unverified'`,
   `created_via: 'bootstrap_search'` — before scoring (Part 4's own unchanged logic) ever runs.

Confirmed live end-to-end, Colombia "Tomate Chonto" → United States: discovery ran the query `"common tomato
varieties grown in United States"`, extracted 2 candidate names after de-duplication/cap — "Caribe Tomato" and
"Carolina Gold Tomato" — bootstrapped both for real (Caribe: `firmness: firm`, `primary_culinary_use: salad`;
Carolina Gold: `shape: round`, `firmness: firm`; neither got a Wikimedia Commons Tier B image — a real, visible
coverage gap, not hidden), and both immediately appeared in `GET /api/species-gallery/review-queue` alongside the
Colombia-side entries. Scoring then picked "Caribe Tomato" — worth noting plainly: both candidates scored 0 (no
shared filled trait between either US variety and Chonto's own `shape: oblong` — Caribe had no `shape` value at
all, Carolina Gold's `shape: round` disagreed with Chonto's `oblong`), so the tie-break (`confirmed`-status equal,
then earliest `created_at`) — not a stronger trait match — is what actually decided the winner here. This is
accurate, real behavior of the unchanged Part 4 scoring/tie-break rule against genuinely sparse, just-bootstrapped
data, reported as-is rather than tuned after the fact.

The response now also carries `discovered_count`/`discovered_varieties`/`discovery_note` so a caller (and the
Gallery UI) can see exactly what a `/match` call bootstrapped on its own behalf, and the UI shows a real loading
notice for this case (`SpeciesGalleryPanel.jsx`) since a first-time discovery run does real web + image lookups
per candidate and can take up to roughly a minute — every repeat match for the same pair is instant again
afterward, served straight from the cache like everywhere else in this subsystem.

### 4.2 A real reported bug: the tie-break ignored `max_possible`, so "no data" could beat "disagreed"

`score_variety_pair` (Part 4) already computes `max_possible` — how many trait fields were even comparable between
two varieties (both sides had a value for it) — but until this fix, `find_best_match`'s tie-break never looked at
it: ties were broken purely by confirmed-over-unverified, then `created_at`. That let a candidate with **zero**
comparable data (0 score / 0 max_possible — nothing shared to compare at all) out-rank a candidate that actually
had one shared trait and disagreed on it (0 score / 1 max_possible), purely because it happened to be bootstrapped
first. Confirmed live exactly as reported: matching Colombia's "Tomate Chonto" against United States picked
"Caribe Tomato" (0/0) over "Carolina Gold Tomato" (0/1, disagreeing on `shape`) before this fix, by creation order
alone.

**Real data behind the fix** — recomputed live against every same-species variety pair actually in the `varieties`
table (re-run any time via `score_variety_pair` against real rows; grows as more varieties are bootstrapped):

```
5 real bootstrapped varieties (before this pass's own Open Food Facts testing added 2 more, see Part 8):
  distribution of PER-VARIETY field-fill counts: {0: 2, 1: 1, 2: 2}

The only species with more than one variety, Solanum lycopersicum (4 varieties: "Kidney" Tomato, Tomate Chonto,
Caribe Tomato, Carolina Gold Tomato), gives 6 real PAIRWISE comparisons — the number that actually matters for
max_possible, since max_possible is the INTERSECTION of both sides' filled fields, not either side's own count:

  "Kidney" Tomato vs Tomate Chonto:          max_possible=0
  "Kidney" Tomato vs Caribe Tomato:           max_possible=0
  "Kidney" Tomato vs Carolina Gold Tomato:    max_possible=0
  Tomate Chonto vs Caribe Tomato:             max_possible=0
  Tomate Chonto vs Carolina Gold Tomato:      max_possible=1  (disagreed on shape: oblong vs round)
  Caribe Tomato vs Carolina Gold Tomato:      max_possible=1  (agreed on firmness: firm)

Real pairwise max_possible distribution: {0: 4, 1: 2} — never higher in this sample (individual per-variety
field-fill counts topped out at 2, and the pairwise intersection can never exceed the smaller side's own count).
```

This directly falsifies a threshold of `max_possible >= 2`: it would have rejected **every** real comparison this
app had ever produced (0 of 6) — the data doesn't justify it. `max_possible >= 1` keeps exactly the 2 of 6 pairs
that had a genuine shared, comparable trait (one real agreement, one real disagreement) while excluding the 4
pairs with literally nothing in common — precisely the bug this threshold targets, without being so strict it
excludes nearly everything given how sparse real LangSearch-derived characteristics currently are.

**`MIN_COMPARABLE_FIELDS = 1`** (`species_gallery/matching.py`) is the threshold implemented. It is not a hard
filter (a candidate below it can still win if it's genuinely the only one scored — this subsystem always prefers
showing a best-effort, auditable answer over refusing to answer at all) — it's inserted into the tie-break sort
key, ahead of confirmed-status and `created_at`: `sort(key=lambda row: (-score, max_possible < 1, -max_possible,
confidence_status != 'confirmed', created_at))`. Confirmed live after the fix: the same Tomate Chonto → United
States match now correctly picks Carolina Gold Tomato (max_possible=1, a real comparison) over Caribe Tomato
(max_possible=0, nothing shared) — `all_candidates` in the response still shows both scores for transparency.

After this pass's own Open Food Facts bootstrap testing (Part 8) added 2 more varieties (Red Cargamanto Beans /
Phaseolus vulgaris, Oryzica Rice / Oryza sativa), n grew to 7 — but neither new variety shares a species with an
existing one, so the real pairwise distribution above is unchanged (still {0: 4, 1: 2} across the same 6 tomato
pairs). The threshold will be worth re-checking again once more than one variety exists for the same
Open-Food-Facts-sourced species.

---

## Part 5 — Review queue

`Variety.confidence_status` **is** the review queue — `GET /api/species-gallery/review-queue` lists every row still
`'auto-filled - unverified'`; `POST .../{id}/confirm` and `DELETE .../{id}` flip or remove it. This is the same
queryable-pending / confirm / reject shape `price_comparison.py`'s translation-suggestions endpoints already use,
applied to a new table with a very different row shape (characteristics, two image tiers) rather than shoehorned
into that same table. No AI/paid-API call anywhere in this confirmation flow.

The Gallery UI shows an unverified variety with the same blue "estimated, not yet confirmed" badge SAM/Market
Opportunities already use (`.market-analysis__estimated-badge`) — a confirmed variety gets no badge at all, same
precedent as SAM Overview's own confirmed-figures convention, so a fresh bootstrap can never look as trustworthy as
a human-confirmed row.

---

## Part 6 — Cost guardrail

Before any real bulk bootstrap run, `POST /api/species-gallery/cost-guardrail` resolves species (free, GBIF-backed)
for a batch of products and counts how many `(scientific_name, variety_name, country)` triples are missing from the
database — **without** calling LangSearch or Commons for any of them.

Run once, for real, against this app's actual catalog (all 773 distinct product names from
`GET /api/product-hs-codes`, cross-referenced with which countries each is actually sourced in): **532 combinations
would need a genuine bootstrap**, anchored to **67 distinct species**, with 247 product names correctly unresolved
(no dictionary/GBIF anchor, skipped rather than guessed). Country attribution for this count used each product's
real source (USA sourcing snapshot and custom Settings sources are already English-tagged with their own country;
any remaining name was attributed to Colombia, the only other real source) — a product genuinely sold in more than
one of those specific sources would be undercounted rather than overcounted, so 532 is a conservative floor, not an
inflated estimate.

---

## Part 7 — What was not built, and why

**Optional classical-CV secondary signal (spec's own "build only if time permits"):** not built in this pass.
Reason: real, honest trait-based matching (Part 4) and the full resolve → bootstrap → review → match pipeline
already needed the available time to build and verify properly end-to-end against live external services; adding
OpenCV color-histogram/contour comparison on top would need `opencv-python` added to `requirements.txt` (not
currently a dependency) and its own verification pass, which didn't fit. If added later, it must stay a secondary,
clearly-labeled signal shown alongside the trait-match score — never replacing or feeding into it.

---

## Part 8 — Open Food Facts: a second bootstrap source, packaged/branded goods only

Fresh produce/meat/seafood/dairy stay on the GBIF + LangSearch + Wikimedia pipeline (Parts 1–3) exactly as built —
unchanged. This is a **separate, additional** source, scoped strictly to packaged/branded goods (rice, oil, sugar,
chocolate, panela, beans, ...), gated on category so it can never fire for the wrong kind of product.

### 8.1 Scope and the hook point

Routed on: Colombia's `granos_procesados` category or USA's `Grains (Export)` category (this app's own
`CANONICAL_CATEGORIES` — `priceComparisonData.js` — and `backend/usa_sources/grains.py`'s raw category string).
Confirmed live by reading the real code path, not assumed: `buildProductPortfolio()`
(`src/services/productPortfolio.js`) only exposes a product's already-resolved **display label** by the time it
reaches the Gallery (`categoryInfo()`/`CATEGORY_CODES` convert `granos_procesados` → `"Grains & Processed"`; USA's
`"Grains (Export)"` happens to map to itself) — the raw taxonomy key doesn't survive that far. `SpeciesGalleryPanel.jsx`
checks a selected product's own `category` against those two labels and sends the backend a clean, explicit
`category: 'packaged_goods'` (never a raw frontend label leaking into the API) on both `bootstrapVariety` and
`matchVariety` calls; `backend/species_gallery/openfoodfacts_client.PACKAGED_GOODS_CATEGORIES` also accepts the
raw `'granos_procesados'`/`'Grains & Processed'`/`'Grains (Export)'` strings directly, for robustness against a
future caller passing them straight through. `bootstrap_variety` (`bootstrap.py`) branches on this at its very top
— a packaged-goods category routes to `_bootstrap_from_openfoodfacts` entirely instead of steps 1–3, never both.

### 8.2 The endpoint: a real, live-discovered gotcha, re-verified

The originally-specified endpoint, `GET https://world.openfoodfacts.org/api/v2/search`, was re-tested live in this
pass (not assumed broken or fixed either way) and found genuinely **flaky for an anonymous/keyless caller**: one
real request (`categories_tags_en=rice&page_size=3`) returned a clean 200 with real data; a near-identical repeat
request minutes later returned a real 503 — Open Food Facts' own "Page temporarily unavailable... not available
to anonymous users" HTML error page, not a client-side parameter issue. Not safe as the primary path for a
keyless, $0 client that must degrade honestly.

**The endpoint actually used**: `GET https://search.openfoodfacts.org/search?q=<term>&page_size=<n>` — Open Food
Facts' newer, separate Elasticsearch-backed search microservice. Confirmed live, repeatedly, real 200s with real
structured hits carrying `code`, `brands` (list), `quantity` (e.g. `"2 lbs"`), `categories_tags`, `countries_tags`,
`image_front_url`/`image_url`, and `product_name` directly on each hit — no extra per-barcode lookup needed just
to get a usable image. `GET .../api/v2/product/{barcode}.json` was also re-confirmed live and reliable for a
**known** barcode (a real "Supreme Rice" 2 lbs product) — not used here, since these Colombia/USA products won't
have a known barcode to look up by, but it's why product-lookup (15 req/min) and search (10 req/min) carry
separate published rate limits, both enforced independently in `openfoodfacts_client.py` via a real sliding-window
limiter that **sleeps** to stay under the limit — never a fire-then-catch-429 retry.

Both endpoints are free and require no API key — $0 maintained.

### 8.3 A real false-positive this pass caught, and the fix

An early version matched purely on any query word (>2 chars) appearing anywhere in a hit's product name/brand.
Confirmed live this was a real problem, not hypothetical: searching **"Regular Rice"** (a Colombian
wholesale-market generic commodity name, no real brand behind it) matched a completely unrelated hit whose own
`brands` field is literally `"Regular"` — a JIK-brand bleach product, matched purely because both query words
happen to be individually common. Fixed with `_GENERIC_COMMODITY_WORDS` (`openfoodfacts_client.py`): a query must
contain at least one **distinctive** token — not in that generic/descriptor list (rice, oil, sugar, beans, corn,
regular, packaged, vegetable, bottle, pound, export, bulk, yellow, white, ...) — before any hit is ever accepted;
a hit is only accepted if that distinctive token itself appears in the hit's own product name/brand/category text.
A query with **no** distinctive token at all (e.g. a plain, unbranded wholesale-market entry) returns `None`
immediately, without even calling the API — an honest "nothing specific enough to search by", never a
coincidental generic-word accept.

### 8.4 Cache-first, image tiering, and "no match → leave empty"

Cache-first discipline is unchanged and inherited for free: the router already checks the `varieties` table for
the exact `(scientific_name, variety_name, source_country)` triple before ever calling `bootstrap_variety` at all
— Open Food Facts is never queried for an already-persisted triple, exactly like LangSearch/Commons.

When a genuine match is found, its image is stored as **`image_tier_a`, never `image_tier_b`**: `image_tier_b` is
structurally Wikimedia-Commons-only with verified, reusable per-image license metadata (Part 2.1); an Open Food
Facts product photo doesn't carry that same per-image verified-license guarantee, so it stays internal-only — the
same tier LangSearch's own best-effort image already used. Characteristics stored: `package_size` (Open Food
Facts' own `quantity`), `brand`, `off_category` — real, structured fields from Open Food Facts itself, not
keyword-extracted from free text like `characteristics.py` does for produce. Every row is still persisted
`confidence_status='auto-filled - unverified'`, landing in the same review queue as everything else, whether or
not a match was found — a genuine "no match" still gets a row (with empty `characteristics_json`, a null image,
and an honest `bootstrap_note` saying so), never silently skipped.

**No match → left empty, never a generic search image substituted** — enforced structurally: `search_product`
returns `None` on no genuine match, and `_bootstrap_from_openfoodfacts` never falls back to any other image
source for a packaged-goods variety.

### 8.5 Real coverage test — 17 real Granos y Procesados/Grains (Export) products

Pulled from the real, live-cached product catalog (`price_comparison_snapshots` for `la_mayorista`/`corabastos`/
`usa_grains`, run through this app's own real `productTranslations.js` English names — the same strings
`bootstrap_variety` actually receives as `variety_name`), not invented:

| Product (real, translated) | Country | Result |
|---|---|---|
| Regular Rice | Colombia | No distinctive term — skipped, no API call |
| Oryzica Rice | Colombia | Searched — no match |
| Vegetable Oil (500ml bottle) | Colombia | No distinctive term — skipped |
| Packaged Sugar | Colombia | No distinctive term — skipped |
| Panela | Colombia | No distinctive term — skipped |
| Panela, Pastusa style | Colombia | Searched — no match |
| Panela, Valluna style | Colombia | Searched — no match |
| Panela, Regional style | Colombia | Searched — no match |
| **Red Cargamanto Beans** | Colombia | **Matched** — brand "Goya", barcode 41331025065 |
| Calima Beans (Nima brand) | Colombia | Searched — no match |
| "Radical" Beans | Colombia | Searched — no match |
| Hard Yellow Corn (Rocol variety) | Colombia | Searched — no match |
| "Crystal" Soup Rice | Colombia | Searched — no match |
| Drinking Chocolate (by the pound) | Colombia | No distinctive term — skipped |
| Chickpeas | Colombia | No distinctive term — skipped |
| US #2 Yellow Corn | United States | No distinctive term — skipped |
| US #1 Soybeans | United States | No distinctive term — skipped |

**Result: 1 genuine match out of 9 real live searches actually attempted** (1/17 of the full real set; the other
8 of 17 had no distinctive brand/name at all — plain wholesale-market generic commodity entries — and were
correctly never even searched). This is the expected, honest shape of this source, exactly per its own scope
warning: Open Food Facts skews European/North American brand coverage, and small regional Colombian brands
("Oryzica", "Rocol", "Nima", "Radical" — all real brand/variety names in this app's own catalog) genuinely aren't
in it. Confirmed end-to-end live through the real API (`POST /api/species-gallery/varieties/bootstrap`,
`category: 'packaged_goods'`): both the real match (Red Cargamanto Beans → Goya) and a real no-match (Oryzica
Rice) persist correctly, a repeat call for the same triple returns the identical cached row (no re-query), and
both land in `GET /api/species-gallery/review-queue` like every other bootstrap.

**Not yet a bulk-run-ready source** — per its own spec, this coverage number (1/9 real searches, 1/17 of the full
tested set) is reported honestly as a small first test, not treated as reliable for the whole `granos_procesados`/
`Grains (Export)` category without a larger real run first.

---

## Part 9 — A real Wikimedia Commons image-relevance bug, root-caused and fixed

A real, live row already in the `varieties` table — `"Grey" Orange` (Colombia, `Citrus sinensis`) — had bootstrapped
`File:Aleksander_Gierymski_-_Jewish_woman_selling_oranges_-_Google_Art_Project.jpg` as its Tier B image: an 1880s
painting, not a photo of the fruit. Investigated live, not guessed:

- **`filetype:bitmap` isn't a photo-vs-art filter** — it only restricts container format (raster vs. vector); a
  scanned painting saved as JPEG still matches it.
- **The file's own MIME type (`image/jpeg`) is identical to a real photo's** — also not a usable signal alone.
- **The file's real Commons categories are unambiguous**, confirmed live via
  `action=query&titles=<file>&prop=categories`: `Category:Artworks digital representation of 2D work`,
  `Category:Featured pictures of paintings from Poland`, `Category:Google Art Project works by Aleksander
  Gierymski`, `Category:PD-Art (PD-old-auto-expired)`, etc.

### 9.1 The fix, and three more real false positives found verifying it

`backend/species_gallery/commons_client.py` now fetches each search candidate's real categories
(`action=query&titles=<file>&prop=categories&cllimit=50`) and rejects it against `_ART_EXCLUSION_KEYWORDS` — built
from real category text seen across several more real Commons food-image searches in this pass (`painting`,
`artwork`, `drawing`, `illustration`, `engraving`, `sketch`, `google art project`, `digital representation of 2d
work`, `museum collection`, `still life`, `watercolor`, `lithograph`, `woodcut`, `etching`, `fresco`, `tapestry`,
`mural`, `pd-art`, `clip art`, `stamp`/`stamps`, `art museum`/`gallery`, ...) — not the original brief's list taken
as final. **`portrait` was deliberately left out**: confirmed live that `Category:Portrait orientation` (a photo
ASPECT-RATIO tag, one of Commons' most common categories on completely ordinary photos) would false-positive on a
bare substring match; a real art-portrait category is already caught by `painting`/`artwork`/`google art project`.

Re-verifying this fix live against the real `"Grey" Orange` case surfaced three MORE real false-positive shapes,
each root-caused and fixed in turn rather than papered over:

1. **A real photograph of an unrelated animal** (`Front_view_of_a_resting_Canis_lupus_ssp.jpg` — a grey wolf) won
   next, once the painting was excluded — real license, real photo, zero art categories, just irrelevant. Fixed by
   reusing this codebase's own existing generic-vs-distinctive-token pattern (`openfoodfacts_client.py`'s
   `_GENERIC_COMMODITY_WORDS`/`_distinctive_terms`, Part 8.3 above): a candidate must have a real anchor term
   (from the variety name/species label, minus generic color/quality descriptors like "grey") appearing in its own
   title/categories before it's accepted at all.
2. **A real "dominant colors" Commons category** (`Category:Black, cream, gray, green, orange, red, white` — the
   wolf's own coat/eye colors) still matched the anchor term "orange" purely because Commons tags photos with their
   dominant on-screen colors, comma-separated. Fixed by detecting and stripping this specific category shape
   (`_is_color_palette_category`) before anchor-matching runs.
3. **"orange" the fruit collides with "orange" the color adjective in open-ended natural language** — a real
   landscape photo tagged `Category:Orange sky in North Rhine-Westphalia` (a sunset) still matched. An open-ended
   blacklist of disambiguating qualifier words (river, free state, colour, a drag-strip nickname, ...) caught
   several real cases but is inherently unbounded. Replaced with a bounded, POSITIVE requirement instead: a
   known-ambiguous anchor word (`_AMBIGUOUS_ANCHOR_WORDS = {'orange'}` today, grown only from a real case like this
   one) only counts as a match in a fragment that ALSO carries a real produce/fruit-context word (`fruit`, `citrus`,
   `tree`, `orchard`, `oranges`, ...) — a bare, unqualified category like Commons' own real `Category:Oranges` still
   validates normally.

The candidate pool was also widened from 5 to 10 results (`srlimit`) — confirmed live that Commons' own relevance
ordering for this genuinely ambiguous query re-shuffles slightly between otherwise-identical live requests, pushing
a real, relevant photo just outside a 5-result window on one call and back inside it on the next.

**Query-side bias, tested and reported honestly**: biasing the search query toward species context
(`f'{variety_name} {species_label} fruit photograph'`) was tried live against every real variety already in this
app's own database (`"Grey" Orange`/`Citrus sinensis`, `"Kidney" Tomato`/`Solanum lycopersicum`, Roma Tomato, Tomate
Chonto, Caribe Tomato — each with their real scientific binomial) — confirmed live it returns **zero raw search
hits** in every one of those real cases; CirrusSearch's relevance engine doesn't degrade to a worse-ranked result
when too many required-ish terms are combined, it returns nothing. `find_variety_image` still tries this biased
query first, then falls back to the original, narrower query when the biased one returns nothing — which is what
actually still returns candidates in every real case tested. Reported plainly, matching this subsystem's own
"confirmed live, here's what actually works" style: **the category-exclusion + anchor-term gates are doing
effectively all of the real preventive work right now**, not the query bias.

### 9.2 Re-verified against the real case, and a real audit of every existing image

Re-running the fixed `find_variety_image("\"Grey\" Orange", "Citrus sinensis")` live, repeatedly: the Gierymski
painting is correctly excluded every time, and the result now consistently lands on
`File:Bergamot_-_Sour_Orange_-_January_2013.jpg` — CC BY 2.0, real photographer attribution, real category
`Category:Cross sections of bergamot oranges` — a genuine photo of a citrus fruit. The DB row (`"Grey" Orange`,
Colombia) was corrected to this image; its `bootstrap_note` records what the original image was and why it was
replaced.

**Full audit of every real row in `varieties` with a non-null `image_tier_b`** (only two existed): re-checked each
one's real Commons categories against the new filter.

| Variety | Image | Real categories | Verdict |
|---|---|---|---|
| `"Kidney" Tomato` (Colombia) | `Rajčica.JPG` | `Solanum lycopersicum (cultivars)`, `Tomatoes on black background`, `Mutations in tomatoes`, ... | **Genuinely fine** — a real tomato photo, no art/irrelevance markers. Left unchanged. |
| `"Grey" Orange` (Colombia) | Gierymski painting | `Artworks digital representation of 2D work`, `Featured pictures of paintings from Poland`, `PD-Art`, ... | **Wrong** — an artwork, not a photo. Corrected (see 9.1 above). |

**Result: 1 of 2 existing Tier B images was wrong; it has been corrected. The other was already genuinely
correct.** No image was silently re-bootstrapped without this being recorded here.

---

## Part 10 — UI restructure: a guided, stepped flow (`SpeciesGalleryPanel.jsx`)

The previous layout was a flat "pick any product, see every variety in one list" panel. It's now a guided sequence
matching how this feature is actually meant to be used — none of the underlying matching/bootstrap/caching/
threshold logic changed, only how it's presented:

1. **Origin country** — reuses the same "has a real Country Product Portfolio" country pool
   `MarketOpportunitiesPanel.jsx`'s own Source dropdown already draws from (`fetchProductSources()`,
   `product_count > 0`), not a new list.
2. **Products in that country, grouped by species/HS code** — reuses `resolveSpecies()` (already used elsewhere in
   this panel) and `fetchProductHsCodes()` (the same cache Available Categories/SAM/TAM/Market Opportunities already
   read) to collapse every portfolio product name that resolves to the same species into one entry — e.g. Colombia's
   ten distinct tomato product names (`"Kidney" Tomato`, `Tomate Chonto`, ...) now show as one `"Kidney" Tomato (HS
   070200)` group (labeled by the resolved common name when one exists, otherwise the first product name
   alphabetically), not ten separate top-level rows. Supports search/filter by product name or HS code. A product
   that doesn't resolve to a real species simply has no group — the same "never guessed" discipline Part 1 already
   applies.
3. **Select a group** (e.g. the Tomato group).
4. **Varieties of that species already cached for the origin country** — existing `Variety` rows, filtered to
   `source_country === originCountry`, re-presented nested under the selected group instead of flattened. A
   "bootstrap a new variety" affordance stays here (this pass didn't remove any existing capability, just relocated
   it to its natural home) for when nothing is cached yet.
5. **Select a variety** — its card (Tier B image, species anchor, characteristics in plain humanized language, e.g.
   "Shape: oblong") renders using the same `VarietyCard` rendering the old layout already had, just relocated.
6. **Destination country** — a second country selector (reuses `fetchReferenceCountries()`, the broad reference-country
   list, since a match's own discovery step can search any country, not just ones with their own portfolio here),
   appearing only once a variety is selected.
7. **Automatic match** — picking the destination country IS the confirming action (no extra button): it immediately
   calls the existing, unchanged `/api/species-gallery/match` (auto-discovery + the already-fixed
   `MIN_COMPARABLE_FIELDS` threshold) and shows the source/target cards side by side plus the score breakdown
   rendered as plain sentences (e.g. *"Shape: they disagree — the source variety is 'oblong', the target is
   'round'."*) instead of only a raw table. A genuine "no reliable match" result (`best_match: null`) shows the
   backend's own message plainly, never an empty/broken-looking state.

**Confirmed live end-to-end (Playwright)**: Colombia → "Kidney" Tomato group (HS 070200, `Solanum lycopersicum`, 10
underlying product names) → its 2 cached varieties → selected `"Kidney" Tomato` → destination United States →
matched against `Caribe Tomato` (score 0/0, "neither variety has any characteristics on file to compare yet" — an
honest empty-overlap result, not a wrong one). A second run selecting `Tomate Chonto` instead reproduced this
methodology doc's own Part 4.2 real case exactly: matched against `Carolina Gold Tomato`, score 0/1, rendered as
*"Shape: they disagree — the source variety is 'oblong', the target is 'round'."*

**Review Queue** moved to its own tab (`Review Queue (N)`), fully separate from the main step-by-step flow — same
list/confirm/reject functionality as before, confirmed still working live (all 7 real DB rows listed, confirm/reject
buttons present) from its new location.
