import { useEffect, useMemo, useState } from 'react'
import { buildProductPortfolio } from '../../services/productPortfolio'
import { fetchProductHsCodes } from '../../services/productHsCodes'
import { fetchProductSources } from '../../services/productSources'
import { fetchReferenceCountries } from '../../services/commercialStructure'
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

// Guided, stepped flow (this pass's own information-architecture rework —
// see VARIETY_GALLERY_METHODOLOGY.md's own UI section): origin country ->
// grouped product list (by species/HS code, not one row per variety) ->
// product -> variety list for that product+country -> a specific variety's
// card -> destination country -> an automatic cross-market match. The
// underlying data/endpoints are entirely unchanged from the previous flat
// layout — only how they're sequenced and presented changed. The Review
// Queue keeps 100% of its previous behavior, just moved to its own tab
// (see `Tabs` below) since it's a maintenance view, not part of this main
// path.

// Addition 2 hook, carried over unchanged from the previous layout: Colombia's
// 'granos_procesados'/USA's 'Grains (Export)' categories (this app's own
// CANONICAL_CATEGORIES — priceComparisonData.js / backend/usa_sources/grains.py)
// route a bootstrap to Open Food Facts (packaged/branded goods only) instead
// of the produce GBIF+LangSearch+Wikimedia pipeline. buildProductPortfolio()
// already converts the raw taxonomy key to its display LABEL by the time it
// reaches this panel — see productPortfolio.js's own categoryInfo()/CATEGORY_CODES.
const PACKAGED_GOODS_LABELS = new Set(['Grains & Processed', 'Grains (Export)'])

function bootstrapCategoryFor(entity) {
  return entity && PACKAGED_GOODS_LABELS.has(entity.category) ? 'packaged_goods' : 'produce'
}

