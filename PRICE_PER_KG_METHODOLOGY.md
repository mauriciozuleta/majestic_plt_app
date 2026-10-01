# Price per kg — Methodology

This document explains how every product price in this app becomes a comparable **price per kilogram in USD**, and
what happens when a source doesn't quote its price per kilogram — a carton, a crate, a dozen, a bundle, a single
fruit. It applies to the Country Product Portfolio tables (Colombia, United States, and every source added in
Settings ▸ Product analysis sources) and to Market Opportunities, which compares those per-kg figures across
countries.

---

## 1. The rule, in order

For every priced row, the app uses the **first** of these that applies, and labels which one it used:

1. **Already per kg.** The source quotes the price per kilogram. Used as-is.
2. **Official conversion.** The unit has a fixed, published definition — a pound, a hundredweight, a USDA egg
   size class, a USDA grain test weight, a Colombian arroba — or **the source itself states the pack's net weight**
   (a USDA carton line such as "25 lb cartons loose"). Pure arithmetic, no estimate. Shown as *"Official: …"*.
3. **AI estimate, labeled as such.** Only for count-based units with no stated weight (a crate of papayas, a
   bunch of garlic), and only where a comparison actually needs it. Always flagged *"AI estimate, not an official
   standard"* and marked for review in Market Opportunities. Never overrides a rule-1 or rule-2 figure.
4. **Your own override.** A price and/or pack weight you enter for one exact row (the ✏️ button) always wins over
   everything above.
5. **Otherwise: no per-kg figure.** The row either isn't stored at all (USDA produce, section 3) or is shown with
   a plain explanation of why it can't be converted — never with a guessed number.

Currency is converted **after** the per-kg figure is known (section 6).

---

## 2. United States — USDA AMS Market News reports

| Category | Source unit | Conversion | Type |
| --- | --- | --- | --- |
| Beef, Pork | USD per cwt | 1 cwt = 100 lb = 45.359 kg | Official |
| Poultry | USD per lb | 1 lb = 0.45359237 kg | Official |
| Eggs | USD per dozen, by size class | USDA minimum net weight per dozen: Jumbo 30 oz, Extra Large 27, Large 24, Medium 21, Small 18, Peewee 15 (1 oz = 28.3495 g) | Official |
| Grains | USD per bushel | USDA standard test weight: corn 56 lb, soybeans 60 lb, wheat 60 lb | Official |
| Produce (FL/CA shipping point) | USD per carton, flat or container | The net weight USDA prints on the pack's own line — see section 3 | Official |

---

## 3. USDA produce — cartons, flats and containers

### 3.1 Where the weight comes from

The two shipping-point reports (Orlando vegetables `or_fv120`, Fresno fruit `fr_fv110`) price produce per
carton, never per pound. But every price block sits under a **container line** that USDA prints itself, and most of
those state the net weight:

```
---GRAPES: DEMAND FAIRLY GOOD. MARKET ABOUT STEADY.
RED GLOBE
19 lb containers bagged              <- container line: 19 lb
large-extra large 24.95-28.95 mostly 26.95-28.95
```

The parser (`backend/usa_sources/common.py`) reads that container line and computes its net weight **only from
what USDA wrote**:

| Container line in the report | Net weight used |
| --- | --- |
| `25 lb cartons loose` | 25 lb |
| `19 lb containers bagged` | 19 lb |
| `flats 8 1-lb containers with lids` | 8 × 1 lb = 8 lb |
| `flats 12 6-oz cups with lids` | 12 × 6 oz = 72 oz = 4.5 lb |

Some price lines carry their own container instead of sitting under one (`flats 12 6-oz cups with lids
16.00-22.00`); the same rule applies to that line.

### 3.2 Rows that are not stored

If the container line states **no weight** — a volume or layer measure — the row is dropped at import and never
reaches the database:

| Container line | Why it's dropped |
| --- | --- |
| `flats 12 1-pint containers with lids` | A pint is a volume; the fill weight isn't stated |
| `1/2 bushel cartons` | A bushel is a volume; weight varies by commodity |
| `cartons 2 layer` | A layer count, not a weight |

