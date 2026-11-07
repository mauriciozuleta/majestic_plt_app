import { useEffect, useState } from 'react'
import { documentViewUrl, fetchDocumentText } from '../../../../services/documents'

// A small Markdown reader for the documents people upload (headings, paragraphs, bullet and numbered lists, tables, code blocks,
// blockquotes, rules, and **bold** / *italic* / `code` / [links](url) inside text). Not a full CommonMark implementation.
function inline(text, keyPrefix) {
  const parts = []
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*?\*(?!\*)|\[[^\]]+\]\([^)\s]+\))/g
  let last = 0
  let match
  let index = 0
  while ((match = pattern.exec(text))) {
    if (match.index > last) parts.push(text.slice(last, match.index))
    const token = match[0]
    const key = `${keyPrefix}-${index++}`
    if (token.startsWith('**')) parts.push(<strong key={key}>{inline(token.slice(2, -2), key)}</strong>)
    else if (token.startsWith('`')) parts.push(<code key={key}>{token.slice(1, -1)}</code>)
    else if (token.startsWith('[')) {
      const [, label, href] = token.match(/\[([^\]]+)\]\(([^)\s]+)\)/)
      parts.push(
        <a key={key} href={href} target="_blank" rel="noreferrer">
          {label}
        </a>,
      )
    } else parts.push(<em key={key}>{inline(token.slice(1, -1), key)}</em>)
    last = match.index + token.length
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts
}

const isTableRow = (line) => /^\s*\|.*\|\s*$/.test(line)
const splitRow = (line) => line.trim().replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim())

function MarkdownText({ markdown }) {
  const lines = markdown.replace(/\r/g, '').split('\n')
  const blocks = []
  let i = 0
  let key = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) {
      i += 1
    } else if (line.trim().startsWith('```')) {
      const code = []
      i += 1
      while (i < lines.length && !lines[i].trim().startsWith('```')) code.push(lines[i++])
      i += 1
      blocks.push(<pre key={key++}>{code.join('\n')}</pre>)
    } else if (/^#{1,6}\s/.test(line)) {
      const level = line.match(/^#+/)[0].length
      const Tag = `h${Math.min(level + 1, 6)}`
      blocks.push(<Tag key={key++}>{inline(line.replace(/^#+\s*/, ''), `h${key}`)}</Tag>)
      i += 1
    } else if (/^\s*(---|\*\*\*)\s*$/.test(line)) {
      blocks.push(<hr key={key++} />)
      i += 1
    } else if (isTableRow(line) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      const header = splitRow(line)
      i += 2
      const rows = []
      while (i < lines.length && isTableRow(lines[i])) rows.push(splitRow(lines[i++]))
      blocks.push(
        <div key={key++} className="doc-viewer__table-wrap">
          <table>
            <thead>
              <tr>{header.map((cell, c) => <th key={c}>{inline(cell, `th${key}-${c}`)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((row, r) => (
                <tr key={r}>{row.map((cell, c) => <td key={c}>{inline(cell, `td${key}-${r}-${c}`)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
    } else if (/^\s*>/.test(line)) {
      const quote = []
      while (i < lines.length && /^\s*>/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, ''))
      blocks.push(<blockquote key={key++}>{inline(quote.join(' '), `q${key}`)}</blockquote>)
    } else if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line)
      const items = []
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
        const indent = lines[i].match(/^\s*/)[0].length
        items.push({ indent, text: lines[i].replace(/^\s*([-*]|\d+\.)\s+/, '') })
        i += 1
        // wrapped continuation lines of the same item
        while (i < lines.length && lines[i].trim() && !/^\s*([-*]|\d+\.)\s+/.test(lines[i]) && !lines[i].trim().startsWith('```') && !isTableRow(lines[i]) && /^\s{2,}/.test(lines[i])) {
          items[items.length - 1].text += ` ${lines[i++].trim()}`
        }
      }
      const List = ordered ? 'ol' : 'ul'
      blocks.push(
        <List key={key++}>
          {items.map((item, n) => (
            <li key={n} style={{ marginLeft: `${Math.min(item.indent, 8) * 0.5}rem` }}>
              {inline(item.text, `li${key}-${n}`)}
            </li>
          ))}
        </List>,
      )
    } else {
      const paragraph = []
      while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|\s*>|\s*([-*]|\d+\.)\s+|\s*```)/.test(lines[i]) && !isTableRow(lines[i])) paragraph.push(lines[i++].trim())
      blocks.push(<p key={key++}>{inline(paragraph.join(' '), `p${key}`)}</p>)
    }
  }
  return <div className="doc-viewer__markdown">{blocks}</div>
}

// Shows one document in place of downloading it: Markdown rendered, other text as it is, a PDF embedded.
function DocumentViewer({ document, onClose }) {
  const extension = document.original_filename.slice(document.original_filename.lastIndexOf('.')).toLowerCase()
  const isPdf = extension === '.pdf'
  const [state, setState] = useState({ status: isPdf ? 'ready' : 'loading', text: '', error: '' })

  useEffect(() => {
    if (isPdf) return undefined
    let cancelled = false
    fetchDocumentText(document.id)
      .then((text) => !cancelled && setState({ status: 'ready', text, error: '' }))
      .catch((error) => !cancelled && setState({ status: 'error', text: '', error: error.message }))
    return () => {
      cancelled = true
    }
  }, [document.id, isPdf])

  useEffect(() => {
    const onKey = (event) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="doc-viewer__overlay" role="dialog" aria-modal="true" aria-label={document.name} onClick={onClose}>
      <div className="doc-viewer" onClick={(event) => event.stopPropagation()}>
        <header className="doc-viewer__header">
          <div>
            <h3>{document.name}</h3>
            <span>{document.original_filename}</span>
          </div>
          <button type="button" className="documentation__link-btn" onClick={onClose}>
            Close
          </button>
        </header>
        <div className="doc-viewer__body">
          {state.status === 'loading' && <p className="documentation__hint">Loading…</p>}
          {state.status === 'error' && <p className="documentation__hint documentation__hint--error">{state.error}</p>}
          {isPdf && <iframe title={document.name} src={documentViewUrl(document.id)} className="doc-viewer__pdf" />}
          {!isPdf && state.status === 'ready' && (extension === '.md' ? <MarkdownText markdown={state.text} /> : <pre className="doc-viewer__plain">{state.text}</pre>)}
        </div>
      </div>
    </div>
  )
}

export default DocumentViewer
