export const SORT_OPTIONS = [
  { value: 'level', label: 'Level (org chart order)' },
  { value: 'alphabetical', label: 'Alphabetical' },
  { value: 'salary-desc', label: 'Salary (high to low)' },
  { value: 'salary-asc', label: 'Salary (low to high)' },
  { value: 'area', label: 'Area' },
]

function byName(a, b) {
  return a.office_name.localeCompare(b.office_name)
}

/**
 * Sorts payroll rows for display. Used by both the Structured and Matrix views
 * so switching views keeps the same ordering. Ties fall back to alphabetical
 * so the order stays stable and predictable.
 */
export function sortPositions(rows, sortBy) {
  const sorted = [...rows]

  switch (sortBy) {
    case 'alphabetical':
      return sorted.sort(byName)
    case 'level':
      return sorted.sort((a, b) => a.level - b.level || byName(a, b))
    case 'salary-desc':
      return sorted.sort((a, b) => b.year_salary - a.year_salary || byName(a, b))
    case 'salary-asc':
      return sorted.sort((a, b) => a.year_salary - b.year_salary || byName(a, b))
    case 'area':
      return sorted.sort((a, b) => (a.area || 'Unassigned').localeCompare(b.area || 'Unassigned') || byName(a, b))
    default:
      return sorted
  }
}
