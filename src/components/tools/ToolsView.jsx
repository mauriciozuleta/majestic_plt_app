import { NavLink, Outlet } from 'react-router-dom'
import './ToolsView.css'

const TOOLS = [
  { to: '/tools/tax-calculator', label: 'Tax Calculator' },
  { to: '/tools/rag-files', label: 'RAG Files' },
  { to: '/tools/accounting-health-check', label: 'Accounting Health Check' },
]

// The sidebar's Tools tab: the Tax Calculator and RAG Files live under it.
function ToolsView() {
  return (
    <div className="tools-view">
      <nav className="tools-view__nav" aria-label="Tools">
        {TOOLS.map((tool) => (
          <NavLink key={tool.to} to={tool.to} className={({ isActive }) => `tools-view__item ${isActive ? 'is-active' : ''}`}>
            {tool.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  )
}

export default ToolsView
