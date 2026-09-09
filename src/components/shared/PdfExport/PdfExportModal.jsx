import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'
import { IconDownload, IconLayoutColumns, IconLayoutRows, IconX } from '@tabler/icons-react'
import PdfDocument from './PdfDocument'
import { PAPER_SIZES, computePageBox } from './paperSizes'
import './PdfExportModal.css'

function slugify(value) {
  return (value || 'export')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
}

function PdfExportModal({ spec, company, exportedBy, onClose }) {
  const [orientation, setOrientation] = useState('portrait')
  const [paperSize, setPaperSize] = useState('letter')
  const [generating, setGenerating] = useState(false)
  const [generateError, setGenerateError] = useState('')
  const previewRef = useRef(null)

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const handleDownload = async () => {
    if (!previewRef.current) return
    setGenerating(true)
    setGenerateError('')
    try {
      const pageBox = computePageBox(paperSize, orientation)
      const pageEls = Array.from(previewRef.current.querySelectorAll('.pdf-doc__page'))
      if (pageEls.length === 0) throw new Error('Nothing to export')

      const canvases = []
      for (const pageEl of pageEls) {
        // eslint-disable-next-line no-await-in-loop
        const canvas = await html2canvas(pageEl, { scale: 2, backgroundColor: '#ffffff', useCORS: true })
        canvases.push(canvas)
      }

      const firstHeightIn = (canvases[0].height / canvases[0].width) * pageBox.widthIn
      const pdf = new jsPDF({ unit: 'in', orientation, format: [pageBox.widthIn, firstHeightIn] })

      canvases.forEach((canvas, index) => {
        const heightIn = (canvas.height / canvas.width) * pageBox.widthIn
        if (index > 0) pdf.addPage([pageBox.widthIn, heightIn], orientation)
        pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, pageBox.widthIn, heightIn)
      })

      const fileName = `${slugify(company?.name)}-${slugify(spec.documentTitle)}.pdf`
      pdf.save(fileName)
    } catch (err) {
      setGenerateError(err.message || 'Could not generate the PDF')
    } finally {
      setGenerating(false)
    }
  }

  return createPortal(
    <div className="pdf-export-modal__overlay">
      <div className="pdf-export-modal" role="dialog" aria-modal="true" aria-label="Export to PDF preview">
        <header className="pdf-export-modal__header">
          <h3>Export to PDF</h3>
          <div className="pdf-export-modal__toggle" role="group" aria-label="Paper size">
            {Object.entries(PAPER_SIZES).map(([key, size]) => (
              <button key={key} type="button" aria-pressed={paperSize === key} onClick={() => setPaperSize(key)}>
                {size.label}
              </button>
            ))}
          </div>
          <div className="pdf-export-modal__toggle" role="group" aria-label="Page orientation">
            <button type="button" aria-pressed={orientation === 'portrait'} onClick={() => setOrientation('portrait')}>
              <IconLayoutRows size={14} stroke={1.8} /> Portrait
            </button>
            <button type="button" aria-pressed={orientation === 'landscape'} onClick={() => setOrientation('landscape')}>
              <IconLayoutColumns size={14} stroke={1.8} /> Landscape
            </button>
          </div>
          <button type="button" className="pdf-export-modal__close" onClick={onClose} title="Close">
            <IconX size={16} stroke={1.8} />
          </button>
        </header>

        <div className="pdf-export-modal__preview-wrap">
          <div className="pdf-export-modal__preview" ref={previewRef}>
            <PdfDocument
              spec={spec}
              company={company}
              orientation={orientation}
              paperSize={paperSize}
              exportedBy={exportedBy}
              variant="preview"
            />
          </div>
        </div>

        <footer className="pdf-export-modal__footer">
          <span className="pdf-export-modal__hint">
            {generateError ? <span className="pdf-export-modal__error">{generateError}</span> : 'Each sheet above is one PDF page.'}
          </span>
          <div className="pdf-export-modal__actions">
            <button type="button" className="pdf-export-modal__cancel" onClick={onClose} disabled={generating}>
              Cancel
            </button>
            <button type="button" className="pdf-export-modal__print" onClick={handleDownload} disabled={generating}>
              <IconDownload size={14} stroke={1.8} /> {generating ? 'Generating…' : 'Download PDF'}
            </button>
          </div>
        </footer>
      </div>
    </div>,
    document.body,
  )
}

export default PdfExportModal
