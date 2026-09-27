import { useEffect, useMemo, useState } from 'react'
import { buildProductPortfolio } from '../../services/productPortfolio'
import { fetchProductHsCodes } from '../../services/productHsCodes'
import {
  bootstrapVariety,
  confirmVariety,
  fetchConfigStatus,
  fetchReviewQueue,
  fetchVarietiesPublic,
  matchVariety,
  rejectVariety,
  resolveSpecies,
} from '../../services/speciesGallery'

// Confidence-status badge: reuses this app's existing badge vocabulary
// (MarketAnalysisView.css's .market-analysis__estimated-badge, the same
// blue "filled in, not yet verified" treatment SAM/Market Opportunities
// already use) rather than inventing a new color. A confirmed variety gets
// NO badge at all — the plain card — same precedent as SAM Overview's own
// "confirmed (no badge at all, the plain figure)" convention, so a
// human-confirmed row is never dressed up with a badge of its own that
// could be confused with the unverified one.
// Addition 2 hook: Colombia's 'granos_procesados' category and USA's
// 'Grains (Export)' category (this app's own CANONICAL_CATEGORIES — see
// priceComparisonData.js / backend/usa_sources/grains.py) route a bootstrap
// to Open Food Facts (packaged/branded goods only — rice, oil, sugar,
// chocolate, panela, beans, ...) instead of the produce GBIF+LangSearch+
// Wikimedia pipeline. By the time a product reaches this panel,
// buildProductPortfolio() has already converted the raw taxonomy key to
// its display LABEL ('Grains & Processed' for Colombia, 'Grains (Export)'
// for USA — confirmed by reading productPortfolio.js's own
// categoryInfo()/CATEGORY_CODES, not assumed) — so this checks against
// those labels and sends the backend a clean, explicit 'packaged_goods'
// category rather than leaking a frontend label string into the API.
const PACKAGED_GOODS_LABELS = new Set(['Grains & Processed', 'Grains (Export)'])

function bootstrapCategoryFor(product) {
  return product && PACKAGED_GOODS_LABELS.has(product.category) ? 'packaged_goods' : 'produce'
}

function ConfidenceBadge({ status }) {
  if (status === 'confirmed') return null
  return <span className="market-analysis__estimated-badge">Auto-filled · Unverified</span>
}

function VarietyCard({ variety, isSelected, onSelect, selectable }) {
  return (
    <div className={`species-gallery__variety-card ${isSelected ? 'is-selected' : ''}`}>
      {variety.image_tier_b ? (
        <img className="species-gallery__variety-image" src={variety.image_tier_b} alt={variety.variety_name} />
      ) : (
        <div className="species-gallery__variety-image species-gallery__variety-image--empty">No public image yet</div>
      )}
      <div className="species-gallery__variety-body">
        <div className="species-gallery__variety-name">{variety.variety_name}</div>
        <div className="species-gallery__variety-country">{variety.source_country}</div>
        <ConfidenceBadge status={variety.confidence_status} />
        {variety.image_tier_b_license && (
          <p className="species-gallery__attribution">
            {variety.image_tier_b_license} — {variety.image_tier_b_attribution}
          </p>
        )}
        {selectable && (
          <button type="button" className="species-gallery__select-button" onClick={() => onSelect(variety)}>
            {isSelected ? 'Selected as source' : 'Use as source'}
          </button>
        )}
      </div>
    </div>
  )
}

