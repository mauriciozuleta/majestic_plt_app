import { useState } from 'react'
import { runAssistantAction, sendChatMessage } from '../../services/chat'
import { useAppStore } from '../../store/useAppStore'

// Messages live in the global store, not local state — background-job
// completions (see services/backgroundJobs.js) are pushed here from
// wherever they finish, not just from this mounted component, so they need
// to land somewhere that survives navigation.
export function useChatbox() {
  const messages = useAppStore((state) => state.assistantMessages)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)

  const push = (message) =>
    useAppStore.setState((state) => ({
      assistantMessages: [...state.assistantMessages, { id: Date.now() + Math.random(), ...message }],
    }))

  const handleSend = async () => {
    const trimmed = draft.trim()
    if (!trimmed || sending) return

    const history = [...useAppStore.getState().assistantMessages, { sender: 'user', text: trimmed }]
    push({ sender: 'user', text: trimmed })
    setDraft('')
    setSending(true)

    try {
      const { reply, sources, actions } = await sendChatMessage(history)
      push({ sender: 'bot', text: reply, sources })
      actions.forEach((action) => {
        // Failures are reported into the chat by runBackgroundJob itself,
        // except a failure to even start one.
        runAssistantAction(action).catch((error) => push({ sender: 'bot', text: `Could not finish that: ${error.message}` }))
      })
    } catch (error) {
      push({ sender: 'bot', text: error.message })
    } finally {
      setSending(false)
    }
  }

  return { messages, draft, setDraft, handleSend, sending }
}
