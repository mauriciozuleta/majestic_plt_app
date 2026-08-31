const YEAR_SALARY_PATTERN = /^Year\s+(\d+)\s+Salary$/i

/**
 * Parses the flat payroll template this app generates via "Download format"
 * (one row per hire; positions are grouped by repeating the same "Position"
 * text across their rows). Returns { positions, warnings }. `positions` is
 * empty when the file doesn't look like this template at all.
 */
export function parseFlatTemplate(jsonRows) {
  if (!Array.isArray(jsonRows) || jsonRows.length === 0) {
    return { positions: [], warnings: ['No rows were found in the file.'] }
  }

  const sampleKeys = Object.keys(jsonRows[0])
  const yearColumns = sampleKeys
    .map((key) => {
      const match = YEAR_SALARY_PATTERN.exec(key.trim())
      return match ? { key, year: Number(match[1]) } : null
    })
    .filter(Boolean)
    .sort((a, b) => a.year - b.year)

  if (!sampleKeys.includes('Position') || yearColumns.length === 0) {
    return { positions: [], warnings: ["This file doesn't look like a payroll template exported from this app."] }
  }

  const positionsByName = new Map()
  const warnings = []

  jsonRows.forEach((row) => {
    const name = String(row.Position ?? '').trim()
    if (!name) return

    if (!positionsByName.has(name)) {
      positionsByName.set(name, {
        name,
        area: '',
        parentName: '',
        compByYear: yearColumns.map(() => 0),
        employees: [],
      })
    }
    const position = positionsByName.get(name)

    const area = String(row.Area ?? '').trim()
    if (area && !position.area) position.area = area

    const parentName = String(row['Subordinated To'] ?? '').trim()
    if (parentName && !position.parentName) position.parentName = parentName

    yearColumns.forEach(({ key }, yearIndex) => {
      if (position.compByYear[yearIndex]) return
      const value = Number(row[key])
      if (row[key] !== '' && Number.isFinite(value)) position.compByYear[yearIndex] = value
    })

    const employeeName = String(row['Employee Name'] ?? '').trim()
    const startDate = String(row['Start Date'] ?? '').trim()
    const endDate = String(row['End Date'] ?? '').trim()
    if (employeeName || startDate || endDate) {
      position.employees.push({
        employee_name: employeeName || null,
        start_date: startDate,
        end_date: endDate || null,
      })
    }
  })

  const positions = Array.from(positionsByName.values())
  positions.forEach((position) => {
    if (position.employees.length === 0) {
      position.employees.push({ employee_name: null, start_date: '', end_date: null })
    }
    if (position.parentName && position.parentName === position.name) {
      warnings.push(`"${position.name}" lists itself as "Subordinated To" — leaving it at the top of the chart.`)
      position.parentName = ''
    }
  })

  return { positions, warnings }
}
