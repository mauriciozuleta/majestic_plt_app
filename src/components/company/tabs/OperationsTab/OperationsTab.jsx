import { lazy, Suspense } from 'react'
import { useParams } from 'react-router-dom'
import CommercialOperationsView from './CommercialOperationsView/CommercialOperationsView'
const PackerPage = lazy(() => import('../../../../features/packer/PackerPage'))

// Market Analysis moved out to its own module (sidebar ▸ Market Analysis,
// see components/marketAnalysis) — what's left here is Commercial Operations.
function OperationsTab() {
  const { companyId, sub } = useParams()
  if (sub === 'cargo-load-operations') return <Suspense fallback={<p>Loading Cargo Load Operations…</p>}><PackerPage key={companyId} companyId={companyId} /></Suspense>
  return <CommercialOperationsView companyId={companyId} />
}

export default OperationsTab
