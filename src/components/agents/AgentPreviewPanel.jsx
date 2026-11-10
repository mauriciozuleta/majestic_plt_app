import { AGENT_MAY, RECENT_RUNS, SCHEDULED_TASKS } from './agentsPreviewData'

// PREVIEW ONLY: static sample data, and every button is disabled — nothing here is wired to the app.
function AgentPreviewPanel() {
  return (
    <aside className="agents-preview" aria-label="Schedules and runs (preview)">
      <div className="agents-preview__banner">Preview - not active yet</div>

      <section>
        <h2 className="agents-preview__title">Scheduled tasks</h2>
        <div className="agents-preview__stack">
          {SCHEDULED_TASKS.map((task) => (
            <div key={task.id} className="agents-preview__card">
              <div className="agents-preview__row">
                <div className="agents-preview__name">{task.name}</div>
                <span className={`agents-preview__pill agents-preview__pill--${task.tone}`}>{task.status}</span>
              </div>
              <div className="agents-preview__meta">{task.when}</div>
              {task.actions.length > 0 && (
                <div className="agents-preview__actions">
                  {task.actions.map((label) => (
                    <button key={label} type="button" disabled>
                      {label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="agents-preview__title">Recent runs</h2>
        <ul className="agents-preview__stack">
          {RECENT_RUNS.map((run) => (
            <li key={run.id} className="agents-preview__card">
              <div className="agents-preview__row">
                <span className="agents-preview__name">{run.name}</span>
                <span className={`agents-preview__result agents-preview__result--${run.tone}`}>{run.result}</span>
              </div>
              <div className="agents-preview__meta">{run.detail}</div>
              {run.action && (
                <div className="agents-preview__actions">
                  <button type="button" disabled>
                    {run.action}
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section className="agents-preview__card">
        <h2 className="agents-preview__title">What the agent may do</h2>
        <ul className="agents-preview__may">
          {AGENT_MAY.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <div className="agents-preview__meta">Sample data for illustration.</div>
    </aside>
  )
}

export default AgentPreviewPanel
