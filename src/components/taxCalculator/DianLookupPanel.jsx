import { useState } from 'react'
import { DIAN_STEPS } from '../../services/dianTax'
import './ColombiaDianPanel.css'

const validity = (tax) => (tax ? `${tax.validFrom || '—'} → ${tax.validTo || 'open-ended'}` : '—')
const rateText = (tax) => (tax ? (tax.rate != null ? `${tax.rate}%` : tax.formulaRaw) : '—')

// The DIAN side of the product step when Colombia is the import country: where the rates come from (the product's HS code), what DIAN is doing,
// and the few things it can ask the user — which tariff line when the code covers several, which row when it lists several valid Gravamen/IVA rows.
// `flow` comes from useDianFlow. See backend/tax_calc/colombia_dian/README.md.
function DianLookupPanel({ flow, productName }) {
  const { status, progress, lookup, error, code, chosen, typedCode, setTypedCode, choose, selectLine, refresh } = flow
  const [draftCode, setDraftCode] = useState('')
  const [showRaw, setShowRaw] = useState(false)
  const [copied, setCopied] = useState(false)
  const ok = lookup?.status === 'ok' ? lookup : null
  const seen = new Set(progress.map((event) => event.step))
  const lastStep = progress.length ? progress[progress.length - 1].step : null
  const running = status === 'running'

  const copyJson = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(lookup, null, 2))
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard unavailable
    }
  }
  const exportJson = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(lookup, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `dian-${ok?.query?.resolvedHsCode || 'lookup'}-${ok?.query?.consultationDate || ''}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="dian">
      <p className="tax-calc__hint">
        <strong>Colombia (DIAN)</strong>: the Gravamen and the IVA of {productName ? `“${productName}”` : 'the product'} are read from DIAN’s tariff consultation (MUISCA WebArancel) using its HS code
        {code ? ` ${code}` : ''}. A lookup takes about 5–20 seconds; results are as of today (DIAN’s consultation has no date field).
      </p>

      {!code && (
        <div className="dian__form">
          <label>
            This product has no HS code — type one
            <input value={draftCode} onChange={(event) => setDraftCode(event.target.value)} placeholder="0702000000" inputMode="numeric" onKeyDown={(event) => event.key === 'Enter' && setTypedCode(draftCode)} />
          </label>
          <button type="button" className="tax-calc__primary" onClick={() => setTypedCode(draftCode)} disabled={!draftCode.trim()}>
            Look up on DIAN
          </button>
        </div>
      )}
      {code && typedCode && (
        <p className="tax-calc__hint">
          Using the code you chose: <strong>{typedCode}</strong>.
        </p>
      )}

      {(running || progress.length > 0) && (
        <ol className="dian__steps" aria-label="Progress">
          {DIAN_STEPS.map((step) => (
            <li key={step.key} className={seen.has(step.key) ? (step.key === lastStep && running ? 'is-current' : 'is-done') : ''}>
              {step.label}
            </li>
          ))}
        </ol>
      )}

      {error && <p className="tax-calc__error">{error}</p>}

      {lookup?.status === 'error' && (
        <div className="dian__error" role="alert">
          <strong>{lookup.error.code}</strong>
          <span>{lookup.error.message}</span>
          {lookup.error.diagnostics && (
            <details>
              <summary>Diagnostics</summary>
              <pre>{JSON.stringify(lookup.error.diagnostics, null, 2)}</pre>
            </details>
          )}
        </div>
      )}

      {lookup?.status === 'selection_required' && (
        <div className="dian__selection">
          <p>
            <strong>{lookup.inputHsCode}</strong> covers {lookup.matches.length} tariff lines at DIAN. Choose the one that is this product:
          </p>
          <ul>
            {lookup.matches.map((match) => (
              <li key={match.hsCode}>
                <button type="button" onClick={() => selectLine(match.hsCode)}>
                  <strong>{match.hsCode}</strong> <span>{match.description}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {ok && (
        <div className="dian__result">
          <div className="dian__product">
            <strong>{ok.query.resolvedHsCode}</strong>
            <span>{ok.product.description}</span>
            <em>
              Chapter {ok.product.chapter} · heading {ok.product.heading}
              {ok.query.inputHsCode !== ok.query.resolvedHsCode && ` · from ${ok.query.inputHsCode}`}
            </em>
          </div>

          <div className="dian__taxes">
            <div className="dian__tax">
              <span className="dian__tax-title">Gravamen arancelario</span>
              <strong className="dian__tax-rate">{ok.gravamen ? rateText(ok.gravamen) : '—'}</strong>
              {ok.gravamen && (
                <>
                  <span className="dian__tax-meta">Valid {validity(ok.gravamen)}</span>
                  <span className="dian__tax-meta">DIAN: “{ok.gravamen.formulaRaw}”</span>
                </>
              )}
            </div>
            <div className="dian__tax">
              <span className="dian__tax-title">IVA</span>
              <strong className="dian__tax-rate">{ok.iva ? rateText(ok.iva) : '—'}</strong>
              {ok.iva && (
                <>
                  <span className="dian__tax-meta">Valid {validity(ok.iva)}</span>
                  <span className="dian__tax-meta">DIAN: “{ok.iva.formulaRaw}”</span>
                  {ok.iva.classification && <span className={`dian__chip is-${ok.iva.classification}`}>{ok.iva.classification === 'excluded' ? 'EXCLUIDO' : 'EXENTO'}</span>}
                </>
              )}
            </div>
          </div>

          {ok.needsInput.map((item) => {
            const rows = item.tax === 'gravamen' ? ok.gravamenRows : ok.ivaRows
            return (
              <div key={item.tax} className="dian__choose">
                <p>
                  {item.tax === 'gravamen'
                    ? 'DIAN lists more than one Gravamen valid today and does not say how they combine. Choose the one that applies:'
                    : 'The IVA depends on the product’s own description (DIAN lists several rows). Choose the one that applies:'}
                </p>
                <ul>
                  {item.rowIndexes.map((index) => (
                    <li key={index}>
                      <label>
                        <input type="radio" name={`dian-${item.tax}`} checked={chosen[item.tax] === index} onChange={() => choose(item.tax, index)} />
                        <span>
                          <strong>{rateText(rows[index])}</strong> · {rows[index].concept || 'row'} · valid {validity(rows[index])}
                          <em> “{rows[index].formulaRaw}”</em>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}

          <div className="dian__actions">
            <button type="button" className="tax-calc__link" onClick={() => setShowRaw((value) => !value)}>
              {showRaw ? 'Hide raw data' : 'View raw data'}
            </button>
            <button type="button" className="tax-calc__link" onClick={copyJson}>
              {copied ? 'Copied' : 'Copy JSON'}
            </button>
            <button type="button" className="tax-calc__link" onClick={exportJson}>
              Export JSON
            </button>
            {ok.source.fromCache && (
              <button type="button" className="tax-calc__link" onClick={refresh}>
                Refresh from DIAN
              </button>
            )}
          </div>
          {showRaw && <pre className="dian__raw">{JSON.stringify(lookup, null, 2)}</pre>}
        </div>
      )}
    </div>
  )
}

export default DianLookupPanel
