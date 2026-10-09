"""Storage, source selection and assembly of the tourism indicators.

Rules that matter (see README.md):
  * every observation keeps its source, dataset, edition and retrieval time; sources never overwrite each other;
  * for each indicator the sources allowed by `constants.INDICATORS[...].source_priority` are tried in order, and nothing else is ever substituted;
  * the dependency ratio is receipts / GDP of the SAME country and year, stored as its own CALCULATED observation;
  * a missing value is reported as missing with the reason — never estimated, never borrowed from another year.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .. import models
from . import calc, http, idb, quality, registry, statista, unsd, worldbank, wttc
from . import constants as c

PROVIDER_DEFINITIONS = {
    c.WORLD_BANK: ('World Bank', 'none', [c.TOURISM_RECEIPTS, c.GDP_USD, c.POPULATION]),
    c.IDB: ('Inter-American Development Bank', 'none', []),  # filled from idb_registry.json
    c.WTTC: ('World Travel & Tourism Council (licensed files)', 'licensed_file', [c.TOURISM_GDP_TOTAL, c.TOURISM_EMPLOYMENT]),
    c.STATISTA: ('Statista', 'api_key', []),  # filled from statista_registry.json
    c.UNSD: ('United Nations Statistics Division — SDG API', 'none', [c.TOURISM_GDP_DIRECT]),
}
REASONS = {
    c.TOURISM_GDP_TOTAL: 'No WTTC (or Statista) observation is loaded. Import a licensed WTTC file in the Providers panel; the value is never estimated, and the UN direct GDP share is not a substitute.',
    c.TOURISM_EMPLOYMENT: 'No WTTC (or Statista) observation is loaded. Import a licensed WTTC file in the Providers panel; the value is never estimated.',
    c.TOURISM_DEPENDENCY: 'Needs international tourism receipts and GDP for the same year; one of them is missing.',
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_providers(db: Session) -> None:
    # rows stored before the total/direct split used the code TOURISM_GDP; it always meant WTTC's total contribution
    db.query(models.TourismObservation).filter_by(indicator_code=c.LEGACY_TOURISM_GDP_CODE).update({'indicator_code': c.TOURISM_GDP_TOTAL})
    existing = {row.provider_id for row in db.query(models.TourismProvider).all()}
    for provider_id, (name, auth, indicators) in PROVIDER_DEFINITIONS.items():
        if provider_id not in existing:
            db.add(models.TourismProvider(provider_id=provider_id, provider_name=name, enabled=True, authentication_type=auth, connection_status='unknown', supported_indicators=indicators))
    db.commit()


def provider_enabled(db: Session, provider_id: str) -> bool:
    row = db.get(models.TourismProvider, provider_id)
    return True if row is None else bool(row.enabled)


# ------------------------------------------------------------------ storage
def upsert_observation(db: Session, *, country: models.TourismCountry, indicator_code: str, year: int, value_text, source: str, dataset: str | None, url: str | None,
                       edition: str = '', note: str | None = None, estimated: bool = False, calculated: bool = False, import_id: int | None = None) -> models.TourismObservation | None:
    value = calc.to_decimal(value_text)
    if value is None:
        return None
    unit = c.INDICATORS[indicator_code].unit
    status, problems = quality.validate(indicator_code, float(value), unit, year, iso_known=True, is_calculated=calculated, is_estimated=estimated)
    full_note = ' '.join(part for part in (note, 'Validation: ' + ' '.join(problems) if problems else '') if part) or None
    observation = (
        db.query(models.TourismObservation)
        .filter_by(country_id=country.country_id, indicator_code=indicator_code, reference_year=year, data_source=source, dataset_edition=edition or '')
        .first()
    )
    if observation is None:
        observation = models.TourismObservation(country_id=country.country_id, indicator_code=indicator_code, reference_year=year, data_source=source, dataset_edition=edition or '')
        db.add(observation)
    observation.value = float(value)
    observation.value_text = format(value, 'f')
    observation.unit = unit
    observation.source_dataset = dataset
    observation.source_url = url
    observation.data_retrieved_at = now_iso()
    observation.methodology_note = full_note
    observation.is_estimated = estimated
    observation.is_calculated = calculated
    observation.data_quality_status = status
    observation.import_id = import_id
    return observation


def _fresh(db: Session, country_id: str, source: str, hours: int = c.CACHE_TTL_HOURS) -> bool:
    latest = (
        db.query(models.TourismObservation.data_retrieved_at)
        .filter_by(country_id=country_id, data_source=source)
        .order_by(models.TourismObservation.data_retrieved_at.desc())
        .first()
    )
    if not latest:
        return False
    try:
        return datetime.fromisoformat(latest[0]) > datetime.now(timezone.utc) - timedelta(hours=hours)
    except ValueError:
        return False


def _set_provider(db: Session, provider_id: str, status: str, detail: str | None, synced: bool = False) -> None:
    ensure_providers(db)
    row = db.get(models.TourismProvider, provider_id)
    row.connection_status, row.status_detail = status, detail
    if synced:
        row.last_sync = now_iso()
    db.commit()


# ------------------------------------------------------------------ sync
def sync_world_bank(db: Session, countries: list[models.TourismCountry], *, force: bool = False) -> list[str]:
    """Fetches receipts, GDP and population for the countries that have no fresh World Bank data. Returns warnings (never raises on a provider failure)."""
    if not provider_enabled(db, c.WORLD_BANK):
        return ['The World Bank provider is disabled; stored data only.']
    targets = [country for country in countries if country.in_world_bank and country.iso_alpha3]
    stale = [country for country in targets if force or not _fresh(db, country.country_id, c.WORLD_BANK)]
    if not stale:
        return []
    by_iso3 = {country.iso_alpha3: country for country in stale}
    try:
        data = worldbank.fetch_all(list(by_iso3))
    except http.ProviderError as error:
        _set_provider(db, c.WORLD_BANK, 'error', str(error))
        return [f'World Bank unavailable ({error}); showing stored data only.']
    for indicator_code, (rows, edition) in data.items():
        for row in rows:
            country = by_iso3.get(row['iso3'])
            if country is None:
                continue
            upsert_observation(
                db, country=country, indicator_code=indicator_code, year=row['year'], value_text=row['value_text'], source=c.WORLD_BANK,
                dataset=worldbank.SOURCE_DATASET, url=worldbank.indicator_url(country.iso_alpha3, c.WORLD_BANK_INDICATORS[indicator_code]),
                edition=f'lastupdated {edition}' if edition else '', note=f'World Bank indicator {c.WORLD_BANK_INDICATORS[indicator_code]}.',
            )
    db.commit()
    _set_provider(db, c.WORLD_BANK, 'ok', f'{len(stale)} country(ies) refreshed.', synced=True)
    return []


def _provider_synced_recently(db: Session, provider_id: str, hours: int = c.CACHE_TTL_HOURS) -> bool:
    row = db.get(models.TourismProvider, provider_id)
    if row is None or not row.last_sync or row.connection_status not in ('ok', 'partial'):
        return False
    try:
        return datetime.fromisoformat(row.last_sync) > datetime.now(timezone.utc) - timedelta(hours=hours)
    except ValueError:
        return False


def sync_unsd(db: Session, *, force: bool = False) -> dict:
    """Downloads the whole ST_GDP_ZS series (one request covers every country), maps the UN areas to the registry through their M49 codes and stores
    TOURISM_GDP_DIRECT_PCT. Skipped when the provider synced in the last 24 h. Never raises on a provider failure."""
    ensure_providers(db)
    if not provider_enabled(db, c.UNSD):
        return {'stored': 0, 'warnings': ['The UN SDG API provider is disabled; stored data only.']}
    if not force and _provider_synced_recently(db, c.UNSD):
        return {'stored': 0, 'warnings': [], 'skipped': True}
    registry.seed_registry(db)
    try:
        areas = unsd.fetch_geo_areas()
        rows, stats = unsd.fetch_series_rows()
    except http.ProviderError as error:
        _set_provider(db, c.UNSD, 'error', str(error))
        return {'stored': 0, 'warnings': [f'UN SDG API unavailable ({error}); showing stored data only.']}
    mapping = registry.assign_m49(db, areas)
    by_m49 = {row.un_m49: row for row in db.query(models.TourismCountry).filter(models.TourismCountry.un_m49.isnot(None)).all()}
    warnings: list[str] = []
    stored = rejected = 0
    covered: set[str] = set()
    chosen: dict[tuple, dict] = {}
    for row in rows:
        country = by_m49.get(row['m49'])
        if country is None:
            continue  # an aggregate (World, a region ...) or an area with no registry country
        if row['units'] not in (None, 'PERCENT'):
            rejected += 1
            warnings.append(f"{row['name']} {row['year']}: unit {row['units']} is not PERCENT; not stored.")
            continue
        key = (country.country_id, row['year'])
        current = chosen.get(key)
        if current is not None:  # two records for one area and year (another reporting type): the global-monitoring one wins, nothing is averaged
            rejected += 1
            if current['reporting_type'] == 'G' or row['reporting_type'] != 'G':
                continue
        chosen[key] = row
    for (country_id, year), row in chosen.items():
        country = db.get(models.TourismCountry, country_id)
        notes = [unsd.METHODOLOGY, f'UNSD SDG API series {unsd.SERIES} (SDG 8.9.1).']
        if row['agency']:
            notes.append(f"Reporting agency: {row['agency']}.")
        if row['nature']:
            notes.append(f"Nature of the data: {row['nature']}.")
        if row['footnotes']:
            notes.append('Footnotes: ' + ' '.join(row['footnotes']))
        observation = upsert_observation(
            db, country=country, indicator_code=c.TOURISM_GDP_DIRECT, year=year, value_text=row['value_text'], source=c.UNSD, dataset=unsd.DATASET,
            url=unsd.area_url(row['m49']), note=' '.join(notes), estimated=any('estimate' in note.lower() for note in row['footnotes']),
        )
        if observation is None:
            rejected += 1
            continue
        stored += 1
        covered.add(country_id)
    db.commit()
    detail = (f"{stored} observation(s) for {len(covered)} countries/territories ({stats['total']} records, {stats['pages']} page(s)); "
              f"{len(mapping['unmatched_areas'])} UN area(s) without a registry country (regions and other aggregates).")
    if mapping['conflicts']:
        warnings.append('M49 conflicts: ' + '; '.join(mapping['conflicts']))
    _set_provider(db, c.UNSD, 'ok' if not warnings else 'partial', detail, synced=True)
    return {'stored': stored, 'countries': len(covered), 'rejected': rejected, 'warnings': warnings, 'unmatched_areas': mapping['unmatched_areas'], 'detail': detail}


def sync_all(db: Session, countries: list[models.TourismCountry], *, force: bool = False) -> list[str]:
    """The automatic providers (World Bank per country, UN SDG API for everyone); returns their warnings."""
    warnings = sync_world_bank(db, countries, force=force)
    warnings += sync_unsd(db, force=force)['warnings']
    return warnings


def _country_for(matcher: registry.NameMatcher, db: Session, key: str, kind: str) -> models.TourismCountry | None:
    if kind == 'name':
        return matcher.match(key)
    code = key.upper()
    if kind == 'iso2':
        return db.get(models.TourismCountry, code)
    return db.query(models.TourismCountry).filter_by(iso_alpha3=code).first()


def sync_registered(db: Session, provider_id: str) -> dict:
    """Explicit sync of the IDB or Statista datasets declared in their registry files (never part of a normal compare request)."""
    if provider_id not in (c.IDB, c.STATISTA):
        raise ValueError('Only the IDB and Statista providers have a remote sync.')
    if not provider_enabled(db, provider_id):
        return {'stored': 0, 'warnings': [f'{provider_id} is disabled.']}
    registry.seed_registry(db)
    matcher = registry.NameMatcher(db)
    stored, warnings = 0, []
    if provider_id == c.IDB:
        datasets = idb.load_registry()
        if not datasets:
            _set_provider(db, c.IDB, 'not_configured', 'idb_registry.json lists no dataset with definition_matches=true.')
            return {'stored': 0, 'warnings': ['No IDB dataset is registered.']}
        jobs = [(dataset, lambda dataset=dataset: idb.normalize(dataset, idb.fetch_records(dataset['resource_id']))) for dataset in datasets]
        sources = c.IDB
    else:
        state, detail = statista.status()
        if state != 'configured':
            _set_provider(db, c.STATISTA, state, detail)
            return {'stored': 0, 'warnings': [detail]}
        reg = statista.load_registry()
        jobs = [(dataset, lambda dataset=dataset: statista.fetch(dataset, reg)) for dataset in reg['datasets']]
        sources = c.STATISTA
    for dataset, run in jobs:
        try:
            rows = run()
        except http.ProviderError as error:
            warnings.append(f"{dataset['indicator']}: {error}")
            continue
        if dataset['unit'] != c.INDICATORS[dataset['indicator']].unit:
            warnings.append(f"{dataset['indicator']}: dataset unit \"{dataset['unit']}\" differs from the expected \"{c.INDICATORS[dataset['indicator']].unit}\"; not stored.")
            continue
        for row in rows:
            country = _country_for(matcher, db, row['key'], row['kind'])
            if country is None:
                continue
            observation = upsert_observation(
                db, country=country, indicator_code=dataset['indicator'], year=row['year'], value_text=row['value_text'], source=sources,
                dataset=dataset.get('dataset_name'), url=dataset.get('source_url'), edition=str(dataset.get('edition') or ''),
                note=dataset.get('attribution') or f'{sources} dataset registered by an administrator.',
            )
            stored += 1 if observation else 0
    db.commit()
    _set_provider(db, provider_id, 'ok' if not warnings else 'partial', '; '.join(warnings) or f'{stored} observation(s) stored.', synced=True)
    return {'stored': stored, 'warnings': warnings}


# ------------------------------------------------------------------ selection
def _observations(db: Session, country_id: str, indicator_code: str) -> list[models.TourismObservation]:
    return db.query(models.TourismObservation).filter_by(country_id=country_id, indicator_code=indicator_code).filter(models.TourismObservation.value.isnot(None)).all()


def _best_by_year(observations: list[models.TourismObservation], indicator_code: str) -> dict[int, models.TourismObservation]:
    """One observation per year: the allowed source with the highest priority, then the newest edition."""
    order = c.INDICATORS[indicator_code].source_priority
    best: dict[int, models.TourismObservation] = {}
    for obs in observations:
        if obs.data_source not in order:
            continue
        current = best.get(obs.reference_year)
        key = (-order.index(obs.data_source), obs.dataset_edition or '')
        if current is None or key > (-order.index(current.data_source), current.dataset_edition or ''):
            best[obs.reference_year] = obs
    return best


def compute_dependency(db: Session, country: models.TourismCountry) -> int:
    """Stores TOURISM_DEPENDENCY = receipts / GDP x 100 for every year in which both exist (same country, same year). Returns the number stored."""
    receipts = _best_by_year(_observations(db, country.country_id, c.TOURISM_RECEIPTS), c.TOURISM_RECEIPTS)
    gdp = _best_by_year(_observations(db, country.country_id, c.GDP_USD), c.GDP_USD)
    stored = 0
    for year in sorted(set(receipts) & set(gdp)):
        r, g = receipts[year], gdp[year]
        ratio = calc.tourism_dependency(r.value_text, g.value_text)
        if ratio is None:
            continue
        upsert_observation(
            db, country=country, indicator_code=c.TOURISM_DEPENDENCY, year=year, value_text=ratio, source=c.CALCULATED, dataset='International tourism receipts / GDP', url=None,
            note=f'{r.data_source} receipts {r.value_text} USD / {g.data_source} GDP {g.value_text} USD x 100, both {year}. Not the WTTC tourism GDP contribution.', calculated=True,
        )
        stored += 1
    if stored:
        db.commit()
    return stored


def effective_status(obs: models.TourismObservation) -> str:
    if obs.data_quality_status == c.VERIFIED and obs.reference_year < datetime.now(timezone.utc).year - c.HISTORICAL_AFTER_YEARS:
        return c.HISTORICAL
    return obs.data_quality_status


def _cell(obs: models.TourismObservation | None, reason: str | None = None) -> dict:
    if obs is None:
        return {'value': None, 'value_text': None, 'year': None, 'status': c.MISSING, 'reason': reason}
    return {
        'value': obs.value, 'value_text': obs.value_text, 'unit': obs.unit, 'year': obs.reference_year, 'source': obs.data_source, 'dataset': obs.source_dataset,
        'edition': obs.dataset_edition or None, 'url': obs.source_url, 'retrieved_at': obs.data_retrieved_at, 'status': effective_status(obs),
        'is_estimated': obs.is_estimated, 'is_calculated': obs.is_calculated, 'note': obs.methodology_note, 'reason': None,
    }


def pick(db: Session, country: models.TourismCountry, indicator_code: str, year: int | None) -> dict:
    """The cell for one indicator: year=None means the latest available observation of the first source (in priority order) that has one."""
    observations = _observations(db, country.country_id, indicator_code)
    for source in c.INDICATORS[indicator_code].source_priority:
        candidates = [o for o in observations if o.data_source == source and (year is None or o.reference_year == year)]
        if candidates:
            return _cell(max(candidates, key=lambda o: (o.reference_year, o.dataset_edition or '')))
    return _cell(None, _reason(country, indicator_code, year, observations))


def _reason(country: models.TourismCountry, indicator_code: str, year: int | None, observations: list) -> str:
    if year is not None and observations:
        years = sorted({o.reference_year for o in observations})
        return f'No {year} observation in an allowed source; available years: {years[0]}–{years[-1]}. Other years are never substituted.'
    if indicator_code == c.TOURISM_GDP_DIRECT:
        if not country.un_m49:
            return f'No UN M49 area code could be matched for {country.country_name}, so the UN SDG API (ST_GDP_ZS) cannot be queried for it. The WTTC total contribution is a different indicator and is not used.'
        return f'The UN SDG API (series ST_GDP_ZS) has no tourism direct GDP observation for {country.country_name}. The WTTC total contribution is a different indicator and is not used.'
    if indicator_code in REASONS:
        return REASONS[indicator_code]
    if not country.in_world_bank:
        return f'{country.country_name} is not in the World Bank country list (no verified alpha-3 code). Register an IDB/Statista dataset or import data.'
    return 'The World Bank has no observation for this country and indicator.'


def build_row(db: Session, country: models.TourismCountry, year: int | None) -> dict:
    cells = {code: pick(db, country, code, year) for code in (*c.DISPLAY_INDICATORS, c.GDP_USD)}
    return {
        'country_id': country.country_id, 'country': country.country_name, 'iso_alpha2': country.iso_alpha2, 'iso_alpha3': country.iso_alpha3, 'region': country.region,
        'territory_status': country.territory_status, 'parent_country': country.parent_country, 'in_world_bank': country.in_world_bank, 'un_m49': country.un_m49, 'indicators': cells,
    }


def compare(db: Session, codes: list[str], year: int | None, *, refresh: bool = False) -> dict:
    ensure_providers(db)
    found, unknown = registry.resolve_codes(db, codes)
    warnings = sync_all(db, found, force=refresh)
    rows = []
    for country in found:
        compute_dependency(db, country)
        row = build_row(db, country, year)
        for code, cell in row['indicators'].items():
            if cell['value'] is None and cell['reason'] is None:
                cell['reason'] = 'Missing.'
        rows.append(row)
    if unknown:
        warnings.append('Unknown country code(s) ignored: ' + ', '.join(unknown))
    return {'year': year if year is not None else 'latest', 'rows': rows, 'warnings': warnings, 'unknown': unknown}


def history(db: Session, code: str, year_from: int | None, year_to: int | None, *, refresh: bool = False) -> dict:
    ensure_providers(db)
    found, unknown = registry.resolve_codes(db, [code])
    if not found:
        raise KeyError(code)
    country = found[0]
    warnings = sync_all(db, [country], force=refresh)
    compute_dependency(db, country)
    series = {}
    for indicator_code in (*c.DISPLAY_INDICATORS, c.GDP_USD):
        best = _best_by_year(_observations(db, country.country_id, indicator_code), indicator_code)
        series[indicator_code] = [
            {'year': y, **{k: v for k, v in _cell(best[y]).items() if k in ('value', 'unit', 'source', 'status', 'edition', 'is_calculated', 'is_estimated')}}
            for y in sorted(best) if (year_from is None or y >= year_from) and (year_to is None or y <= year_to)
        ]
    return {'country': {'country_id': country.country_id, 'country': country.country_name, 'iso_alpha3': country.iso_alpha3}, 'series': series, 'warnings': warnings}


def detail(db: Session, code: str, year: int | None) -> dict:
    ensure_providers(db)
    found, unknown = registry.resolve_codes(db, [code])
    if not found:
        raise KeyError(code)
    country = found[0]
    warnings = sync_all(db, [country])
    compute_dependency(db, country)
    row = build_row(db, country, year)
    provenance = (
        db.query(models.TourismObservation).filter_by(country_id=country.country_id)
        .order_by(models.TourismObservation.indicator_code, models.TourismObservation.reference_year.desc()).all()
    )
    for indicator_code, cell in row['indicators'].items():
        if cell['value'] is None:
            warnings.append(f"{c.INDICATORS[indicator_code].label}: {cell['reason']}")
        elif cell['status'] in (c.REQUIRES_REVIEW, c.HISTORICAL):
            warnings.append(f"{c.INDICATORS[indicator_code].label} ({cell['year']}): {cell['status']}. {cell['note'] or ''}".strip())
    return {
        'row': row, 'warnings': warnings,
        'observations': [
            {'indicator': o.indicator_code, 'year': o.reference_year, 'value': o.value, 'unit': o.unit, 'source': o.data_source, 'dataset': o.source_dataset, 'edition': o.dataset_edition or None,
             'status': effective_status(o), 'retrieved_at': o.data_retrieved_at, 'url': o.source_url, 'note': o.methodology_note}
            for o in provenance
        ],
    }


# ------------------------------------------------------------------ WTTC file import
def import_wttc(db: Session, *, file_name: str, content: bytes, edition: str, unit: str = 'percent') -> dict:
    """Imports an authorised WTTC CSV/XLSX file. unit: 'percent' (12.5 = 12.5%) or 'fraction' (0.125 = 12.5%). Every rejected row is reported."""
    if unit not in ('percent', 'fraction'):
        raise ValueError('unit must be "percent" or "fraction".')
    ensure_providers(db)
    registry.seed_registry(db)
    matcher = registry.NameMatcher(db)
    parsed = wttc.parse(file_name, content)
    edition = (edition or '').strip() or f'file {file_name}'
    job = models.TourismImportJob(provider=c.WTTC, file_name=file_name, import_date=now_iso(), dataset_edition=edition, row_count=len(parsed.rows) + len(parsed.rejected),
                                  success_count=0, rejected_count=0, validation_report={})
    db.add(job)
    db.flush()
    rejected = list(parsed.rejected)
    unmatched: set[str] = set()
    seen: dict[tuple, str] = {}
    stored, years = 0, set()
    values = [calc.to_decimal(row['value_text']) for row in parsed.rows]
    numeric = [v for v in values if v is not None]
    warnings = []
    if unit == 'percent' and numeric and max(numeric) <= 1:
        warnings.append('Every value is 1 or less: if the file stores fractions (0.125 = 12.5%), re-import it with unit "fraction".')
    current_year = datetime.now(timezone.utc).year
    for row, value in zip(parsed.rows, values):
        country = None
        if row['code_text']:
            code = row['code_text']
            country = db.get(models.TourismCountry, code) if len(code) == 2 else db.query(models.TourismCountry).filter_by(iso_alpha3=code).first() if len(code) == 3 else None
        if country is None and row['country_text']:
            country = matcher.match(row['country_text'])
        if country is None:
            unmatched.add(row['country_text'] or row['code_text'])
            rejected.append({'row': row['source_row'], 'reason': f"Country \"{row['country_text'] or row['code_text']}\" is not in the registry."})
            continue
        if value is None:
            rejected.append({'row': row['source_row'], 'reason': f"Value \"{row['value_text']}\" is not a number."})
            continue
        percent = value * 100 if unit == 'fraction' else value
        if not 0 <= percent <= 100:
            rejected.append({'row': row['source_row'], 'reason': f'{percent} is not a share between 0 and 100 (unit error?).'})
            continue
        key = (country.country_id, row['indicator'], row['year'])
        if key in seen and seen[key] != format(percent, 'f'):
            rejected.append({'row': row['source_row'], 'reason': f'Duplicate {country.country_name} {row["indicator"]} {row["year"]} with a different value.'})
            continue
        seen[key] = format(percent, 'f')
        observation = upsert_observation(
            db, country=country, indicator_code=row['indicator'], year=row['year'], value_text=percent, source=c.WTTC, dataset=file_name,
            url='https://researchhub.wttc.org/', edition=edition,
            note='Licensed WTTC data imported by an administrator: total contribution (direct + indirect + induced), % of GDP / of total employment.',
            estimated=row['year'] >= current_year, import_id=job.import_id,
        )
        if observation is not None:
            stored += 1
            years.add(row['year'])
    job.success_count, job.rejected_count = stored, len(rejected)
    job.validation_report = {'rejected': rejected[:300], 'rejected_total': len(rejected), 'unmatched_countries': sorted(unmatched), 'warnings': warnings,
                             'years': [min(years), max(years)] if years else None, 'unit': unit}
    db.commit()
    _set_provider(db, c.WTTC, 'ready' if stored else 'awaiting_import', f'{stored} observation(s) from {file_name} ({edition}).', synced=True)
    return import_job_dict(job)


def import_job_dict(job: models.TourismImportJob) -> dict:
    return {'import_id': job.import_id, 'provider': job.provider, 'file_name': job.file_name, 'import_date': job.import_date, 'dataset_edition': job.dataset_edition,
            'row_count': job.row_count, 'success_count': job.success_count, 'rejected_count': job.rejected_count, 'validation_report': job.validation_report}


# ------------------------------------------------------------------ providers
def providers_status(db: Session, *, check: bool = False) -> list[dict]:
    ensure_providers(db)
    if check:
        try:
            unsd.fetch_area('388')
            _set_provider(db, c.UNSD, 'ok', 'Connection test passed (Jamaica, M49 388).')
        except http.ProviderError as error:
            _set_provider(db, c.UNSD, 'error', str(error))
        try:
            worldbank.fetch_indicator(['JAM'], c.WORLD_BANK_INDICATORS[c.POPULATION], date_from=2020)
            _set_provider(db, c.WORLD_BANK, 'ok', 'Connection test passed.')
        except http.ProviderError as error:
            _set_provider(db, c.WORLD_BANK, 'error', str(error))
    idb_datasets = idb.load_registry()
    state, detail = statista.status()
    wttc_count = db.query(models.TourismObservation).filter_by(data_source=c.WTTC).count()
    live = {
        c.IDB: ('configured' if idb_datasets else 'not_configured', f'{len(idb_datasets)} dataset(s) registered in idb_registry.json.' if idb_datasets else 'idb_registry.json lists no dataset with definition_matches=true.'),
        c.STATISTA: (state, detail),
        c.WTTC: ('ready' if wttc_count else 'awaiting_import', f'{wttc_count} observation(s) imported.' if wttc_count else 'No licensed file imported yet. ' + wttc.WttcApiAdapter.reason),
    }
    out = []
    for row in db.query(models.TourismProvider).order_by(models.TourismProvider.provider_id).all():
        if row.provider_id in live:
            row.connection_status, row.status_detail = live[row.provider_id]
        supported = list(row.supported_indicators or [])
        if row.provider_id == c.IDB:
            supported = sorted({d['indicator'] for d in idb_datasets})
        if row.provider_id == c.STATISTA:
            supported = sorted({d['indicator'] for d in statista.load_registry()['datasets']})
        out.append({
            'provider_id': row.provider_id, 'provider_name': row.provider_name, 'enabled': row.enabled, 'authentication_type': row.authentication_type, 'last_sync': row.last_sync,
            'connection_status': row.connection_status, 'detail': row.status_detail, 'supported_indicators': supported,
            'observations': db.query(models.TourismObservation).filter_by(data_source=row.provider_id).count(),
        })
    db.commit()
    return out
