import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchCountryProductPrices, fetchMarketOpportunityExchangeRate } from '../../services/marketOpportunities'
import { fetchRagCountries } from '../../services/ragFiles'
import { calculateTax, fetchTaxCountries, refreshTariffData, searchTariffLines } from '../../services/taxCalculator'
import { computeTaxMultipliers, fetchTaxMultipliers, formatMultiplier, productKey, suggestTariffLine } from '../../services/taxMultipliers'
import { EMPTY_FORM, useTaxCalcStore } from '../../store/useTaxCalcStore'
import { usePersistentSet } from '../../utils/usePersistentSet'
import { formatCurrencyValue, formatDualCurrency } from '../../utils/currencyFormat'
import './TaxCalculatorView.css'

const num = (text) => (text === '' || text == null || Number.isNaN(Number(text)) ? null : Number(text))
const digitsOf = (text) => (text || '').replace(/\D/g, '')

function TaxCalculatorView() {
  const { destination, origin, query, product, line, lineNote, form, result, history, update, setForm, addHistory, removeHistory, clearHistory } = useTaxCalcStore()

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
  const [countries, setCountries] = useState([])
  const [originNames, setOriginNames] = useState([])
  const [originProducts, setOriginProducts] = useState(null) // null while loading
  const [multipliers, setMultipliers] = useState(new Map())
  const [productFilter, setProductFilter] = useState('')
  const [lines, setLines] = useState(null)
  const [searching, setSearching] = useState(false)
  const [rate, setRate] = useState(null) // local currency units per USD
  const [error, setError] = useState('')
  const [updating, setUpdating] = useState(false)
  const [priceChoices, setPriceChoices] = useState([]) // portfolio products that could give the price of a searched tariff line
  const previousDestination = useRef(destination)

  const info = countries.find((item) => item.country === destination)
  const currency = info?.currency || 'USD'

  // ------------------------------------------------------------ loading
  useEffect(() => {
    fetchTaxCountries()
      .then((data) => {
        setCountries(data.countries)
        if (!data.countries.some((item) => item.country === useTaxCalcStore.getState().destination)) update({ destination: data.countries[0]?.country || '' })
      })
      .catch((err) => setError(err.message))
    fetchRagCountries()
      .then((data) => {
        const names = data.countries.map((item) => item.country)
        setOriginNames(names)
        if (!useTaxCalcStore.getState().origin && names.length > 0) update({ origin: names.includes('Colombia') ? 'Colombia' : names[0] })
      })
      .catch(() => {})
  }, [update])

  useEffect(() => {
    setRate(null)
    if (!currency || currency === 'USD') return
    fetchMarketOpportunityExchangeRate(currency)
      .then((data) => setRate(data.available ? data.rate : null))
      .catch(() => setRate(null))
  }, [currency])

  // the origin's portfolio, with its prices per kg
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

  // every product of the portfolio gets its multiplier for this destination (stored server side), shown in the list
  useEffect(() => {
    setMultipliers(new Map())
    if (!destination || !origin || !originProducts || originProducts.length === 0) return undefined
    let cancelled = false
    computeTaxMultipliers(destination, origin, originProducts)
      .then(() => fetchTaxMultipliers(destination, origin))
      .then((map) => !cancelled && setMultipliers(map))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [destination, origin, originProducts])

  // the tariff search
  useEffect(() => {
    if (!destination || query.trim().length < 2) {
      setLines(null)
      return undefined
    }
    setSearching(true)
    const timer = setTimeout(() => {
      searchTariffLines(destination, query.trim())
        .then((data) => {
          setLines(data.lines)
          setError('')
        })
        .catch((err) => setError(err.message))
        .finally(() => setSearching(false))
    }, 300)
    return () => clearTimeout(timer)
  }, [destination, query])

  // a destination change (not the first render): the product's tariff line belongs to the old destination
  useEffect(() => {
    if (previousDestination.current === destination) return
    previousDestination.current = destination
    setLines(null)
    setPriceChoices([])
    update({ line: null, lineNote: '', result: null })
    if (useTaxCalcStore.getState().product) chooseProduct(useTaxCalcStore.getState().product, { keepPrice: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [destination])

  // ------------------------------------------------------------ choices
  async function chooseProduct(item, { keepPrice = false } = {}) {
    setError('')
    setPriceChoices([])
    update({ product: item, result: null })
    if (!keepPrice) setForm({ price: item.priceUsdPerKg != null ? String(Number(item.priceUsdPerKg.toFixed(4))) : '' })
    try {
      const suggestion = await suggestTariffLine(useTaxCalcStore.getState().destination, { name: item.name, hsCode: item.hsCode, origin: useTaxCalcStore.getState().origin, priceUsdPerKg: item.priceUsdPerKg })
      update({ line: suggestion.line, lineNote: suggestion.line ? suggestion.note || '' : 'No tariff line was found automatically — search the tariff below.' })
    } catch (err) {
      setError(err.message)
    }
  }

  function chooseLine(item) {
    update({ line: item, lineNote: '', result: null })
    // a portfolio product of the origin under the same HS code gives the price per kg
    const code = digitsOf(item.code).slice(0, 6)
    const words = query.toLowerCase().split(/\s+/).filter((word) => word.length > 2 && !/^\d+$/.test(word))
    const same = (originProducts || []).filter((p) => p.hsCode && digitsOf(p.hsCode).slice(0, 6) === code)
    const named = same.filter((p) => words.length > 0 && words.every((word) => p.name.toLowerCase().includes(word.replace(/e?s$/, ''))))
    const pool = named.length > 0 ? named : same
    const withPrice = pool.filter((p) => p.priceUsdPerKg != null)
    if (withPrice.length === 1) {
      update({ product: withPrice[0] })
      setForm({ price: String(Number(withPrice[0].priceUsdPerKg.toFixed(4))) })
      setPriceChoices([])
    } else {
      setPriceChoices(withPrice.slice(0, 30))
    }
  }

  const goods = useMemo(() => (num(form.price) != null && num(form.quantity) != null ? num(form.price) * num(form.quantity) : null), [form.price, form.quantity])
  const canCalculate = Boolean(line) && goods != null && num(form.quantity) > 0

  const calculate = async () => {
    setError('')
    try {
      const data = await calculateTax(destination, {
        code: line.code,
        price_per_kg_usd: num(form.price),
        quantity_kg: num(form.quantity),
        quantity_units: num(form.units),
        origin: origin || null,
        commercial_importer: form.commercial,
      })
      update({ result: data })
      addHistory({ id: `${Date.now()}`, savedAt: new Date().toISOString(), destination, origin, product, line, lineNote, form, result: data })
    } catch (err) {
      setError(err.message)
      update({ result: null })
    }
  }

  const updateData = async () => {
    setUpdating(true)
    setError('')
    try {
      const updated = await refreshTariffData(destination)
      setCountries((current) => current.map((item) => (item.country === destination ? updated : item)))
    } catch (err) {
      setError(err.message)
    } finally {
      setUpdating(false)
    }
  }

  const loadHistory = (entry) => {
    update({ destination: entry.destination, origin: entry.origin, product: entry.product, line: entry.line, lineNote: entry.lineNote, form: entry.form, result: entry.result })
  }

  const money = (usd, digits = 2) => {
    const options = { minimumFractionDigits: digits, maximumFractionDigits: digits }
    return rate && currency !== 'USD' ? formatDualCurrency(usd * rate, currency, usd, options) : formatCurrencyValue(usd, 'USD', options)
  }

  const shownProducts = useMemo(() => {
    const words = productFilter.toLowerCase().split(/\s+/).filter(Boolean)
    return (originProducts || []).filter((p) => words.every((word) => `${p.name} ${p.category || ''}`.toLowerCase().includes(word)))
  }, [originProducts, productFilter])
  const resultMultiplier = result && result.inputs.goods_value_usd > 0 ? result.total_tax_usd / result.inputs.goods_value_usd : null

  return (
    <div className="panel-surface tax-calc">
      <header className="tax-calc__header">
        <button type="button" className="tax-calc__toggle" onClick={togglePanel} aria-expanded={!collapsed}>
          <span className={`tax-calc__chevron ${collapsed ? '' : 'is-open'}`}>▸</span>
          <h3>Tax Calculator</h3>
        </button>
        <p>
          The import taxes of a shipment, calculated from each country’s published tariff. Choose the countries, pick the product, and enter the quantity. No AI is involved: every
          figure comes with its formula. Freight and insurance are handled in the logistics module, so they are not part of this calculation.
        </p>
      </header>

      {!collapsed && (
        <>
      {error && <p className="tax-calc__error">{error}</p>}

      <section className="tax-calc__section">
        <h4>1 · Countries</h4>
        <div className="tax-calc__countries">
          <label>
            Buying from (origin)
            <select value={origin} onChange={(event) => update({ origin: event.target.value, result: null })}>
              {originNames.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <div className="tax-calc__destination">
            <span>Importing into (destination)</span>
            <div className="tax-calc__tabs" role="tablist">
              {countries.map((item) => (
                <button key={item.country} type="button" role="tab" aria-selected={item.country === destination} className={`tax-calc__tab ${item.country === destination ? 'is-active' : ''}`} onClick={() => update({ destination: item.country })}>
                  {item.country}
                </button>
              ))}
            </div>
          </div>
        </div>
        {info && (
          <p className="tax-calc__hint">
            Tariff data: {info.source} · {info.lines.toLocaleString('en-US')} lines · {info.data_date ? `file from ${info.data_date}` : 'not loaded'}
            {info.can_refresh && (
              <button type="button" className="tax-calc__link" onClick={updateData} disabled={updating} title={info.refresh_note}>
                {updating ? 'Updating…' : 'Update tariff data'}
              </button>
            )}
          </p>
        )}
      </section>

      <section className="tax-calc__section">
        <h4>2 · Product</h4>
        <div className="tax-calc__portfolio">
          <div className="tax-calc__portfolio-head">
            <strong>{origin ? `${origin}’s product portfolio` : 'Product portfolio'}</strong>
            <input type="text" value={productFilter} onChange={(event) => setProductFilter(event.target.value)} placeholder="Filter the list…" aria-label="Filter the portfolio" />
          </div>
          {originProducts === null && <p className="tax-calc__hint">Loading {origin}’s products…</p>}
          {originProducts && originProducts.length === 0 && <p className="tax-calc__hint">{origin} has no products in its portfolio — search the tariff below instead.</p>}
          {originProducts && originProducts.length > 0 && (
            <ul className="tax-calc__results tax-calc__results--products" aria-label="Portfolio products">
              {shownProducts.map((item) => {
                const multiplier = multipliers.get(productKey(item.name))
                return (
                  <li key={item.name}>
                    <button type="button" className={product?.name === item.name ? 'is-selected' : ''} onClick={() => chooseProduct(item)}>
                      <strong>{item.name}</strong>
                      <span>
                        {item.category || 'Uncategorized'}
                        {item.hsCode ? ` · HS ${item.hsCode}` : ''}
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

        <p className="tax-calc__or">…or any other product — search {destination || 'the destination'}’s tariff by name or code:</p>
        <input type="text" className="tax-calc__search" value={query} onChange={(event) => update({ query: event.target.value })} placeholder="Product name (tomatoes, chicken wings…) or tariff code (0702…)" aria-label="Search the tariff" />
        {searching && <p className="tax-calc__hint">Searching…</p>}
        {lines && lines.length === 0 && <p className="tax-calc__hint">No tariff line matches “{query}”. Try another word, or a code.</p>}
        {lines && lines.length > 0 && (
          <ul className="tax-calc__results">
            {lines.map((item) => (
              <li key={item.code}>
                <button type="button" className={line?.code === item.code ? 'is-selected' : ''} onClick={() => chooseLine(item)}>
                  <strong>{item.code}</strong>
                  <span>{item.path}</span>
                  <em>{item.summary}</em>
                </button>
              </li>
            ))}
          </ul>
        )}

        {priceChoices.length > 0 && (
          <label className="tax-calc__price-choice">
            Price per kg from {origin}’s portfolio
            <select
              value=""
              onChange={(event) => {
                const picked = priceChoices.find((p) => p.name === event.target.value)
                if (picked) {
                  update({ product: picked })
                  setForm({ price: String(Number(picked.priceUsdPerKg.toFixed(4))) })
                  setPriceChoices([])
                }
              }}
            >
              <option value="">Choose a product to fill in its price…</option>
              {priceChoices.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name} — {formatCurrencyValue(p.priceUsdPerKg, 'USD')}/kg
                </option>
              ))}
            </select>
          </label>
        )}

        {line && (
          <div className="tax-calc__selected">
            <strong>{line.code}</strong> <span>{line.path}</span>
            <em>{line.summary}</em>
            {lineNote && <small>{lineNote}</small>}
            {product && (
              <small>
                Product: {product.name}
                {product.priceUsdPerKg != null ? ` — ${origin} price ${formatCurrencyValue(product.priceUsdPerKg, 'USD')}/kg (${product.source})` : ''}
              </small>
            )}
          </div>
        )}
      </section>

      <section className="tax-calc__section">
        <h4>3 · Quantity</h4>
        <div className="tax-calc__form">
          <label>
            Price per kg (USD)
            <input type="number" min="0" step="any" value={form.price} onChange={(event) => setForm({ price: event.target.value })} />
          </label>
          <label>
            Quantity (kg)
            <input type="number" min="0" step="any" value={form.quantity} onChange={(event) => setForm({ quantity: event.target.value })} />
          </label>
          {line?.units && line.units.toLowerCase() !== 'kg' && (
            <label>
              Quantity in {line.units}
              <input type="number" min="0" step="any" value={form.units} onChange={(event) => setForm({ units: event.target.value })} />
            </label>
          )}
          <label className="tax-calc__check">
            <input type="checkbox" checked={form.commercial} onChange={(event) => setForm({ commercial: event.target.checked })} /> Registered commercial importer
          </label>
        </div>
        <div className="tax-calc__actions">
          <button type="button" className="tax-calc__primary" onClick={calculate} disabled={!canCalculate}>
            Calculate taxes
          </button>
          {goods != null && <span className="tax-calc__hint">Goods value: {formatCurrencyValue(goods, 'USD')}</span>}
          {!line && <span className="tax-calc__hint">Choose a product or a tariff line first.</span>}
          <button type="button" className="tax-calc__link" onClick={() => update({ product: null, line: null, lineNote: '', query: '', form: EMPTY_FORM, result: null })}>
            Clear
          </button>
        </div>
      </section>

      {result && (
        <section className="tax-calc__result" aria-label="Result">
          <div className="tax-calc__headline">
            <div className="tax-calc__total tax-calc__total--final">
              <span>Cost of the goods with import taxes paid</span>
              <strong>{money(result.landed_cost_usd)}</strong>
              <em>{result.inputs.quantity_kg > 0 && `${money(result.landed_cost_usd / result.inputs.quantity_kg, 3)} per kg`}</em>
            </div>
            <div className="tax-calc__total">
              <span>Import taxes{result.complete ? '' : ' (at least — see warnings)'}</span>
              <strong>{money(result.total_tax_usd)}</strong>
              <em>
                {result.total_per_kg_usd != null && `${formatCurrencyValue(result.total_per_kg_usd, 'USD', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} per kg · `}
                {resultMultiplier != null && `tax multiplier ${formatMultiplier(resultMultiplier)} (${result.total_pct_of_goods?.toLocaleString('en-US')}% of the goods value)`}
              </em>
            </div>
          </div>
          <table className="tax-calc__table">
            <thead>
              <tr>
                <th>Tax</th>
                <th>Rate</th>
                <th>Charged on</th>
                <th>Calculation</th>
                <th className="is-num">Amount</th>
              </tr>
            </thead>
            <tbody>
              <tr className="tax-calc__basis">
                <td colSpan={3}>{result.value_basis.name}</td>
                <td>{result.value_basis.formula}</td>
                <td className="is-num">{formatCurrencyValue(result.value_basis.amount_usd, 'USD')}</td>
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
                  <td className="is-num">{money(tax.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <table className="tax-calc__table tax-calc__final" aria-label="Cost of the goods">
            <caption>Cost of the goods</caption>
            <tbody>
              <tr>
                <td>Goods</td>
                <td className="is-num">{money(result.inputs.goods_value_usd)}</td>
              </tr>
              <tr>
                <td>+ Import taxes{result.complete ? '' : ' (at least)'}</td>
                <td className="is-num">{money(result.total_tax_usd)}</td>
              </tr>
              <tr className="tax-calc__final-total">
                <td>= Cost with import taxes paid</td>
                <td className="is-num">{money(result.landed_cost_usd)}</td>
              </tr>
              {result.inputs.quantity_kg > 0 && (
                <tr className="tax-calc__final-total">
                  <td>Per kg ({result.inputs.quantity_kg.toLocaleString('en-US')} kg)</td>
                  <td className="is-num">{money(result.landed_cost_usd / result.inputs.quantity_kg, 3)}</td>
                </tr>
              )}
              {result.taxes.some((tax) => tax.recoverable) && (
                <tr className="is-recoverable">
                  <td>Cash paid at the border also includes the advance payments marked above (credited later, so not part of the cost)</td>
                  <td className="is-num">{money(result.taxes.filter((tax) => tax.recoverable).reduce((sum, tax) => sum + tax.amount, 0))}</td>
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
        <section className="tax-calc__section" aria-label="Calculations performed">
          <h4>
            Calculations performed{' '}
            <button type="button" className="tax-calc__link" onClick={clearHistory}>
              Clear all
            </button>
          </h4>
          <ul className="tax-calc__history">
            {history.map((entry) => (
              <li key={entry.id}>
                <button type="button" onClick={() => loadHistory(entry)} title="Open this calculation">
                  <strong>{entry.product?.name || entry.line?.path?.split(' > ').pop() || entry.line?.code}</strong>
                  <span>
                    {entry.origin || '—'} → {entry.destination} · {Number(entry.result.inputs.quantity_kg).toLocaleString('en-US')} kg · taxes {formatCurrencyValue(entry.result.total_tax_usd, 'USD')} · with taxes{' '}
                    {formatCurrencyValue(entry.result.landed_cost_usd, 'USD')}
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
