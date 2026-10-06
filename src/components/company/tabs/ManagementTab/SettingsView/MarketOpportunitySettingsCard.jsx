import { useEffect, useState } from 'react'
import { fetchMarketOpportunitySettings, saveMarketOpportunitySettings } from '../../../../../services/marketOpportunitySettings'
import './MarketOpportunitySettingsCard.css'

const TABS = [
  { key: 'margin', label: 'Market opportunity margin' },
  { key: 'destination', label: 'Destination Market' },
]

// '' while typing, a number otherwise
const toDraft = (value) => (value == null ? '' : String(value))
const toNumber = (text) => (text === '' || text == null ? null : Number(text))
const draftTiers = (tiers) => tiers.map((tier) => ({ ...tier, min: toDraft(tier.min), max: toDraft(tier.max) }))
const draftMarkets = (markets) => markets.map((market) => ({ ...market, min: toDraft(market.min), max: toDraft(market.max), cargo_cap_kg: toDraft(market.cargo_cap_kg),
    sell_pct: toDraft(market.sell_pct),
    min_margin_pct: toDraft(market.min_margin_pct),
    cap_reduction_kg: toDraft(market.cap_reduction_kg),
  }))

function RangeCells({ minValue, maxValue, onMin, onMax, minDisabled, maxDisabled, maxPlaceholder = '' }) {
  return (
    <div className="mo-settings__range">
      <span>between</span>
      <input type="number" min="0" step="any" value={minValue} onChange={(event) => onMin(event.target.value)} disabled={minDisabled} aria-label="From" />
      <span>% and</span>
      <input
        type="number"
        min="0"
        step="any"
        value={maxValue}
        onChange={(event) => onMax(event.target.value)}
        disabled={maxDisabled}
        placeholder={maxPlaceholder}
        aria-label="To"
      />
      <span>%</span>
    </div>
  )
}

