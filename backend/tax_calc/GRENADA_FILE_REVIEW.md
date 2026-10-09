# Grenada customs duties file — consistency review (2026-10-09)

File: knowledge base "Grenada customs duties.md" = Grenada Customs Act, Cap. 75A, with subsidiary legislation (614 pages). Calculator: `grenada.py`.

## What the file contains (page = the file's `page-N` marker)
| Pages | Content |
|---|---|
| 1–150 | Customs Act subsidiary legislation: Boarding Station Notice, Origin of Goods Regulations (CARICOM, OECS), Customs (Import Duty on Rum) Order, (… on Whisky) Order (p.51), Customs Regulations (entry, valuation, warehousing, drawback, working hours), Warehouse Notices |
| 154–163 | Conditions of the origin rules, then SRO 42 of 2009: Parliament's resolution replacing the Fifth Schedule with the new CET (passed 22 Jan 2010, **in force 1 Feb 2010**), CET text based on **HS 2007** (CARICOM Secretariat, 13 May 2006) |
| 164–~560 | Schedule of Rates: HEADING / DESCRIPTION / RATE OF DUTY / UNIT / SITC, 6,256 rated 8-digit lines |
| ~564–591 | Conditional duty exemptions, ineligible items |
| 592–611 | Lists A, C, D (rates each member state applies; **Grenada = 6th value**: CET, ANT&BAR, BDS, BEL, DOM, GRENADA …) |

## Inconsistencies and gaps found
1. **EPA orders are missing.** The index (p.1) lists "11. Economic Partnership Agreement Tariff Order" and "12. … Order, 2011", but the text never appears (the file ends with List D, p.614). EU-origin goods therefore cannot get the EPA preferential rate; the calculator warns.
2. **Rum and whisky: the Orders contradict the CET.** Rum Order (SRO 30/1961): EC$9.36 per liquid gallon general / EC$9.00 preferential (strength ≤ proof; EC$9 per proof gallon above). Whisky Order (SRO 33/1961): EC$15.36 / 15.00 per liquid gallon, EC$17.04 / 16.20 per proof gallon above proof. The 2010 CET schedule and List C give Grenada an ad valorem rate for the same goods (e.g. rum 2208.40.10: 35%, CET 25%; whisky 2208.30.10: 35%, CET 15%). The Orders say "notwithstanding any law to the contrary" and are not repealed in the file. Calculator: uses the CET rate and warns with both figures.
3. **"Preferential" is undefined.** The Orders use a preferential rate, but the Customs Regulations' Preferential Tariff part (regs 116–128) is "Revoked. SRO 12 of 1980" — nothing says who qualifies.
4. **Schedule vs Lists disagree on 11 lines** (schedule rate → Grenada's List value): 1005.90.00 maize 25% → Free (List A, p.192); 2208.90.90 spirits 35% → 30% (C, p.223); 2710.11.30 motor spirit Free → 20% (C, p.235); 2714.90.90 5% → 10% (C, p.237); 7113.20.00, 7114.11.00, 7114.19.00, 7117.19.00, 7117.90.00 jewellery 30% → 35% (C, pp.421–422); 8413.30.00 5% → 10% (C, p.480); 8512.40.00 25% → 35% (C, p.510). The other ~286 comparable lines agree. Calculator: uses the List rate, warns "CONFLICT IN THE FILE" on those lines.
5. **Rates for Grenada are not the CET rates**: beef 0201.10.00 CET 40% → schedule/List 30%; poultry wings 0207.14.20 CET 40% → Free; onions 0703.10.10 CET 40% → Free. This is intended (national rates), but it means the CET column must never be used for Grenada.
6. **Old edition.** HS 2007, resolution of Jan 2010; CARICOM has moved to HS 2017/2022. A current product code may not exist; Lists A/C/D are the 2010 versions.
7. **52 lines in unreadable List rows** (values wrapped across lines or specific rates written as "$14.31 per litre"): schedule rate shown with a warning (mostly alcohol and a few dairy lines).
8. **Layout/OCR quirks** handled by the parser: descriptions centred around the code line (text above and below), rate on the last description line, "0207.14.20  Wings" with different spacing, garbled headers ("RATEOFD UTY"), "ational" for "national" (p.156).
9. Not in the file at all: VAT (15% from public sources), customs service charge/fees, excise, the zero-rated food list.

## Parser checks that passed
No duplicated schedule codes; all 96 chapters present; every parent heading ("Other:") has children; the 90 codes that appear in Lists A/C/D but not as rated lines are parent headings.
