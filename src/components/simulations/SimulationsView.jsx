import { NavLink, Navigate, Outlet, useParams } from 'react-router-dom'
import { useAppStore } from '../../store/useAppStore'
import './SimulationsView.css'

function SimulationsIndexRedirect() {
  const companies = useAppStore((state) => state.companies)
  if (companies.length === 0) return null
  return <Navigate to={`/simulations/${companies[0].id}/parameters`} replace />
}

function SimulationsView() {
  const { companyId } = useParams()
  const companies = useAppStore((state) => state.companies)

  if (companies.length === 0) {
    return (
      <div className="panel-surface">
        <h3>Simulations</h3>
        <p>Add a company first to configure its simulation parameters.</p>
      </div>
    )
  }

  return (
    <section className="simulations-workspace">
      <div className="simulations-workspace__header">
        <h3>Simulations</h3>
        <p>Scenario planning and model-based decision analysis across companies.</p>
      </div>

      <nav className="simulations-workspace__tabs" aria-label="Company">
        {companies.map((company) => (
          <NavLink
            key={company.id}
            to={`/simulations/${company.id}/parameters`}
            className={({ isActive }) => `simulations-workspace__tab ${isActive || company.id === companyId ? 'is-active' : ''}`}
          >
            {company.name}
          </NavLink>
        ))}
      </nav>

      {companyId && (
        <div className="simulations-workspace__subtabs">
          <NavLink
            to={`/simulations/${companyId}/parameters`}
            className={({ isActive }) => `simulations-workspace__subtab ${isActive ? 'is-active' : ''}`}
          >
            Sim Parameters
          </NavLink>
        </div>
      )}

      <div className="simulations-workspace__content">
        <Outlet />
      </div>
    </section>
  )
}

export default SimulationsView
export { SimulationsIndexRedirect }
