import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  createRoadmapTask,
  deleteRoadmapTask,
  fetchRoadmapTasks,
  updateRoadmapTask,
} from '../../../../../services/roadmap'
import { subscribeToCompanyDataChange } from '../../../../../services/companyDataSync'

export function useRoadmapData(companyId) {
  const [tasks, setTasks] = useState([])
  const [selectedTaskId, setSelectedTaskId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchRoadmapTasks(companyId)
      setTasks(data)
      setError(null)
      setSelectedTaskId((currentTaskId) => {
        if (!data.length) return null
        return data.find((task) => task.id === currentTaskId) ? currentTaskId : data[0].id
      })
    } catch (fetchError) {
      setError(fetchError.message)
    } finally {
      setLoading(false)
    }
  }, [companyId])

  useEffect(() => {
    if (!companyId) {
      setTasks([])
      setLoading(false)
      setError('No company selected')
      return
    }

    reload()
  }, [companyId, reload])

  useEffect(() => subscribeToCompanyDataChange(companyId, reload), [companyId, reload])

  const addTask = useCallback(
    async (task) => {
      const created = await createRoadmapTask(companyId, task)
      setTasks((prev) => [...prev, created])
      setSelectedTaskId(created.id)
    },
    [companyId],
  )

  const saveTask = useCallback(async (taskId, updates) => {
    const updated = await updateRoadmapTask(taskId, updates)
    setTasks((prev) => prev.map((task) => (task.id === taskId ? updated : task)))
  }, [])

  const setTaskParent = useCallback(async (taskId, parentTaskId) => {
    const updated = await updateRoadmapTask(taskId, {
      parent_task_id: parentTaskId || null,
    })
    setTasks((prev) => prev.map((task) => (task.id === taskId ? updated : task)))
  }, [])

  const removeTask = useCallback(
    async (taskId) => {
      await deleteRoadmapTask(taskId)
      setTasks((prev) => prev.filter((task) => task.id !== taskId))
      if (selectedTaskId === taskId) {
        setSelectedTaskId(null)
      }
    },
    [selectedTaskId],
  )

  const selectedTask = useMemo(
    () => tasks.find((task) => task.id === selectedTaskId) ?? null,
    [selectedTaskId, tasks],
  )

  return {
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
    reload,
  }
}
