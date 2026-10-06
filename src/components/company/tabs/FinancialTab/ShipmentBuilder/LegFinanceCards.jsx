import { formatCurrencyValue } from '../../../../../utils/currencyFormat'
import { useLegFinance } from './useLegFinance'

const usd0 = (value) => formatCurrencyValue(value, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })

// The three cards of a leg row beside its Shipment builder card: Shipment Revenue, COS (red) and Profit — see useLegFinance.js
// for how each leg works them out.
function LegFinanceCards({ route, legKey, branches }) {
  const { status, data, error } = useLegFinance(route, legKey, branches)
  const empty = error || (legKey === 'outbound' && !route.outbound_shipment ? 'No shipment built for this leg yet' : undefined)
  const show = (value) => (status === 'loading' ? '…' : data && value != null ? usd0(value) : '—')
  const card = (label, value, note, tone) => (
    <div className={`revenue-streams-view__metric is-${legKey}`} title={note ?? empty}>
      <span className="revenue-streams-view__metric-label">{label}</span>
      <span className={`revenue-streams-view__metric-value ${tone ? `revenue-streams-view__money is-${tone}` : ''}`}>{show(value)}</span>
    </div>
  )
  return (
    <>
      {card('Shipment Revenue', data?.revenue, data?.notes?.revenue, 'revenue')}
      {card('COS', data?.cos, data?.notes?.cos, 'cos')}
      {card('Profit', data?.profit, data?.notes?.profit, data?.profit != null && data.profit < 0 ? 'cos' : 'revenue')}
    </>
  )
}

export default LegFinanceCards
