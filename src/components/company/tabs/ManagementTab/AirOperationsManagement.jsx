import { Navigate, useParams } from 'react-router-dom'
import { useAppStore } from '../../../../store/useAppStore'
import FinancialSubNav from '../FinancialTab/FinancialSubNav'
import StubSection from '../FinancialTab/StubSection'
import FleetManagement from './FleetManagement/FleetManagement'

const SECTIONS = [
  { slug: 'crew-management', label: 'Crew Management' },
  { slug: 'training-management', label: 'Training Management' },
  { slug: 'fleet-management', label: 'Fleet Management' },
]

export default function AirOperationsManagement() {
  const { companyId, section } = useParams()
  const company = useAppStore(state => state.companies.find(item => item.id === companyId))
  const basePath = `/company/${companyId}/management/air-operations-management`
  if (!/majestic.*cargo/i.test(company?.name || '')) return <Navigate to={`/company/${companyId}/management/roadmap`} replace />
  if (!SECTIONS.some(item => item.slug === section)) return <Navigate to={`${basePath}/crew-management`} replace />
  return <div className="panel-surface">
    <h3>Air Operations Management</h3>
    <FinancialSubNav basePath={basePath} items={SECTIONS} />
    {section === 'fleet-management' ? <FleetManagement key={companyId} companyId={companyId} /> :
      <StubSection title={SECTIONS.find(item => item.slug === section).label} description={section === 'crew-management' ? 'Crew management workspace.' : 'Training management workspace.'} />}
  </div>
}
