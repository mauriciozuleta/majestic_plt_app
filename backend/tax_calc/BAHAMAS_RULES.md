# Bahamas — rules for the tax calculator

Source: knowledge-base document "bahamas-customs-1 duties explanation" = **Tariff Bill 2018 (latest draft 25 May 2018, in force 1 July 2018) + its
full schedule** (845 PDF pages, text layout, no HTML tables). Section / page numbers below are the document's own. This note lists what the
calculator needs from the *law*; the rates come from the schedule table.

## 1. What is charged (Part II)
| Rule | Source | Calculator consequence |
|---|---|---|
| Duty is charged on all imported goods | s.3 | one customs-duty line per tariff code |
| Rate = **General Rate** (3rd column) and/or **Specific Rate** (4th column) | s.4(1) | ad valorem, specific, or both (beer: 10% **and** $10 BSD per gallon) |
| Goods eligible for the **Applicable Preferential Rate** (6th column) pay the EPA rate instead | s.4(1), Part B 2(c) | only for EU/CARIFORUM-EPA origin; see §3 |
| The Minister may, **by Order**, replace the General Rate with an alternate rate **up to the Maximum Variable Rate** (5th column) | s.4(2), s.15(c) | see §2 |
| `%` = percent ad valorem of "the value of the entered product(s)" | Part B 2(d) | base = customs value (the Act does not define it here; CIF is the Bahamian practice — **verify**) |
| **+1% ad valorem on goods entered for warehousing / re-warehousing** (in addition to duty) | s.9 | optional "bonded warehouse" flag; off by default |
| Anti-dumping / countervailing duty, by Order, extra to duty | s.10 | warning only (no list in this document) |
| **Excise** under the Excise Act 2018 is paid at entry, on top of duty | s.11, Part B 6 | applies to some articles in chapters **24, 27, 40, 61, 63, 69, 70, 71, 84, 85, 87, 90, 91, 93** (tobacco, fuels, tyres, clothing, glass, jewellery, machinery, vehicles, …). The Excise Act is **not** in this document → warn on those chapters; food chapters are not affected |
| Duty on houses built in Port Area (Hawksbill Creek): 25% of 40% of construction cost | s.8 | irrelevant for food, ignore |

## 2. The variable rate (the rule the user asked about)
* Column 5 "Maximum Variable Rate" is a **ceiling the Minister may switch on by Order**, replacing (not adding to) the General Rate for that
  article (Part B 2(b); s.4(2)). It is **not** charged by default.
* The Order must state a commencement date and be **gazetted at least 5 days before** it starts (s.15(c)). The Minister can also remove an item
  from the variable-rate list, reinstating the General Rate (s.15(d)).
* In the schedule the ceiling is **300%** on about 640 lines (meat, poultry, offal, dairy, fresh vegetables, fish — the protected food lines) and
  100% on 6 lines; most lines have none.
* Examples (General / Max variable): fresh tomatoes 0702.0000 **10% / 300%**; chicken breasts, thighs, wings 0207.14xx **30% / 300%**; turkey
  0207.2xxx **5% / 300%**; beef 0201.xxxx **Free / 300%**; bovine/swine offal 0206.xxxx **Free / 300%**; milk 0401.xxxx **Free / 300%**.
* **Calculator design:** use the General Rate. Keep a small table of *active Orders* (code → current rate, with the Order's date and a
  "rate in force" flag), editable like `overrides.json`, so the user can enter an Order when one is gazetted. A line with a variable-rate ceiling shows a
  warning "the Minister may raise this up to 300% by Order; check the Gazette". No Order list exists in the uploaded document — **we cannot know which Orders
  are in force today**, and 2018 rates may have changed since (the Bill itself changed several: salmon, tomato paste, potatoes, nut spreads, tofu → Free;
  fabric softener, concrete tiles → 25%; rechargeable batteries → 10%).

## 3. Preferential (EPA) rate
* Column 6 holds either nothing or the letters **"EPA"** (5,273 lines). "EPA" means: look up the rate in the **Second Schedule** of the Tariff Act
  for goods from the EPA countries listed in its Note 2 (CARIFORUM–EU Economic Partnership Agreement). **The Second Schedule is not in this
  document** (s.16 says its rates take effect with the Act). Until it is loaded: origin in the EU/EPA list → warn "EPA preferential rate may apply, not
  loaded"; every other origin → General Rate. Colombia / USA are not EPA partners, so the General Rate applies to them.
