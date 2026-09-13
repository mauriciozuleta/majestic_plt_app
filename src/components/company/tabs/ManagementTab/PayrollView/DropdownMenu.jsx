import { useEffect, useRef, useState } from 'react'
import './DropdownMenu.css'

/** A toolbar button that opens a small popup menu of actions. Closes on an
 * outside click. `children` is a render function `(close) => <...>` so each
 * item can close the menu itself after handling its own click — closing via
 * a capture-phase listener on the panel was tried first and swallowed the
 * items' own onClick handlers entirely, so this hands control back to the
 * caller instead. */
function DropdownMenu({ label, className = '', children }) {
  const containerRef = useRef(null)
  const [isOpen, setIsOpen] = useState(false)
  const close = () => setIsOpen(false)

  useEffect(() => {
    if (!isOpen) return undefined
    const handleOutsideClick = (event) => {
      if (!containerRef.current?.contains(event.target)) setIsOpen(false)
    }
    document.addEventListener('mousedown', handleOutsideClick)
    return () => document.removeEventListener('mousedown', handleOutsideClick)
  }, [isOpen])

  return (
    <div className={`dropdown-menu ${className}`} ref={containerRef}>
      <button type="button" className="dropdown-menu__trigger payroll-view__btn" onClick={() => setIsOpen((prev) => !prev)} aria-expanded={isOpen}>
        {label}
        <span className="dropdown-menu__chevron">▾</span>
      </button>
      {isOpen && (
        <div className="dropdown-menu__panel" role="menu">
          {children(close)}
        </div>
      )}
    </div>
  )
}

export default DropdownMenu
