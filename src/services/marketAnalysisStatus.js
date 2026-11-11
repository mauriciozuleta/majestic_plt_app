// Which built documents/data exist for every active country, for the Market Analysis table's status columns. Worked out on the SERVER now
// (backend/portfolio/status.py, GET /api/portfolio/market-analysis-status); this file only asks for it.
import { API_BASE } from './apiBase'

// -> { [countryId]: { profile: {generated_at} | null, analyses: [{target_country_id, target_country_name, source_country_name, generated_at}], missingCount, hsMissingCount, hasProductData } }
// `countries` is kept for the caller's sake: the server answers for every commercial country and the table looks its rows up by id.
export async function buildMarketAnalysisStatus() {
  const response = await fetch(`${API_BASE}/api/portfolio/market-analysis-status`)
  if (!response.ok) throw new Error('Could not load the Market Analysis status.')
  return (await response.json()).countries
}
