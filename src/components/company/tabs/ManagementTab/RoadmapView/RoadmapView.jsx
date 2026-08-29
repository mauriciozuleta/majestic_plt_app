import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAppStore } from '../../../../../store/useAppStore'
import RoadmapToolbar from './RoadmapToolbar'
import RoadmapChart from './RoadmapChart'
import TaskEditPanel from './TaskEditPanel'
import { useRoadmapData } from './useRoadmapData'
import { subscribeToCompanyDataChange } from '../../../../../services/companyDataSync'
import { fetchSettings } from '../../../../../services/settings'
import './RoadmapView.css'

function buildTaskHierarchy(tasks) {
  const byId = new Map(tasks.map((task) => [task.id, { ...task, children: [] }]))
  const roots = []

  tasks.forEach((task) => {
    const current = byId.get(task.id)
    const parent = task.parent_task_id ? byId.get(task.parent_task_id) : null
    if (parent && parent.id !== current.id) {
      parent.children.push(current)
      return
    }
    roots.push(current)
  })

  const bySortIndexThenId = (a, b) => {
    const left = Number(a.sort_index ?? 0)
    const right = Number(b.sort_index ?? 0)
    if (left === right) return String(a.id).localeCompare(String(b.id))
    return left - right
  }

  roots.sort(bySortIndexThenId)
  byId.forEach((node) => {
    node.children.sort(bySortIndexThenId)
  })

  const derivedById = new Map()

  function derive(node, depth = 0) {
    const derivedChildren = node.children.map((child) => derive(child, depth + 1))
    const descendants = derivedChildren.flatMap((child) => [child.id, ...child.descendantIds])
    const isGroupTask = derivedChildren.length > 0

    let start = node.start
    let end = node.end
    if (isGroupTask) {
      start = derivedChildren.reduce(
        (earliest, child) => (child.start < earliest ? child.start : earliest),
        derivedChildren[0].start,
      )
      end = derivedChildren.reduce(
        (latest, child) => (child.end > latest ? child.end : latest),
        derivedChildren[0].end,
      )
    }

    const derived = {
      ...node,
      depth,
      start,
      end,
      isGroupTask,
      childIds: derivedChildren.map((child) => child.id),
      descendantIds: descendants,
      children: derivedChildren,
    }
    derivedById.set(derived.id, derived)
    return derived
  }

  const rootDerived = roots.map((root) => derive(root, 0))
  const flat = []
  const flatten = (node) => {
    flat.push(node)
    node.children.forEach(flatten)
  }
  rootDerived.forEach(flatten)

  const orderedIds = flat.map((task) => task.id)
  return { flat, derivedById, orderedIds }
}

