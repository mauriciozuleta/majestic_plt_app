import { useEffect, useRef } from 'react'
import './Chatbox.css'
import { IconSend } from '@tabler/icons-react'
import { useChatbox } from './useChatbox'

function Chatbox() {
  const { messages, draft, setDraft, handleSend, sending } = useChatbox()
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, sending])

  return (
    <div className="chatbox">
      <div className="chatbox__header">Assistant</div>
      <div className="chatbox__messages">
        {messages.length === 0 ? (
          <div className="chatbox__message chatbox__message--bot">No messages yet.</div>
        ) : (
          messages.map((message) => (
            <div key={message.id} className={`chatbox__message chatbox__message--${message.sender}`}>
              {message.text}
              {message.sources?.length > 0 && (
                <div className="chatbox__sources">From: {message.sources.join(' · ')}</div>
              )}
            </div>
          ))
        )}
        {sending && <div className="chatbox__message chatbox__message--bot">Thinking…</div>}
        <div ref={endRef} />
      </div>
      <div className="chatbox__composer">
        <input
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              handleSend()
            }
          }}
          placeholder="Ask about your documents…"
          disabled={sending}
        />
        <button type="button" onClick={handleSend} disabled={sending} aria-label="Send message">
          <IconSend size={14} stroke={1.8} />
        </button>
      </div>
    </div>
  )
}

export default Chatbox
