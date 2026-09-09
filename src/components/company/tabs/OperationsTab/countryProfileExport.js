// PDF export for a Country Commercial Profile (AI-researched markdown
// document). Visually matches the shared PdfExport module's letterhead/
// footer branding (src/components/shared/PdfExport/PdfDocument.css) —
// same fonts, colors, and document chrome as the Start-up Investment
// export — but that module is hard-wired to a ledger table shape (periods,
// category subtotals, one money total per row), which prose content
// doesn't fit. Rather than force a markdown document through a table
// renderer, this replicates the same visual identity with its own,
// simpler flow: real-height DOM measurement to paginate prose blocks
// (headings/paragraphs/lists), the same html2canvas + jsPDF pipeline the
// shared module itself uses.

import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'
import { computePageBox } from '../../../shared/PdfExport/paperSizes'

const FONTS_LINK =
  "@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');"

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]))
}

function inlineMarkdown(text) {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
}

// Parses the fixed heading/paragraph/list/blockquote shape the profile
// prompt asks Claude to write in — not a general-purpose Markdown parser.
function parseMarkdownBlocks(markdown) {
  const lines = markdown.split('\n')
  const blocks = []
  let paragraphLines = []

  const flushParagraph = () => {
    if (paragraphLines.length) {
      blocks.push({ type: 'p', html: inlineMarkdown(paragraphLines.join(' ')) })
      paragraphLines = []
    }
  }

  lines.forEach((rawLine) => {
    const line = rawLine.trim()
    if (!line) {
      flushParagraph()
      return
    }
    if (line.startsWith('# ')) {
      flushParagraph()
      blocks.push({ type: 'h1', html: inlineMarkdown(line.slice(2)) })
    } else if (line.startsWith('## ')) {
      flushParagraph()
      blocks.push({ type: 'h2', html: inlineMarkdown(line.slice(3)) })
    } else if (line.startsWith('> ')) {
      flushParagraph()
      blocks.push({ type: 'blockquote', html: inlineMarkdown(line.slice(2)) })
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      flushParagraph()
      blocks.push({ type: 'li', html: inlineMarkdown(line.slice(2)) })
    } else {
      paragraphLines.push(line)
    }
  })
  flushParagraph()
  return blocks
}

function blockElement(block) {
  const el = document.createElement(block.type === 'li' ? 'div' : block.type === 'blockquote' ? 'div' : block.type)
  el.className = `country-profile-pdf__${block.type}`
  el.innerHTML = block.type === 'li' ? `&bull;&nbsp; ${block.html}` : block.html
  return el
}

const BLOCK_STYLES = `
  ${FONTS_LINK}
  .country-profile-pdf { font-family: 'IBM Plex Sans', system-ui, sans-serif; color: #171b1f; }
  .country-profile-pdf__h1 { font-family: 'Fraunces', Georgia, serif; font-weight: 600; font-size: 1.3rem; margin: 0 0 0.3rem; text-wrap: balance; }
  .country-profile-pdf__h2 { font-family: 'Fraunces', Georgia, serif; font-weight: 600; font-size: 1.05rem; color: #0c7a52; margin: 1.1rem 0 0.4rem; border-bottom: 1px solid #dfe3e6; padding-bottom: 0.25rem; }
  .country-profile-pdf__p { font-size: 0.82rem; line-height: 1.55; margin: 0 0 0.6rem; color: #171b1f; }
  .country-profile-pdf__li { font-size: 0.82rem; line-height: 1.5; margin: 0 0 0.35rem; padding-left: 0.9rem; text-indent: -0.9rem; color: #171b1f; }
  .country-profile-pdf__blockquote { font-size: 0.74rem; line-height: 1.5; margin: 0 0 0.8rem; padding: 0.5rem 0.75rem; background: #fdf1e2; border: 1px solid #f0d6ac; border-radius: 6px; color: #a45400; }
`

function buildLetterhead(company, title, eyebrow) {
  const header = document.createElement('div')
  header.style.cssText =
    'display:flex;align-items:flex-start;justify-content:space-between;gap:1.5rem;padding-bottom:1.1rem;border-bottom:1px solid #c7ccd1;margin-bottom:0.8rem;'
  const logoHtml = company?.logo
    ? `<img src="${company.logo}" style="width:46px;height:46px;border-radius:9px;object-fit:contain;background:#fff;border:1px solid #dfe3e6;padding:3px;" />`
    : `<div style="width:46px;height:46px;border-radius:9px;background:#f4f6f5;border:1px solid #e0e4e2;display:flex;align-items:center;justify-content:center;font-family:'Fraunces',Georgia,serif;font-weight:600;color:#5b6570;">${escapeHtml((company?.name ?? '?').slice(0, 2).toUpperCase())}</div>`
  header.innerHTML = `
    <div style="display:flex;align-items:center;gap:0.85rem;">
      ${logoHtml}
      <div>
        <div style="font-family:'Fraunces',Georgia,serif;font-weight:600;font-size:1.32rem;letter-spacing:-0.01em;">${escapeHtml(company?.name ?? 'Untitled Company')}</div>
        ${company?.companyType ? `<div style="font-size:0.68rem;color:#5b6570;text-transform:uppercase;letter-spacing:0.08em;margin-top:0.15rem;">${escapeHtml(company.companyType)}</div>` : ''}
      </div>
    </div>
    <div style="text-align:right;">
      <div style="font-size:0.66rem;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;color:#5b6570;">${escapeHtml(eyebrow)}</div>
      <div style="font-family:'Fraunces',Georgia,serif;font-weight:600;font-size:1.1rem;margin-top:0.15rem;">${escapeHtml(title)}</div>
    </div>
  `
  return header
}

