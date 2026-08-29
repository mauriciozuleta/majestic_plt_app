import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import AddOfficeModal from './AddOfficeModal'
import OrgChartCanvas from './OrgChartCanvas'
import { useOrgChartData } from './useOrgChartData'
import './OrgChartView.css'

function OrgChartView({ companyId: companyIdProp }) {
  const params = useParams()
  const companyId = companyIdProp ?? params.companyId
  const [isModalOpen, setModalOpen] = useState(false)
  const [selectedNodeId, setSelectedNodeId] = useState(null)
  const [selectedYear, setSelectedYear] = useState(0)
  const [editorValues, setEditorValues] = useState({ officeName: '', employeeName: '', area: '' })

  const {
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
  } = useOrgChartData(companyId, selectedYear)

  useEffect(() => {
    setSelectedYear((previousYear) => Math.max(0, Math.min(Number(previousYear ?? 0), projectionYears)))
  }, [projectionYears])

  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedNodeId) ?? null,
    [nodes, selectedNodeId],
  )

  useEffect(() => {
    if (!selectedNode) {
      setEditorValues({ officeName: '', employeeName: '', area: '' })
      return
    }

    setEditorValues({
      officeName: selectedNode.data.officeName || '',
      employeeName: selectedNode.data.employeeName || '',
      area: selectedNode.data.area || '',
    })
  }, [selectedNode])

  return (
    <div className="org-chart-view">
      <div className="org-chart-view__toolbar">
        <label className="org-chart-view__year-selector">
          Projection year
          <select
            value={selectedYear}
            onChange={(event) => setSelectedYear(Number(event.target.value))}
            aria-label="Select org chart projection year"
          >
            {Array.from({ length: projectionYears + 1 }, (_, index) => index).map((yearNumber) => (
              <option key={yearNumber} value={yearNumber}>
                Year {yearNumber}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="org-chart-view__add-btn org-chart-view__add-btn--primary"
          onClick={() => setModalOpen(true)}
        >
          + Add office
        </button>
        <button type="button" className="org-chart-view__add-btn" onClick={() => autoArrange('TB')}>
          Auto-arrange
        </button>
      </div>

      <OrgChartCanvas
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={connectOffices}
        onNodeDragStop={persistNodePosition}
        onNodeClick={(node) => setSelectedNodeId(node.id)}
        onEdgesDelete={(deletedEdges) => {
          deletedEdges.forEach((edge) => {
            removeEdge(edge.id)
          })
        }}
      />

      {loading && nodes.length === 0 ? (
        <div className="org-chart-view__status">Loading org chart...</div>
      ) : null}
      {error && nodes.length === 0 ? (
        <div className="org-chart-view__status org-chart-view__status--error">{error}</div>
      ) : null}

      {selectedNode ? (
        <section className="org-chart-view__editor">
          <h4>Edit office</h4>
          <form
            className="org-chart-view__editor-form"
            onSubmit={async (event) => {
              event.preventDefault()
              await editOffice(selectedNode.id, editorValues)
            }}
          >
            <label>
              Office name
              <input
                type="text"
                value={editorValues.officeName}
                onChange={(event) =>
                  setEditorValues((prev) => ({ ...prev, officeName: event.target.value }))
                }
              />
            </label>
            <label>
              Employee name
              <input
                type="text"
                value={editorValues.employeeName}
                onChange={(event) =>
                  setEditorValues((prev) => ({ ...prev, employeeName: event.target.value }))
                }
              />
            </label>
            <label>
              Area
              <input
                type="text"
                value={editorValues.area}
                onChange={(event) => setEditorValues((prev) => ({ ...prev, area: event.target.value }))}
              />
            </label>
            <div className="org-chart-view__editor-actions">
              <button type="submit" className="org-chart-view__editor-save">
                Save
              </button>
              <button
                type="button"
                className="org-chart-view__editor-delete"
                onClick={async () => {
                  await removeOffice(selectedNode.id)
                  setSelectedNodeId(null)
                }}
              >
                Delete
              </button>
            </div>
          </form>
        </section>
      ) : (
        <div className="org-chart-view__status">Select an office node to edit details.</div>
      )}

      {isModalOpen && (
        <AddOfficeModal
          onSave={async (values) => {
            await addOffice(values)
            setModalOpen(false)
          }}
          onCancel={() => setModalOpen(false)}
        />
      )}
    </div>
  )
}

export default OrgChartView
