import { formatCurrencyValue } from '../../../../../utils/currencyFormat'
import { useLegFinance } from './useLegFinance'

const usd0 = (value) => formatCurrencyValue(value, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })

// The three money cells of a route row: Shipment Revenue, COS and Profit, each the sum of the two legs (see useLegFinance.js for
// how a leg works them out). A leg with nothing to show yet (no shipment built, no GSA terms…) adds nothing and the tooltip says
// which legs were counted; "—" when neither leg has a figure.
function RouteFinanceCells({ route, origin, destination, returnBranch, aircraft, provider }) {
  const context = { origin, destination, returnBranch, aircraft, provider }
  const outbound = useLegFinance(route, 'outbound', context)
  const back = useLegFinance(route, 'return', context)
  const loading = outbound.status === 'loading' || back.status === 'loading'

  const total = (field) => {
    const parts = [
      ['outbound', outbound.data?.[field]],
      ['return', back.data?.[field]],
    ].filter(([, value]) => value != null)
    return { value: parts.length ? parts.reduce((sum, [, value]) => sum + value, 0) : null, legs: parts.map(([leg, value]) => `${leg} ${usd0(value)}`) }
  }
  const revenue = total('revenue')
  const cos = total('cos')
  const profit = total('profit')
  const show = (sum) => (loading ? '…' : sum.value != null ? usd0(sum.value) : '—')
  const title = (sum) => (sum.legs.length ? `Outbound + return leg: ${sum.legs.join(' + ')}` : outbound.error || 'No leg has a figure yet — see the leg cards')
  return (
    <>
      <td className="revenue-streams-view__money is-revenue" title={title(revenue)}>
        {show(revenue)}
      </td>
      <td className="revenue-streams-view__money is-cos" title={title(cos)}>
        {show(cos)}
      </td>
      <td className={`revenue-streams-view__money ${profit.value != null && profit.value < 0 ? 'is-cos' : 'is-revenue'}`} title={title(profit)}>
        {show(profit)}
      </td>
    </>
  )
}

export default RouteFinanceCells
