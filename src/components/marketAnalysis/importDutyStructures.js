// One line per country describing how its import duties are built — shown as the tooltip of the "Import duties structure" column in
// Market Analysis ▸ Country Information. Which countries have a calculator comes from the backend (GET /tax-calc/countries) plus
// Colombia (live DIAN lookup); a country with a calculator but no line here falls back to its tariff source.
export const IMPORT_DUTY_STRUCTURES = {
  jamaica: 'Import duty + additional stamp duty + SCF and environmental levies on the CIF value, then GCT 15% on CIF + duties. Jamaica Customs tariff; CARICOM origin pays no import duty.',
  'united states': 'MFN, special-program (CBERA, USMCA, CAFTA-DR…) or Column 2 duty — ad valorem, specific or compound — on the customs value, plus MPF 0.3464% and HMF 0.125% (sea). No federal VAT; Section 232/301/IEEPA duties are not computed.',
  'trinidad and tobago': 'CARICOM Common External Tariff on the CIF value (ad valorem or TT$ specific); CARICOM origin pays no duty. VAT 12.5% is shown but not counted (recoverable; basic foods zero-rated).',
  bahamas: 'General rate on the CIF value; the Minister may impose up to the maximum variable rate (e.g. 300%) by Order; $ BSD specific rates on some lines; EPA column for EU origin. VAT 10% shown, not counted.',
  'saint lucia': 'CARICOM CET (2012 edition) on the CIF value with Saint Lucia\'s own rates from Lists A and C; EPA phase-down for EU origin; CARICOM origin pays no duty. VAT 12.5% shown, not counted.',
  grenada: 'CARICOM CET (HS 2007) on the CIF value using the Grenadian own rates from Lists A and C (they replace the CET rate); CARICOM origin pays no duty; rum and whisky also have 1961 Orders that conflict with the CET. VAT 15% shown, not counted.',
  barbados: 'Barbados Customs Tariff (S.I. 2019 No. 57): duty on the CIF value, 60% on Part 1 Section B goods, a Special Safeguard additional duty on Section C goods when the price is below the trigger price, inspection fee / countervailing duty (T&T dairy) / excise where printed, and VAT at the rate printed on each line (17.5% or 0%). CARICOM origin pays no duty.',
  colombia: 'Gravamen arancelario and IVA read live from DIAN\'s tariff consultation for the product\'s HS code.',
}

export const COLOMBIA_CALCULATOR = { country: 'Colombia', source: 'DIAN MUISCA WebArancel (live lookup)' }
