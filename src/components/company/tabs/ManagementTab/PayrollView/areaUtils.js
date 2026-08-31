function normalize(value) {
  return String(value ?? '').trim().toLowerCase().replace(/\s+/g, ' ')
}

function levenshteinDistance(a, b) {
  const rows = a.length + 1
  const cols = b.length + 1
  const distances = Array.from({ length: rows }, () => new Array(cols).fill(0))

  for (let i = 0; i < rows; i += 1) distances[i][0] = i
  for (let j = 0; j < cols; j += 1) distances[0][j] = j

  for (let i = 1; i < rows; i += 1) {
    for (let j = 1; j < cols; j += 1) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1
      distances[i][j] = Math.min(
        distances[i - 1][j] + 1,
        distances[i][j - 1] + 1,
        distances[i - 1][j - 1] + cost,
      )
    }
  }

  return distances[rows - 1][cols - 1]
}

/**
 * True when two area names are likely the same area typed slightly differently —
 * identical once case/whitespace is normalized, or close enough (small edit
 * distance relative to length) to smell like a typo rather than a new area.
 */
export function areasResemble(areaA, areaB) {
  const normalizedA = normalize(areaA)
  const normalizedB = normalize(areaB)
  if (!normalizedA || !normalizedB) return false
  if (normalizedA === normalizedB) return true

  const distance = levenshteinDistance(normalizedA, normalizedB)
  const longerLength = Math.max(normalizedA.length, normalizedB.length)
  return longerLength > 0 && distance / longerLength <= 0.2
}

/**
 * Groups area names (as actually spelled/cased on positions) into clusters of
 * likely-duplicates. Only clusters with more than one distinct spelling are
 * returned — a single spelling used everywhere isn't a problem.
 */
export function clusterResemblingAreas(areaNames) {
  const clusters = []

  areaNames.forEach((area) => {
    const match = clusters.find((cluster) => cluster.some((member) => areasResemble(member, area)))
    if (match) {
      if (!match.includes(area)) match.push(area)
    } else {
      clusters.push([area])
    }
  })

  return clusters.filter((cluster) => cluster.length > 1)
}

/**
 * Picks which spelling in a cluster to keep: whichever is used by the most
 * positions, breaking ties alphabetically so the result is stable.
 */
export function pickCanonicalArea(cluster, countsByArea) {
  return [...cluster].sort((a, b) => {
    const countDiff = (countsByArea.get(b) || 0) - (countsByArea.get(a) || 0)
    if (countDiff !== 0) return countDiff
    return a.localeCompare(b)
  })[0]
}
