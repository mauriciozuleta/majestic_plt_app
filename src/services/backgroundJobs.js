// Runs a "start, then poll until done" background job independently of
// any React component's lifecycle — a plain setTimeout chain, not a React
// effect, so it keeps running (and, critically, still posts its result to
// the global assistant store) even after the component that triggered it
// unmounts (switching pills/countries/tabs) or was never re-visited. The
// backend job itself is a real FastAPI BackgroundTask that also survives
// the triggering HTTP request ending — this just keeps the frontend aware
// of when it's actually done.

import { useAppStore } from '../store/useAppStore'

const POLL_INTERVAL_MS = 5000

export function runBackgroundJob({ start, poll, label }) {
  return start().then(
    () =>
      new Promise((resolve, reject) => {
        const tick = () => {
          poll()
            .then((data) => {
              if (data.building) {
                setTimeout(tick, POLL_INTERVAL_MS)
                return
              }
              if (data.error) {
                useAppStore.getState().addAssistantMessage(`${label} failed: ${data.error}`)
                reject(new Error(data.error))
                return
              }
              if (data.exists) {
                useAppStore.getState().addAssistantMessage(`${label} is ready — click View to see it.`)
                resolve(data)
                return
              }
              // Not building, no error, no file yet — the background task
              // hasn't picked up the job yet; keep waiting.
              setTimeout(tick, POLL_INTERVAL_MS)
            })
            .catch(reject)
        }
        tick()
      }),
  )
}
