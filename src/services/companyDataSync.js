const DATA_SYNC_EVENT = 'majestic-company-data-changed'
const DATA_SYNC_KEY_PREFIX = 'majestic-company-data-changed:'
const DATA_SYNC_CHANNEL = 'majestic-company-data-sync'

export function broadcastCompanyDataChange(companyId, source = 'unknown') {
  if (typeof window === 'undefined' || !companyId) return

  const payload = JSON.stringify({ companyId, source, timestamp: Date.now() })
  window.localStorage.setItem(`${DATA_SYNC_KEY_PREFIX}${companyId}`, payload)
  if ('BroadcastChannel' in window) {
    const channel = new BroadcastChannel(DATA_SYNC_CHANNEL)
    channel.postMessage({ companyId, source, timestamp: Date.now() })
    channel.close()
  }
  window.dispatchEvent(new CustomEvent(DATA_SYNC_EVENT, { detail: { companyId, source } }))
}

export function subscribeToCompanyDataChange(companyId, onChange) {
  if (typeof window === 'undefined' || !companyId) return () => {}

  const handleStorage = (event) => {
    if (!event.key?.startsWith(DATA_SYNC_KEY_PREFIX)) return
    if (event.key !== `${DATA_SYNC_KEY_PREFIX}${companyId}`) return
    onChange()
  }

  const handleCustomEvent = (event) => {
    if (event.detail?.companyId !== companyId) return
    onChange()
  }

  const channel = 'BroadcastChannel' in window ? new BroadcastChannel(DATA_SYNC_CHANNEL) : null
  const handleBroadcastChannel = (event) => {
    if (event.data?.companyId !== companyId) return
    onChange()
  }

  window.addEventListener('storage', handleStorage)
  window.addEventListener(DATA_SYNC_EVENT, handleCustomEvent)
  channel?.addEventListener('message', handleBroadcastChannel)

  return () => {
    window.removeEventListener('storage', handleStorage)
    window.removeEventListener(DATA_SYNC_EVENT, handleCustomEvent)
    channel?.removeEventListener('message', handleBroadcastChannel)
    channel?.close()
  }
}