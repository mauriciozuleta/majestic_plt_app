# Catalog normalization module

One place that turns any catalog row — `(product name, unit text, price)` — into a **price per kg**, and converts **both ways** between a count of items and
a weight. Built as a separate module first (nothing in the app calls it yet); the plan is to run every downloaded catalog through it before the app uses it.

| File | What it does |
| --- | --- |
| `units.py` | Reads the unit text deterministically: `weight` (stated: "3 lb bag", "per lb", "6 x 500 g", "flats 8 1-lb containers", "11-12 oz", "bulto de 50 kilos"), `count` ("each", "per bunch", "4 count mesh bags", "dozen", "100's", "box of 18"), `volume`, or `unknown`. A bare "kg"/"g" unit takes the pack weight written in the name ("Green Peas 340G"). |
| `researcher.py` | Web research (Anthropic `web_search`, same key/model conventions as `weight_research/`) of the weight of ONE item of a product: typical, min, max, and a standard wholesale carton when one exists. Batched (12 products per call), JSON answer, sources and confidence kept. A product with no reliable source comes back empty with the reason. |
| `store.py` | `MemoryStore` (tests) and `DbStore` (table `catalog_item_weights`, model `CatalogItemWeight`): each (product, count unit) is researched once for the whole app. |
| `service.py` | `normalize_price` (one row), `normalize_catalog` (a whole catalog: researches what is missing, then converts every row), `items_in_weight` (a 10 kg box -> how many items), `weight_of_items` (8 items -> kg). |
| `evaluate.py` | Live check: `python -m backend.catalog_normalization.evaluate` (add `--skip-web` for the deterministic half). |

## Rules

* A weight written in the data is used as written (`stated_weight`).
* Official fixed factors are used as such and labelled `official_factor`: USDA egg dozen weights (size from the name, "large" assumed and flagged when absent),
  USDA bushel test weights (corn 56 lb, soybeans 60, wheat 60).
* Anything that needs the weight of an item comes from the researched store (`researched_item_weight`), with its confidence and sources. Without it the row says
  `needs_research`; it is never guessed. Volumes (liters, gallons) and unknown units are `unconvertible` — a density is not guessed.
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

## Not done yet (next phase)

Refactoring the app to feed catalogs through this module (frontend `unitConversion.js`, `genericUnitConversion.js`, `countWeightConversion.js`,
`weightResearch.js`, backend `unit_weight_estimates`, `weight_research`), storing normalized catalogs per country, price-currency handling and the MARS retail
catalog as its first input.
