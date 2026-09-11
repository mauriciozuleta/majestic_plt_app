import { useEffect, useMemo, useState } from 'react'
import { useEdgesState, useNodesState } from '@xyflow/react'
import OrgChartCanvas from '../../company/tabs/ManagementTab/OrgChartView/OrgChartCanvas'
import { getLayoutedNodes } from '../../company/tabs/ManagementTab/OrgChartView/orgChartLayout'
import StructureNode from './StructureNode'
import './CommercialStructureChart.css'

const nodeTypes = { structureNode: StructureNode }

function buildGraph(companyName, regions, countries, branches, selection, onDeleteNode) {
  const rawNodes = []
  const edges = []

  rawNodes.push({
    id: 'company-root',
    type: 'structureNode',
    data: {
      kind: 'company',
      label: companyName || 'Company',
    },
    position: { x: 0, y: 0 },
  })

  regions.forEach((region) => {
    rawNodes.push({
      id: `region-${region.id}`,
      type: 'structureNode',
      data: {
        kind: 'region',
        label: region.name,
        manager: region.manager_name,
        user: region.user_name,
      },
      selected: region.id === selection.regionId,
      position: { x: 0, y: 0 },
    })
    edges.push({ id: `e-company-${region.id}`, source: 'company-root', target: `region-${region.id}` })
  })

  countries.forEach((country) => {
    rawNodes.push({
      id: `country-${country.id}`,
      type: 'structureNode',
      data: {
        kind: 'country',
        label: country.name,
        sub: [country.country_code, country.currency_code].filter(Boolean).join(' / '),
        manager: country.manager_name,
        user: country.user_name,
        onDelete: onDeleteNode ? () => onDeleteNode('country', country) : undefined,
      },
      selected: country.id === selection.countryId,
      position: { x: 0, y: 0 },
    })
    if (country.region_id) {
      edges.push({ id: `e-${country.region_id}-${country.id}`, source: `region-${country.region_id}`, target: `country-${country.id}` })
    }
  })

  branches.forEach((branch) => {
    rawNodes.push({
      id: `branch-${branch.id}`,
      type: 'structureNode',
      data: {
        kind: 'branch',
        label: branch.name,
        sub: branch.airport,
        manager: branch.manager_name,
        user: branch.user_name,
        onDelete: onDeleteNode ? () => onDeleteNode('branch', branch) : undefined,
      },
      selected: branch.id === selection.branchId,
      position: { x: 0, y: 0 },
    })
    if (branch.country_id) {
      edges.push({ id: `e-${branch.country_id}-${branch.id}`, source: `country-${branch.country_id}`, target: `branch-${branch.id}` })
    }
  })

  const nodes = getLayoutedNodes(rawNodes, edges, 'TB', {
    width: 230,
    height: 118,
    nodesep: 56,
    ranksep: 90,
  })

  return { nodes, edges }
}

function CommercialStructureChart({
  companyName,
  regions,
  countries,
  branches,
  selectedRegionId,
  selectedCountryId,
  selectedBranchId,
  onSelectNode,
  onDeleteNode,
}) {
  const [showMiniMap, setShowMiniMap] = useState(false)

  const selection = useMemo(
    () => ({ regionId: selectedRegionId, countryId: selectedCountryId, branchId: selectedBranchId }),
    [selectedRegionId, selectedCountryId, selectedBranchId],
  )

  const graph = useMemo(
    () => buildGraph(companyName, regions, countries, branches, selection, onDeleteNode),
    [companyName, regions, countries, branches, selection, onDeleteNode],
  )

  const [nodes, setNodes, onNodesChange] = useNodesState(graph.nodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(graph.edges)

  useEffect(() => {
    setNodes(graph.nodes)
    setEdges(graph.edges)
  }, [graph, setNodes, setEdges])

  const handleNodeClick = (node) => {
    const [kind] = node.id.split('-')
    const recordId = node.id.slice(kind.length + 1)

    if (kind === 'region') {
      const region = regions.find((item) => item.id === recordId)
      if (region) onSelectNode('region', region)
    } else if (kind === 'country') {
      const country = countries.find((item) => item.id === recordId)
      if (country) onSelectNode('country', country)
    } else if (kind === 'branch') {
      const branch = branches.find((item) => item.id === recordId)
      if (branch) onSelectNode('branch', branch)
    }
  }

  const handleAutoArrange = () => {
    setNodes(graph.nodes)
    setEdges(graph.edges)
  }

  if (regions.length === 0) {
    return <div className="commercial-structure-chart__empty">No commercial structure data yet.</div>
  }

  return (
    <div className="commercial-structure-chart">
      <div className="commercial-structure-chart__toolbar">
        <button type="button" onClick={() => setShowMiniMap((value) => !value)}>
          {showMiniMap ? 'Hide Mini Map' : 'Show Mini Map'}
        </button>
        <button type="button" onClick={handleAutoArrange}>
          Auto Arrange
        </button>
      </div>
      <OrgChartCanvas
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={() => {}}
        onNodeDragStop={() => {}}
        onNodeClick={handleNodeClick}
        onEdgesDelete={() => {}}
        showMiniMap={showMiniMap}
        showInteractive={false}
      />
    </div>
  )
}

export default CommercialStructureChart
