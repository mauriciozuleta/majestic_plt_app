import { useEffect, useState } from 'react'
import './HomeView.css'
import MetricCard from './MetricCard'
import StartupInvestmentSummaryCard from './StartupInvestmentSummaryCard'
import PhaseSummaryCards from './PhaseSummaryCards'
import PlaceholderMetricCard from './PlaceholderMetricCard'
import { fetchSamOverviewSummary, fetchTamGlobalOverviewSummary } from '../../services/globalTradeData'
import { useAppStore } from '../../store/useAppStore'

// Compact "$1.3B" / "$420M" / "$85K" form for the TAM/SAM cards only —
// deliberately different from this app's usual code-before-$, dual-currency
// convention (utils/currencyFormat.js), which is for real per-transaction
// amounts; these are order-of-magnitude portfolio totals where a compact
// form reads better in a small Home card.
function formatCompactUsd(value) {
  const number = Number(value) || 0
  const abs = Math.abs(number)
  if (abs >= 1e9) return `$${(number / 1e9).toFixed(1)}B`
  if (abs >= 1e6) return `$${(number / 1e6).toFixed(1)}M`
  if (abs >= 1e3) return `$${(number / 1e3).toFixed(1)}K`
  return `$${number.toFixed(0)}`
}

function HomeView() {
  const companies = useAppStore((state) => state.companies)
  // Read straight from the persisted SAM/TAM snapshots (see
  // backend/routers/comtrade.py's sam_overview_summary /
  // tam_global_overview_summary) — a plain DB read, never a live Comtrade
  // recompute, so Home never triggers trade-data work just by being
  // opened. null until the fetch resolves; computed_at stays null forever
  // if that tab has never been viewed yet in Market Analysis.
  const [tamSummary, setTamSummary] = useState(null)
  const [samSummary, setSamSummary] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetchTamGlobalOverviewSummary()
      .then((data) => {
        if (!cancelled) setTamSummary(data)
      })
      .catch(() => {
        if (!cancelled) setTamSummary(null)
      })
    fetchSamOverviewSummary()
      .then((data) => {
        if (!cancelled) setSamSummary(data)
      })
      .catch(() => {
        if (!cancelled) setSamSummary(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const tamValue = tamSummary?.computed_at ? formatCompactUsd(tamSummary.total_value) : '—'
  const tamSub = tamSummary?.computed_at
    ? `in ${tamSummary.category_count} ${tamSummary.category_count === 1 ? 'category' : 'categories'}`
    : 'Not yet computed — view Market Size ▸ TAM'
  const samValue = samSummary?.computed_at ? formatCompactUsd(samSummary.total_value) : '—'
  const samSub = samSummary?.computed_at
    ? `in ${samSummary.category_count} ${samSummary.category_count === 1 ? 'category' : 'categories'}`
    : 'Not yet computed — view Market Size ▸ SAM'

  return (
    <div className="home-view">
      <div className="home-view__grid">
        <MetricCard label="Active companies" value={String(companies.length)} tone="teal" />
        <MetricCard label="Financial performance" value="+18.4%" tone="amber" />
        <PhaseSummaryCards companies={companies} />
        <StartupInvestmentSummaryCard />
        <MetricCard label="TAM" value={tamValue} sub={tamSub} tone="teal" />
        <MetricCard label="SAM" value={samValue} sub={samSub} tone="amber" />
        {/* No real SOM calculation exists yet — same explicit placeholder
            treatment already used for ROI/Valuation below, not a new
            component. */}
        <PlaceholderMetricCard label="SOM" companies={companies} />
        <PlaceholderMetricCard label="Return on Investment (ROI)" companies={companies} />
        <PlaceholderMetricCard label="Valuation" companies={companies} />
      </div>
    </div>
  )
}

export default HomeView
