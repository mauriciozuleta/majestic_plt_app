// CSV/PDF export for the product comparison table. Doesn't reuse the
// shared PdfExport module (src/components/shared/PdfExport) — that one is
// built around ledger-style reports (periods as columns, category
// subtotals, a single money total per row), which doesn't fit this table's
// shape (per-source COP/USD prices, unit, diff%). Reuses the same
// underlying libraries (html2canvas + jsPDF) it uses, just with a bespoke,
// simpler paginated document.

import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'
import { downloadCsv } from '../../../../../utils/exportCsv'
import { computePageBox } from '../../../../shared/PdfExport/paperSizes'

const ROWS_PER_PDF_PAGE = 20

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]))
}

function formatMoneyCell(cop, usd) {
  if (cop == null) return '—'
  const copText = `COP$${Math.round(cop).toLocaleString('en-US')}`
  return usd != null ? `US$${usd.toFixed(2)} (${copText})` : copText
}

export function exportProductsToCsv(rows, filename) {
  const headers = [
    'Product (EN)',
    'Product (ES)',
    'Category',
    'Unit',
    'La Mayorista (COP)',
    'La Mayorista (USD)',
    'La Mayorista (COP/kg)',
    'Corabastos (COP)',
    'Corabastos (USD)',
    'Corabastos (COP/kg)',
    'Difference %',
    'Match',
  ]
  const csvRows = rows.map((r) => [
    r.productEn,
    r.productEs,
    r.category,
    r.unit,
    r.laMayoristaCop ?? '',
    r.laMayoristaUsd != null ? r.laMayoristaUsd.toFixed(2) : '',
    r.laMayoristaPerKgCop != null ? r.laMayoristaPerKgCop.toFixed(2) : '',
    r.corabastosCop ?? '',
    r.corabastosUsd != null ? r.corabastosUsd.toFixed(2) : '',
    r.corabastosPerKgCop != null ? r.corabastosPerKgCop.toFixed(2) : '',
    r.diffPct != null ? r.diffPct.toFixed(1) : '',
    r.sourceTag,
  ])
  downloadCsv(filename, headers, csvRows)
}

function buildPdfPageElement(rowsChunk, pageIndex, pageCount, meta) {
  const container = document.createElement('div')
  container.style.cssText =
    'width:1400px;background:#ffffff;color:#111827;font-family:Arial,Helvetica,sans-serif;padding:36px;box-sizing:border-box;'
  container.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;">
      <div style="font-size:20px;font-weight:700;">Colombia Product Analysis</div>
      <div style="font-size:12px;color:#6b7280;">Page ${pageIndex + 1} of ${pageCount} — ${escapeHtml(meta.generatedAt)}</div>
    </div>
    <div style="font-size:12px;color:#374151;margin-bottom:18px;">
      La Mayorista (Medellín) vs Corabastos (Bogotá) — ${escapeHtml(meta.rateLabel)}
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:11px;">
      <thead>
        <tr style="background:#f3f4f6;">
          ${['Product', 'Category', 'Unit', 'La Mayorista', 'La Mayorista /kg', 'Corabastos', 'Corabastos /kg', 'Diff % (per kg)', 'Match']
            .map((h) => `<th style="text-align:left;padding:6px 8px;border-bottom:2px solid #d1d5db;">${h}</th>`)
            .join('')}
        </tr>
      </thead>
      <tbody>
        ${rowsChunk
          .map(
            (r) => `
          <tr>
            <td style="padding:5px 8px;border-bottom:1px solid #e5e7eb;">
              ${escapeHtml(r.productEn)}
              <div style="color:#9ca3af;font-size:10px;font-style:italic;">${escapeHtml(r.productEs)}</div>
            </td>
            <td style="padding:5px 8px;border-bottom:1px solid #e5e7eb;">${escapeHtml(r.category)}</td>
            <td style="padding:5px 8px;border-bottom:1px solid #e5e7eb;">${escapeHtml(r.unit)}</td>
            <td style="padding:5px 8px;border-bottom:1px solid #e5e7eb;text-align:right;">${escapeHtml(formatMoneyCell(r.laMayoristaCop, r.laMayoristaUsd))}</td>
            <td style="padding:5px 8px;border-bottom:1px solid #e5e7eb;text-align:right;">${r.laMayoristaPerKgCop != null ? escapeHtml(formatMoneyCell(r.laMayoristaPerKgCop, null)) : '—'}</td>
            <td style="padding:5px 8px;border-bottom:1px solid #e5e7eb;text-align:right;">${escapeHtml(formatMoneyCell(r.corabastosCop, r.corabastosUsd))}</td>
            <td style="padding:5px 8px;border-bottom:1px solid #e5e7eb;text-align:right;">${r.corabastosPerKgCop != null ? escapeHtml(formatMoneyCell(r.corabastosPerKgCop, null)) : '—'}</td>
            <td style="padding:5px 8px;border-bottom:1px solid #e5e7eb;text-align:right;">${r.diffPct != null ? `${r.diffPct.toFixed(1)}%` : '—'}</td>
            <td style="padding:5px 8px;border-bottom:1px solid #e5e7eb;">${escapeHtml(r.sourceTag)}</td>
          </tr>`,
          )
          .join('')}
      </tbody>
    </table>
  `
  return container
}

export async function exportProductsToPdf(rows, meta, filename) {
  const pageBox = computePageBox('letter', 'landscape')
  const chunks = []
  for (let i = 0; i < rows.length; i += ROWS_PER_PDF_PAGE) chunks.push(rows.slice(i, i + ROWS_PER_PDF_PAGE))
  if (chunks.length === 0) chunks.push([])

  const host = document.createElement('div')
  host.style.cssText = 'position:fixed;left:-10000px;top:0;'
  document.body.appendChild(host)

  try {
    const pdf = new jsPDF({ unit: 'in', orientation: 'landscape', format: [pageBox.widthIn, pageBox.heightIn] })
    for (let i = 0; i < chunks.length; i += 1) {
      const pageEl = buildPdfPageElement(chunks[i], i, chunks.length, meta)
      host.appendChild(pageEl)
      // eslint-disable-next-line no-await-in-loop
      const canvas = await html2canvas(pageEl, { scale: 2, backgroundColor: '#ffffff' })
      const heightIn = Math.min((canvas.height / canvas.width) * pageBox.widthIn, pageBox.heightIn)
      if (i > 0) pdf.addPage([pageBox.widthIn, pageBox.heightIn], 'landscape')
      pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, pageBox.widthIn, heightIn)
      host.removeChild(pageEl)
    }
    pdf.save(filename)
  } finally {
    document.body.removeChild(host)
  }
}
