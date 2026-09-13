// Job titles are free-typed in a few different places (Add Position, the
// Matrix's position editor), and the same title easily ends up saved under
// slightly different casing/spacing ("Secretary / Assistant" vs "secretary /
// Assistant") — which then reads as two unrelated positions everywhere that
// groups or looks up by title. Matching/grouping already happens case-
// insensitively (see PayrollMatrix's job-title grouping); this is the other
// half — stopping a new typo-cased duplicate from being saved in the first
// place, by snapping it back to whichever spelling already exists.
export function normalizeJobTitle(name) {
  return (name || '').trim().replace(/\s+/g, ' ').toLowerCase()
}

/** If `name` matches an existing title case/whitespace-insensitively,
 * returns that existing title's exact saved spelling instead of the new
 * input — so typing "secretary / assistant" when "Secretary / Assistant"
 * already exists saves under the existing spelling, not a new variant. A
 * genuinely new title (no match) is returned trimmed, as typed. */
export function resolveCanonicalJobTitle(name, existingNames) {
  const trimmed = (name || '').trim().replace(/\s+/g, ' ')
  const key = normalizeJobTitle(trimmed)
  const match = existingNames.find((existing) => normalizeJobTitle(existing) === key)
  return match ?? trimmed
}
