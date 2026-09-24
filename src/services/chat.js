import { API_BASE } from './apiBase'
import { runBackgroundJob } from './backgroundJobs'
import { buildCompetitivenessAnalysis, buildCountryProfile, fetchCompetitivenessAnalysis, fetchCountryProfile } from './commercialStructure'
import { getCategorySummary } from './competitivenessInputs'

// `history` is the chat log so far ({ sender: 'user' | 'bot', text }), ending
// with the message being sent. Resolves to { reply, sources, actions } —
// actions are builds the assistant asked for (see backend/routers/assistant.py).
export const sendChatMessage = async (history) => {
  const response = await fetch(`${API_BASE}/assistant/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages: history.map((message) => ({ role: message.sender === 'user' ? 'user' : 'assistant', text: message.text })),
    }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || 'The assistant could not answer right now.')
  }
  return response.json()
}

// Runs a build the assistant requested through the same background-job path
// the Operations tab buttons use, so completion (or failure) lands back in
// this chat on its own.
export function runAssistantAction(action) {
  if (action.type === 'build_country_profile') {
    return runBackgroundJob({
      start: () => buildCountryProfile(action.company_id, action.country_id),
      poll: () => fetchCountryProfile(action.company_id, action.country_id),
      label: `${action.country_name} Commercial Profile`,
    })
  }
  if (action.type === 'build_competitiveness') {
    return runBackgroundJob({
      start: async () => {
        const categorySummary = await getCategorySummary(action.source_country_name)
        if (!categorySummary || !categorySummary.length) {
          throw new Error(`No Product Analysis data loaded for ${action.source_country_name} yet — click Update on its Product Analysis tab first.`)
        }
        return buildCompetitivenessAnalysis(action.company_id, action.target_country_id, action.source_country_name, categorySummary)
      },
      poll: () => fetchCompetitivenessAnalysis(action.company_id, action.target_country_id, action.source_country_name),
      label: `${action.source_country_name} → ${action.target_country_name} Competitiveness Analysis`,
    })
  }
  return Promise.resolve()
}
