// Which built documents/data exist for every active country, for the Market
// Analysis table's status columns. Aggregated on the frontend from the same
// endpoints each country's own tabs already use — there's no dedicated
// backend endpoint for this, since it's just a join of things that already
// have one.
import { fetchAllCompetitivenessAnalyses, fetchProfiledCountries } from './commercialStructure'
import { fetchCustomSourceProducts } from './productSources'
import { fetchPriceComparisonSnapshot } from '../components/company/tabs/OperationsTab/MarketAnalysis/priceComparisonFetchers'
import { fetchUsaSourcingSnapshot } from '../components/company/tabs/OperationsTab/MarketAnalysis/usaSourcingFetchers'

// Returns { [countryId]: { profile: {generated_at} | null, analyses: [{target_country_id, target_country_name, source_country_name, generated_at}], hasProductData: bool } }
export async function buildMarketAnalysisStatus(countries) {
  const companyIds = [...new Set(countries.map((country) => country.company_id))]

  const [profileLists, analysisLists, colombiaSnapshots, usaSnapshots, customSources] = await Promise.all([
    Promise.all(companyIds.map((id) => fetchProfiledCountries(id).catch(() => []))),
    Promise.all(companyIds.map((id) => fetchAllCompetitivenessAnalyses(id).catch(() => []))),
    fetchPriceComparisonSnapshot().catch(() => []),
    fetchUsaSourcingSnapshot().catch(() => []),
    fetchCustomSourceProducts().catch(() => []),
  ])

  const profileByCountryId = new Map(profileLists.flat().map((row) => [row.country_id, row]))
  // An analysis is filed under its TARGET's company, but its SOURCE can be a
  // country that belongs to any company — matching by name across every
  // company's list (not just this country's own) is what finds it either way.
  const analyses = analysisLists.flat()
  const hasColombiaData = colombiaSnapshots.some((snapshot) => snapshot.products?.length > 0)
  const hasUsaData = usaSnapshots.some((snapshot) => snapshot.products?.length > 0)
  const customCountries = new Set(customSources.map((source) => source.country_name.trim().toLowerCase()))

  const status = {}
  countries.forEach((country) => {
    const nameLower = country.name.trim().toLowerCase()
    status[country.id] = {
      profile: profileByCountryId.get(country.id) || null,
      analyses: analyses.filter(
        (row) => row.source_country_name?.trim().toLowerCase() === nameLower || row.target_country_id === country.id,
      ),
      hasProductData: (nameLower === 'colombia' && hasColombiaData) || (nameLower === 'united states' && hasUsaData) || customCountries.has(nameLower),
    }
  })
  return status
}
