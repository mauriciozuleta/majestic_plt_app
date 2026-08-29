import { useState } from 'react'
import { sendChatMessage } from '../../services/chat'

const initialMessages = []

export function useChatbox() {
  const [messages, setMessages] = useState(initialMessages)
  const [draft, setDraft] = useState('')

  const handleSend = async () => {
    const trimmed = draft.trim()
    if (!trimmed) return

    const userMessage = {
      id: Date.now(),
      sender: 'user',
      text: trimmed,
    }

    setMessages((previous) => [...previous, userMessage])
    setDraft('')

    const reply = await sendChatMessage(trimmed)
    setMessages((previous) => [...previous, { ...reply, sender: reply.sender || 'bot' }])
  }

  return { messages, draft, setDraft, handleSend }
}