function buildFooter(company, title, exportedBy) {
  const footer = document.createElement('div')
  footer.style.cssText = 'margin-top:1.4rem;padding-top:1rem;border-top:1px solid #dfe3e6;font-size:0.62rem;color:#5b6570;'
  const now = new Date()
  footer.innerHTML = `
    <div style="display:flex;justify-content:space-between;">
      <span>Exported by ${escapeHtml(exportedBy || 'Unknown user')}</span>
      <span>${now.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}</span>
    </div>
    <div style="display:flex;justify-content:space-between;margin-top:0.4rem;">
      <span>${escapeHtml(company?.name ?? '')} &middot; ${escapeHtml(title)}</span>
    </div>
  `
  return footer
}

export async function exportCountryProfileToPdf(markdown, { company, title, exportedBy }, filename) {
  const pageBox = computePageBox('letter', 'portrait')
  const pageWidthPx = pageBox.widthIn * 96
  const pageHeightPx = pageBox.heightIn * 96
  const paddingPx = 2.3 * 16 * 6 // approximate rem->px at 16px root, matching PdfDocument's page padding scale
  const contentWidthPx = pageWidthPx - 2.4 * 16 * 6
  const contentHeightPx = pageHeightPx - paddingPx

  const blocks = parseMarkdownBlocks(markdown)

  // Measure real rendered block heights off-screen before paginating —
  // more reliable than pre-estimating, since prose block heights vary a
  // lot by type and content length (unlike the ledger's uniform rows).
  const styleTag = document.createElement('style')
  styleTag.textContent = BLOCK_STYLES
  document.head.appendChild(styleTag)

  const measureHost = document.createElement('div')
  measureHost.className = 'country-profile-pdf'
  measureHost.style.cssText = `position:fixed;left:-10000px;top:0;width:${contentWidthPx}px;`
  document.body.appendChild(measureHost)

  const measured = blocks.map((block) => {
    const el = blockElement(block)
    measureHost.appendChild(el)
    const height = el.getBoundingClientRect().height
    return { block, height }
  })
  document.body.removeChild(measureHost)

  const headerReserve = 110
  const footerReserve = 90
  const pages = []
  let current = []
  let currentHeight = 0
  measured.forEach(({ block, height }, index) => {
    const isFirstPage = pages.length === 0
    const available = contentHeightPx - (isFirstPage ? headerReserve : 0) - (index === measured.length - 1 ? footerReserve : 0)
    if (current.length && currentHeight + height > available) {
      pages.push(current)
      current = []
      currentHeight = 0
    }
    current.push(block)
    currentHeight += height
  })
  if (current.length) pages.push(current)
  if (pages.length === 0) pages.push([])

  const host = document.createElement('div')
  host.style.cssText = 'position:fixed;left:-10000px;top:0;'
  document.body.appendChild(host)

  try {
    const pdf = new jsPDF({ unit: 'in', orientation: 'portrait', format: [pageBox.widthIn, pageBox.heightIn] })
    for (let i = 0; i < pages.length; i += 1) {
      const pageEl = document.createElement('div')
      pageEl.className = 'country-profile-pdf'
      pageEl.style.cssText = `width:${pageWidthPx}px;min-height:${pageHeightPx}px;background:#fdfcf9;padding:2.3rem 2.4rem 1.9rem;box-sizing:border-box;`
      if (i === 0) pageEl.appendChild(buildLetterhead(company, title, 'Country Commercial Profile'))
      pages[i].forEach((block) => pageEl.appendChild(blockElement(block)))
      if (i === pages.length - 1) pageEl.appendChild(buildFooter(company, title, exportedBy))

      host.appendChild(pageEl)
      // eslint-disable-next-line no-await-in-loop
      const canvas = await html2canvas(pageEl, { scale: 2, backgroundColor: '#fdfcf9' })
      const heightIn = Math.min((canvas.height / canvas.width) * pageBox.widthIn, pageBox.heightIn)
      if (i > 0) pdf.addPage([pageBox.widthIn, pageBox.heightIn], 'portrait')
      pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, pageBox.widthIn, heightIn)
      host.removeChild(pageEl)
    }
    pdf.save(filename)
  } finally {
    document.body.removeChild(host)
    document.head.removeChild(styleTag)
  }
}
