import { useCallback, useEffect, useState } from 'react'
import { addEdge, useEdgesState, useNodesState } from '@xyflow/react'
import {
  createOrgChartEdge,
  createOrgChartNode,
  deleteOrgChartEdge,
  deleteOrgChartNode,
  fetchOrgChartEdges,
  fetchOrgChartNodes,
  updateOrgChartNode,
} from '../../../../../services/orgChart'
import { broadcastCompanyDataChange, subscribeToCompanyDataChange } from '../../../../../services/companyDataSync'
import { fetchSettings } from '../../../../../services/settings'
import { getLayoutedNodes } from './orgChartLayout'

function toFlowNode(row) {
  return {
    id: row.id,
    type: 'officeNode',
    position: { x: row.position_x, y: row.position_y },
    data: { officeName: row.office_name, employeeName: row.employee_name, area: row.area },
  }
}

function toFlowEdge(row) {
  return { id: row.id, source: row.source_node_id, target: row.target_node_id }
}

export function useOrgChartData(companyId, selectedYear) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [projectionYears, setProjectionYears] = useState(5)

  const reload = useCallback(async () => {
    if (!companyId) {
      setNodes([])
      setEdges([])
      setLoading(false)
      setError('No company selected')
      return
    }

    setLoading(true)
    try {
      const [nodeRows, edgeRows, settings] = await Promise.all([
        fetchOrgChartNodes(companyId, selectedYear),
        fetchOrgChartEdges(companyId, selectedYear),
        fetchSettings(),
      ])
      const nextProjectionYears = Math.max(5, Math.min(10, Number(settings.projection_years ?? 5)))
      setProjectionYears(nextProjectionYears)
      setNodes(nodeRows.map(toFlowNode))
      setEdges(edgeRows.map(toFlowEdge))
      setError(null)
    } catch (loadError) {
      setError(loadError.message)
    } finally {
      setLoading(false)
    }
  }, [companyId, selectedYear, setEdges, setNodes])

  useEffect(() => {
    reload()
  }, [reload])

  useEffect(() => subscribeToCompanyDataChange(companyId, reload), [companyId, reload])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined

    const handleFocus = () => reload()
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        reload()
      }
    }

    window.addEventListener('focus', handleFocus)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      window.removeEventListener('focus', handleFocus)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [reload])

  const addOffice = useCallback(
    async ({ officeName, employeeName, area }) => {
      const created = await createOrgChartNode(companyId, {
        office_name: officeName,
        employee_name: employeeName || null,
        area: area || null,
        position_x: 80 + Math.round(Math.random() * 200),
        position_y: 80 + Math.round(Math.random() * 200),
      }, selectedYear)
      setNodes((prev) => [...prev, toFlowNode(created)])
      broadcastCompanyDataChange(companyId, 'org-chart:add-office')
    },
    [companyId, selectedYear, setNodes],
  )

  const editOffice = useCallback(
    async (nodeId, { officeName, employeeName, area }) => {
      await updateOrgChartNode(nodeId, {
        office_name: officeName,
        employee_name: employeeName || null,
        area: area || null,
      })
      setNodes((prev) =>
        prev.map((node) =>
          node.id === nodeId
            ? {
                ...node,
                data: { officeName, employeeName, area },
              }
            : node,
        ),
      )
      broadcastCompanyDataChange(companyId, 'org-chart:edit-office')
    },
    [companyId, setNodes],
  )

  const persistNodePosition = useCallback(async (nodeId, position) => {
    await updateOrgChartNode(nodeId, {
      position_x: Math.round(position.x),
      position_y: Math.round(position.y),
    })
    broadcastCompanyDataChange(companyId, 'org-chart:move-office')
  }, [companyId])

  const removeOffice = useCallback(
    async (nodeId) => {
      await deleteOrgChartNode(nodeId)
      setNodes((prev) => prev.filter((node) => node.id !== nodeId))
      setEdges((prev) => prev.filter((edge) => edge.source !== nodeId && edge.target !== nodeId))
      broadcastCompanyDataChange(companyId, 'org-chart:delete-office')
    },
    [companyId, setEdges, setNodes],
  )

  const connectOffices = useCallback(
    async (connection) => {
      if (!connection.source || !connection.target) return
      const created = await createOrgChartEdge(companyId, {
        source_node_id: connection.source,
        target_node_id: connection.target,
      })
      setEdges((prev) => addEdge({ ...connection, id: created.id }, prev))
      broadcastCompanyDataChange(companyId, 'org-chart:connect-offices')
    },
    [companyId, setEdges],
  )

  const removeEdge = useCallback(
    async (edgeId) => {
      await deleteOrgChartEdge(edgeId)
      setEdges((prev) => prev.filter((edge) => edge.id !== edgeId))
      broadcastCompanyDataChange(companyId, 'org-chart:delete-edge')
    },
    [companyId, setEdges],
  )

  const autoArrange = useCallback(
    async (direction = 'TB') => {
      const layouted = getLayoutedNodes(nodes, edges, direction)
      setNodes(layouted)
      await Promise.all(
        layouted.map((node) =>
          updateOrgChartNode(node.id, {
            position_x: Math.round(node.position.x),
            position_y: Math.round(node.position.y),
          }),
        ),
      )
      broadcastCompanyDataChange(companyId, 'org-chart:auto-arrange')
    },
    [companyId, edges, nodes, setNodes],
  )

  return {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    loading,
    error,
    projectionYears,
    addOffice,
    editOffice,
    persistNodePosition,
    removeOffice,
    connectOffices,
    removeEdge,
    autoArrange,
    reload,
  }
}