* No CARICOM, Colombia or US preference appears in this document (CARICOM treatment for the Bahamas is not in the schedule → do **not** apply a
  CARICOM waiver as Jamaica/T&T do).

## 4. Exemptions — Chapter 98 (s.5–6, Part B 4)
* Chapter 98 codes (9801–9861+) give **Free** or a reduced rate to *who/what the goods are for*, "subject to conditions of use, purpose and
  requirements" (s.6). They are not product-based, so the calculator never applies them automatically: offer an optional "special regime" select and
  warn otherwise.
* Relevant to the food business: **9806** goods for registered floriculturists, horticulturists, agricultural co-operatives and **farmers** (Free);
  **9807** livestock and fish-farming goods (Free); **9808** registered commercial & bone fishermen (Free); **9831** feed for zoo animals; **9853**
  Agriculture Manufacturers Act (Free); **9852** Hotel Encouragement Act (Free; hotels are a likely customer); **9833** Spirit & Beer manufacturing
  (Free under 5 years, 10% over); **9830** bulk fresh water (Free). Conditions sit in Chapter 98 Notes 3–5 (read before relying on them).
* Also generic: baggage, samples (98.25), school supplies, medical equipment, relief goods, re-imported goods (98.48), etc. — not needed for trade
  calculators.

## 5. Quantity / unit rules
* Column 7 gives the statistical unit. Food lines are in **pound** (a few in **gallon**, **number**, **square yard**, **ton**). A **specific rate** is
  charged per that unit (beer/ale/stout: **$10 BSD per gallon**; mixed fermented drinks: $4 BSD per gallon). BSD is pegged 1:1 to USD.
* The unit table (Part B 3) has codes (EA, DZN, CWA hundred-pound, GLI UK gallon, PGL proof gallon, BLL US barrel, …): when a specific rate exists
  convert the user's kg / litres to the line's unit (1 kg = 2.2046 lb; the **gallon is the UK gallon** = 4.546 L, the table says "GLI GALLON (UK)").
* **"Unpackaged" = any package exceeding 20 pounds** (Part B 2(e); chapters 8 and 12 only). Nuts and fruit have separate lines for unpackaged
  vs packaged — e.g. 0801.xx10 "Unpackaged (20 pounds or more)" 5%. The calculator needs a "package size over 20 lb" question for chapters 8 and 12.
* Rate wording: "Free" = 0%; a bare `%` = ad valorem; "New" in the Objects-and-Reasons table marks a newly created rate/code (antique/vintage vehicles).

## 6. Classification rules (Part A, Part B 1)
General Rules of Interpretation of the HS (GRI 1–6) apply: headings and notes decide; most specific heading wins (3a); the Bahamas schedule has
**8-digit codes written 0000.0000** (4-digit heading + 4-digit national subheading) and 6-digit HS compatibility. Subheadings follow the same rules as
headings (Part B 1). Our mapping (product → HS6 → tariff line) already handles several lines under one HS6 as "review".

## 7. NOT in this document — needed before the Bahamas calculator can be called complete
* **VAT** (Value Added Tax Act): standard rate (10% since 2022 by public sources — verify), with zero-rating of basic foods; **Customs
  processing / user fees** and any **stamp tax**; **Excise Act 2018** rates; the **gazetted Orders** changing rates since 2018; the **EPA Second
  Schedule**; Chapter 98 Notes 3–5 conditions. State plainly in the result which of these were not computed (same pattern as `warnings`).

## 8. What the parser must handle (schedule format)
* Plain-text columns (position-based): `code | description (wraps over several lines) | General | Specific | Max variable | Preferential | unit`.
  About 6,050 lines have a code `NNNN.NNNN` followed by values; 4-digit headings (`02.06`) and 6-digit subheadings (`0207.13`) are heading rows with
  no rates; descriptions continue on the next lines; dashes (`-`, `--`, `---`) give the level, as in T&T.
* Page-footer noise ("Page - 24", repeated column headers) between rows; a few pages may be OCR-damaged (the extraction flags every page "table
  relationships require review") — apply the T&T approach: validate each rate token, flag `unreadable`, `overrides.json` for hand fixes.
* Column positions drift by page, so classify tokens by *content* (a `%` or `Free` before `300%` = general; `300%`/`100%` = ceiling; `EPA` =
  preferential; `$N BSD` = specific; last word = unit) rather than by character offset.
* A row with a General rate but nothing else has no ceiling; a row whose first rate is `300%` and General blank must not be read as 300% duty.
