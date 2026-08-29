import './HomeView.css'
import MetricCard from './MetricCard'
import { useAppStore } from '../../store/useAppStore'

function HomeView() {
  const companies = useAppStore((state) => state.companies)

  return (
    <div className="home-view">
      <div className="home-view__grid">
        <MetricCard label="Active companies" value={String(companies.length)} tone="teal" />
        <MetricCard label="Financial performance" value="+18.4%" tone="amber" />
      </div>
    </div>
  )
}

export default HomeView
