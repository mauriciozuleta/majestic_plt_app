import { useState } from 'react'
import { sendChatMessage } from '../../services/chat'
import { useAppStore } from '../../store/useAppStore'

// Messages live in the global store, not local state — background-job
// completions (see services/backgroundJobs.js) are pushed here from
// wherever they finish, not just from this mounted component, so they need
// to land somewhere that survives navigation.
export function useChatbox() {
  const messages = useAppStore((state) => state.assistantMessages)
  const addAssistantMessage = useAppStore((state) => state.addAssistantMessage)
  const [draft, setDraft] = useState('')

  const handleSend = async () => {
    const trimmed = draft.trim()
    if (!trimmed) return

    useAppStore.setState((state) => ({
      assistantMessages: [...state.assistantMessages, { id: Date.now() + Math.random(), sender: 'user', text: trimmed }],
    }))
    setDraft('')

    const reply = await sendChatMessage(trimmed)
    addAssistantMessage(reply.text)
  }

  return { messages, draft, setDraft, handleSend }
}
