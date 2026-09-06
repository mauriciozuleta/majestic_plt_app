import { NavLink } from 'react-router-dom'
import './FinancialSubNav.css'

/** A second-level pill tab bar, for sections nested one level below a
 * Financial sub-tab (e.g. Accounting's statements, Financial Modeling's
 * models) — the same idea as CompanyWorkspace's own sub-tab bar, just
 * scoped one level deeper. */
function FinancialSubNav({ basePath, items }) {
  return (
    <nav className="financial-sub-nav" aria-label="Section">
      {items.map((item) => (
        <NavLink
          key={item.slug}
          to={`${basePath}/${item.slug}`}
          className={({ isActive }) => `financial-sub-nav__item ${isActive ? 'is-active' : ''}`}
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}

export default FinancialSubNav
