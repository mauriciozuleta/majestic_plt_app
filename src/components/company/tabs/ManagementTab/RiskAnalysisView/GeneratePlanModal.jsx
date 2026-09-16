import { useState } from 'react'
import { fetchRiskPlan, startRiskPlan } from '../../../../../services/riskAnalysis'
import { runBackgroundJob } from '../../../../../services/backgroundJobs'
import './RiskAnalysisView.css'

// Same fixed markdown shape as Country Commercial Profile's own viewer
// (heading levels + bullets + paragraphs) — no need for a full markdown
// library for AI output this structured.
function MarkdownBody({ markdown }) {
  const lines = markdown.split('\n')
  const elements = []
  let paragraph = []
  let key = 0
  const flush = () => {
    if (paragraph.length) {
      elements.push(<p key={key++}>{paragraph.join(' ')}</p>)
      paragraph = []
    }
  }
  lines.forEach((rawLine) => {
    const line = rawLine.trim()
    if (!line) return flush()
    if (line.startsWith('# ')) {
      flush()
      elements.push(<h1 key={key++}>{line.slice(2)}</h1>)
    } else if (line.startsWith('## ')) {
      flush()
      elements.push(<h2 key={key++}>{line.slice(3)}</h2>)
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      flush()
      elements.push(<li key={key++}>{line.slice(2)}</li>)
    } else {
      paragraph.push(line)
    }
  })
  flush()
  return <div className="plan-body">{elements}</div>
}

function GeneratePlanModal({ companyId, categories, onClose }) {
  const [categoryId, setCategoryId] = useState(categories[0]?.id ?? '')
  const [status, setStatus] = useState('select') // select | building | error | result
  const [content, setContent] = useState('')
  const [error, setError] = useState('')

  const handleGenerate = async () => {
    setStatus('building')
    setError('')
    try {
      const data = await runBackgroundJob({
        start: () => startRiskPlan(companyId, categoryId),
        poll: () => fetchRiskPlan(companyId, categoryId),
        label: 'Risk plan',
      })
      setContent(data.content)
      setStatus('result')
    } catch (err) {
      setError(err.message)
      setStatus('error')
    }
  }

  const selectedCategory = categories.find((c) => c.id === categoryId)

  return (
    <div className="modal-overlay" onClick={status === 'building' ? undefined : onClose}>
      <div className="modal modal--wide" onClick={(event) => event.stopPropagation()}>
        {status === 'select' && (
          <>
            <h3>Generate investor-facing plan</h3>
            <p className="modal-sub">
              Only risks currently scored as "Well managed" are included — the point is to show risk is under
              control, not to expose gaps.
            </p>
            <label>
              Category
              <select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
                {categories.map((cat) => (
                  <option key={cat.id} value={cat.id}>
                    {cat.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="modal-actions">
              <button type="button" className="btn" onClick={onClose}>
                Cancel
              </button>
              <button type="button" className="btn modal-save" onClick={handleGenerate} disabled={!categoryId}>
                Generate
              </button>
            </div>
          </>
        )}

        {status === 'building' && (
          <div className="plan-status">
            <div className="plan-status__spinner" />
            <p>Writing the {selectedCategory?.name} plan…</p>
          </div>
        )}

        {status === 'error' && (
          <>
            <h3>Couldn't generate the plan</h3>
            <p className="modal-error">{error}</p>
            <div className="modal-actions">
              <button type="button" className="btn" onClick={onClose}>
                Close
              </button>
              <button type="button" className="btn modal-save" onClick={() => setStatus('select')}>
                Try again
              </button>
            </div>
          </>
        )}

        {status === 'result' && (
          <>
            <div className="plan-scroll">
              <MarkdownBody markdown={content} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" onClick={onClose}>
                Close
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default GeneratePlanModal
