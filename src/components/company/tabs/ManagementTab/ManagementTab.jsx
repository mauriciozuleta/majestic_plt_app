import { useParams } from 'react-router-dom'
import { Navigate } from 'react-router-dom'
import RoadmapView from './RoadmapView/RoadmapView'
import OrgChartView from './OrgChartView/OrgChartView'
import PayrollView from './PayrollView/PayrollView'

function ManagementTab() {
  const { companyId, sub } = useParams()

  switch (sub) {
    case 'org-chart':
      return <OrgChartView companyId={companyId} />
    case 'payroll':
      return <PayrollView companyId={companyId} />
    case 'settings':
      return <Navigate to="/settings" replace />
    case 'roadmap':
    default:
      return <RoadmapView companyId={companyId} />
  }
}

export default ManagementTab