function humanizeKey(key) {
  return (key || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

// Plain-language rendering of a variety's characteristics_json blob (spec's
// own "in plain readable language" requirement for step 5's card) — a
// schema-less dict (shape/firmness/... for produce; package_size/brand/...
// for packaged goods), so this just humanizes whatever keys are actually
// present rather than assuming a fixed vocabulary.
function characteristicsSummary(characteristics) {
  const entries = Object.entries(characteristics || {}).filter(([, value]) => value != null && value !== '')
  if (entries.length === 0) return null
  return entries.map(([key, value]) => `${humanizeKey(key)}: ${value}`)
}

// Turns /match's own field_breakdown (a raw table today) into plain
// sentences — spec's own "prose, not just a raw table" requirement for
// step 7's result.
function matchExplanationSentences(fieldBreakdown) {
  return (fieldBreakdown || []).map((row) => {
    const label = humanizeKey(row.field)
    if (row.source_value == null && row.target_value == null) {
      return `${label}: neither variety has this trait on file — not comparable.`
    }
    if (row.source_value == null || row.target_value == null) {
      return `${label}: only one side has data for this trait (${row.source_value ?? row.target_value}) — not comparable.`
    }
    if (row.matched) return `${label}: both varieties agree — ${row.source_value}.`
    return `${label}: they disagree — the source variety is "${row.source_value}", the target is "${row.target_value}".`
  })
}

// Groups the origin country's own Country Product Portfolio entries purely
// by their already-classified HS code — the same cache (fetchProductHsCodes)
// and the same "skip anything not yet classified" rule buildCategoryCoverage()
// already applies for Available Categories/SAM/TAM, never a second scheme.
// No species resolution here: a country's own portfolio names sharing one HS
// code (e.g. Colombia's "Chonto Tomato"/"Rincon Tomato" both under 070200)
// are already real, known varieties of that category on their own — species
// anchoring only happens lazily, per PRODUCT, once one of these names is
// actually selected (see selectProduct below), so listing this group never
// depends on GBIF/LangSearch and never silently drops an unclassified
// product from view the way a required-resolution step would.
function buildGroupedProducts(portfolio, hsByName, originCountry) {
  const inCountry = portfolio.filter((product) => product.countries.includes(originCountry))
  const groups = new Map()
  inCountry.forEach((product) => {
    const hs = hsByName[product.name.toLowerCase()]
    if (!hs || !hs.hs_code) return
    if (!groups.has(hs.hs_code)) {
      groups.set(hs.hs_code, { hsCode: hs.hs_code, description: hs.description || null, category: product.category, productNames: [] })
    }
    groups.get(hs.hs_code).productNames.push(product.name)
  })

  return Array.from(groups.values())
    .map((group) => ({
      ...group,
      productNames: [...group.productNames].sort((a, b) => a.localeCompare(b)),
      label: group.description ? `${group.hsCode} ${group.description}` : group.hsCode,
    }))
    .sort((a, b) => a.hsCode.localeCompare(b.hsCode))
}

function ConfidenceBadge({ status }) {
  if (status === 'confirmed') return null
  return <span className="market-analysis__estimated-badge">Auto-filled · Unverified</span>
}

// The whole card is the click target when selectable — not just the small
// "Use as source" label at the bottom — real usage showed people naturally
// click the card/name itself and get no response, since the tiny label
// underneath was the only thing actually wired to onSelect.
function VarietyCard({ variety, isSelected, onSelect, selectable, showDetail }) {
  const summary = showDetail ? characteristicsSummary(variety.characteristics) : null
  const cardProps = selectable
    ? {
        role: 'button',
        tabIndex: 0,
        onClick: () => onSelect(variety),
        onKeyDown: (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onSelect(variety)
          }
        },
      }
    : {}
  return (
    <div
      className={`species-gallery__variety-card ${isSelected ? 'is-selected' : ''} ${selectable ? 'is-selectable' : ''}`}
      {...cardProps}
    >
      {variety.image_tier_b ? (
        <img className="species-gallery__variety-image" src={variety.image_tier_b} alt={variety.variety_name} />
      ) : (
        <div className="species-gallery__variety-image species-gallery__variety-image--empty">No public image yet</div>
      )}
      <div className="species-gallery__variety-body">
        <div className="species-gallery__variety-name">{variety.variety_name}</div>
        <div className="species-gallery__variety-country">{variety.source_country}</div>
        {showDetail && (
          <div className="species-gallery__variety-anchor">
            <em>{variety.scientific_name}</em>
          </div>
        )}
        <ConfidenceBadge status={variety.confidence_status} />
        {summary && (
          <ul className="species-gallery__characteristics">
            {summary.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        )}
        {variety.image_tier_b_license && (
          <p className="species-gallery__attribution">
            {variety.image_tier_b_license} — {variety.image_tier_b_attribution}
          </p>
        )}
        {selectable && (
          <span className="species-gallery__select-button">{isSelected ? 'Selected as source' : 'Use as source'}</span>
        )}
      </div>
    </div>
  )
}

function Tabs({ active, onChange, reviewCount }) {
  return (
    <div className="species-gallery__tabs">
      <button type="button" className={`species-gallery__tab ${active === 'flow' ? 'is-active' : ''}`} onClick={() => onChange('flow')}>
        Variety Gallery
      </button>
      <button type="button" className={`species-gallery__tab ${active === 'review' ? 'is-active' : ''}`} onClick={() => onChange('review')}>
        Review Queue{reviewCount > 0 ? ` (${reviewCount})` : ''}
      </button>
    </div>
  )
}

export default function SpeciesGalleryPanel() {
  const [activeTab, setActiveTab] = useState('flow')
  const [langsearchConfigured, setLangsearchConfigured] = useState(null)

  const [portfolio, setPortfolio] = useState([])
  const [hsByName, setHsByName] = useState({})
  const [loadStatus, setLoadStatus] = useState('loading')

  // Step 1 — origin country. Same "has a real Country Product Portfolio"
  // pool MarketOpportunitiesPanel's own Source dropdown already draws from
  // (fetchProductSources(), product_count > 0) — this feature's own
  // product list (step 2) only makes sense for a country that actually has
  // one, so this reuses that established list rather than a broader
  // reference-country one that would include countries with nothing to show.
  const [originCountries, setOriginCountries] = useState([])
  const [originCountry, setOriginCountry] = useState('')

  // Step 2/3 — grouped product list (grouped by HS code, expandable to the
  // country's own product names sharing that code).
  const [groups, setGroups] = useState([])
  const [expandedGroups, setExpandedGroups] = useState(new Set())
  const [groupSearch, setGroupSearch] = useState('')
  const [selectedGroup, setSelectedGroup] = useState(null)

  // Step 4/5 — variety list for the selected product+country, then one
  // selected variety's own card.
  const [varietyStatus, setVarietyStatus] = useState('idle')
  const [varieties, setVarieties] = useState([])
  const [selectedVariety, setSelectedVariety] = useState(null)

  const [newVarietyName, setNewVarietyName] = useState('')
  const [bootstrapStatus, setBootstrapStatus] = useState('idle')
  const [bootstrapError, setBootstrapError] = useState(null)

  // Step 6/7 — destination country, then the automatic match.
  const [destinationCountries, setDestinationCountries] = useState([])
  const [destinationCountry, setDestinationCountry] = useState('')
  const [matchStatus, setMatchStatus] = useState('idle')
  const [matchResult, setMatchResult] = useState(null)

  const [reviewQueue, setReviewQueue] = useState([])
  const [reviewStatus, setReviewStatus] = useState('idle')

  useEffect(() => {
    fetchConfigStatus().then((r) => setLangsearchConfigured(r.langsearch_configured)).catch(() => setLangsearchConfigured(false))
    Promise.all([
      buildProductPortfolio().catch(() => []),
      fetchProductHsCodes().catch(() => ({ results: {} })),
      fetchProductSources().catch(() => ({ built_in: [], custom: [] })),
      fetchReferenceCountries().catch(() => []),
    ])
      .then(([portfolioRows, hs, sources, referenceCountries]) => {
        setPortfolio(portfolioRows)
        setHsByName(hs.results || {})
        const allSources = [...(sources.built_in || []), ...(sources.custom || [])]
        const withPortfolio = [...new Set(allSources.filter((row) => row.product_count > 0).map((row) => row.country_name))].sort((a, b) =>
          a.localeCompare(b),
        )
        setOriginCountries(withPortfolio)
        setDestinationCountries([...referenceCountries].sort((a, b) => a.name.localeCompare(b.name)))
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

  // Changing an earlier step clears everything downstream of it — the same
  // "a stale downstream choice must never linger" idiom
  // MarketOpportunitiesPanel's own handleSourceChange/handleTargetChange
  // already use.
  function selectOriginCountry(name) {
    setOriginCountry(name)
    setSelectedGroup(null)
    setGroups(name ? buildGroupedProducts(portfolio, hsByName, name) : [])
    setExpandedGroups(new Set())
    setGroupSearch('')
    setVarieties([])
    setSelectedVariety(null)
    setDestinationCountry('')
    setMatchResult(null)
  }

  function toggleGroupExpanded(hsCode) {
    setExpandedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(hsCode)) next.delete(hsCode)
      else next.add(hsCode)
      return next
    })
  }

  // Species anchoring is deferred to here — the moment one of the country's
  // own portfolio product names is actually picked — rather than run for
  // every product just to build the list above (see buildGroupedProducts).
  // A product name that can't be anchored yet (resolver.py's own "never
  // guessed" rule) surfaces honestly as varietyStatus 'unresolved' instead
  // of silently vanishing from the list.
  function selectProduct(group, productName) {
    setSelectedGroup({
      hsCode: group.hsCode,
      description: group.description,
      category: group.category,
      label: group.label,
      productName,
      scientificName: null,
      commonName: null,
    })
    setSelectedVariety(null)
    setDestinationCountry('')
    setMatchResult(null)
    setNewVarietyName(productName)
    setBootstrapStatus('idle')
    setBootstrapError(null)
    setVarieties([])
    setVarietyStatus('loading')
    resolveSpecies([{ key: productName, name: productName, hs_description: group.description }])
      .then(({ results }) => {
        const resolution = results[productName]
        if (!resolution || resolution.status !== 'resolved') {
          setVarietyStatus('unresolved')
          return null
        }
        setSelectedGroup((prev) =>
          prev && prev.hsCode === group.hsCode && prev.productName === productName
            ? { ...prev, scientificName: resolution.scientific_name, commonName: resolution.common_name || null }
            : prev,
        )
        return fetchVarietiesPublic(resolution.scientific_name).then((rows) => {
          setVarieties(rows.filter((row) => row.source_country === originCountry))
          setVarietyStatus('ready')
        })
      })
      .catch(() => setVarietyStatus('error'))
  }

  function selectVariety(variety) {
    setSelectedVariety(variety)
    setDestinationCountry('')
    setMatchResult(null)
  }

  function runBootstrap() {
    if (!selectedGroup || !newVarietyName || !originCountry) return
    setBootstrapStatus('loading')
    setBootstrapError(null)
    bootstrapVariety({
      scientificName: selectedGroup.scientificName,
      commonName: selectedGroup.commonName,
      varietyName: newVarietyName,
      sourceCountry: originCountry,
      category: bootstrapCategoryFor(selectedGroup),
    })
      .then(() => fetchVarietiesPublic(selectedGroup.scientificName))
      .then((rows) => {
        setVarieties(rows.filter((row) => row.source_country === originCountry))
        setBootstrapStatus('ready')
        setNewVarietyName('')
        refreshReviewQueue()
      })
      .catch((err) => {
        setBootstrapStatus('error')
        setBootstrapError(err.message)
      })
  }

  // Step 7 — automatic: picking a destination country IS the confirming
  // action, per spec ("keep it feeling automatic, not another manual
  // multi-click setup"). Triggers the existing, unchanged /match flow
  // (auto-discovery + the already-fixed MIN_COMPARABLE_FIELDS threshold).
  function selectDestinationCountry(name) {
    setDestinationCountry(name)
    setMatchResult(null)
    if (!name || !selectedVariety) return
    setMatchStatus('loading')
    matchVariety({ sourceVarietyId: selectedVariety.id, targetCountry: name, category: bootstrapCategoryFor(selectedGroup) })
      .then((result) => {
        setMatchResult(result)
        setMatchStatus('ready')
      })
      .catch(() => setMatchStatus('error'))
  }

  function handleConfirm(varietyId) {
    confirmVariety(varietyId).then(() => {
      refreshReviewQueue()
      if (selectedGroup) fetchVarietiesPublic(selectedGroup.scientificName).then((rows) => setVarieties(rows.filter((row) => row.source_country === originCountry)))
    })
  }

  function handleReject(varietyId) {
    rejectVariety(varietyId).then(() => {
      refreshReviewQueue()
      if (selectedGroup) fetchVarietiesPublic(selectedGroup.scientificName).then((rows) => setVarieties(rows.filter((row) => row.source_country === originCountry)))
    })
  }

  const filteredGroups = useMemo(() => {
    const term = groupSearch.trim().toLowerCase()
    if (!term) return groups
    return groups.filter(
      (group) =>
        group.label.toLowerCase().includes(term) ||
        (group.hsCode || '').toLowerCase().includes(term) ||
        group.productNames.some((name) => name.toLowerCase().includes(term)),
    )
  }, [groups, groupSearch])

  const destinationOptions = useMemo(() => destinationCountries.filter((row) => row.name !== originCountry), [destinationCountries, originCountry])

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

      <Tabs active={activeTab} onChange={setActiveTab} reviewCount={reviewQueue.length} />

      {activeTab === 'review' && (
        <div className="species-gallery__review-queue species-gallery__review-queue--tab">
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
      )}

      {activeTab === 'flow' && (
        <div className="species-gallery__steps">
          {loadStatus === 'loading' && <p className="species-gallery__hint">Loading the product catalog…</p>}
          {loadStatus === 'error' && <p className="species-gallery__notice">Could not load the product catalog.</p>}

          {/* Step 1 */}
          <div className="species-gallery__step">
            <h5>1. Origin country</h5>
            <label className="market-opportunities__field">
              Origin
              <select value={originCountry} onChange={(e) => selectOriginCountry(e.target.value)}>
                <option value="">Select a country…</option>
                {originCountries.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            {originCountries.length === 0 && loadStatus === 'ready' && (
              <p className="species-gallery__hint">
                No country has a Country Product Portfolio with real products yet — add one in Settings ▸ Product analysis
                sources.
              </p>
            )}
          </div>

          {/* Steps 2/3 */}
          {originCountry && (
            <div className="species-gallery__step">
              <h5>2. Products in {originCountry} (grouped by HS code)</h5>
              <input
                type="text"
                placeholder="Search by product name, HS code, or category…"
                value={groupSearch}
                onChange={(e) => setGroupSearch(e.target.value)}
                className="species-gallery__search"
              />
              {groups.length === 0 && (
                <p className="species-gallery__hint">
                  No classified product yet for {originCountry}'s portfolio — HS-code classification runs in the background
                  and this list picks it up automatically once it's done.
                </p>
              )}
              <ul className="species-gallery__product-list">
                {filteredGroups.map((group) => {
                  const isExpanded = groupSearch.trim() !== '' || expandedGroups.has(group.hsCode)
                  return (
                    <li key={group.hsCode} className="species-gallery__group">
                      <button type="button" className="species-gallery__group-header" onClick={() => toggleGroupExpanded(group.hsCode)}>
                        <span className="species-gallery__group-toggle">{isExpanded ? '▾' : '▸'}</span>
                        {group.label}
                        <span className="species-gallery__product-countries">
                          {group.productNames.length} variet{group.productNames.length === 1 ? 'y' : 'ies'}
                        </span>
                      </button>
                      {isExpanded && (
                        <ul className="species-gallery__group-list">
                          {group.productNames.map((name) => (
                            <li key={name}>
                              <button
                                type="button"
                                className={`species-gallery__product-item ${
                                  selectedGroup?.hsCode === group.hsCode && selectedGroup?.productName === name ? 'is-active' : ''
                                }`}
                                onClick={() => selectProduct(group, name)}
                              >
                                {name}
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          {/* Steps 4/5 */}
          {selectedGroup && (
            <div className="species-gallery__step">
              <h5>
                3. Varieties of {selectedGroup.productName} in {originCountry}
              </h5>
              {bootstrapCategoryFor(selectedGroup) === 'packaged_goods' && (
                <p className="species-gallery__hint">
                  This product is a packaged/branded good ({selectedGroup.category}) — bootstrap will search Open Food Facts
                  (brand/package size/image) instead of the produce web-search + Wikimedia pipeline.
                </p>
              )}
              {varietyStatus === 'loading' && <p className="species-gallery__hint">Anchoring {selectedGroup.productName} to a species…</p>}
              {varietyStatus === 'unresolved' && (
                <p className="species-gallery__notice">
                  Could not anchor {selectedGroup.productName} to a known species yet — try another product name from this
                  group, or a more specific one.
                </p>
              )}
              <div className="species-gallery__variety-grid">
                {varietyStatus === 'ready' && varieties.length === 0 && (
                  <p className="species-gallery__hint">No variety cached yet for {selectedGroup.productName} in {originCountry} — bootstrap one below.</p>
                )}
                {varieties.map((variety) => (
                  <VarietyCard
                    key={variety.id}
                    variety={variety}
                    isSelected={selectedVariety?.id === variety.id}
                    onSelect={selectVariety}
                    selectable
                  />
                ))}
              </div>

              <div className="species-gallery__bootstrap-form">
                <input
                  type="text"
                  value={newVarietyName}
                  onChange={(e) => setNewVarietyName(e.target.value)}
                  placeholder="New variety name"
                />
                <button
                  type="button"
                  onClick={runBootstrap}
                  disabled={!newVarietyName || bootstrapStatus === 'loading' || !selectedGroup?.scientificName}
                >
                  {bootstrapStatus === 'loading' ? 'Bootstrapping…' : `Add / bootstrap a variety for ${originCountry}`}
                </button>
                {bootstrapStatus === 'error' && <p className="species-gallery__notice">{bootstrapError}</p>}
              </div>
            </div>
          )}

          {/* Step 5 detail card */}
          {selectedVariety && (
            <div className="species-gallery__step">
              <h5>
                4. {selectedVariety.variety_name} — {selectedVariety.source_country}
              </h5>
              <div className="species-gallery__variety-grid species-gallery__variety-grid--single">
                <VarietyCard variety={selectedVariety} selectable={false} showDetail />
              </div>
            </div>
          )}

          {/* Steps 6/7 */}
          {selectedVariety && (
            <div className="species-gallery__step">
              <h5>5. Destination country and match</h5>
              <label className="market-opportunities__field">
                Destination
                <select value={destinationCountry} onChange={(e) => selectDestinationCountry(e.target.value)}>
                  <option value="">Select a country…</option>
                  {destinationOptions.map((row) => (
                    <option key={row.name} value={row.name}>
                      {row.name}
                    </option>
                  ))}
                </select>
              </label>

              {matchStatus === 'loading' && (
                <p className="species-gallery__hint">
                  Searching for {destinationCountry} varieties not seen before and bootstrapping any newly discovered ones
                  (real web search + image lookups per variety) — this can take up to a minute the first time a target
                  country has nothing cached yet. Subsequent matches for the same pair are instant.
                </p>
              )}

              {matchStatus === 'error' && <p className="species-gallery__notice">Could not run the match — try again.</p>}

              {matchResult && (
                <div className="species-gallery__match-result">
                  {matchResult.discovered_count > 0 && (
                    <p className="species-gallery__hint">
                      Discovered and bootstrapped {matchResult.discovered_count} new {destinationCountry} variet
                      {matchResult.discovered_count === 1 ? 'y' : 'ies'}: {matchResult.discovered_varieties.map((v) => v.variety_name).join(', ')}.
                    </p>
                  )}
                  {!matchResult.best_match && <p className="species-gallery__notice">{matchResult.message}</p>}
                  {matchResult.best_match && (
                    <>
                      <div className="species-gallery__match-pair">
                        <VarietyCard variety={matchResult.source_variety} selectable={false} showDetail />
                        <VarietyCard variety={matchResult.best_match} selectable={false} showDetail />
                      </div>
                      <p className="species-gallery__score">
                        Match score: {matchResult.score} / {matchResult.max_possible} comparable trait
                        {matchResult.max_possible === 1 ? '' : 's'}
                      </p>
                      {matchResult.field_breakdown.length === 0 ? (
                        <p className="species-gallery__hint">Neither variety has any characteristics on file to compare yet.</p>
                      ) : (
                        <ul className="species-gallery__explanation">
                          {matchExplanationSentences(matchResult.field_breakdown).map((sentence, index) => (
                            <li key={index}>{sentence}</li>
                          ))}
                        </ul>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
