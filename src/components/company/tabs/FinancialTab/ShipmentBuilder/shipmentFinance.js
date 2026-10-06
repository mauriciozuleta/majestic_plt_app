import { fetchMarketAnalysisRegions } from '../../../../../services/commercialStructure'
import { fetchCountryProductPrices, fetchMarketOpportunityComparisons } from '../../../../../services/marketOpportunities'
import { marketLevelFor, suggestedSellPrice, UNMATCHED_MARKET_KEY } from '../../../../../services/marketOpportunitySettings'
import { fetchTaxMultipliers, productKey } from '../../../../../services/taxMultipliers'

// The money side of a built shipment (cost, market level, suggested sale price), shared by the shipment cards
// (ShipmentPanel) and the Revenue route table (RouteFinanceCells).

// What a shipment's products are priced from: the comparison's source/target prices and the tax multipliers of its
// countries, plus the countries themselves. Cached for a short while — a page asks for it once per route and leg.
const CONTEXT_TTL_MS = 30000
const contextCache = new Map()

async function loadContext(source, target, needPortfolio) {
  const prices = await fetchMarketOpportunityComparisons(source, [target]).then(async (saved) => {
    const map = new Map(
      (saved.rows || []).map((row) => [productKey(row.product_name), { priceUsdPerKg: row.source_price_normalized, targetPriceUsdPerKg: row.target_price_normalized }]),
    )
    // products with no match in the target market aren't in the comparison: their price is the source portfolio's
    if (needPortfolio(map)) {
      const portfolio = await fetchCountryProductPrices(source).catch(() => [])
      portfolio.forEach((product) => {
        if (!map.has(productKey(product.name))) map.set(productKey(product.name), { priceUsdPerKg: product.priceUsdPerKg, targetPriceUsdPerKg: null, noMatch: true })
      })
    }
    return map
  })
  const multipliers = await fetchTaxMultipliers(target, source).catch(() => new Map())
  return { countries: { source, target }, prices, multipliers }
}

// -> { countries: { source, target }, prices, multipliers }; throws when a leg's airports aren't in an active Market Analysis country
export async function loadShipmentContext(shipment, origin, destination) {
  const regions = await fetchMarketAnalysisRegions()
  const locate = (branch) => {
    for (const row of regions) {
      const country = row.countries.find((entry) => entry.id === branch?.country_id)
      if (country) return country.name
    }
    return null
  }
  const source = locate(origin)
  const target = locate(destination)
  if (!source || !target) throw new Error('The leg’s airports aren’t in an active Market Analysis country.')
  const needPortfolio = (map) => shipment.items.some((item) => !map.has(productKey(item.product_name)))
  const key = `${source}>${target}`
  const cached = contextCache.get(key)
  // a cached context only serves a shipment whose products it already covers
  if (cached && Date.now() - cached.at < CONTEXT_TTL_MS) {
    const context = await cached.promise
    if (!needPortfolio(context.prices)) return context
  }
  const promise = loadContext(source, target, needPortfolio)
  contextCache.set(key, { at: Date.now(), promise })
  promise.catch(() => contextCache.delete(key))
  return promise
}

// The cost chain of one product of a built shipment:
//   FCA = kg x the origin country's price per kg (the one the saved Market Opportunities comparison used)
//   DAP = kg x the leg's price per kg (air fare); DAP subtotal = FCA + DAP
//   DDP at Terminal = DAP subtotal x the product's tax multiplier (Market Opportunities
//   origin -> destination comparison); DDP total = DAP subtotal + those taxes.
// Any figure that can't be worked out is null.
export function costsFor(item, { prices, multipliers, airfarePerKg }) {
  const fcaPerKg = prices?.get(productKey(item.product_name))?.priceUsdPerKg ?? null
  const fca = fcaPerKg != null ? item.kg * fcaPerKg : null
  const dap = airfarePerKg != null ? item.kg * airfarePerKg : null
  const subtotal = fca != null && dap != null ? fca + dap : null
  const multiplier = multipliers?.get(productKey(item.product_name))?.tax_multiplier ?? null
  const taxes = subtotal != null && multiplier != null ? subtotal * multiplier : null
  const ddp = subtotal != null && taxes != null ? subtotal + taxes : null
  return { fcaPerKg, fca, dap, subtotal, multiplier, taxes, ddp }
}

// Each product's cost, market level (its DDP per kg as a % of the target price against the Destination Market ranges; a product
// with no match in the target market is a niche market product) and suggested sale price (that level's rule x its weight), and the
// shipment's totals — null unless every product has one.
// -> { items: Map(item -> { cost, level, sale: { perKg, total, note } }), ddpTotal, saleTotal }
export function financeForShipment(shipment, context, airfarePerKg, destinationMarkets) {
  const items = new Map()
  shipment.items.forEach((item) => {
    const cost = costsFor(item, { prices: context?.prices, multipliers: context?.multipliers, airfarePerKg })
    const entry = context?.prices?.get(productKey(item.product_name))
    const ddpPerKg = cost.ddp != null && item.kg ? cost.ddp / item.kg : null
    let level
    if (entry?.noMatch) {
      const niche = destinationMarkets.find((market) => market.key === UNMATCHED_MARKET_KEY)
      level = { level: niche?.label ?? 'Niche Markets', key: UNMATCHED_MARKET_KEY, share: null, configured: true, noMatch: true }
    } else {
      level = marketLevelFor(ddpPerKg, entry?.targetPriceUsdPerKg ?? null, destinationMarkets)
    }
    const sell = suggestedSellPrice(level?.key, ddpPerKg, entry?.targetPriceUsdPerKg ?? null, destinationMarkets)
    items.set(item, { cost, level, sale: { perKg: sell.value, total: sell.value != null ? sell.value * item.kg : null, note: sell.note } })
  })
  const all = [...items.values()]
  const complete = (pick) => (all.length && all.every((entry) => pick(entry) != null) ? all.reduce((sum, entry) => sum + pick(entry), 0) : null)
  return { items, ddpTotal: complete((entry) => entry.cost.ddp), saleTotal: complete((entry) => entry.sale.total) }
}
