import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import './AreaAutocomplete.css'

/**
 * A self-contained "pick or type an area" input. Native <input list="...">
 * datalists turned out to lose to the browser's own remembered-value
 * autofill in practice — the dropdown just never showed. This renders its
 * own suggestion list instead, via a portal so it isn't clipped by the
 * Matrix's scrollable table, so it's guaranteed to show the areas that
 * actually exist rather than whatever the browser guesses from history.
 */
function AreaAutocomplete({ value, isDirty, options, onChange, className = '', placeholder }) {
  const [inputValue, setInputValue] = useState(value || '')
  const [open, setOpen] = useState(false)
  const [rect, setRect] = useState(null)
  const wrapperRef = useRef(null)
  const listRef = useRef(null)

  useEffect(() => {
    setInputValue(value || '')
  }, [value])

  useEffect(() => {
    if (!open) return undefined

    const updateRect = () => {
      if (wrapperRef.current) setRect(wrapperRef.current.getBoundingClientRect())
    }
    updateRect()

    const handlePointerDown = (event) => {
      if (
        wrapperRef.current?.contains(event.target) ||
        listRef.current?.contains(event.target)
      ) {
        return
      }
      setOpen(false)
    }
    const handleScroll = () => setOpen(false)

    document.addEventListener('mousedown', handlePointerDown)
    window.addEventListener('scroll', handleScroll, true)
    window.addEventListener('resize', handleScroll)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      window.removeEventListener('scroll', handleScroll, true)
      window.removeEventListener('resize', handleScroll)
    }
  }, [open])

  const filtered = options.filter((option) => option.toLowerCase().includes(inputValue.trim().toLowerCase()))
  const showCreateOption = inputValue.trim() && !options.some((option) => option.toLowerCase() === inputValue.trim().toLowerCase())

  const commit = (nextValue) => {
    setInputValue(nextValue)
    setOpen(false)
    onChange(nextValue)
  }

  return (
    <div className="area-autocomplete" ref={wrapperRef}>
      <input
        type="text"
        autoComplete="off"
        className={`area-autocomplete__input ${isDirty ? 'is-dirty' : ''} ${className}`}
        placeholder={placeholder}
        value={inputValue}
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          setInputValue(event.target.value)
          setOpen(true)
          onChange(event.target.value)
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === 'Escape') {
            event.currentTarget.blur()
            setOpen(false)
          }
        }}
      />
      {open && rect && (filtered.length > 0 || showCreateOption) &&
        createPortal(
          <ul
            className="area-autocomplete__list"
            ref={listRef}
            style={{ position: 'fixed', top: rect.bottom + 2, left: rect.left, width: rect.width }}
          >
            {filtered.map((option) => (
              <li key={option}>
                <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => commit(option)}>
                  {option}
                </button>
              </li>
            ))}
            {showCreateOption && (
              <li className="area-autocomplete__create">
                <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => commit(inputValue.trim())}>
                  Use "{inputValue.trim()}"
                </button>
              </li>
            )}
          </ul>,
          document.body,
        )}
    </div>
  )
}

export default AreaAutocomplete
