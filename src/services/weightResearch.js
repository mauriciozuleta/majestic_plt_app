// AI-researched pack/carton weights, for products whose price the scrapers
// can't convert to $/kg on their own (see MarketAnalysis/unitConversion.js
// for what "can't" means and why). Global, not per-company — see
// backend/routers/weight_research.py.

import { API_BASE } from './apiBase'
import { useAppStore } from '../store/useAppStore'

const POLL_INTERVAL_MS = 5000

export async function fetchWeightResearch() {
  const response = await fetch(`${API_BASE}/weight-research`)
  if (!response.ok) throw new Error(`Request failed (${response.status})`)
  return response.json()
}

async function startWeightResearch(items) {
  const response = await fetch(`${API_BASE}/weight-research`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

// Kicks off (or joins, if one is already running) the background
// weight-research job and resolves once it's done, posting a notice to
// the assistant panel — same "survives navigating away" shape as the
// other background AI jobs (see backgroundJobs.js), just with its own
// polling loop since this job's "done" signal is `building` going false,
// not a single output file appearing.
export function researchMissingWeights(items) {
  return startWeightResearch(items).then((startResult) => {
    if (startResult.status === 'no_items') return fetchWeightResearch()
    return new Promise((resolve, reject) => {
      const tick = () => {
        fetchWeightResearch()
          .then((data) => {
            if (data.building) {
              setTimeout(tick, POLL_INTERVAL_MS)
              return
            }
            if (data.error) {
              useAppStore.getState().addAssistantMessage(`Weight research failed: ${data.error}`)
              reject(new Error(data.error))
              return
            }
            useAppStore.getState().addAssistantMessage('Weight research is ready — the price-per-kg columns have been updated.')
            resolve(data)
          })
          .catch(reject)
      }
      tick()
    })
  })
}
