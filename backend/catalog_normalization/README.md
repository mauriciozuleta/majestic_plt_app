# Catalog normalization module

One place that turns any catalog row — `(product name, unit text, price)` — into a **price per kg**, and converts **both ways** between a count of items and
a weight. Built as a separate module first (nothing in the app calls it yet); the plan is to run every downloaded catalog through it before the app uses it.

| File | What it does |
| --- | --- |
| `units.py` | Reads the unit text deterministically: `weight` (stated: "3 lb bag", "per lb", "6 x 500 g", "flats 8 1-lb containers", "11-12 oz", "bulto de 50 kilos"), `count` ("each", "per bunch", "4 count mesh bags", "dozen", "100's", "box of 18"), `volume`, or `unknown`. A bare "kg"/"g" unit takes the pack weight written in the name ("Green Peas 340G"). |
| `researcher.py` | Web research (Anthropic `web_search`, same key/model conventions as `weight_research/`) of the weight of ONE item of a product: typical, min, max, and a standard wholesale carton when one exists. Batched (12 products per call), JSON answer, sources and confidence kept. A product with no reliable source comes back empty with the reason. |
| `translate.py` | Spanish -> English product names for the Colombian catalogs, the ONE translation used by the whole app: user overrides (table `product_translation_overrides`) > the curated dictionary `data/product_translations_es_en.json` (279 entries; the frontend's `productTranslations.js` imports the same file) > fuzzy match (Levenshtein >= 0.85). A name that misses all three stays Spanish and is flagged. Colombian products are normalized, researched and cached under their English names; item weights researched earlier under Spanish names are copied to the English key (`migrate_weights_to_english`). |
| `reference.py` | Item weights from PUBLISHED data, no AI and no network: USDA's Standard Reference table (`data/usda_sr28_produce.json`, 1,713 fruit/vegetable/herb/legume foods with household weights and refuse %; rebuilt with `build_usda_reference.py`) read through ~65 hand-curated rules (`data/usda_item_rules.json`): product name -> one USDA food + one measure. `edible` rules divide by (1 - refuse%) to get the weight as bought (1 pineapple: 905 g edible, 49% refuse -> 1,775 g); heads/bunches are taken as sold. No rule, no answer (no fuzzy matching). |
| `store.py` | `MemoryStore` (tests) and `DbStore` (table `catalog_item_weights`, model `CatalogItemWeight`): each (product, count unit) is researched once for the whole app. |
| `service.py` | `normalize_price` (one row), `normalize_catalog` (a whole catalog: researches what is missing, then converts every row), `items_in_weight` (a 10 kg box -> how many items), `weight_of_items` (8 items -> kg). |
| `evaluate.py` | Live check: `python -m backend.catalog_normalization.evaluate` (add `--skip-web` for the deterministic half). |

## Rules

* A weight written in the data is used as written (`stated_weight`).
* Official fixed factors are used as such and labelled `official_factor`: USDA egg dozen weights (size from the name, "large" assumed and flagged when absent),
  USDA bushel test weights (corn 56 lb, soybeans 60, wheat 60).
* Anything that needs the weight of an item is answered in this order: the exact row's whole-pack weight (`priced_unit`), **USDA's published table** (`reference_item_weight`, free, no AI),
  then the web-researched store (`researched_item_weight`), each with its confidence and sources. Without any of them the row says `needs_research`; it is never guessed. Volumes (liters, gallons) and unknown units are `unconvertible` — a density is not guessed.
* A count pack ("4 count bag") = count x the weight of one item; a bunch/head/sleeve uses the researched weight of that unit.

## Test results (2026-11-07)

* `python -m unittest backend.tests.test_catalog_normalization` — 14 tests (parser cases built from real unit strings of the Colombia, USA, Jamaica, Saint Lucia and
  Trinidad catalogs; both conversion directions; research called once per distinct product).
* Live, part A — 10 products priced by a stated weight: 10/10 equal to the hand-computed $/kg.
* Live, part B — 10 products priced by the unit (pineapple, Hass avocado 4-count bag, mango, watermelon, cantaloupe, iceberg lettuce, cilantro bunch, cauliflower,
  slicing cucumber, bell pepper 3-count bag): 10/10 researched item weights inside the plausible range, each with a note and sources. Examples: pineapple about
  1.4 kg (8 weigh about 11 kg; a 10 kg box holds about 7); Hass avocado about 170 g (a 10 kg box holds about 59).

The "plausible ranges" in `evaluate.py` are the reviewer's general produce knowledge, not an independent ground truth: the real check is the source each
note cites.

## Wiring into the app (2026-11-07)

* **At save time:** `snapshot_store.save_snapshot` runs `catalog.annotate_with_db` for every product catalog (`la_mayorista`, `corabastos`, `usa_*`, `custom_*`): each product
  gets a `norm` block next to its raw fields (price per kg, pack weight, items per pack, method, confidence, note, sources). Only the deterministic part and the
  already-researched weights run here — never the web. Raw fields are untouched.
* **API** (`routers/catalog_normalization.py`): `GET /api/catalog-normalization/status`, `POST .../reannotate`, `POST .../research` (`{limit, dry_run}`, a background
  job; Colombia's catalogs first; fresh-food products only: HS chapters 02-04, 06-10, 12, or no HS yet with an explicit unit, never packaged goods), `GET .../weights`,
  `GET .../convert`, `GET .../items` (both directions).
* **Frontend:** `services/catalogNorm.js`; the Market Opportunities collectors, the product portfolio, and the Colombia / USA / custom-source tables use `norm.price_per_kg`
  and fall back to the legacy conversions (`unitConversion.js`, `genericUnitConversion.js`) only where the module produced nothing. The legacy code is still there,
  to be removed once the per-row override and weight-research screens are moved to the module's store.
* **Parity check** (legacy vs module, 7,351 stored products): 3,472 identical, 476 converted only by the module, 0 converted only by the legacy code, 88 different —
  all explained: 49 names like "Bacon 200 gr" (the legacy read it as 1 g: 13,590 $/kg, now 67.95), 14 pack multipliers ("4x125g"), 24 averaged ranges ("Avg 6-7LBS").
* **USDA My Market News (MARS):** `usa_sources/mars.py` (key `USDA_MYMARKETNEWS_API_KEY`, always a date window) and `usa_sources/retail_produce.py` (report FVWRETAIL:
  latest week, national, conventional fruit and vegetables). Stored as source `usa_retail_produce` (default price level: retail): the packs are kept as `detail` rows,
  the module converts each pack, and ONE row per commodity is rebuilt with the store-count weighted average USD/kg (60 commodities today; 65 packs wait for item weights).
  Endpoint `GET /market-analysis/usa/retail-produce`.

## Corabastos packages (found while wiring the translator)

Corabastos prints `<PRESENTATION> (N per package)` and a `Precio Unidad` = Precio Extra / N. For CAJA, CAJA DE MADERA, CANASTILLA, BOLSA (produce boxes, baskets, bags) N is the package's kilograms and the price is **already per kg**: checked against La Mayorista's per-kg prices for the same products (banana, mango, pineapple, granadilla, lulo, tree tomato, platano, yuca, papaya), median ratio 1.1; read as a price per single piece a banana would cost 15,553 COP/kg against La Mayorista's 2,000. The legacy frontend rule (price per single piece, weight researched) was wrong for these 22 rows; the module treats them as per kg. ATADO/ROLLO are priced per bunch, DOCENA per piece (research needed: 10 rows).

## USDA reference layer (2026-11-09)

Added so the research needs no AI or credit for most produce. Coverage on the stored catalogs: of the 65 retail packs priced per unit, USDA answers 53 (10 left: cilantro, parsley,
collards, garlic, leeks, mustard/turnip greens, green onions, radishes); Corabastos' unit-priced list needs 5 instead of 10; the research queue went from 884 to 624 products.
Checks: `test_reference_weights.py` (8); the PDF test (`evaluate_retail_pdf.py`) 10/10 with 9 of the 10 unit-priced packs answered by USDA; and an independent cross-check on 7 commodities that
MARS lists both "per lb" and "each": the USDA weights land closer to the per-pound price than the AI-researched ones (mean |log ratio| 0.52 vs 0.66; 0 = identical). The check is noisy on
purpose-built grounds (a price per piece is often not a price per pound): across all 19 comparable commodities the median ratio is 1.26 and 6 are within 25%, so every USDA-based
row is flagged "USDA" (medium confidence) in the tables and in Market Opportunities. Known weak spots: watermelon (8.7 kg as bought is heavy for a retail seedless melon), papaya
(`fruit, large` for the Colombian types), lemons/limes/avocados sold singly at a premium.

## The "need data" form (2026-11-09)

Market Analysis ▸ Country Information ▸ Country Product Portfolio shows a red pill ("N need data") for every country whose unit-priced catalog rows (each, per bunch, a counted bag) still have
no weight of one item. It opens `MissingDataModal.jsx`: one row per product with blank weight fields (and an optional typical range) to type, an **AI Search** button that researches the blanks
on the web (`POST /suggest`, 12 products per call, nothing saved), a check on every value (`validation.py`: plausible range per unit, USDA's published weight, and the price per kg it produces
against the same product listed with a weight, compared only inside one currency group) and a **Save to DB** button that appears once a valid value exists (`POST /weights`: saves, converts every
catalog again, updates the pills). A value typed by a person (confidence `user`) wins over USDA and over research. Endpoints: `GET /missing-summary`, `GET /missing?country=`, `POST /validate`,
`POST /suggest`, `POST /weights`. Tests: `test_missing_data_form.py` (12: validation rules, the four endpoints on an in-memory database); the form was also driven in the running app.

## Refactor status (2026-11-07): the module is the only conversion in the app

* **Removed:** the frontend's per-country conversions (`genericUnitConversion.js`, the Colombia/USA functions of `unitConversion.js`), the Haiku count-to-weight path
  (`countWeightConversion.js`, `services/unitWeightEstimates.js`, router + package `unit_weight_estimates`) and the old pack-weight research (`services/weightResearch.js`,
  router + package `weight_research`). `unitConversion.js` keeps only the user's manual price/weight overrides and row signatures. The old tables
  (`product_unit_weight_estimates`, `product_weight_research`) are left in the database; their 70 usable estimates were copied into the module as whole-pack weights
  (`priced_unit`).
* **Everything reads `norm`:** the Colombia, USA and custom-source tables, the product portfolio, Market Opportunities (which asks the module to research the weight of one item
  only for products of MATCHED pairs, then converts those rows again), the exports (they take the tables' values). The three "Research Missing Weights" buttons became
  "Research item weights (N)" and run the module's research job.
* **Verified:** 146 backend tests; parity against the old conversions (0 lost); the PDF test (`evaluate_retail_pdf.py`): 10/10 packs over a pound, 10/10 non-weight packs; all four
  table views and the research button exercised in the running app.

## Not done yet

* **Live web research has not run since the wiring:** the Anthropic account's credit balance is too low (2026-11-07), so the research job, and Market Opportunities' use of it,
  were only exercised up to the API's refusal (the error reaches the user readably). 884 products wait for it.
* Volumes (milk, oil, drinks) are not converted: a density per product would have to be researched.
* Price levels: the retail source is flagged retail, but no retail-to-wholesale adjustment is applied.
