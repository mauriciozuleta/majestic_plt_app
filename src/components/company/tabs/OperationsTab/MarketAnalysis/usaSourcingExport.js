// CSV/PDF export for the USA sourcing table — same approach as
// priceComparisonExport.js (bespoke, reusing html2canvas + jsPDF rather
// than the ledger-style shared PdfExport module, which doesn't fit a flat
// per-product price list any better here than it did for Colombia).

import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'
import { downloadCsv } from '../../../../../utils/exportCsv'
import { computePageBox } from '../../../../shared/PdfExport/paperSizes'

const ROWS_PER_PDF_PAGE = 24

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]))
}

export function exportUsaSourcingToCsv(rows, filename) {
  const headers = ['Category', 'Product', 'Price (USD)', 'Price per kg (USD)', 'Unit', 'Source Date', 'Quality Note', 'Report']
  const csvRows = rows.map((r) => [
    r.category,
    r.productEn,
    r.price,
    r.pricePerKg != null ? r.pricePerKg.toFixed(4) : '',
    r.unit,
    r.sourceDate ?? '',
    r.qualityNote ?? '',
    r.report ?? '',
  ])
  downloadCsv(filename, headers, csvRows)
}

function buildPdfPageElement(rowsChunk, pageIndex, pageCount, meta) {
  const container = document.createElement('div')
  container.style.cssText =
    'width:1400px;background:#ffffff;color:#111827;font-family:Arial,Helvetica,sans-serif;padding:36px;box-sizing:border-box;'
  container.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;">
      <div style="font-size:20px;font-weight:700;">USA Sourcing</div>
      <div style="font-size:12px;color:#6b7280;">Page ${pageIndex + 1} of ${pageCount} — ${escapeHtml(meta.generatedAt)}</div>
    </div>
    <div style="font-size:12px;color:#374151;margin-bottom:18px;">USDA AMS export/domestic wholesale prices — FOB/shipping-point basis, per category.</div>
    <table style="width:100%;border-collapse:collapse;font-size:11px;">
      <thead>
        <tr style="background:#f3f4f6;">
          ${['Category', 'Product', 'Price', 'Price/kg', 'Unit', 'Date', 'Quality Note']
            .map((h) => `<th style="text-align:left;padding:6px 8px;border-bottom:2px solid #d1d5db;">${h}</th>`)
            .join('')}
        </tr>
      </thead>
      <tbody>
        ${rowsChunk
          .map(
            (r) => `
          <tr>
            <td style="padding:5px 8px;border-bottom:1px solid #e5e7eb;">${escapeHtml(r.category)}</td>
            <td style="padding:5px 8px;border-bottom:1px solid #e5e7eb;">${escapeHtml(r.productEn)}</td>
            <td style="padding:5px 8px;border-bottom:1px solid #e5e7eb;text-align:right;">$${escapeHtml(r.price)}</td>
            <td style="padding:5px 8px;border-bottom:1px solid #e5e7eb;text-align:right;">${r.pricePerKg != null ? `$${r.pricePerKg.toFixed(2)}` : '—'}</td>
            <td style="padding:5px 8px;border-bottom:1px solid #e5e7eb;">${escapeHtml(r.unit)}</td>
            <td style="padding:5px 8px;border-bottom:1px solid #e5e7eb;">${escapeHtml(r.sourceDate)}</td>
            <td style="padding:5px 8px;border-bottom:1px solid #e5e7eb;font-size:10px;color:#4b5563;">${escapeHtml(r.qualityNote)}</td>
          </tr>`,
          )
          .join('')}
      </tbody>
    </table>
  `
  return container
}

export async function exportUsaSourcingToPdf(rows, meta, filename) {
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
