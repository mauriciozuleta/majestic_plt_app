import { useMemo, useState } from 'react'
import { IconX } from '@tabler/icons-react'
import { addTourismCountry } from '../../services/tourism'

const SELECTION_KEY = 'tourism:saved-selection'

export function loadSavedSelection() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(SELECTION_KEY) || 'null')
    return Array.isArray(parsed) ? parsed : null
  } catch {
    return null
  }
}

// Searchable multi-select over the whole country/territory registry: autocomplete, regions, select-all-supported, save, and manual additions.
function CountrySelector({ registry, regions, selected, onChange, onRegistryChanged }) {
  const [query, setQuery] = useState('')
  const [region, setRegion] = useState('')
  const [note, setNote] = useState('')
  const [manual, setManual] = useState(null)
  const byId = useMemo(() => new Map(registry.map((country) => [country.country_id, country])), [registry])

  const suggestions = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return []
    return registry
      .filter((country) => !selected.includes(country.country_id))
      .filter((country) => country.country_name.toLowerCase().includes(needle) || country.iso_alpha2.toLowerCase() === needle || (country.iso_alpha3 || '').toLowerCase() === needle)
      .slice(0, 8)
  }, [query, registry, selected])

  const add = (ids) => onChange([...selected, ...ids.filter((id) => !selected.includes(id))])

  const save = () => {
    try {
      window.localStorage.setItem(SELECTION_KEY, JSON.stringify(selected))
      setNote(`Saved ${selected.length} countries.`)
    } catch {
      setNote('Could not save in this browser.')
    }
  }

  const submitManual = async (event) => {
    event.preventDefault()
    try {
      const created = await addTourismCountry({
        name: manual.name,
        iso_alpha2: manual.iso2,
        iso_alpha3: manual.iso3 || null,
        region: manual.region,
        territory: manual.territory,
        parent_country: manual.parent || null,
      })
      setManual(null)
      setNote(`${created.country_name} added to the registry.`)
      await onRegistryChanged()
      add([created.country_id])
    } catch (error) {
      setNote(error.message)
    }
  }

  return (
    <div className="tourism__selector">
      <div className="tourism__selector-row">
        <div className="tourism__search">
          <input type="search" placeholder="Search a country or territory (name, ISO code)…" value={query} onChange={(event) => setQuery(event.target.value)} />
          {suggestions.length > 0 && (
            <ul className="tourism__suggestions">
              {suggestions.map((country) => (
                <li key={country.country_id}>
                  <button
                    type="button"
                    onClick={() => {
                      add([country.country_id])
                      setQuery('')
                    }}
                  >
                    {country.country_name}
                    <small>
                      {country.iso_alpha2}
                      {country.iso_alpha3 ? `/${country.iso_alpha3}` : ''} · {country.region}
                      {country.territory_status === 'territory' ? ' · territory' : ''}
                      {!country.coverage.world_bank ? ' · not in World Bank' : ''}
                    </small>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <select value={region} onChange={(event) => setRegion(event.target.value)} aria-label="Region">
          <option value="">Region…</option>
          {regions.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <button type="button" disabled={!region} onClick={() => add(registry.filter((country) => country.region === region).map((country) => country.country_id))}>
          Add region
        </button>
        <button type="button" onClick={() => add(registry.filter((country) => country.coverage.world_bank).map((country) => country.country_id))}>
          Select all supported ({registry.filter((country) => country.coverage.world_bank).length})
        </button>
        <button type="button" onClick={() => onChange([])} disabled={selected.length === 0}>
          Clear
        </button>
        <button type="button" onClick={save} disabled={selected.length === 0}>
          Save selection
        </button>
        <button type="button" onClick={() => setManual(manual ? null : { name: '', iso2: '', iso3: '', region: regions[0] || 'Caribbean', territory: false, parent: '' })}>
          {manual ? 'Cancel' : 'Add country manually'}
        </button>
      </div>

      {manual && (
        <form className="tourism__manual" onSubmit={submitManual}>
          <input required placeholder="Name" value={manual.name} onChange={(event) => setManual({ ...manual, name: event.target.value })} />
          <input required maxLength={2} placeholder="ISO alpha-2" value={manual.iso2} onChange={(event) => setManual({ ...manual, iso2: event.target.value.toUpperCase() })} />
          <input maxLength={3} placeholder="ISO alpha-3 (optional)" value={manual.iso3} onChange={(event) => setManual({ ...manual, iso3: event.target.value.toUpperCase() })} />
          <select value={manual.region} onChange={(event) => setManual({ ...manual, region: event.target.value })}>
            {regions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <label>
            <input type="checkbox" checked={manual.territory} onChange={(event) => setManual({ ...manual, territory: event.target.checked })} /> Dependent territory
          </label>
          {manual.territory && <input maxLength={2} placeholder="Parent (alpha-2)" value={manual.parent} onChange={(event) => setManual({ ...manual, parent: event.target.value.toUpperCase() })} />}
          <button type="submit">Add</button>
          <small className="tourism__muted">No World Bank code is assumed: a country added here only gets data from the other providers.</small>
        </form>
      )}

      <div className="tourism__chips">
        {selected.map((id) => (
          <span key={id} className="tourism__chip">
            {byId.get(id)?.country_name || id}
            <button type="button" onClick={() => onChange(selected.filter((item) => item !== id))} aria-label={`Remove ${byId.get(id)?.country_name || id}`}>
              <IconX size={12} />
            </button>
          </span>
        ))}
        {selected.length === 0 && <span className="tourism__muted">No countries selected.</span>}
      </div>
      {note && <p className="tourism__muted">{note}</p>}
    </div>
  )
}

export default CountrySelector
