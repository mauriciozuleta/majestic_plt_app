import { useState } from 'react'

export function useCloneSelection() {
  const [cloneMode, setCloneMode] = useState(false)
  const [deleteMode, setDeleteMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState([])

  const toggleCloneMode = () => {
    setCloneMode((prev) => !prev)
    setDeleteMode(false)
    setSelectedIds([])
  }

  const toggleDeleteMode = () => {
    setDeleteMode((prev) => !prev)
    setCloneMode(false)
    setSelectedIds([])
  }

  const toggleSelected = (nodeId) => {
    setSelectedIds((prev) =>
      prev.includes(nodeId) ? prev.filter((id) => id !== nodeId) : [...prev, nodeId],
    )
  }

  const reset = () => {
    setCloneMode(false)
    setDeleteMode(false)
    setSelectedIds([])
  }

  return {
    cloneMode,
    deleteMode,
    selectedIds,
    toggleCloneMode,
    toggleDeleteMode,
    toggleSelected,
    reset,
  }
}