On the 29 September 2026 reports this removed 2 of 20 domestic rows (grape tomatoes in pints, okra in ½-bushel
cartons). A carton price with no weight can't become a per-kg figure without guessing, so it isn't kept.

### 3.3 Which price is used

Each line quotes a full range and often a narrower **"mostly"** band — where most trades happened. The app uses the
**top of the "mostly" band**, or the single "mostly" value when USDA gives one (`6.00-12.00 mostly 10.00` → 10.00).
Only when there's no "mostly" figure does it use the top of the full range. The full quote is kept in the row's
note, so you can always see what was chosen.

A line that is really the wrapped end of the previous line's qualifier (`…mostly 23.95-25.95 some` /
`varieties 29.95-30.95`) is a sub-price for part of the same lot, not a separate product, and is skipped.

### 3.4 Product names

USDA prints qualifiers above each price block — `ORGANIC`, and variety or type names such as `RED GLOBE`,
`Autumn Royal`, `ROMA`, `MATURE GREENS`. They become part of the product name, so two differently priced lots
never share one name:

- `Strawberries (Santa Maria California)` — conventional, USD 10.00 per 8 lb flat
- `Strawberries, Organic (Santa Maria California)` — USD 20.00 per 8 lb flat
- `Grapes, Red Globe (San Joaquin Valley And Kern District California)`
- `Tomatoes, Mature Greens (Alabama)`

Size grades (`5x5 size`, `large-extra large`, `medium`) stay in the unit column, not the name, since they don't
change the carton weight.

### 3.5 Worked examples (29 September 2026 reports)

| Product | Quote | Pack weight | Per kg |
| --- | --- | --- | --- |
| Tomatoes, Mature Greens (Alabama), 5x5 | USD 18.35 per 25 lb carton | 25 lb = 11.340 kg | 18.35 ÷ 11.340 = **USD 1.62/kg** |
| Strawberries (Oxnard) | USD 10.00 per flat of 8 × 1 lb | 8 lb = 3.629 kg | **USD 2.76/kg** |
| Blackberries (South and Central District) | USD 18.00 per flat of 12 × 6 oz | 4.5 lb = 2.041 kg | **USD 8.82/kg** |
| Grapes, Red Globe (San Joaquin Valley) | USD 28.95 per 19 lb container | 19 lb = 8.618 kg | **USD 3.36/kg** |

### 3.6 Known gaps

- **Import sections are excluded.** Fresno's report mixes domestic districts with "MEXICO CROSSINGS THROUGH …"
  sections; those are never imported, since this is a USA-origin portfolio.
- **Rows without a region heading are excluded.** The reports are two columns. A price block that starts at the top
  of the right-hand column, with no region heading of its own, can't be attributed to a region reliably, so it's
  dropped rather than guessed (on 29 September this included Roma tomatoes and the organic grape section).
- **Coverage is whatever USDA reports that day.** These are daily reports of what actually traded; a crop that
  didn't trade doesn't appear.

---

## 4. Colombia — La Mayorista and Corabastos

**La Mayorista** quotes most products per kg (used as-is). Rows named with another unit are converted when the
unit has a fixed weight: libra (1 lb), arroba (25 lb), grams, or a stated kilo count. A product priced per
**unidad** (one item, e.g. one egg) has no fixed weight and is left non-comparable unless section 5 applies.

**Corabastos** publishes a daily bulletin with columns *Presentación*, *Cantidad* and *Precio Unidad*, where
**Precio Unidad is always Precio Extra ÷ Cantidad**. What that means depends on the unit:

- **KILO, BULTO, TONELADA** — Cantidad is a kilogram count (1, 25–70, 1000), so Precio Unidad is already per kg.
- **Package units where Cantidad is the item count** — e.g. `CAJA DE MADERA (18 per package)` for papayas.
  Corabastos has already divided the crate price by 18, so the price shown is **per single fruit**, not per crate.
- **Package units where the count is in the description** — e.g. `30 UNIDADES (1 per package)` for eggs.
  Cantidad is 1, so the price shown is for the **whole 30-egg pack**.

