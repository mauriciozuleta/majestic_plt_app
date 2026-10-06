import { fetchMarketAnalysisRegions, fetchCommercialBranches } from './commercialStructure'
import { fetchRevenueStreamRoutes } from './revenueStreams'
import { fetchAircraftCatalogue, fetchCharterProviders } from './airLogistics'
import { outboundPricePerKg } from '../components/company/tabs/FinancialTab/routeMetrics'

// For Market Opportunities: has a shipment been built (Financial ▸ Revenue ▸ route ▸ Shipment builder) for a
// source -> target country pair, and what is that route's air fare per kg (its Price x Kg)?
// -> Map(targetCountry -> { airfarePerKg, note, routeName }) holding only the targets that have a built shipment
export async function fetchBuiltShipmentAirfares(companies, sourceCountry, targetCountries) {
  const regions = await fetchMarketAnalysisRegions()
  const countryNameById = new Map(regions.flatMap((row) => row.countries.map((country) => [country.id, country.name])))
  const perCompany = await Promise.all(
    companies.map(async (company) => {
      const [routes, branches, providers, aircraft] = await Promise.all([
        fetchRevenueStreamRoutes(company.id).catch(() => []),
        fetchCommercialBranches(company.id).catch(() => []),
        fetchCharterProviders(company.id).catch(() => []),
        fetchAircraftCatalogue(company.id).catch(() => []),
      ])
      return { routes, branches, providers, aircraft }
    }),
  )
  // A route usually links branches owned by different companies, so look them up across all of them.
  const branchById = new Map(perCompany.flatMap((entry) => entry.branches).map((branch) => [branch.id, branch]))
  const providerById = new Map(perCompany.flatMap((entry) => entry.providers).map((item) => [item.id, item]))
  const aircraftById = new Map(perCompany.flatMap((entry) => entry.aircraft).map((item) => [item.id, item]))

  const result = new Map()
  perCompany
    .flatMap((entry) => entry.routes)
    .filter((route) => route.outbound_shipment)
    .forEach((route) => {
      const origin = branchById.get(route.origin_branch_id)
      const destination = branchById.get(route.destination_branch_id)
      const target = countryNameById.get(destination?.country_id)
      if (countryNameById.get(origin?.country_id) !== sourceCountry || !targetCountries.includes(target)) return
      const price = outboundPricePerKg(route, {
        origin,
        destination,
        returnBranch: route.return_branch_id ? branchById.get(route.return_branch_id) : null,
        aircraft: aircraftById.get(route.aircraft_id),
        provider: providerById.get(route.charter_provider_id),
      })
      // First route with a usable air fare wins; otherwise keep the reason it has none.
      if (!result.has(target) || (result.get(target).airfarePerKg == null && price.value != null)) {
        result.set(target, { airfarePerKg: price.value, note: price.note, routeName: `${origin?.airport || origin?.name} → ${destination?.airport || destination?.name}` })
      }
    })
  return result
}
