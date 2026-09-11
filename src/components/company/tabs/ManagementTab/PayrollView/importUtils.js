/**
 * Parses the flat payroll template this app generates via "Download format"
 * — one row per position. "Level" sets that position's compensation via the
 * level reference table baked into the same sheet; the app resolves the
 * actual figure client-side against the levels it already has loaded.
 * "Compensation (custom)", when filled in, overrides that level-derived
 * figure for this one position — "Compensation (standard)" is read-only
 * reference text in the sheet and is never read back in here. Both the
 * "Level" header (this position's own) and the reference table's own
 * "Level" header collide once read through the sheet's header row; the
 * xlsx library dedupes same-named headers by suffixing "_1", "_2", ... in
 * column order, so the reference table's copy always lands on `Level_1`,
 * never on plain `Level` — that's what keeps this parser reading the right
 * one without needing to know the reference table's column position.
 *
 * A position's identity is its (name, "Subordinated To") pair, not the name
 * alone — a role like "Secretary / Assistant" can legitimately recur many
 * times, once per manager it answers to, and each of those is a distinct
 * position, not the same one repeated. Two rows only collide as a genuine
 * duplicate when BOTH the name and the parent match. Multiple people
 * holding the exact same position under the exact same manager is a
 * headcount matter, handled afterward in the Payroll Matrix, not something
 * this import distinguishes.
 *
 * Returns { positions, warnings }. `positions` is empty when the file
 * doesn't look like this template at all.
 */
// Users hand-edit these headers in Excel (observed in the wild: a stray
// leading/trailing space on "Compensation (standard)"), so header lookups
// go through a trimmed-key map rather than exact bracket access — a header
// cell with incidental whitespace shouldn't silently drop that column.
function normalizedRow(row) {
  const byTrimmedKey = {}
  Object.entries(row).forEach(([key, value]) => {
    byTrimmedKey[key.trim()] = value
  })
  return byTrimmedKey
}

export function parseFlatTemplate(jsonRows) {
  if (!Array.isArray(jsonRows) || jsonRows.length === 0) {
    return { positions: [], warnings: ['No rows were found in the file.'] }
  }

  const sampleKeys = Object.keys(jsonRows[0]).map((key) => key.trim())
  if (!sampleKeys.includes('Position')) {
    return { positions: [], warnings: ["This file doesn't look like a payroll template exported from this app."] }
  }

  const positions = []
  const warnings = []
  const seenComposites = new Set()

  jsonRows.forEach((rawRow) => {
    const row = normalizedRow(rawRow)
    const name = String(row.Position ?? '').trim()
    if (!name) return

    const parentName = String(row['Subordinated To'] ?? '').trim()
    const composite = `${name}::${parentName}`
    if (seenComposites.has(composite)) {
      warnings.push(
        `"${name}" under "${parentName || 'top of chart'}" appears more than once — only the first row for that exact ` +
          'combination was used.',
      )
      return
    }
    seenComposites.add(composite)

    const customSalaryRaw = row['Compensation (custom)']
    const customSalary = customSalaryRaw !== '' && customSalaryRaw !== null && customSalaryRaw !== undefined ? Number(customSalaryRaw) : null

    positions.push({
      name,
      location: String(row.location ?? '').trim(),
      level: String(row.Level ?? '').trim() || null,
      customSalary: Number.isFinite(customSalary) ? customSalary : null,
      area: String(row.Area ?? '').trim(),
      parentName,
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
