import './Chatbox.css'
import { IconSend } from '@tabler/icons-react'
import { useChatbox } from './useChatbox'

function Chatbox() {
  const { messages, draft, setDraft, handleSend } = useChatbox()

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
            </div>
          ))
        )}
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
          placeholder="Message"
        />
        <button type="button" onClick={handleSend} aria-label="Send message">
          <IconSend size={14} stroke={1.8} />
        </button>
      </div>
    </div>
  )
}

export default Chatbox
