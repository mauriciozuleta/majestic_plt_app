import { useParams } from 'react-router-dom'
import CommercialOperationsView from './CommercialOperationsView/CommercialOperationsView'

// Market Analysis moved out to its own module (sidebar ▸ Market Analysis,
// see components/marketAnalysis) — what's left here is Commercial Operations.
function OperationsTab() {
  const { companyId } = useParams()
  return <CommercialOperationsView companyId={companyId} />
}

export default OperationsTab