function RoadmapView({ companyId: companyIdProp }) {
  const [zoom, setZoom] = useState('Week')
  const [zoomScale, setZoomScale] = useState(1)
  const [calendarMode, setCalendarMode] = useState('real')
  const params = useParams()
  const companyId = companyIdProp ?? params.companyId
  const company = useAppStore((state) =>
    state.companies.find((entry) => entry.id === companyId),
  )
  const companies = useAppStore((state) => state.companies)

  const companyThemeStyle = company
    ? {
        '--roadmap-progress-color': company.accentFrom,
        '--roadmap-progress-outline': company.accentTo,
      }
    : undefined

  const {
    tasks,
    loading,
    error,
    selectedTask,
    selectedTaskId,
    setSelectedTaskId,
    addTask,
    saveTask,
    removeTask,
    setTaskParent,
  } = useRoadmapData(companyId)

  const { flat: displayTasks, derivedById, orderedIds } = useMemo(() => buildTaskHierarchy(tasks), [tasks])
  const selectedTaskDerived = useMemo(
    () => (selectedTaskId ? derivedById.get(selectedTaskId) ?? null : null),
    [derivedById, selectedTaskId],
  )

  const selectedTaskIndex = selectedTaskDerived ? orderedIds.indexOf(selectedTaskDerived.id) : -1
  const previousTaskId = selectedTaskIndex > 0 ? orderedIds[selectedTaskIndex - 1] : null
  const previousTask = previousTaskId ? derivedById.get(previousTaskId) ?? null : null
  const canIndent = Boolean(
    selectedTaskDerived
      && previousTask
      && previousTask.id !== selectedTaskDerived.id
      && !selectedTaskDerived.descendantIds.includes(previousTask.id),
  )

  const parentTask = selectedTaskDerived?.parent_task_id
    ? derivedById.get(selectedTaskDerived.parent_task_id) ?? null
    : null
  const canOutdent = Boolean(selectedTaskDerived && selectedTaskDerived.parent_task_id)
  const selectedTaskChildren = selectedTaskDerived?.children ?? []
  const selectedTaskParentId = selectedTaskDerived?.parent_task_id ?? null
  const siblingTasks = selectedTaskDerived
    ? displayTasks.filter((task) => (task.parent_task_id ?? null) === selectedTaskParentId)
    : []
  const selectedSiblingIndex = selectedTaskDerived
    ? siblingTasks.findIndex((task) => task.id === selectedTaskDerived.id)
    : -1
  const canMoveUp = selectedSiblingIndex > 0
  const canMoveDown = selectedSiblingIndex > -1 && selectedSiblingIndex < siblingTasks.length - 1

  const moveSelectedTask = async (direction) => {
    if (!selectedTaskDerived) return

    const siblings = siblingTasks
    const currentIndex = selectedSiblingIndex
    const targetIndex = direction === 'up' ? currentIndex - 1 : currentIndex + 1
    if (currentIndex < 0 || targetIndex < 0 || targetIndex >= siblings.length) return

    const currentTask = siblings[currentIndex]
    const targetTask = siblings[targetIndex]

    await Promise.all([
      saveTask(currentTask.id, { sort_index: Number(targetTask.sort_index ?? 0) }),
      saveTask(targetTask.id, { sort_index: Number(currentTask.sort_index ?? 0) }),
    ])
  }

  useEffect(() => {
    let cancelled = false

    const loadCalendarMode = async () => {
      try {
        const settings = await fetchSettings()
        if (!cancelled) {
          setCalendarMode(settings.calendar_mode ?? 'real')
        }
      } catch {
        if (!cancelled) {
          setCalendarMode('real')
        }
      }
    }

    loadCalendarMode()
    const unsubscribe = subscribeToCompanyDataChange(companyId, loadCalendarMode)

    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [companyId])

  if (loading) return <div className="roadmap-view__status">Loading roadmap...</div>
  if (error) return <div className="roadmap-view__status roadmap-view__status--error">{error}</div>

  return (
    <div className="roadmap-view" style={companyThemeStyle} lang="en-US">
      <RoadmapToolbar
        zoom={zoom}
        onZoomChange={setZoom}
        onAddTask={addTask}
        companies={companies}
        calendarMode={calendarMode}
      />
      <RoadmapChart
        tasks={displayTasks}
        zoom={zoom}
        zoomScale={zoomScale}
        onZoomScaleChange={setZoomScale}
        calendarMode={calendarMode}
        selectedTaskId={selectedTaskId}
        onSelectTask={setSelectedTaskId}
        companies={companies}
      />
      <div className="roadmap-view__panels">
        {selectedTaskDerived ? (
          <TaskEditPanel
            task={selectedTaskDerived}
            calendarMode={calendarMode}
            onSave={(updates) => {
              const nextUpdates = selectedTaskDerived.isGroupTask
                ? { ...updates, progress: selectedTaskDerived.progress }
                : updates
              return saveTask(selectedTaskDerived.id, nextUpdates)
            }}
            onDelete={() => removeTask(selectedTaskDerived.id)}
            onIndent={canIndent ? () => setTaskParent(selectedTaskDerived.id, previousTask.id) : null}
            onOutdent={canOutdent ? () => setTaskParent(selectedTaskDerived.id, parentTask?.parent_task_id ?? null) : null}
            onMoveUp={canMoveUp ? () => moveSelectedTask('up') : null}
            onMoveDown={canMoveDown ? () => moveSelectedTask('down') : null}
            childrenTasks={selectedTaskChildren}
            companies={companies}
          />
        ) : (
          <div className="roadmap-view__status">Select a task row to edit details.</div>
        )}
      </div>
    </div>
  )
}

export default RoadmapView
