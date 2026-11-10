// Shipment builder constants. The LOGIC that used to live here — which products are candidates (best comparison row per product, ordered by rating, Country SAM and Diff %),
// each candidate's market level / cargo cap / thin-margin cap reduction, and how the kilos are shared (wholesalers first, then premium, the niche products split the rest,
// manual weights kept, whole kg) — runs on the server now: backend/shipments/allocation.py, GET /api/shipments/candidates and POST /api/shipments/allocate. The rules are
// written down in docs/shipment_builder_allocation.md and held by backend/tests/test_shipments_parity.py.

// Only these opportunity ratings are candidates, in this order; Complex, Difficult, Not Viable and unrated products are left out.
export const SHIPMENT_RATINGS = ['Very High', 'High', 'Challenging']
// Every rating, in the scale's order — for a list the user chose themselves (the priority list), where nothing is left out.
export const ALL_RATINGS = ['Very High', 'High', 'Challenging', 'Complex', 'Difficult', 'Not Viable', 'Unrated']

// Most a product can get: one with a known Country SAM, or one whose market size couldn't be defined.
export const SAM_CAP_KG = 1500
export const NO_SAM_CAP_KG = 200
