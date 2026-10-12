# Turks and Caicos Islands — rules, file check and what is still missing (2026-10-12)

Two knowledge-base files, both needed:
1. **"tariffs-duties 2010 turks aand Caicos"** — Customs Tariff (General) Order 2010 (L.N. 13/2010, in force 1 Aug 2010), 885 pages: the Order (pp.3–4), Parts I–II (units, interpretation), Part IV exemptions (≈ pp.8–32),
   and **Part III, the Customs Tariff itself (pp.33–835): 5,315 tariff codes**, then an alphabetical index. Calculator: `turks_caicos.py`.
2. **"turks and caicos customs ordinance"** — Customs Ordinance Cap. 19.04 (law as at 31 Dec 2014), where Part III is "(Omitted)"; it supplies the **charges** (processing fee, freight charge, fuel duty), the valuation rule and the flat rate.

## The tariff table
Columns: HEADING No. · TARIFF CODE (7 digits = HS6 + 1, e.g. 0207.142) · DESCRIPTION · UNIT · SUPP. UNIT · IMPORT DUTY RATE · EXPORT DUTY RATE.
* **Rates:** 0% (571 lines — most food, incl. poultry, beef, vegetables, fruit), 10% (515), 15% (272), 30% (3,766 — the general rate), 40%, 45%, 50% …; **specific amounts on 37 lines**: beer/stout $11.91/gal, sparkling wine $21.38/gal, other wine $16.94/gal, spirits and liqueurs $42.38/gal,
  tobacco $45.64/lb, cigarettes $90.52 per 1,000, fuels $0.09–$0.44/gal; **43 vehicle lines "LANDED COST"** (35%/45%/50% by engine size and value, 10% for tractors/hybrid buses).
* The **export duty column is empty** in the file (nothing to parse).
* Layout quirks handled: unit and rate sometimes on the next line, "LANDED COST" printed on the line below the rate, a heading number sharing the line with its only tariff code (`07.02  0702.000  Tomatoes`), pages without a column header, first letters split by the OCR ("T  omatoes").

## What the calculator applies
| Charge | Rule | Source |
|---|---|---|
| Import duty | the rate of the tariff line, on the **value of the goods (the "normal price", excluding freight and insurance)**; **landed cost** (price + freight + insurance + other charges) for the vehicle lines; specific amounts × quantity (lb from kg; gal and thousands from the units entered) | Ordinance s.93; Order 2(3) |
| Customs processing fee | **7.5% of the value of goods imported — on every import, also on 0%-duty goods** | Ordinance s.137 |
| Charge on insurance and freight | **7.5%** of the freight + insurance cost; **5%** on building materials (sand, cement, blocks, steel); **none** on motor vehicles and petroleum | s.135; L.N. 39/2013 |
| Fuel | tariff duty **plus US$0.85 per imperial gallon** (applied to codes 2710.110 and 2710.191–.196 — an assumption of what "fuel" means) | L.N. 11/2010, 12/2011, 38/2013 |
| Origin | no preference applied (the Governor may vary duty by origin, s.74 — no such order in the files); no CARICOM waiver | s.74 |
| VAT | none: neither file mentions a VAT or sales tax on imports | — |

## Missing or uncertain (checked 2026-10-12)
1. **Amendments are not in the files.** The Ordinance says Part III was *amended by L.N. 16/2010 and 38/2011*; the uploaded tariff is the original Order (L.N. 13/2010). Rates changed by those notices (and later ones) are not reflected. The calculator warns.
2. **12 lines have no import-duty rate printed** (0204.430 boneless sheep meat, 0204.500 goat meat, 0703.900 leeks, 0708.900 other legumes, 2106.900, 2711.140, 7201.500, 7209.900, 8107.900, 8412.390, 8482.800, 8701.100): reported as incomplete, never guessed; add the rate to `overrides.json`.
3. **Exemptions are warnings only.** Part IV (government, public servants' vehicles $25,000 with 50% relief, disaster relief, charities, statutory bodies, scientific research …) needs certificates and approvals; the **flat 33% rate** for baggage/personal effects and small consignments (≤ $200) is not applied. For the processing fee and the freight charge only **the Government and Interhealth Canada** are exempt (Schedule 3).
4. **Freight and insurance:** the 7.5% charge needs them; the Tax Calculator page and the Tax × multipliers pass none, so on those screens only duty + 7.5% processing fee appear (a warning says so).
5. **The processing-fee base** is "the value of goods imported"; the file does not say whether freight is included — the goods value is used.
6. **Fuel definition** (which tariff lines are "fuel" for the US$0.85) is not given; LPG (2711) is not included.
7. **Edition:** HS 2007-based Tariff 2010; 7-digit codes — a current product's HS code may not exist or may map to a different line.
8. Import licences, sanitary/phytosanitary permits and duty-free-shop rules (10% of selling price) are outside the calculation.
