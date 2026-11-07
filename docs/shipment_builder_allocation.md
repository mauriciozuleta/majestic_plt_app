# How the shipment builder assigns kilos to each product

*Majestic P.L.T. — Financial ▸ Revenue Streams ▸ "Build shipment" / "Update shipment". Written from the code as of 2026-11-05
(`ShipmentBuilder/shipmentBuilder.js`, `ShipmentBuilderModal.jsx`, `shipmentFinance.js`, `services/marketOpportunitySettings.js`).*

## 1. In one paragraph

A shipment is built for **one leg of one route** (outbound or return). The builder takes the products on the **priority list** of the
route's origin → destination country pair, decides each product's **market level** (Wholesalers, Premium or Niche) from its landed (DDP)
price against the destination's price, gives every product a **cargo cap** from that level, and then fills the aircraft **in a fixed
order**: wholesalers first, premium second, niche last. Whatever the aircraft cannot take is taken from the *last* group served. Weights
the user typed in by hand are kept and come off the capacity first.

## 2. The inputs

| Input | Where it comes from | Used for |
| --- | --- | --- |
| **Capacity (kg)** | The route's aircraft **max payload** (Air Logistics catalogue). *Not* the leg's "target cargo %" or "available cargo" — those are shown on the route but the builder fills the whole max payload. | The total to distribute |
| **Priority list** | Market Analysis ▸ Market Opportunities, "Add to priority list", per (source country, target country) | Which products may ship. No priority list → no shipment (the modal sends you to Market Opportunities). |
| **Comparison rows** | The saved Market Opportunities comparison source → target (computed on the spot if none is saved) | Source price, target price, Diff %, opportunity rating, HS code, matched target product |
| **Country SAM** | Global Trade Data, per HS-6 code and the destination's region (`fetchProductSam`) | Ordering inside a group; picks the default cap when no cargo cap is set |
| **Air fare per kg** | The leg's *Price × Kg* on the route (leg cost ÷ available cargo, or the GSA price on return legs) | Part of the DDP price |
| **Tax multiplier** | The destination's tax calculator for the HS code (taxes ÷ goods value, see `tax_calc/mapping.py`) | Part of the DDP price |
| **Destination Market settings** | Settings ▸ Market Opportunity settings ▸ Destination Market | Price ranges per level, cargo caps, sell %, wholesaler margin rule |
| **Manual weights** | Details ▸ Edit on a product of an existing shipment | Kept as typed when the shipment is updated |

## 3. Step 1 — which products are candidates

1. The priority list of the pair gives the product names.
2. Each name is looked up in the comparison. A comparison has one row per matched *target* product, so the same source product can
   appear several times; the builder keeps the row with the **lowest Diff %** (best margin) and that row's rating.
3. Priority-list products with **no match in the target market** are not in the comparison. They are taken from the origin's product
   portfolio (price, HS code) and ship as **Niche** products by definition (no target price to compare with).
4. Products on the list that are no longer in the latest comparison are reported ("Not in the latest comparison any more") and left out.
5. Every product starts **ticked**; when updating a shipment, only the products of the previous shipment start ticked. The user can tick
   or untick products, singly or by rating group, before pressing Build. Only the ticked products are allocated.

The list is displayed grouped by **rating** (Very High, High, Challenging, Complex, Difficult, Not Viable, Unrated) and, inside a
rating, sorted by **Country SAM descending** (bigger target market first) then **Diff % ascending** (bigger margin first). Missing values
sort last. *This display order does not decide the kilos* — the market level does (step 3). The rating is shown for information and for the
Market Opportunities views; the builder includes every rating that is on the priority list.

Rating scale used by the comparison (Diff % = source price as a % of the target price; Settings ▸ Market Opportunity settings):
Very High 0–20 %, High 20–30 %, Challenging 30–50 %, Complex 50–65 %, Difficult 65–100 %, Not Viable above 100 %.

## 4. Step 2 — the market level of each product

For each matched product:

```
FCA per kg   = the origin country's price per kg (from the comparison)
DAP per kg   = FCA + the leg's air fare per kg
DDP per kg   = DAP × (1 + the product's tax multiplier)
share        = DDP per kg ÷ the target price per kg × 100
```

The share is compared with the **Destination Market ranges** (current settings):

| Level | Share range (DDP as % of the target price) | Cargo cap | Sell price rule |
| --- | --- | --- | --- |
| **Wholesalers** | 0 – 70 % | 1,500 kg | 70 % of the target price (never below DDP) |
| **Niche Markets** | 70 – 100 % | 500 kg | DDP + 20 % |
| **Premium Market** | 100 – 2,000 % | 200 kg | DDP + 30 % |

A product with no DDP or no target price (missing air fare, missing multiplier, missing price) has **no level** and is treated like a
niche product for allocation. A product with no match in the target market is Niche.

## 5. Step 3 — the cargo cap of each product

The **cap** is the most one product can get:

1. its level's **Cargo Cap** from the settings (1,500 / 500 / 200 kg above);
2. if that level has none (no level, or the cap is empty): **1,500 kg** when the product has a Country SAM above zero, **200 kg** when it
   has none (`SAM_CAP_KG`, `NO_SAM_CAP_KG`);
3. **Wholesaler margin rule.** A wholesale product whose profit margin is thin is shipped less. Margin = (suggested sale price − DDP) ÷
   DDP, the sale price being the wholesaler rule above. If the margin is **below the minimum (15 %)**, the cap is reduced by the
   **cap reduction (500 kg)**, to a floor of 0. Example: a wholesaler with a 1,500 kg cap and a 12 % margin gets a 1,000 kg cap.

## 6. Step 4 — filling the aircraft

`allocateShipment(products, capacityKg, fixedKg)`:

1. **Manual weights** (Details ▸ Edit, flagged *manual*) are kept as typed, rounded down, and subtracted from the capacity. The remainder is the
   **budget**.
2. The remaining products are ordered: **Wholesalers → Premium → Niche**, then Country SAM descending, then Diff % ascending.
3. Three cases, in order:
   - **The wholesalers alone fill the aircraft** (the sum of their caps ≥ budget): *every* product, of all levels, is brought down to one
     common cap ("water-filling": a product with a cap below the common level keeps its own cap and the kilos it leaves go to the others).
   - **Otherwise** every wholesaler gets its **full cap**. Then:
     - if the premium caps also fit: every premium product gets its **full cap**, and the **niche products (and products with no level)
       split what is left evenly**, none above its own cap (water-filling);
     - if the premium caps do not fit: the **premium and niche products share what the wholesalers left evenly** (water-filling), so
       nobody is dropped.
4. **Whole kilos.** Each amount is rounded down; the kilos lost to rounding go, one each, to the first products in the ordering above that are
   still under their cap.
5. Products that end with 0 kg are not listed. Each product gets `sharePct` = its kg ÷ total allocated kg. The result is sorted by kg.
6. **Unallocated cargo.** If every cap is reached and the aircraft still has room, the rest is shown as "unallocated (product limits
   reached)" — the builder never pushes a product above its cap to fill the aircraft.

### Worked example (illustrative)

Capacity 6,000 kg; three wholesalers (caps 1,500, 1,500, 1,000 after a margin reduction), two premium (200 each), four niche
(500 each).

- Wholesalers: 4,000 kg. Left: 2,000.
- Premium: 400 kg. Left: 1,600.
- Niche: 1,600 ÷ 4 = 400 kg each (each below its 500 kg cap).
- Total 6,000 kg, nothing unallocated.

With a 3,000 kg aircraft the wholesalers' caps (4,000 kg) exceed the budget, so all nine products are water-filled together: the two
premium products (cap 200) are served first and keep 200 kg each; the other seven products share the remaining 2,600 kg evenly, about
371 kg each (all below their own caps). Total 3,000 kg.

## 7. After the allocation — what is computed from the kilos

(`shipmentFinance.js`, shown on the shipment cards and in the Revenue route table)

```
FCA total     = kg × origin price per kg
DAP total     = kg × the leg's air fare per kg;  DAP subtotal = FCA + DAP
DDP total     = DAP subtotal × (1 + tax multiplier)
Sale price/kg = by market level (see section 4); never below DDP per kg
Sale total    = sale price per kg × kg
```

The shipment header shows the kilos allocated vs the capacity, the number of products, unallocated kg, the **DDP total** and the **sale
total** (each only when every product has the figures it needs).

## 8. Editing a built shipment

Details ▸ Edit lets the user type a weight for one product. It must be above 0 kg and not exceed **the free room on the aircraft plus the
product's current weight**. The product is flagged *manual*, the shares are recalculated, and the next **Update shipment** keeps that weight
and shares only what is left among the other products.

## 9. Things worth knowing (observations from the code)

1. **Capacity is the aircraft's max payload**, not the leg's target cargo % / available cargo. If the route is meant to carry only, say,
   80 % of the payload for this shipment, the builder does not know — the user must edit weights by hand.
2. **The rating does not change the kilos.** A "Challenging" wholesale product gets the same priority as a "Very High" one; only its market
   level and cap matter. Ratings only decide what is on the list and its display order.
3. **Country SAM only breaks ties inside a market level** and chooses the 1,500 / 200 kg default cap when a level has no cap. It is not a
   limit on how much the destination can absorb.
4. **A missing air fare, tax multiplier or price removes the product's market level**, so it is allocated as a niche product with the
   default cap — check the Market level column in the builder before building.
5. **Rounding** can leave a product one kilo above an even split; this is by design (first products in order get the spare kilos).
6. **Nothing is dropped:** a product that is ticked always receives kilos unless the aircraft is full of manual weights.
7. A return shipment is built the same way as an outbound one, from the pair destination country → return country, with that leg's
   own air fare.