// Settings ▸ Market Opportunity settings. "Market opportunity margin" is the rating scale the backend applies to every
// comparison (diff % = source price as a % of the target price — lower is a bigger margin); each range starts where the
// previous one ends, so editing one end moves its neighbour. "Destination Market" holds the Premium / Niche / Wholesaler
// ranges (stored; not used by a calculation yet).
function MarketOpportunitySettingsCard() {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState('margin')
  const [status, setStatus] = useState('loading')
  const [tiers, setTiers] = useState([])
  const [markets, setMarkets] = useState([])
  const [message, setMessage] = useState('')
  const [messageType, setMessageType] = useState('info')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchMarketOpportunitySettings()
      .then((data) => {
        if (cancelled) return
        setTiers(draftTiers(data.margin_tiers))
        setMarkets(draftMarkets(data.destination_markets))
        setStatus('ready')
      })
      .catch((error) => {
        if (cancelled) return
        setMessage(error.message)
        setMessageType('error')
        setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [])

  // The upper end of a range is the lower end of the next one.
  const setTierMax = (index, value) =>
    setTiers((prev) => prev.map((tier, i) => (i === index ? { ...tier, max: value } : i === index + 1 ? { ...tier, min: value } : tier)))
  const setTierMin = (index, value) =>
    setTiers((prev) => prev.map((tier, i) => (i === index ? { ...tier, min: value } : i === index - 1 ? { ...tier, max: value } : tier)))
  const setMarket = (index, field, value) => setMarkets((prev) => prev.map((market, i) => (i === index ? { ...market, [field]: value } : market)))

  const handleSave = async () => {
    setSaving(true)
    setMessage('')
    try {
      const saved = await saveMarketOpportunitySettings({
        margin_tiers: tiers.map((tier) => ({ rating: tier.rating, min: toNumber(tier.min), max: toNumber(tier.max) })),
        destination_markets: markets.map((market) => ({
          key: market.key,
          label: market.label,
          min: toNumber(market.min),
          max: toNumber(market.max),
          cargo_cap_kg: toNumber(market.cargo_cap_kg),
          sell_pct: toNumber(market.sell_pct),
          min_margin_pct: toNumber(market.min_margin_pct),
          cap_reduction_kg: toNumber(market.cap_reduction_kg),
        })),
      })
      setTiers(draftTiers(saved.margin_tiers))
      setMarkets(draftMarkets(saved.destination_markets))
      setMessage('Saved. Saved comparisons were re-rated with the new margin scale.')
      setMessageType('success')
    } catch (error) {
      setMessage(error.message)
      setMessageType('error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="settings-view__card">
      <button type="button" className="settings-view__card-toggle" onClick={() => setOpen((prev) => !prev)} aria-expanded={open}>
        <span className={`settings-view__tax-chevron ${open ? 'is-expanded' : ''}`}>▸</span>
        <div className="settings-view__section-heading">
          <h4>Market Opportunity settings</h4>
          <p>The opportunity-rating margins Market Opportunities uses, and the destination market categories.</p>
        </div>
      </button>

      {open && (
        <>
          <div className="mo-settings__tabs" role="tablist">
            {TABS.map((item) => (
              <button
                key={item.key}
                type="button"
                role="tab"
                aria-selected={tab === item.key}
                className={`mo-settings__tab ${tab === item.key ? 'is-active' : ''}`}
                onClick={() => setTab(item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>

          {status === 'loading' && <p className="mo-settings__hint">Loading…</p>}
          {status === 'ready' && tab === 'margin' && (
            <div className="mo-settings__list">
              <p className="mo-settings__hint">
                Diff % is the source price as a percentage of the target market&apos;s price: the lower it is, the bigger the margin. Each range starts where the previous one ends.
              </p>
              {tiers.map((tier, index) => (
                <div key={tier.rating} className="mo-settings__row">
                  <strong>{tier.rating}</strong>
                  <RangeCells
                    minValue={tier.min}
                    maxValue={tier.max}
                    onMin={(value) => setTierMin(index, value)}
                    onMax={(value) => setTierMax(index, value)}
                    minDisabled={index === 0}
                    maxDisabled={index === tiers.length - 1}
                    maxPlaceholder={index === tiers.length - 1 ? 'no limit' : ''}
                  />
                </div>
              ))}
            </div>
          )}
          {status === 'ready' && tab === 'destination' && (
            <div className="mo-settings__list">
              <p className="mo-settings__hint">The range each destination market category covers (the product&apos;s DDP price as a % of its target price) and its Cargo Cap — the most kg of one product of that category the Shipment builder loads — and its suggested sell price rule (wholesalers: a % of the target price; niche and premium: the profit % over the DDP price). The builder fills wholesalers first, then niche markets, then premium.</p>
              {markets.map((market, index) => (
                <div key={market.key} className="mo-settings__row">
                  <strong>{market.label}</strong>
                  <RangeCells
                    minValue={market.min}
                    maxValue={market.max}
                    onMin={(value) => setMarket(index, 'min', value)}
                    onMax={(value) => setMarket(index, 'max', value)}
                  />
                  <label className="mo-settings__cap">
                    Cargo Caps
                    <input
                      type="number"
                      min="0"
                      step="any"
                      value={market.cargo_cap_kg}
                      onChange={(event) => setMarket(index, 'cargo_cap_kg', event.target.value)}
                      aria-label={`${market.label} cargo cap in kg`}
                    />
                    <span>kg</span>
                  </label>
                  <label className="mo-settings__cap" title={market.key === 'wholesalers' ? 'Suggested sell price = this % of the target price' : 'Suggested sell price = the DDP price plus this % of profit'}>
                    {market.key === 'wholesalers' ? 'Sell at (% of target price)' : 'Profit over DDP'}
                    <input
                      type="number"
                      min="0"
                      step="any"
                      value={market.sell_pct}
                      onChange={(event) => setMarket(index, 'sell_pct', event.target.value)}
                      aria-label={`${market.label} sell price %`}
                    />
                    <span>%</span>
                  </label>
                  {market.key === 'wholesalers' && (
                    <>
                      <label
                        className="mo-settings__cap"
                        title="A wholesale product whose profit margin ((sale price − cost) / cost) is below this loses the cap reduction from its cargo cap"
                      >
                        Min profit margin
                        <input
                          type="number"
                          min="0"
                          step="any"
                          value={market.min_margin_pct}
                          onChange={(event) => setMarket(index, 'min_margin_pct', event.target.value)}
                          aria-label="Wholesalers minimum profit margin %"
                        />
                        <span>%</span>
                      </label>
                      <label className="mo-settings__cap" title="Kg taken off the cargo cap of a wholesale product whose margin is under the minimum">
                        Cap reduction
                        <input
                          type="number"
                          min="0"
                          step="any"
                          value={market.cap_reduction_kg}
                          onChange={(event) => setMarket(index, 'cap_reduction_kg', event.target.value)}
                          aria-label="Wholesalers cap reduction in kg"
                        />
                        <span>kg</span>
                      </label>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}

          {status === 'ready' && (
            <button type="button" className="settings-view__btn" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
          )}
          {message && <p className={`mo-settings__message is-${messageType}`}>{message}</p>}
        </>
      )}
    </div>
  )
}

export default MarketOpportunitySettingsCard
