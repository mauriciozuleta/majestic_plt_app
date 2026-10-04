// Which "Add Products" form a company's revenue streams use — each company gets
// its own, personalised to how it earns revenue. Until a company's form is set
// up here, its streams are listed without one.
//
//   'air-cargo-route' — FRESH24: origin / destination / return airports, the
//     air logistics provider and aircraft (AddRouteModal), with each route's
//     leg cards and the Shipment builder.
const REVENUE_PRODUCT_FORMS = {
  'fresh24-1788630345959': 'air-cargo-route',
}

export const revenueProductFormFor = (companyId) => REVENUE_PRODUCT_FORMS[companyId] ?? null
