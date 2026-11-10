// For Market Opportunities: has a shipment been built (Financial ▸ Revenue ▸ route ▸ Shipment builder) for a source -> target country pair, and what is that route's air fare per
// kg (its Price x Kg)? Computed on the server now (backend/shipments/service.py built_shipment_airfares).
// -> Map(targetCountry -> { airfarePerKg, note, routeName }) holding only the targets that have a built shipment
export { fetchPairPricing } from './shipments'
