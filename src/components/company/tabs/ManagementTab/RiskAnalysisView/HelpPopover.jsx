import { useEffect, useRef, useState } from 'react'
import './RiskAnalysisView.css'

// A small "?" icon that toggles a floating explanation box — used beside
// the page title and each category title instead of a permanent on-page
// legend, so the explanation is there when needed without taking up space
// otherwise.
function HelpPopover({ children, align = 'left' }) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const handleOutsideClick = (event) => {
      if (!containerRef.current?.contains(event.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleOutsideClick)
    return () => document.removeEventListener('mousedown', handleOutsideClick)
  }, [open])

  return (
    <span className="help-popover" ref={containerRef}>
      <button
        type="button"
        className="help-popover__trigger"
        onClick={() => setOpen((prev) => !prev)}
        aria-label="Explain scoring"
        aria-expanded={open}
      >
        ?
      </button>
      {open && <div className={`help-popover__panel help-popover__panel--${align}`}>{children}</div>}
    </span>
  )
}

export default HelpPopover
