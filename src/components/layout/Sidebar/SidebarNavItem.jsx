import './SidebarNavItem.css'
import { NavLink } from 'react-router-dom'

function SidebarNavItem({ icon: Icon, label, to, onClick, active }) {
  const content = (
    <>
      <span className="sidebar-nav-item__icon">
        <Icon size={16} stroke={1.8} />
      </span>
      <span className="sidebar-nav-item__label">{label}</span>
    </>
  )

  if (to) {
    return (
      <NavLink
        to={to}
        end={to === '/'}
        className={({ isActive }) =>
          `sidebar-nav-item ${isActive || active ? 'is-active' : ''}`
        }
        onClick={onClick}
      >
        {content}
      </NavLink>
    )
  }

  return (
    <button type="button" className="sidebar-nav-item sidebar-nav-button" onClick={onClick}>
      {content}
    </button>
  )
}

export default SidebarNavItem
