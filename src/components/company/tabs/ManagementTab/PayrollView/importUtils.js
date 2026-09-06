/**
 * Parses the flat payroll template this app generates via "Download format"
 * — one row per position. "Level" sets that position's compensation via the
 * level reference table baked into the same sheet; the app resolves the
 * actual figure client-side against the levels it already has loaded.
 * Returns { positions, warnings }. `positions` is empty when the file
 * doesn't look like this template at all.
 */
export function parseFlatTemplate(jsonRows) {
  if (!Array.isArray(jsonRows) || jsonRows.length === 0) {
    return { positions: [], warnings: ['No rows were found in the file.'] }
  }

  const sampleKeys = Object.keys(jsonRows[0])
  if (!sampleKeys.includes('Position')) {
    return { positions: [], warnings: ["This file doesn't look like a payroll template exported from this app."] }
  }

  const positions = []
  const warnings = []
  const seenNames = new Set()

  jsonRows.forEach((row) => {
    const name = String(row.Position ?? '').trim()
    if (!name) return

    if (seenNames.has(name)) {
      warnings.push(`"${name}" appears more than once — only the first row for that position was used.`)
      return
    }
    seenNames.add(name)

    positions.push({
      name,
      level: String(row.Level ?? '').trim() || null,
      area: String(row.Area ?? '').trim(),
      parentName: String(row['Subordinated To'] ?? '').trim(),
    })
  })

  positions.forEach((position) => {
    if (position.parentName && position.parentName === position.name) {
      warnings.push(`"${position.name}" lists itself as "Subordinated To" — leaving it at the top of the chart.`)
      position.parentName = ''
    }
  })

  return { positions, warnings }
}
