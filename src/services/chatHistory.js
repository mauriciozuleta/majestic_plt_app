// The persisted Assistant chat log (backend/routers/assistant.py). Kept apart
// from chat.js so the store can import it without an import cycle
// (chat.js -> backgroundJobs.js -> store).
import { API_BASE } from './apiBase'

// Most recent messages, oldest first.
export const fetchChatHistory = async () => {
  const response = await fetch(`${API_BASE}/assistant/messages`)
  if (!response.ok) throw new Error(`Request failed (${response.status})`)
  return response.json()
}

export const saveChatMessage = async (message) => {
  const response = await fetch(`${API_BASE}/assistant/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: message.id, sender: message.sender, text: message.text, sources: message.sources || [] }),
  })
  if (!response.ok) throw new Error(`Request failed (${response.status})`)
  return response.json()
}
