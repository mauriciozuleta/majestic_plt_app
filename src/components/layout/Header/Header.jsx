import './Header.css'
import { IconUserCircle } from '@tabler/icons-react'
import { useAppStore } from '../../../store/useAppStore'

function Header() {
  const currentUser = useAppStore((state) => state.currentUser)

  return (
    <header className="header-shell">
      <div className="header-inner">
        <div className="header-brand">
          <span className="header-status-dot" aria-hidden="true" />
          <span className="header-brand-text">MAJESTIC P.L.T.</span>
        </div>

        <div className="header-user">
          <IconUserCircle size={18} stroke={1.8} />
          <span>{currentUser?.name ?? 'M. Zuleta'}</span>
        </div>
      </div>
      <div className="header-divider" />
    </header>
  )
}

export default Header
