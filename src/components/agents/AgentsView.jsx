import AgentChatPanel from './AgentChatPanel'
import AgentPreviewPanel from './AgentPreviewPanel'
import { AGENT_MODE, CATALOG_SERVICE_CHIP } from './agentsPreviewData'
import './agents.css'

// Agents: the Assistant chat (the only working part) in the center, and a static preview of the future scheduling agent on the right.
function AgentsView() {
  return (
    <section className="agents">
      <div className="agents__main">
        <header className="agents__header">
          <div>
            <h1>Agents</h1>
            <p>Ask the Assistant about your documents and let it build profiles, analyses and refreshes for you.</p>
          </div>
          <div className="agents__chips">
            <span className="agents__chip" title="Preview - not active yet">
              {AGENT_MODE}
            </span>
            <span className="agents__chip agents__chip--ok" title="Preview - not active yet">
              <span className="agents__dot" aria-hidden="true" />
              {CATALOG_SERVICE_CHIP}
            </span>
          </div>
        </header>

        <div className="agents__chat">
          <AgentChatPanel />
        </div>
      </div>

      <AgentPreviewPanel />
    </section>
  )
}

export default AgentsView
