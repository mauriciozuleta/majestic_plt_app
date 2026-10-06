import { useEffect, useState } from 'react'

// A Set held in state that survives leaving the page (tab changes, reloads): stored in localStorage under `key`.
// Same [value, setValue] shape as useState, so functional updates work.
export function usePersistentSet(key) {
  const [value, setValue] = useState(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem(key) || '[]')
      return new Set(Array.isArray(saved) ? saved : [])
    } catch {
      return new Set()
    }
  })
  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify([...value]))
    } catch {
      // storage unavailable — the state still works for this visit
    }
  }, [key, value])
  return [value, setValue]
}
