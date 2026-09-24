import { NavLink, Navigate, Outlet, useParams } from 'react-router-dom'
import { useAppStore } from '../../store/useAppStore'
import '../simulations/SimulationsView.css'

function DocumentationIndexRedirect() {
  const companies = useAppStore((state) => state.companies)
  if (companies.length === 0) return null
  return <Navigate to={`/documentation/${companies[0].id}`} replace />
}

// Documentation lives in the sidebar rather than inside a company. The
// knowledge base is portfolio-wide, but the report directories (profiles,
// analyses, start-up investment) are per company, so the same company tab
// strip as Simulations picks which company's reports to list.
function DocumentationView() {
  const { companyId } = useParams()
  const companies = useAppStore((state) => state.companies)

  if (companies.length === 0) {
    return (
      <div className="panel-surface">
        <h3>Documentation</h3>
        <p>Add a company first to see its documentation.</p>
      </div>
    )
  }

  return (
    <section className="simulations-workspace">
      <nav className="simulations-workspace__tabs" aria-label="Company">
        {companies.map((company) => (
          <NavLink
            key={company.id}
            to={`/documentation/${company.id}`}
            className={({ isActive }) => `simulations-workspace__tab ${isActive || company.id === companyId ? 'is-active' : ''}`}
          >
            {company.name}
          </NavLink>
        ))}
      </nav>

      <div className="simulations-workspace__content">
        <Outlet />
      </div>
    </section>
  )
}

export default DocumentationView
export { DocumentationIndexRedirect }
