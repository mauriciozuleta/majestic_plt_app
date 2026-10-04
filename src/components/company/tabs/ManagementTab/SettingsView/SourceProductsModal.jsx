import { useEffect, useMemo, useState } from 'react'
import { fetchProductSourceProducts } from '../../../../../services/productSources'
import './SourceProductsModal.css'

// How a source's products were obtained — so a one-page read isn't mistaken
// for a full supermarket catalog.
const ORIGIN_LABELS = {
  catalog: 'Downloaded by the supermarket catalog app (every selected category page).',
  // A dedicated reader (e.g. Jamaica's Ministry of Agriculture workbooks) or
  // the generic one-page reader — the source's own note says which.
  site: 'Read by Majestic from the web address.',
  file: 'Loaded from a products file.',
}

const formatPrice = (product) =>
  product.price == null
    ? '—'
    : `${product.currency ? `${product.currency} ` : ''}${Number(product.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

// The products a custom source currently holds — what comparisons and the
// portfolio actually use from it.
function SourceProductsModal({ sourceId, onClose }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

  useEffect(() => {
    let cancelled = false
    fetchProductSourceProducts(sourceId)
      .then((result) => !cancelled && setData(result))
      .catch((err) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [sourceId])

  const products = useMemo(() => {
    const needle = search.trim().toLowerCase()
    const list = data?.products ?? []
    return needle ? list.filter((product) => `${product.name} ${product.category ?? ''}`.toLowerCase().includes(needle)) : list
  }, [data, search])
  const categoryCount = useMemo(() => new Set((data?.products ?? []).map((product) => product.category || '')).size, [data])

  const source = data?.source
  return (
    <div className="source-products__overlay" role="dialog" aria-modal="true" aria-label="Source products">
      <div className="source-products">
        <header className="source-products__header">
          <div>
            <span className="source-products__eyebrow">{source ? `${source.country_name} · ${source.analysis_type === 'retail' ? 'Retail' : 'Wholesaler'}` : 'Products'}</span>
            <h3>{source?.name ?? 'Loading…'}</h3>
          </div>
          <button type="button" className="source-products__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        {error && <p className="source-products__error">{error}</p>}
        {source && (
          <p className="source-products__meta">
            {ORIGIN_LABELS[source.origin] || 'Source of these products not recorded.'}{' '}
            {source.origin === 'site' && source.status_message ? `${source.status_message} ` : ''}
            {data.products.length} product{data.products.length === 1 ? '' : 's'} in {categoryCount} categor{categoryCount === 1 ? 'y' : 'ies'}
            {data.fetched_at && ` · loaded ${new Date(data.fetched_at).toLocaleString()}`}
          </p>
        )}

        {data && (
          <>
            <input
              className="source-products__search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search product or category…"
              aria-label="Search products"
            />
            <div className="source-products__table-wrap">
              <table className="source-products__table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Product</th>
                    <th>Category</th>
                    <th className="is-num">Price</th>
                    <th>Unit</th>
                  </tr>
                </thead>
                <tbody>
                  {products.map((product, index) => (
                    <tr key={`${product.id}-${index}`}>
                      <td className="source-products__index">{index + 1}</td>
                      <td>{product.name}</td>
                      <td className="source-products__dim">{product.category || '—'}</td>
                      <td
                        className="is-num"
                        title={
                          product.market_prices?.length
                            ? product.market_prices.map((item) => `${item.market}: ${formatPrice({ ...product, price: item.price })}`).join('\n')
                            : undefined
                        }
                      >
                        {formatPrice(product)}
                        {product.markets > 1 && <span className="source-products__markets">avg of {product.markets} markets</span>}
                      </td>
                      <td className="source-products__dim">{product.unit || '—'}</td>
                    </tr>
                  ))}
                  {products.length === 0 && (
                    <tr>
                      <td colSpan={5} className="source-products__dim">
                        {search ? `No product matches "${search}".` : 'This source has no products.'}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}

        <footer className="source-products__footer">
          <button type="button" className="settings-view__btn" onClick={onClose}>
            Close
          </button>
        </footer>
      </div>
    </div>
  )
}

export default SourceProductsModal