The app treats these two package shapes differently. Getting this wrong divides twice: until 28 September 2026 a
papaya priced at COP 1,556 **per fruit** was being divided by the weight of a whole 18-fruit crate, giving
USD 0.05/kg instead of about USD 0.67/kg.

---

## 4b. Sources added in Settings (Jamaica, Saint Lucia, Trinidad and Tobago, …)

Each source's own unit text is read with fixed factors only (`genericUnitConversion.js`):

| What the source reports | How it converts |
| --- | --- |
| A bare weight unit (`kg`, `lb`, `g`, `oz`) and **no pack size in the product name** | Price per that unit (Jamaica `kg`, Trinidad `lb`/`kg`) |
| A bare weight unit **and a pack size in the product name** (`Picsweet Green Peas 340G`, unit `g`) | Priced per pack — divided by the name's stated weight: XCD 12.15 ÷ 0.340 kg = XCD 35.74/kg |
| A package with its weight in the unit (`45kg bag`, `5lb bundle`) | Divided by that stated weight |
| A volume unit (`L`, `ml`, `gal`) | Not converted — volume isn't weight |
| A count or bare package (`each`, `unit`, `100's`, `Bundle`, `Head`) | Not converted until AI weight research or your override supplies a weight |

The pack-size rule exists because a retail feed (Saint Lucia's Massy Stores) labels a 156 g frozen meal with unit `g`
and the price of the whole pack. Read literally that would be XCD 21.95 **per gram** (XCD 21,950/kg); the name's
"156G" gives the correct XCD 140.71/kg.

A source that records no currency, or a bare `$`, uses the country's official currency (Trinidad and Tobago → TTD).

---

## 5. Count-based units — AI estimates (Market Opportunities only)

When Market Opportunities pairs a product sold by count with one sold by weight, it needs a weight for the count.
In order:

1. **Eggs** — USDA's official dozen weight (section 2). A Colombian grade (A, AA, AAA, Extra) has no official
   match to a USDA size class, so **Large** is assumed, and the row says so.
2. **Everything else** — one Claude Haiku estimate per distinct product, cached permanently, asked for either:
   - the weight of **one single item** when the source already prices one item (Corabastos per-package rows), or
   - the **total net weight of the pack** when the price covers the whole pack.

   Haiku is told to return nothing when it isn't confident; that row then stays non-comparable. Every estimate
   carries its reasoning in the row's note (e.g. *"700 g: round papayas are medium-sized, typically 600–800 g per
   fruit"*) and the row is flagged for review.

Worked example — Round Papaya (Corabastos): COP 1,556 per fruit ÷ 0.700 kg = COP 2,223/kg ÷ 3,334.28 COP per USD
= **USD 0.67/kg**. That's in line with La Mayorista's own per-kg papaya quotes (COP 2,500–3,500/kg).

The Country Product Portfolio tables also offer **Research Missing Weights** (Claude with web search) for any row
still without a weight; its result is labeled with a confidence level and its sources, and never replaces an
official conversion.

---

## 6. Currency

Every per-kg price is converted to USD **separately**, never source currency straight to target currency:

- Rates come from **open.er-api.com** (free, one daily call returns every currency against USD), cached per day
  with the rate's date recorded on every comparison.
- The stored rate is "units of that currency per 1 USD" (e.g. COP 3,334.28), so **USD = local price ÷ rate**.
- **USD** is 1.0 and **XCD** uses its fixed peg of 2.70 per USD — neither needs a network call.

---

## 7. Where this lives in the code

| Concern | File |
| --- | --- |
| USDA produce parsing, pack weights, names | `backend/usa_sources/common.py`, `produce_fl.py`, `produce_ca.py` |
| Official conversions (USA, Colombia) | `src/components/company/tabs/OperationsTab/MarketAnalysis/unitConversion.js` |
| Custom-source units | `…/MarketAnalysis/genericUnitConversion.js` |
| Count-based units, eggs, Haiku prompts | `…/MarketAnalysis/countWeightConversion.js` |
| Corabastos bulletin parsing | `backend/price_sources/corabastos.py` |
| Haiku estimate cache | `backend/routers/unit_weight_estimates.py` |
| Currency | `backend/currency/usd_rates.py` |
