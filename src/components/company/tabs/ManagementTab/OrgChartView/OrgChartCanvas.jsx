import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Background, Controls, MiniMap, ReactFlow } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import OfficeNode from './OfficeNode'
import './OrgChartView.css'

function OrgChartCanvas({
  nodes,
  edges,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onNodeDragStop,
  onNodeClick,
  onEdgesDelete,
}) {
  const nodeTypes = useMemo(() => ({ officeNode: OfficeNode }), [])
  const canvasRef = useRef(null)
  const [reactFlowInstance, setReactFlowInstance] = useState(null)
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 })

  const handleNodeDragStop = useCallback(
    (_, node) => onNodeDragStop(node.id, node.position),
    [onNodeDragStop],
  )

  useEffect(() => {
    if (!canvasRef.current || typeof ResizeObserver === 'undefined') return undefined

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return

      const { width, height } = entry.contentRect
      setCanvasSize({ width: Math.round(width), height: Math.round(height) })
    })

    observer.observe(canvasRef.current)

    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!reactFlowInstance || nodes.length === 0 || canvasSize.width === 0 || canvasSize.height === 0) {
      return undefined
    }

    const frameId = window.requestAnimationFrame(() => {
      reactFlowInstance.fitView({ padding: 0.2, duration: 0 })
    })

    return () => window.cancelAnimationFrame(frameId)
  }, [canvasSize.height, canvasSize.width, edges.length, nodes.length, reactFlowInstance])

  return (
    <div className="org-chart-canvas" ref={canvasRef}>
      {canvasSize.width > 0 && canvasSize.height > 0 ? (
        <ReactFlow
          style={{ width: '100%', height: '100%' }}
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          defaultEdgeOptions={{ type: 'smoothstep' }}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeDragStop={handleNodeDragStop}
          onNodeClick={(_, node) => onNodeClick(node)}
          onEdgesDelete={onEdgesDelete}
          onInit={setReactFlowInstance}
        >
          <Background gap={16} />
          <Controls />
          <MiniMap pannable zoomable />
        </ReactFlow>
      ) : null}
    </div>
  )
}

export default OrgChartCanvas
