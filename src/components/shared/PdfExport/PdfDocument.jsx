import { Fragment } from 'react'
import { computeLedgerMetrics } from './ledgerMetrics'
import { computePageBox } from './paperSizes'
import { paginateRows } from './paginateRows'
import './PdfDocument.css'

const REM_PX = 16
const DOC_PADDING_TOP_REM = 2.3
const DOC_PADDING_BOTTOM_REM = 1.9
const DOC_PADDING_SIDE_REM = 2.4

function money(value) {
  const amount = Number(value) || 0
  return `$${Math.round(amount).toLocaleString()}`
}

function todayLabel() {
  return new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
}

function timeLabel() {
  return new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}

function hexToRgba(hex, alpha) {
  const clean = (hex || '#999999').replace('#', '')
  const full = clean.length === 3 ? clean.split('').map((c) => c + c).join('') : clean
  const value = parseInt(full, 16)
  const r = (value >> 16) & 255
  const g = (value >> 8) & 255
  const b = value & 255
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function longestValueLength(spec) {
  let max = 0
  const consider = (value) => {
    const length = money(value).length
    if (length > max) max = length
  }
  spec.sections.forEach((section) => {
    section.records.forEach((record) => {
      record.values.forEach(consider)
      consider(record.total)
    })
    section.subtotal.values.forEach(consider)
    consider(section.subtotal.total)
  })
  if (spec.totalsRow) {
    spec.totalsRow.values.forEach(consider)
    consider(spec.totalsRow.total)
  }
  return Math.max(max, 1)
}

function PdfDocument({ spec, company, orientation, paperSize, exportedBy, variant = 'preview' }) {
  const { periodLabels, sections, summaryTiles = [], totalsRow, documentTitle, eyebrow, periodsCaption } = spec
  const columnCount = periodLabels.length
  const recordCount = sections.reduce((sum, section) => sum + section.records.length, 0)
  const pageBox = computePageBox(paperSize, orientation)

  const pageWidthPx = pageBox.widthIn * 96
  const pageHeightPx = pageBox.heightIn * 96
  const availableWidthPx = pageWidthPx - DOC_PADDING_SIDE_REM * 2 * REM_PX
  const contentAreaHeightPx = pageHeightPx - (DOC_PADDING_TOP_REM + DOC_PADDING_BOTTOM_REM) * REM_PX

  const maxValueLength = longestValueLength(spec)
  const metrics = computeLedgerMetrics({ columnCount, maxValueLength, availableWidthPx })

  const pages = paginateRows({
    sections,
    totalsRow,
    hasSummaryTiles: summaryTiles.length > 0,
    rowHeightPx: metrics.rowHeightPx,
    contentAreaHeightPx,
  })

  const renderRow = (row, index) => {
    if (row.kind === 'cat') {
      const section = row.section
      return (
        <tr key={`cat-${section.key}`} className="pdf-doc__cat-row" style={{ '--cat-color': section.color }}>
          <td colSpan={columnCount + 2} style={{ backgroundColor: hexToRgba(section.color, 0.12) }}>
            <span className="pdf-doc__cat-dot" />
            {section.label}
            <span className="pdf-doc__cat-meta">
              {section.records.length} line item{section.records.length === 1 ? '' : 's'} &middot; {money(section.subtotal.total)}
            </span>
          </td>
        </tr>
      )
    }
    if (row.kind === 'record') {
      const record = row.record
      return (
        <tr key={`rec-${row.section.key}-${index}`} className="pdf-doc__record-row">
          <td className="pdf-doc__item-name">{record.name}</td>
          {record.values.map((value, i) => (
            <td key={i} className="num">
              {value ? money(value) : '—'}
            </td>
          ))}
          <td className="num pdf-doc__total-cell">{money(record.total)}</td>
        </tr>
      )
    }
    if (row.kind === 'subtotal') {
      const section = row.section
      return (
        <tr key={`sub-${section.key}`} className="pdf-doc__subtotal-row" style={{ color: section.color }}>
          <td>{section.label} — subtotal</td>
          {section.subtotal.values.map((value, i) => (
            <td key={i} className="num">
              {money(value)}
            </td>
          ))}
          <td className="num">{money(section.subtotal.total)}</td>
        </tr>
      )
    }
    return (
      <tr key="grand" className="pdf-doc__grand-row">
        <td>{row.totalsRow.label}</td>
        {row.totalsRow.values.map((value, i) => (
          <td key={i} className="num">
            {money(value)}
          </td>
        ))}
        <td className="num">{money(row.totalsRow.total)}</td>
      </tr>
    )
  }

  const pageStyle = {
    width: `${pageBox.widthIn}in`,
    minHeight: `${pageBox.heightIn}in`,
  }

  return (
    <div className="pdf-doc" data-orientation={orientation} style={{ '--ledger-font': metrics.fontSize, '--ledger-pad': metrics.cellPadding }}>
      {pages.map((rows, pageIndex) => (
        <div
          key={pageIndex}
          className="pdf-doc__page"
          data-variant={variant}
          style={{ ...pageStyle, marginBottom: variant === 'preview' && pageIndex < pages.length - 1 ? '1.5rem' : 0 }}
        >
          <div className="pdf-doc__letterhead">
            <div className="pdf-doc__brand">
              {company?.logo ? (
                <img className="pdf-doc__logo" src={company.logo} alt={`${company?.name ?? 'Company'} logo`} />
              ) : (
                <div className="pdf-doc__logo pdf-doc__logo--placeholder">{(company?.name ?? '?').slice(0, 2).toUpperCase()}</div>
              )}
              <div>
                <div className="pdf-doc__name">{company?.name ?? 'Untitled Company'}</div>
                {company?.companyType && <div className="pdf-doc__type">{company.companyType}</div>}
              </div>
            </div>
            <div className="pdf-doc__doc-meta">
              {eyebrow && <div className="pdf-doc__eyebrow">{eyebrow}</div>}
              <div className="pdf-doc__title">{documentTitle}</div>
              <span className="pdf-doc__confidential">Confidential — Draft</span>
            </div>
          </div>

          <div className="pdf-doc__subhead">
            <span>
              {pageIndex === 0
                ? `${periodsCaption ? `${periodsCaption} · ` : ''}${recordCount} line item${recordCount === 1 ? '' : 's'} across ${sections.length} categor${sections.length === 1 ? 'y' : 'ies'}`
                : `Continued — page ${pageIndex + 1} of ${pages.length}`}
            </span>
            <span>Prepared {todayLabel()}</span>
          </div>

          {pageIndex === 0 && summaryTiles.length > 0 && (
            <div className="pdf-doc__summary">
              {summaryTiles.map((tile) => (
                <div key={tile.label} className={`pdf-doc__tile${tile.primary ? ' pdf-doc__tile--primary' : ''}`}>
                  <div className="pdf-doc__tile-label">{tile.label}</div>
                  <div className="pdf-doc__tile-value">{money(tile.value)}</div>
                </div>
              ))}
            </div>
          )}

          <table
            className="pdf-doc__ledger"
            style={{ '--name-col': `${metrics.namePct}%`, '--num-col': `${(100 - metrics.namePct) / (columnCount + 1)}%` }}
          >
            <colgroup>
              <col style={{ width: 'var(--name-col)' }} />
              {Array.from({ length: columnCount + 1 }, (_, index) => (
                <col key={index} style={{ width: 'var(--num-col)' }} />
              ))}
            </colgroup>
            <thead>
              <tr>
                <th>Line item</th>
                {periodLabels.map((label) => (
                  <th key={label} className="num">
                    {label}
                  </th>
                ))}
                <th className="num">Total</th>
              </tr>
            </thead>
            <tbody>{rows.map((row, index) => renderRow(row, index))}</tbody>
          </table>

          {pageIndex === pages.length - 1 && (
            <>
              <div className="pdf-doc__signoff">
                <div className="pdf-doc__signoff-line">
                  <strong>Exported by</strong>
                  <span>{exportedBy || 'Unknown user'}</span>
                </div>
                <div className="pdf-doc__signoff-line">
                  <strong>Exported on</strong>
                  <span>
                    {todayLabel()} at {timeLabel()}
                  </span>
                </div>
              </div>
              <div className="pdf-doc__footer">
                <span>
                  {company?.name ?? ''} &middot; {documentTitle}
                </span>
                <span>Generated {todayLabel()}</span>
              </div>
            </>
          )}
        </div>
      ))}
    </div>
  )
}

export default PdfDocument
