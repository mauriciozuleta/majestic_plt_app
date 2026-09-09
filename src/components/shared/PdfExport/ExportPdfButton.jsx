import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { IconFileExport } from '@tabler/icons-react'
import { useAppStore } from '../../../store/useAppStore'
import PdfExportModal from './PdfExportModal'
import './ExportPdfButton.css'

function ExportPdfButton({ spec, companyId: companyIdProp, label = 'Export', className }) {
  const params = useParams()
  const companyId = companyIdProp ?? params.companyId
  const companies = useAppStore((state) => state.companies)
  const company = companies.find((item) => item.id === companyId) ?? null
  const currentUser = useAppStore((state) => state.currentUser)
  const [open, setOpen] = useState(false)

  return (
    <>
      <button type="button" className={className ?? 'pdf-export-trigger'} onClick={() => setOpen(true)}>
        <IconFileExport size={14} stroke={1.8} />
        {label}
      </button>
      {open && (
        <PdfExportModal spec={spec} company={company} exportedBy={currentUser?.name} onClose={() => setOpen(false)} />
      )}
    </>
  )
}

export default ExportPdfButton
