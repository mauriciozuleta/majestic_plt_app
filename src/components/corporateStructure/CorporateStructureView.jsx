import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '../../store/useAppStore'
import OrgChartCanvas from '../company/tabs/ManagementTab/OrgChartView/OrgChartCanvas'
import { getLayoutedNodes } from '../company/tabs/ManagementTab/OrgChartView/orgChartLayout'
import CompanyNode from './CompanyNode'
import './CorporateStructureView.css'

const NODE_WIDTH = 190
const NODE_HEIGHT = 96
const NODE_TYPES = { companyNode: CompanyNode }

// Read-only, so every React Flow interaction callback below is a no-op —
// nodes/edges are always freshly derived from useAppStore's companies (see
// buildGraph), so a dragged position or "deleted" edge would just be
// overwritten by the next render anyway. Passing real no-ops (rather than
// leaving these undefined) avoids OrgChartCanvas's own handlers — written
// for the editable org chart — throwing when they call through.
const noop = () => {}

// This is the corporate ownership structure (Company.companyDependency /
// parentCompanyId — which company legally sits under which), distinct from
// Commercial Structure (a company's own countries/branches/markets).
function buildGraph(companies) {
  const companyById = new Map(companies.map((company) => [company.id, company]))

  const rawNodes = companies.map((company) => {
    const parent = company.companyDependency === 'Children' ? companyById.get(company.parentCompanyId) : null
    return {
      id: company.id,
      type: 'companyNode',
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      position: { x: 0, y: 0 },
      data: {
        name: company.name,
        logo: company.logo,
        accentFrom: company.accentFrom,
        accentTo: company.accentTo,
        dependency: company.companyDependency,
        parentName: parent?.name ?? null,
      },
    }
  })

  const edges = companies
    .filter((company) => company.companyDependency === 'Children' && companyById.has(company.parentCompanyId))
    .map((company) => ({
      id: `${company.parentCompanyId}-${company.id}`,
      source: company.parentCompanyId,
      target: company.id,
    }))

  const nodes = getLayoutedNodes(rawNodes, edges, 'TB', {
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
    nodesep: 50,
    ranksep: 90,
  })

  return { nodes, edges }
}

function CorporateStructureView() {
  const companies = useAppStore((state) => state.companies)
  const navigate = useNavigate()

  // Recomputed whenever the companies list changes (a new company added
  // anywhere in the app updates this store, per useAppStore.addCompany),
  // so the chart always reflects the current portfolio without any extra
  // wiring needed here.
  const { nodes, edges } = useMemo(() => buildGraph(companies), [companies])

  return (
    <div className="corporate-structure-view">
      <header className="corporate-structure-view__header">
        <h3>Corporate Structure</h3>
        <p>
          How the companies in this portfolio relate to each other — stand-alone or a subsidiary of another company.
          Click a card to open that company.
        </p>
      </header>

      {companies.length === 0 ? (
        <div className="corporate-structure-view__status">No companies yet — add one from the sidebar to see it here.</div>
      ) : (
        <OrgChartCanvas
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onNodesChange={noop}
          onEdgesChange={noop}
          onConnect={noop}
          onNodeDragStop={noop}
          onNodeClick={(node) => navigate(`/company/${node.id}`)}
          onEdgesDelete={noop}
          showMiniMap={false}
        />
      )}
    </div>
  )
}

export default CorporateStructureView
