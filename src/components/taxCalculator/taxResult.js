// One result shape for every import country, always PER 1 KG in USD, so the page shows them all the same way:
//   { country, goodsUsd, valueBasis: { name, formula, amountUsd }, taxes: [{ name, rate, basis, formula, amount, recoverable, note }],
//     totalTaxUsd, landedUsd, multiplier, pctOfGoods, complete, notes, warnings, sources, line: { code, path } | null }

const usd = (value) => `USD ${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`
const pctText = (rate) => `${Number(rate).toLocaleString('en-US', { maximumFractionDigits: 4 })}%`

// A country that has a tariff file (Jamaica, United States): POST /tax-calc/{country}/calculate answered for quantity_kg = 1.
export function fromTariffResult(country, api) {
  const goods = api.inputs.goods_value_usd
  return {
    country,
    goodsUsd: goods,
    valueBasis: { name: api.value_basis.name, formula: api.value_basis.formula, amountUsd: api.value_basis.amount_usd },
    taxes: api.taxes.map((tax) => ({ name: tax.name, rate: tax.rate, basis: tax.basis, formula: tax.formula, amount: tax.amount, recoverable: tax.recoverable, note: tax.note })),
    totalTaxUsd: api.total_tax_usd,
    landedUsd: api.landed_cost_usd,
    multiplier: goods > 0 ? api.total_tax_usd / goods : null,
    pctOfGoods: api.total_pct_of_goods,
    complete: api.complete,
    notes: api.notes || [],
    warnings: api.warnings || [],
    sources: api.sources || [],
    line: api.line ? { code: api.line.code, path: api.line.path } : null,
  }
}

// Colombia: the Gravamen and IVA DIAN publishes (POST /tax-calc/colombia/dian/calculate) applied to the price of 1 kg.
// `lookup` is the DIAN TaxLookupResult the rates came from; `calc` the pure calculator's answer.
export function fromDianCalculation(price, lookup, calc) {
  const taxes = []
  if (calc.gravamen.amount != null) {
    taxes.push({
      name: 'Gravamen arancelario',
      rate: `${pctText(calc.gravamen.rate)}${calc.gravamen.validFrom ? ` (since ${calc.gravamen.validFrom})` : ''}`,
      basis: 'Customs value',
      formula: `${usd(price)} × ${pctText(calc.gravamen.rate)}`,
      amount: calc.gravamen.amount,
      recoverable: false,
      note: '',
    })
  }
  if (calc.iva.amount != null) {
    const tag = calc.iva.classification === 'excluded' ? 'EXCLUIDO' : calc.iva.classification === 'exempt' ? 'EXENTO' : ''
    taxes.push({
      name: 'IVA',
      rate: calc.iva.rate != null ? `${pctText(calc.iva.rate)}${calc.iva.validFrom ? ` (since ${calc.iva.validFrom})` : ''}` : '—',
      basis: 'Customs value + Gravamen',
      formula: calc.iva.base != null ? `${usd(calc.iva.base)} × ${pctText(calc.iva.rate)}` : 'not listed: 0',
      amount: calc.iva.amount,
      recoverable: false,
      note: tag ? `DIAN lists it as ${tag}` : '',
    })
  }
  const complete = calc.status === 'ok'
  const warnings = [...(calc.warnings || []), ...(lookup.warnings || [])]
  return {
    country: 'Colombia',
    goodsUsd: price,
    valueBasis: { name: 'Customs value (price of 1 kg)', formula: `${usd(price)} × 1 kg`, amountUsd: price },
    taxes,
    totalTaxUsd: calc.totalTaxes ?? 0,
    landedUsd: calc.totalWithTaxes ?? price,
    multiplier: price > 0 && calc.totalTaxes != null ? calc.totalTaxes / price : null,
    pctOfGoods: price > 0 && calc.totalTaxes != null ? Math.round((calc.totalTaxes / price) * 10000) / 100 : null,
    complete,
    notes: calc.notes || [],
    warnings: complete ? warnings : [...warnings, 'A tax is not a plain percentage, so it was not computed: the total is a minimum.'],
    sources: [`${lookup.source.system} — code ${lookup.source.resolvedHsCode}, consulted ${lookup.source.consultationDate}${lookup.source.fromCache ? ' (cached)' : ''}`],
    line: { code: lookup.query.resolvedHsCode, path: lookup.product.description || '' },
  }
}
