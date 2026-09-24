import { Fragment, useEffect, useMemo, useState } from 'react'
import { HS_SECTIONS } from './hsChaptersCatalog'
import { buildCategoryCoverage } from '../../services/productPortfolio'
import { fetchHsProductCatalog } from '../../services/globalTradeData'

const EMPTY_COVERAGE = {}

// Every country code shown at a level is now, by construction (see
// buildCategoryCoverage), the deepest level that specific product's
// classification actually reaches — so each one links straight to that
// product in that country's own product list, pre-filtered to this HS
// code, rather than just being plain text. `onCountryCodeClick` is
// optional so the panel still renders sensibly with no callback wired up.
function CodesCell({ codes, hsCode, onCountryCodeClick }) {
  if (!codes || codes.length === 0) return '—'
  return codes.map((code, index) => (
    <span key={code}>
      {index > 0 && ', '}
      <button
        type="button"
        className="available-categories__code-link"
        onClick={() => onCountryCodeClick?.(code, hsCode)}
        title={`View ${code} products classified under ${hsCode}`}
      >
        {code}
      </button>
    </span>
  ))
}

// The Comtrade HS chapter catalog (97 chapters across 21 sections), browsable
// two ways: expand/collapse a section to see its chapters, or type in the
// search box to filter straight to matching chapters (by name or chapter
// number) across every section at once — matching sections auto-expand so a
// search result is never hidden behind a collapsed header.
//
// On top of the static catalog, every chapter that has at least one real
// product anywhere in the app (across every country's product catalog, built
// -in and custom sources alike) is highlighted green, with the specific
// headings/subheadings actually in use nested underneath it — see
// buildCategoryCoverage() (services/productPortfolio.js) for how that's
// computed. Two extra columns show which countries have that category
// covered, split by whether their source is a wholesaler or retail one —
// each country code is a link (see CodesCell above); `onCountryCodeClick`
// is provided by MarketAnalysisView, which knows how to jump to that
// country's own product list (see its focusPanel/focusCategoryProduct).
function AvailableCategoriesPanel({ onCountryCodeClick } = {}) {
  const [searchTerm, setSearchTerm] = useState('')
  const [expandedSections, setExpandedSections] = useState(() => new Set())
  const [expandedChapters, setExpandedChapters] = useState(() => new Set())
  const [expandedHeadings, setExpandedHeadings] = useState(() => new Set())
  const [coverage, setCoverage] = useState(EMPTY_COVERAGE)
  const [coverageError, setCoverageError] = useState(null)
  const [hsDescByCode, setHsDescByCode] = useState({})

  useEffect(() => {
    let cancelled = false
    buildCategoryCoverage()
      .then((data) => {
        if (!cancelled) setCoverage(data)
      })
      .catch((error) => {
        if (!cancelled) setCoverageError(error?.message || 'Could not load product category coverage.')
      })
    fetchHsProductCatalog()
      .then((rows) => {
        if (cancelled) return
        const map = {}
        rows.forEach((row) => {
          map[row.hs_code] = row.description
        })
        setHsDescByCode(map)
      })
      .catch(() => {
        // Descriptions are a nice-to-have for the nested rows — the code
        // itself is always shown regardless.
      })
    return () => {
      cancelled = true
    }
  }, [])

  const isSearching = searchTerm.trim().length > 0

  // One summary per section ("35 products in 6 countries"), always computed
  // from every chapter the section actually contains — independent of the
  // search box, which only narrows which chapters/sections are currently
  // shown, not what a section's own numbers mean. Products are summed
  // across the section's chapters (safe: a product classifies into exactly
  // one chapter, so chapters within a section never share a product);
  // countries are unioned via a Set instead, since the same country can
  // easily have products in more than one chapter of the same section.
  const sectionSummaries = useMemo(() => {
    const summaries = {}
    HS_SECTIONS.forEach((section) => {
      let productCount = 0
      const countries = new Set()
      section.chapters.forEach((row) => {
        const chapterCoverage = coverage[row.hs_chapter]
        if (!chapterCoverage) return
        productCount += chapterCoverage.productCount || 0
        ;(chapterCoverage.countries || []).forEach((code) => countries.add(code))
      })
      summaries[section.section] = { productCount, countryCount: countries.size }
    })
    return summaries
  }, [coverage])

  const filteredSections = useMemo(() => {
    const needle = searchTerm.trim().toLowerCase()
    if (!needle) return HS_SECTIONS
    return HS_SECTIONS.map((section) => ({
      ...section,
      chapters: section.chapters.filter(
        (row) => row.chapter_name.toLowerCase().includes(needle) || row.hs_chapter.includes(needle),
      ),
    })).filter((section) => section.chapters.length > 0)
  }, [searchTerm])

  const toggleSection = (section) => {
    setExpandedSections((current) => {
      const next = new Set(current)
      if (next.has(section)) next.delete(section)
      else next.add(section)
      return next
    })
  }

  const toggleChapter = (chapter) => {
    setExpandedChapters((current) => {
      const next = new Set(current)
      if (next.has(chapter)) next.delete(chapter)
      else next.add(chapter)
      return next
    })
  }

  const toggleHeading = (heading) => {
    setExpandedHeadings((current) => {
      const next = new Set(current)
      if (next.has(heading)) next.delete(heading)
      else next.add(heading)
      return next
    })
  }

  return (
    <div className="available-categories">
      <label className="available-categories__search">
        Search categories
        <input
          type="text"
          value={searchTerm}
          placeholder="Search by chapter name or number…"
          onChange={(event) => setSearchTerm(event.target.value)}
        />
      </label>

      {coverageError && <p className="market-analysis__hint">{coverageError} Showing the static catalog only.</p>}
      {filteredSections.length === 0 && <p className="market-analysis__hint">No chapter matches "{searchTerm}".</p>}

      <div className="available-categories__sections">
        {filteredSections.map((section) => {
          const isOpen = isSearching || expandedSections.has(section.section)
          const range = `${section.chapters[0].hs_chapter}–${section.chapters[section.chapters.length - 1].hs_chapter}`
          const summary = sectionSummaries[section.section]
          return (
            <div key={section.section} className="available-categories__section">
              <button
                type="button"
                className="available-categories__section-head"
                onClick={() => toggleSection(section.section)}
                aria-expanded={isOpen}
              >
                <span className={`available-categories__chevron ${isOpen ? 'is-open' : ''}`}>▸</span>
                <span className="available-categories__section-title">Section {section.section}</span>
                <span className="available-categories__section-meta">
                  Chapters {range} · {section.chapters.length}
                  {summary && summary.productCount > 0 && (
                    <span className="available-categories__section-summary">
                      {' · '}
                      {summary.productCount} {summary.productCount === 1 ? 'product' : 'products'} in {summary.countryCount}{' '}
                      {summary.countryCount === 1 ? 'country' : 'countries'}
                    </span>
                  )}
                </span>
              </button>
              {isOpen && (
                <table className="available-categories__table">
                  <thead>
                    <tr>
                      <th>Code</th>
                      <th>Category</th>
                      <th>Wholesaler</th>
                      <th>Retail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {section.chapters.map((row) => {
                      const chapterCoverage = coverage[row.hs_chapter]
                      const isMatched = Boolean(chapterCoverage)
                      const headingEntries = isMatched ? Object.entries(chapterCoverage.headings) : []
                      const chapterOpen = expandedChapters.has(row.hs_chapter)
                      return (
                        <Fragment key={row.hs_chapter}>
                          <tr className={isMatched ? 'available-categories__row is-matched' : 'available-categories__row'}>
                            <td className="available-categories__code">
                              <span className="available-categories__code-inner">
                                {isMatched && headingEntries.length > 0 && (
                                  <button
                                    type="button"
                                    className="available-categories__row-toggle"
                                    onClick={() => toggleChapter(row.hs_chapter)}
                                    aria-expanded={chapterOpen}
                                    aria-label={`${chapterOpen ? 'Collapse' : 'Expand'} chapter ${row.hs_chapter}`}
                                  >
                                    <span className={`available-categories__chevron ${chapterOpen ? 'is-open' : ''}`}>▸</span>
                                  </button>
                                )}
                                {row.hs_chapter}
                              </span>
                            </td>
                            <td>{row.chapter_name}</td>
                            <td className="available-categories__codes-cell">
                              <CodesCell codes={chapterCoverage?.wholesaler} hsCode={row.hs_chapter} onCountryCodeClick={onCountryCodeClick} />
                            </td>
                            <td className="available-categories__codes-cell">
                              <CodesCell codes={chapterCoverage?.retail} hsCode={row.hs_chapter} onCountryCodeClick={onCountryCodeClick} />
                            </td>
                          </tr>
                          {isMatched &&
                            chapterOpen &&
                            headingEntries.map(([headingCode, headingData]) => {
                              const subEntries = Object.entries(headingData.subheadings)
                              const headingOpen = expandedHeadings.has(headingCode)
                              return (
                                <Fragment key={headingCode}>
                                  <tr className="available-categories__row available-categories__row--heading is-matched">
                                    <td className="available-categories__code">
                                      <span className="available-categories__code-inner available-categories__code--indent-1">
                                        {subEntries.length > 0 && (
                                          <button
                                            type="button"
                                            className="available-categories__row-toggle"
                                            onClick={() => toggleHeading(headingCode)}
                                            aria-expanded={headingOpen}
                                            aria-label={`${headingOpen ? 'Collapse' : 'Expand'} heading ${headingCode}`}
                                          >
                                            <span className={`available-categories__chevron ${headingOpen ? 'is-open' : ''}`}>▸</span>
                                          </button>
                                        )}
                                        {headingCode}
                                      </span>
                                    </td>
                                    <td>{hsDescByCode[headingCode] || '—'}</td>
                                    <td className="available-categories__codes-cell">
                                      <CodesCell codes={headingData.wholesaler} hsCode={headingCode} onCountryCodeClick={onCountryCodeClick} />
                                    </td>
                                    <td className="available-categories__codes-cell">
                                      <CodesCell codes={headingData.retail} hsCode={headingCode} onCountryCodeClick={onCountryCodeClick} />
                                    </td>
                                  </tr>
                                  {headingOpen &&
                                    subEntries.map(([subheadingCode, subheadingData]) => (
                                      <tr
                                        key={subheadingCode}
                                        className="available-categories__row available-categories__row--subheading is-matched"
                                      >
                                        <td className="available-categories__code">
                                          <span className="available-categories__code-inner available-categories__code--indent-2">
                                            {subheadingCode}
                                          </span>
                                        </td>
                                        <td>{hsDescByCode[subheadingCode] || '—'}</td>
                                        <td className="available-categories__codes-cell">
                                          <CodesCell
                                            codes={subheadingData.wholesaler}
                                            hsCode={subheadingCode}
                                            onCountryCodeClick={onCountryCodeClick}
                                          />
                                        </td>
                                        <td className="available-categories__codes-cell">
                                          <CodesCell
                                            codes={subheadingData.retail}
                                            hsCode={subheadingCode}
                                            onCountryCodeClick={onCountryCodeClick}
                                          />
                                        </td>
                                      </tr>
                                    ))}
                                </Fragment>
                              )
                            })}
                        </Fragment>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default AvailableCategoriesPanel
