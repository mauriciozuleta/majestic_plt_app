import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchCountryProductPrices } from '../../services/marketOpportunities'
import { fetchRagCountries } from '../../services/ragFiles'
import { calculateTax, fetchTaxCountries, refreshTariffData } from '../../services/taxCalculator'
import { computeTaxMultipliers, fetchTaxMultipliers, formatMultiplier, productKey, suggestTariffLine } from '../../services/taxMultipliers'
import { useTaxCalcStore } from '../../store/useTaxCalcStore'
import { usePersistentSet } from '../../utils/usePersistentSet'
import { formatCurrencyValue } from '../../utils/currencyFormat'
import DianLookupPanel from './DianLookupPanel'
import { fromTariffResult } from './taxResult'
import { useDianFlow } from './useDianFlow'
import './TaxCalculatorView.css'

const num = (text) => (text === '' || text == null || Number.isNaN(Number(text)) ? null : Number(text))

// Colombia has no tariff file: its Gravamen and IVA are read from DIAN's site for the product's HS code (backend/tax_calc/colombia_dian/).
const COLOMBIA = { country: 'Colombia', kind: 'dian', source: 'DIAN MUISCA WebArancel (live lookup)', can_refresh: false }

// Every import country works the same way: the export country, the import country, a product from the exporter's list, and the taxes of 1 kg in USD.
function TaxCalculatorView() {
  const { origin, destination, product, line, lineNote, form, result, history, dianLines, update, setForm, addHistory, removeHistory, clearHistory, rememberDianLine } = useTaxCalcStore()

  // The whole panel can be folded away to its header (remembered between visits).
  const [collapsedPanels, setCollapsedPanels] = usePersistentSet('tax-calculator:collapsed')
  const collapsed = collapsedPanels.has('panel')
  const togglePanel = () =>
    setCollapsedPanels((prev) => {
      const next = new Set(prev)
      if (next.has('panel')) next.delete('panel')
      else next.add('panel')
      return next
    })

  const [fileCountries, setFileCountries] = useState([]) // the countries with a tariff file (Jamaica, United States)
  const [originNames, setOriginNames] = useState([])
  const [originProducts, setOriginProducts] = useState(null) // null while loading
  const [multipliers, setMultipliers] = useState(new Map())
  const [productFilter, setProductFilter] = useState('')
  const [candidates, setCandidates] = useState([]) // other tariff lines the product could be under
  const [error, setError] = useState('')
  const [updating, setUpdating] = useState(false)

  const importers = useMemo(() => [...fileCountries.map((item) => ({ ...item, kind: 'file' })), COLOMBIA].sort((a, b) => a.country.localeCompare(b.country)), [fileCountries])
  const info = importers.find((item) => item.country === destination)
  const isDian = info?.kind === 'dian'
  const isFile = info?.kind === 'file'
  const price = num(form.price)

  // ------------------------------------------------------------ loading
  useEffect(() => {
    fetchTaxCountries()
      .then((data) => setFileCountries(data.countries))
      .catch((err) => setError(err.message))
    fetchRagCountries()
      .then((data) => {
        const names = data.countries.map((item) => item.country)
        setOriginNames(names)
        if (!useTaxCalcStore.getState().origin && names.length > 0) update({ origin: names.includes('Colombia') ? 'Colombia' : names[0] })
      })
      .catch(() => {})
  }, [update])

  // a valid import country (never the export country itself)
  useEffect(() => {
    if (importers.length === 0) return
    const current = useTaxCalcStore.getState().destination
    if (!current || !importers.some((item) => item.country === current) || current === origin) {
      const next = importers.find((item) => item.country !== origin)
      if (next && next.country !== current) update({ destination: next.country, line: null, lineNote: '', result: null })
    }
  }, [importers, origin, update])

  // the exporter's portfolio, with its prices per kg
  useEffect(() => {
    if (!origin) return undefined
    let cancelled = false
    setOriginProducts(null)
    fetchCountryProductPrices(origin)
      .then((products) => !cancelled && setOriginProducts(products))
      .catch(() => !cancelled && setOriginProducts([]))
    return () => {
      cancelled = true
    }
  }, [origin])

  // for a country with a tariff file, every product of the portfolio gets its multiplier (stored server side), shown in the list
  useEffect(() => {
    setMultipliers(new Map())
    if (!isFile || !origin || !originProducts || originProducts.length === 0) return undefined
    let cancelled = false
    computeTaxMultipliers(destination, origin, originProducts)
      .then(() => fetchTaxMultipliers(destination, origin))
      .then((map) => !cancelled && setMultipliers(map))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [isFile, destination, origin, originProducts])

  // ------------------------------------------------------------ history
  const record = useCallback(
    (normalized) => {
      const state = useTaxCalcStore.getState()
      if (!normalized || !state.product) return
      addHistory({
        id: `${state.origin}|${state.destination}|${productKey(state.product.name)}`,
        savedAt: new Date().toISOString(),
        origin: state.origin,
        destination: state.destination,
        product: state.product,
        line: state.line,
        price: num(state.form.price),
        result: normalized,
      })
    },
    [addHistory],
  )

  // ------------------------------------------------------------ Colombia (DIAN)
  const onDianResult = useCallback(
    (normalized) => {
      update({ result: normalized })
      record(normalized)
    },
    [update, record],
  )
  const dianFlow = useDianFlow({
    enabled: isDian && Boolean(product),
    hsCode: product?.hsCode || '',
    savedLine: product ? dianLines[productKey(product.name)] : '',
    price,
    onLineChosen: (code) => product && rememberDianLine(productKey(product.name), code),
    onResult: onDianResult,
  })

  // ------------------------------------------------------------ countries with a tariff file
  useEffect(() => {
    if (!isFile || !line || !(price > 0)) return undefined
    let cancelled = false
    const timer = setTimeout(async () => {
      try {
        const api = await calculateTax(destination, { code: line.code, price_per_kg_usd: price, quantity_kg: 1, origin: origin || null, commercial_importer: form.commercial })
        if (cancelled) return
        const normalized = fromTariffResult(destination, api)
        setError('')
        update({ result: normalized })
        record(normalized)
      } catch (err) {
        if (cancelled) return
        setError(err.message)
        update({ result: null })
      }
    }, 350)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [isFile, destination, line?.code, price, origin, form.commercial, update, record]) // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------------ choices
  async function chooseProduct(item, { keepPrice = false, forDestination = destination } = {}) {
    setError('')
    setCandidates([])
    update({ product: item, result: null, line: null, lineNote: '' })
    if (!keepPrice) setForm({ price: item.priceUsdPerKg != null ? String(Number(item.priceUsdPerKg.toFixed(4))) : '' })
    const kind = importers.find((entry) => entry.country === forDestination)?.kind
    if (kind !== 'file') return
    try {
      const suggestion = await suggestTariffLine(forDestination, { name: item.name, hsCode: item.hsCode, origin: useTaxCalcStore.getState().origin, priceUsdPerKg: item.priceUsdPerKg })
      if (useTaxCalcStore.getState().product?.name !== item.name) return // the user already clicked another product
      setCandidates(suggestion.candidates || [])
      update({ line: suggestion.line, lineNote: suggestion.line ? suggestion.note || '' : `No ${forDestination} tariff line was found for this product's HS code.` })
    } catch (err) {
      setError(err.message)
    }
  }

  function changeOrigin(name) {
    setCandidates([])
    update({ origin: name, product: null, line: null, lineNote: '', result: null })
    setForm({ price: '' })
    setProductFilter('')
  }

  function changeDestination(name) {
    setCandidates([])
    update({ destination: name, line: null, lineNote: '', result: null })
    if (product) chooseProduct(product, { keepPrice: true, forDestination: name })
  }

  function chooseLine(code) {
    const picked = candidates.find((item) => item.code === code)
    if (picked) update({ line: picked, lineNote: 'Tariff line chosen by you.', result: null })
  }

  const updateData = async () => {
    setUpdating(true)
    setError('')
    try {
      const updated = await refreshTariffData(destination)
      setFileCountries((current) => current.map((item) => (item.country === destination ? updated : item)))
    } catch (err) {
      setError(err.message)
    } finally {
      setUpdating(false)
    }
  }

  const loadHistory = (entry) => {
    update({ origin: entry.origin, destination: entry.destination, product: entry.product, line: entry.line, lineNote: '', result: entry.result })
    setForm({ price: entry.price != null ? String(entry.price) : '' })
  }

  const shownProducts = useMemo(() => {
    const words = productFilter.toLowerCase().split(/\s+/).filter(Boolean)
    return (originProducts || []).filter((p) => words.every((word) => `${p.name} ${p.category || ''} ${p.hsCode || ''}`.toLowerCase().includes(word)))
  }, [originProducts, productFilter])

  const usd = (value, digits = 2) => formatCurrencyValue(value, 'USD', { minimumFractionDigits: digits, maximumFractionDigits: digits })

  return (
    <div className="panel-surface tax-calc">
      <header className="tax-calc__header">
        <button type="button" className="tax-calc__toggle" onClick={togglePanel} aria-expanded={!collapsed}>
          <span className={`tax-calc__chevron ${collapsed ? '' : 'is-open'}`}>▸</span>
          <h3>Tax Calculator</h3>
        </button>
        <p>
          The import duties and taxes of 1 kg of a product, in USD, from the importing country’s published tariff. Choose the exporting country, the importing country and one of the
          exporter’s products. No AI is involved: every figure comes with its formula. Freight and insurance are handled in the logistics module, so they are not part of this calculation.
        </p>
      </header>

      {!collapsed && (
        <>
          {error && <p className="tax-calc__error">{error}</p>}

          <section className="tax-calc__section">
            <h4>1 · Countries</h4>
            <div className="tax-calc__countries">
              <label>
                Export country (from)
                <select value={origin} onChange={(event) => changeOrigin(event.target.value)}>
                  {originNames.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Import country (to)
                <select value={destination} onChange={(event) => changeDestination(event.target.value)}>
                  {importers.map((item) => (
                    <option key={item.country} value={item.country} disabled={item.country === origin}>
                      {item.country}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {isFile && info && (
              <p className="tax-calc__hint">
                Tariff data: {info.source} · {info.lines?.toLocaleString('en-US')} lines · {info.data_date ? `file from ${info.data_date}` : 'not loaded'}
                {info.can_refresh && (
                  <button type="button" className="tax-calc__link" onClick={updateData} disabled={updating} title={info.refresh_note}>
                    {updating ? 'Updating…' : 'Update tariff data'}
                  </button>
                )}
              </p>
            )}
            {isDian && <p className="tax-calc__hint">Duties and taxes: {info.source} — Gravamen arancelario and IVA, read for the product’s HS code.</p>}
          </section>

          <section className="tax-calc__section">
            <h4>2 · Product</h4>
            <div className="tax-calc__portfolio">
              <div className="tax-calc__portfolio-head">
                <strong>{origin ? `${origin}’s product list` : 'Product list'}</strong>
                <input type="text" value={productFilter} onChange={(event) => setProductFilter(event.target.value)} placeholder="Search the list (name, category or HS code)…" aria-label="Search the product list" />
              </div>
              {originProducts === null && <p className="tax-calc__hint">Loading {origin}’s products…</p>}
              {originProducts && originProducts.length === 0 && <p className="tax-calc__hint">{origin} has no products in its portfolio yet.</p>}
              {originProducts && originProducts.length > 0 && (
                <ul className="tax-calc__results tax-calc__results--products" aria-label="Products">
                  {shownProducts.map((item) => {
                    const multiplier = multipliers.get(productKey(item.name))
                    return (
                      <li key={item.name}>
                        <button type="button" className={product?.name === item.name ? 'is-selected' : ''} onClick={() => chooseProduct(item)}>
                          <strong>{item.name}</strong>
                          <span>
                            {item.category || 'Uncategorized'}
                            {item.hsCode ? ` · HS ${item.hsCode}` : ' · no HS code'}
                          </span>
                          <em>
                            {item.priceUsdPerKg != null ? `${formatCurrencyValue(item.priceUsdPerKg, 'USD')}/kg` : 'no price per kg'}
                            {multiplier && multiplier.tax_multiplier != null ? ` · taxes ${formatMultiplier(multiplier.tax_multiplier)}${multiplier.status === 'review' ? ' (review)' : ''}` : ''}
                          </em>
                        </button>
                      </li>
                    )
                  })}
                  {shownProducts.length === 0 && <li className="tax-calc__hint">No product matches “{productFilter}”.</li>}
                </ul>
              )}
            </div>

            {product && (
              <div className="tax-calc__selected">
                <strong>{product.name}</strong>{' '}
                <span>
                  {origin} → {destination}
                </span>
                <small>
                  {product.category || 'Uncategorized'}
                  {product.hsCode ? ` · HS ${product.hsCode}` : ''}
                  {product.priceUsdPerKg != null ? ` — ${origin} price ${formatCurrencyValue(product.priceUsdPerKg, 'USD')}/kg (${product.source})` : ''}
                </small>
                {isFile && line && (
                  <>
                    <small>
                      Tariff line <strong>{line.code}</strong> — {line.path}
                    </small>
                    {lineNote && <small>{lineNote}</small>}
                    {candidates.length > 1 && (
                      <label className="tax-calc__price-choice">
                        Another tariff line for this product
                        <select value={line.code} onChange={(event) => chooseLine(event.target.value)}>
                          {candidates.map((item) => (
                            <option key={item.code} value={item.code}>
                              {item.code} — {item.path}
                            </option>
                          ))}
                        </select>
                      </label>
                    )}
                  </>
                )}
                {isFile && !line && lineNote && <small>{lineNote}</small>}
              </div>
            )}

            {product && (
              <div className="tax-calc__form">
                <label>
                  Price per kg (USD)
                  <input type="number" min="0" step="any" value={form.price} onChange={(event) => setForm({ price: event.target.value })} />
                </label>
                {destination === 'Jamaica' && (
                  <label className="tax-calc__check">
                    <input type="checkbox" checked={form.commercial} onChange={(event) => setForm({ commercial: event.target.checked })} /> Registered commercial importer
                  </label>
                )}
                {!(price > 0) && <span className="tax-calc__hint">Enter the price of 1 kg to calculate the taxes.</span>}
              </div>
            )}

            {isDian && product && <DianLookupPanel flow={dianFlow} productName={product.name} />}
          </section>

          {result && (
            <section className="tax-calc__result" aria-label="Result">
              <div className="tax-calc__headline">
                <div className="tax-calc__total tax-calc__total--final">
                  <span>1 kg with import taxes paid</span>
                  <strong>{usd(result.landedUsd, 3)}</strong>
                  <em>
                    {result.country} · per 1 kg, in USD
                  </em>
                </div>
                <div className="tax-calc__total">
                  <span>Import taxes per kg{result.complete ? '' : ' (at least — see warnings)'}</span>
                  <strong>{usd(result.totalTaxUsd, 3)}</strong>
                  <em>{result.multiplier != null && `tax multiplier ${formatMultiplier(result.multiplier)} (${result.pctOfGoods?.toLocaleString('en-US')}% of the goods value)`}</em>
                </div>
              </div>
              <table className="tax-calc__table">
                <thead>
                  <tr>
                    <th>Tax</th>
                    <th>Rate</th>
                    <th>Charged on</th>
                    <th>Calculation</th>
                    <th className="is-num">Amount (USD)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="tax-calc__basis">
                    <td colSpan={3}>{result.valueBasis.name}</td>
                    <td>{result.valueBasis.formula}</td>
                    <td className="is-num">{usd(result.valueBasis.amountUsd)}</td>
                  </tr>
                  {result.taxes.map((tax) => (
                    <tr key={tax.name} className={tax.recoverable ? 'is-recoverable' : ''}>
                      <td>
                        {tax.name}
                        {tax.note && <small>{tax.note}</small>}
                      </td>
                      <td>{tax.rate}</td>
                      <td>{tax.basis}</td>
                      <td>{tax.formula}</td>
                      <td className="is-num">{usd(tax.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <table className="tax-calc__table tax-calc__final" aria-label="Cost of 1 kg">
                <caption>Cost of 1 kg</caption>
                <tbody>
                  <tr>
                    <td>Goods</td>
                    <td className="is-num">{usd(result.goodsUsd, 3)}</td>
                  </tr>
                  <tr>
                    <td>+ Import taxes{result.complete ? '' : ' (at least)'}</td>
                    <td className="is-num">{usd(result.totalTaxUsd, 3)}</td>
                  </tr>
                  <tr className="tax-calc__final-total">
                    <td>= 1 kg with import taxes paid</td>
                    <td className="is-num">{usd(result.landedUsd, 3)}</td>
                  </tr>
                  {result.taxes.some((tax) => tax.recoverable) && (
                    <tr className="is-recoverable">
                      <td>Cash paid at the border also includes the advance payments marked above (credited later, so not part of the cost)</td>
                      <td className="is-num">{usd(result.taxes.filter((tax) => tax.recoverable).reduce((sum, tax) => sum + tax.amount, 0))}</td>
                    </tr>
                  )}
                </tbody>
              </table>
              <p className="tax-calc__hint">Freight, insurance, broker, handling and inland transport are not included — they belong to the logistics module.</p>
              {result.notes.length > 0 && (
                <ul className="tax-calc__notes">
                  {result.notes.map((text) => (
                    <li key={text}>{text}</li>
                  ))}
                </ul>
              )}
              {result.warnings.length > 0 && (
                <ul className="tax-calc__warnings">
                  {result.warnings.map((text) => (
                    <li key={text}>{text}</li>
                  ))}
                </ul>
              )}
              <p className="tax-calc__hint">Source: {result.sources.join('; ')}.</p>
            </section>
          )}

          {history.length > 0 && (
            <section className="tax-calc__section" aria-label="Products calculated">
              <h4>
                Products calculated{' '}
                <button type="button" className="tax-calc__link" onClick={clearHistory}>
                  Clear all
                </button>
              </h4>
              <ul className="tax-calc__history">
                {history.map((entry) => (
                  <li key={entry.id}>
                    <button type="button" onClick={() => loadHistory(entry)} title="Open this calculation">
                      <strong>{entry.product?.name}</strong>
                      <span>
                        {entry.origin || '—'} → {entry.destination} · per kg: taxes {formatCurrencyValue(entry.result.totalTaxUsd, 'USD')} · with taxes {formatCurrencyValue(entry.result.landedUsd, 'USD')}
                      </span>
                      <em>{new Date(entry.savedAt).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })}</em>
                    </button>
                    <button type="button" className="tax-calc__remove" onClick={() => removeHistory(entry.id)} aria-label="Remove this calculation">
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  )
}

export default TaxCalculatorView