export default function SpeciesGalleryPanel() {
  const [langsearchConfigured, setLangsearchConfigured] = useState(null)
  const [portfolio, setPortfolio] = useState([])
  const [hsByName, setHsByName] = useState({})
  const [loadStatus, setLoadStatus] = useState('loading')
  const [search, setSearch] = useState('')
  const [selectedProduct, setSelectedProduct] = useState(null)

  const [resolution, setResolution] = useState(null)
  const [resolveStatus, setResolveStatus] = useState('idle')
  const [varieties, setVarieties] = useState([])

  const [newVarietyName, setNewVarietyName] = useState('')
  const [newVarietyCountry, setNewVarietyCountry] = useState('')
  const [bootstrapStatus, setBootstrapStatus] = useState('idle')
  const [bootstrapError, setBootstrapError] = useState(null)

  const [sourceVariety, setSourceVariety] = useState(null)
  const [targetCountry, setTargetCountry] = useState('')
  const [matchResult, setMatchResult] = useState(null)
  const [matchStatus, setMatchStatus] = useState('idle')

  const [reviewQueue, setReviewQueue] = useState([])
  const [reviewStatus, setReviewStatus] = useState('idle')

  useEffect(() => {
    fetchConfigStatus().then((r) => setLangsearchConfigured(r.langsearch_configured)).catch(() => setLangsearchConfigured(false))
    Promise.all([buildProductPortfolio().catch(() => []), fetchProductHsCodes().catch(() => ({ results: {} }))])
      .then(([rows, hs]) => {
        setPortfolio(rows)
        setHsByName(hs.results || {})
        setLoadStatus('ready')
      })
      .catch(() => setLoadStatus('error'))
    refreshReviewQueue()
  }, [])

  function refreshReviewQueue() {
    setReviewStatus('loading')
    fetchReviewQueue()
      .then((rows) => {
        setReviewQueue(rows)
        setReviewStatus('ready')
      })
      .catch(() => setReviewStatus('error'))
  }

  const filteredProducts = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return portfolio.slice(0, 40)
    return portfolio.filter((p) => p.name.toLowerCase().includes(term)).slice(0, 40)
  }, [portfolio, search])

  function selectProduct(product) {
    setSelectedProduct(product)
    setResolution(null)
    setVarieties([])
    setSourceVariety(null)
    setMatchResult(null)
    setNewVarietyName(product.name)
    setNewVarietyCountry(product.countries[0] || '')

    setResolveStatus('loading')
    const hsEntry = hsByName[product.name.toLowerCase()]
    resolveSpecies([{ key: product.name, name: product.name, hs_description: hsEntry?.description || null }])
      .then((r) => {
        const result = r.results[product.name]
        setResolution(result)
        setResolveStatus('ready')
        if (result.status === 'resolved') {
          return fetchVarietiesPublic(result.scientific_name).then(setVarieties)
        }
        return null
      })
      .catch(() => setResolveStatus('error'))
  }

  function runBootstrap() {
    if (!resolution || resolution.status !== 'resolved' || !newVarietyName || !newVarietyCountry) return
    setBootstrapStatus('loading')
    setBootstrapError(null)
    bootstrapVariety({
      scientificName: resolution.scientific_name,
      commonName: resolution.common_name,
      varietyName: newVarietyName,
      sourceCountry: newVarietyCountry,
      category: bootstrapCategoryFor(selectedProduct),
    })
      .then(() => fetchVarietiesPublic(resolution.scientific_name))
      .then((rows) => {
        setVarieties(rows)
        setBootstrapStatus('ready')
        refreshReviewQueue()
      })
      .catch((err) => {
        setBootstrapStatus('error')
        setBootstrapError(err.message)
      })
  }

  function runMatch() {
    if (!sourceVariety || !targetCountry) return
    setMatchStatus('loading')
    matchVariety({ sourceVarietyId: sourceVariety.id, targetCountry, category: bootstrapCategoryFor(selectedProduct) })
      .then((result) => {
        setMatchResult(result)
        setMatchStatus('ready')
      })
      .catch(() => setMatchStatus('error'))
  }

  function handleConfirm(varietyId) {
    confirmVariety(varietyId).then(() => {
      refreshReviewQueue()
      if (resolution?.scientific_name) fetchVarietiesPublic(resolution.scientific_name).then(setVarieties)
    })
  }

  function handleReject(varietyId) {
    rejectVariety(varietyId).then(() => {
      refreshReviewQueue()
      if (resolution?.scientific_name) fetchVarietiesPublic(resolution.scientific_name).then(setVarieties)
    })
  }

  return (
    <section className="species-gallery">
      <header className="species-gallery__header">
        <h4>Variety Gallery</h4>
        <p>
          Every product is anchored to a real biological species (via GBIF), then grown into a persistent database of named
          varieties per country — cross-market matches are scored by a plain, auditable point system, never AI or image
          similarity.
        </p>
        {langsearchConfigured === false && (
          <p className="species-gallery__notice">
            LangSearch is not configured (LANGSEARCH_API_KEY unset) — a bootstrap's characteristics/Tier A image step will be
            skipped. Wikimedia Commons Tier B sourcing and GBIF species resolution are unaffected.
          </p>
        )}
      </header>

      <div className="species-gallery__layout">
        <div className="species-gallery__selector">
          <h5>1. Pick a product</h5>
          <input
            type="text"
            placeholder="Search the product catalog…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="species-gallery__search"
          />
          {loadStatus === 'loading' && <p className="species-gallery__hint">Loading the product catalog…</p>}
          <ul className="species-gallery__product-list">
            {filteredProducts.map((product) => (
              // Keyed on the product's own dedup key (its lowercased name —
              // guaranteed unique, see productPortfolio.js's byKey Map)
              // rather than its display `code`: confirmed live that two
              // distinct products can share the same fallback code (e.g.
              // several tomato variants all classified to the same 4-digit
              // HS heading), which made `code` a non-unique React key.
              <li key={product.name}>
                <button
                  type="button"
                  className={`species-gallery__product-item ${selectedProduct?.code === product.code ? 'is-active' : ''}`}
                  onClick={() => selectProduct(product)}
                >
                  {product.name} <span className="species-gallery__product-countries">{product.countries.join(', ')}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="species-gallery__detail">
          {!selectedProduct && <p className="species-gallery__hint">Select a product to see its species anchor and known varieties.</p>}

          {selectedProduct && (
            <>
              <h5>2. Species anchor</h5>
              {resolveStatus === 'loading' && <p className="species-gallery__hint">Resolving scientific name…</p>}
              {resolution?.status === 'unresolved' && (
                <p className="species-gallery__notice">
                  Could not confidently anchor "{selectedProduct.name}" to a real species ({resolution.reason}) — never guessed.
                </p>
              )}
              {resolution?.status === 'resolved' && (
                <p className="species-gallery__anchor">
                  <em>{resolution.scientific_name}</em>
                  {resolution.cached ? ' (already in the database)' : ' (newly confirmed via GBIF)'}
                </p>
              )}
              {resolution?.status === 'resolved' && bootstrapCategoryFor(selectedProduct) === 'packaged_goods' && (
                <p className="species-gallery__hint">
                  This product is a packaged/branded good ({selectedProduct.category}) — bootstrap will search Open Food
                  Facts (brand/package size/image) instead of the produce web-search + Wikimedia pipeline.
                </p>
              )}

              {resolution?.status === 'resolved' && (
                <>
                  <h5>3. Known varieties</h5>
                  <div className="species-gallery__variety-grid">
                    {varieties.length === 0 && <p className="species-gallery__hint">No variety cached yet for this species — bootstrap one below.</p>}
                    {varieties.map((v) => (
                      <VarietyCard
                        key={v.id}
                        variety={v}
                        isSelected={sourceVariety?.id === v.id}
                        onSelect={setSourceVariety}
                        selectable
                      />
                    ))}
                  </div>

                  <div className="species-gallery__bootstrap-form">
                    <input
                      type="text"
                      value={newVarietyName}
                      onChange={(e) => setNewVarietyName(e.target.value)}
                      placeholder="Variety name"
                    />
                    <input
                      type="text"
                      value={newVarietyCountry}
                      onChange={(e) => setNewVarietyCountry(e.target.value)}
                      placeholder="Country"
                    />
                    <button type="button" onClick={runBootstrap} disabled={bootstrapStatus === 'loading'}>
                      {bootstrapStatus === 'loading' ? 'Bootstrapping…' : 'Add / bootstrap variety'}
                    </button>
                    {bootstrapStatus === 'error' && <p className="species-gallery__notice">{bootstrapError}</p>}
                  </div>

                  <h5>4. Cross-market match</h5>
                  <div className="species-gallery__match-form">
                    <span>Source: {sourceVariety ? `${sourceVariety.variety_name} (${sourceVariety.source_country})` : 'pick a variety above'}</span>
                    <input
                      type="text"
                      value={targetCountry}
                      onChange={(e) => setTargetCountry(e.target.value)}
                      placeholder="Target country"
                    />
                    <button type="button" onClick={runMatch} disabled={!sourceVariety || !targetCountry || matchStatus === 'loading'}>
                      {matchStatus === 'loading' ? 'Matching…' : 'Find best match'}
                    </button>
                  </div>

                  {matchStatus === 'loading' && (
                    <p className="species-gallery__hint">
                      Searching for {targetCountry} varieties not seen before and bootstrapping any newly discovered ones
                      (real web search + image lookups per variety) — this can take up to a minute the first time a target
                      country has nothing cached yet. Subsequent matches for the same pair are instant.
                    </p>
                  )}

                  {matchResult && (
                    <div className="species-gallery__match-result">
                      {matchResult.discovered_count > 0 && (
                        <p className="species-gallery__hint">
                          Discovered and bootstrapped {matchResult.discovered_count} new {targetCountry} variet
                          {matchResult.discovered_count === 1 ? 'y' : 'ies'} this run: {matchResult.discovered_varieties.map((v) => v.variety_name).join(', ')}.
                        </p>
                      )}
                      {!matchResult.best_match && <p className="species-gallery__hint">{matchResult.message}</p>}
                      {matchResult.best_match && (
                        <>
                          <div className="species-gallery__match-pair">
                            <VarietyCard variety={matchResult.source_variety} selectable={false} />
                            <VarietyCard variety={matchResult.best_match} selectable={false} />
                          </div>
                          <p className="species-gallery__score">
                            Score: {matchResult.score} / {matchResult.max_possible}
                          </p>
                          <table className="species-gallery__breakdown">
                            <thead>
                              <tr>
                                <th>Field</th>
                                <th>Source</th>
                                <th>Target</th>
                                <th>Matched</th>
                              </tr>
                            </thead>
                            <tbody>
                              {matchResult.field_breakdown.map((row) => (
                                <tr key={row.field}>
                                  <td>{row.field}</td>
                                  <td>{row.source_value}</td>
                                  <td>{row.target_value}</td>
                                  <td>{row.matched ? '✓' : '—'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </>
                      )}
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>

      <div className="species-gallery__review-queue">
        <h5>Review queue — auto-filled, unverified varieties</h5>
        {reviewStatus === 'loading' && <p className="species-gallery__hint">Loading…</p>}
        {reviewStatus === 'ready' && reviewQueue.length === 0 && <p className="species-gallery__hint">Nothing pending review.</p>}
        <ul className="species-gallery__review-list">
          {reviewQueue.map((row) => (
            <li key={row.id}>
              <span>
                {row.variety_name} — {row.source_country} ({row.scientific_name})
              </span>
              <button type="button" onClick={() => handleConfirm(row.id)}>
                Confirm
              </button>
              <button type="button" onClick={() => handleReject(row.id)}>
                Reject
              </button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
