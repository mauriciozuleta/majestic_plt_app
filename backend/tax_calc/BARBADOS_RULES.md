# Barbados — rules and file review (2026-10-10)

File: knowledge base "Barbados customs duties.md" = **Customs Tariff (Amendment) Order, 2019 — S.I. 2019 No. 57** (Customs Act, Cap. 66), which replaces Parts I and II of the
Customs Tariff with the revised CARICOM CET (HS 2017, 11 April 2018) as printed by the Barbados Government Printer. 1,097 pages. Calculator: `barbados.py`.

## Where things are (the file's `page-N` markers)
| Pages | Content | Used for |
|---|---|---|
| 1–3 | The Amendment Order: **60%** for Section B goods "notwithstanding" Section A; the **Special Safeguard** formula for Section C goods | rules below |
| 46–633 | **Part 1 Section A**, the national schedule: HS · CET suffix · description · **DUTY RATE** · [*one optional cell*] · **VAT RATE** · unit · SITC | every line (6,837) |
| 636–642 | **Section B**: goods charged 60% (86 entries; "ex" = only part of the heading) | duty override |
| 643–652 | **Section C**: Special Safeguard trigger prices in BBD per kg, 1986–88 reference period (90 entries) | additional duty |
| 653–718 | Conditional duty exemptions and the commodities ineligible for them | warning only |
| 719–1053 | "EPA rates until 2020" (HS → EPA rate) | not applied (stale) |
| 1055–1096 | CET Lists A, C, D (Barbados is the 3rd value after the CET rate) | cross-check only |

## The optional cell between DUTY and VAT — its meaning depends on the page header
* **Inspection fee** (chapter 1, live animals): `$20.00 each`, `$10.00 each`, or `$30.00 per batch =< 3 / $35.00 > 3` (poultry). `each` is computed from the number of head; "per batch" is reported, not computed.
* **Countervailing duty** (chapter 4, dairy): `$0.33 per l` with `ex T&T` — charged on goods **from Trinidad and Tobago** (also when they are otherwise CARICOM duty-free); needs the quantity in litres.
* **Excise** (juices 10%, beverages, vehicles 40%, fuels, tobacco, ethanol …): a percentage is charged on **CIF + duty** (the file does not state the base — assumption); specific amounts (`$44.09 per kg`, `$109.99 per m3`) are reported, not computed.
* **Fuel tax** (chapter 27) is a separate column on those pages: reported, not computed.

## Rules the calculator applies
1. Duty on the CIF value (BBD pegged at 2 per US$). **CARICOM origin: duty free** (countervailing duty and excise are not waived).
2. **Section B** (60%) replaces the Section A rate; "ex" entries carry a warning because only part of the heading is covered.
3. **Section C** (Special Safeguard, S.I. 57 s.4): additional duty per kg when the CIF import price is more than 10% below the trigger price. With *difference = trigger − price* and
   *r = difference ÷ trigger*: 0 if r ≤ 10%; 30% of the amount by which the difference exceeds 10%; plus 50% of the excess over 40%; plus 70% of the excess over 60%; plus 90% of the
   excess over 75%. It is charged "in respect of which no quota allocation has been granted" — the calculator assumes none was granted and says so.
4. **VAT** uses the rate printed on the tariff line: **17.5%**, or **0.0% on 221 lines** (poultry, cheese, bananas, tomatoes, many staples). Charged on CIF + duty + excise (+ safeguard); shown, not
   counted (a VAT-registered importer credits it).
5. EU origin: the "EPA rates until 2020" are **not applied** (they expired in 2020); the normal rate is shown with a warning.

## Inconsistencies and gaps found in the file
1. **Section A vs Lists A/C disagree on 46 lines**, almost all protected foods: pork 0203 *184%* (Lists: Free), chicken cuts 0207 *184%* / *40%* (Lists: 15% or Free), beef cuts 0201.20 *40%* (List 30%),
   rearing poultry *184%*, dairy *141%* (Free), spirits-based lines *100%* vs `$2.64`. The Lists are the 2018 CARICOM print; Section A is Barbados's own 2019 tariff, so **the higher of the two rates is used** (standing rule: when the file disagrees with itself the HIGHER rate applies — here almost always Section A) and the
   calculator warns "CONFLICT IN THE FILE" on those lines.
2. **Very high national duties are printed as plain percentages** (tomatoes 199%, onions 216%, shallots 109%, whole chicken 184%, milk 141%); they look like the old specific/seasonal rates converted to ad valorem
   — they are used exactly as printed.
3. **Section C trigger prices are 1986–88 prices** and the "difference" wording of the Order is ambiguous; the standard WTO reading (price below trigger) is implemented.
4. **Section B "ex" entries** are listed by heading with partial descriptions; the exclusions are in the wording around them, which the extraction splits across lines, so the text shown with the warning may include a
   neighbouring item.
5. **"EPA rates until 2020"** covers pages 719–1053 and is out of date.
6. The middle-column header changes by chapter and is garbled by the extraction ("VAILING", "VATE"); the calculator reads the meaning per page and carries it over to continuation pages.
7. **66 lines are flagged "review"** because their duty is a specific amount or could not be read (mostly live animals whose fee text wraps over several lines, plus some tobacco/alcohol/fuel lines); they are reported as incomplete. 25 lines have no VAT cell (the 17.5% default is assumed and flagged by the totals only).
8. Not in the file: customs processing fees, any levy outside the tariff, the VAT Act's own exemptions, the current EPA schedule, and orders after September 2019.
