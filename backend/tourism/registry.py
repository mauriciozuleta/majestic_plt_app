"""Country and territory registry: ISO alpha-2/alpha-3, region, sovereign/territory status, and per-provider coverage.

The base list is the World Bank's own country list (aggregates removed), so alpha-3 codes are never invented: a country the World Bank does not
know has no alpha-3 here and the World Bank connector will not be asked about it. Countries of the app's reference catalog that are missing from
the World Bank list are added with their alpha-2 code only. Anything else can be added manually (alpha-2, optional alpha-3, region).
"""

import re
import unicodedata
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .. import models
from . import http
from .constants import COUNTRY_ALIASES, M49_OVERRIDES, COUNTRY_LIST_TTL_DAYS, REGION_BY_ISO2, REGIONS, TERRITORIES, WORLD_BANK_REGION_TO_APP

WORLD_BANK_COUNTRIES_URL = 'https://api.worldbank.org/v2/country'
ISO2 = re.compile(r'^[A-Z]{2}$')
ISO3 = re.compile(r'^[A-Z]{3}$')


def normalize_name(name: str) -> str:
    """Lower-case, accent-free, punctuation-free form of a country name, for matching provider names."""
    text = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode().lower()
    text = re.sub(r'\(.*?\)', lambda match: match.group(0) if 'part' in match.group(0) else '', text)
    text = re.sub(r'[^a-z0-9 ]+', ' ', text.replace('&', ' and '))
    return re.sub(r'\s+', ' ', text).strip()


def classify_region(iso2: str, wb_region_id: str | None) -> str:
    if iso2 in REGION_BY_ISO2:
        return REGION_BY_ISO2[iso2]
    return WORLD_BANK_REGION_TO_APP.get(wb_region_id or '', 'Other')


def territory_of(iso2: str) -> tuple[str, str | None]:
    if iso2 in TERRITORIES:
        return 'territory', TERRITORIES[iso2]
    return 'country', None


def fetch_world_bank_countries() -> list[dict]:
    """The World Bank's country list without aggregates (region id 'NA'), all pages."""
    rows: list[dict] = []
    page = 1
    while True:
        data = http.get_json(WORLD_BANK_COUNTRIES_URL, {'format': 'json', 'per_page': 400, 'page': page}, ttl_hours=24 * COUNTRY_LIST_TTL_DAYS)
        if not isinstance(data, list) or len(data) < 2 or data[1] is None:
            raise http.ProviderError('Unexpected answer from the World Bank country list.')
        rows.extend(data[1])
        if page >= int(data[0].get('pages', 1)):
            break
        page += 1
    return [row for row in rows if (row.get('region') or {}).get('id') not in (None, '', 'NA')]


def seed_registry(db: Session, *, refresh: bool = False) -> int:
    """Creates/updates registry rows from the World Bank list and the app's reference catalog. Returns the number of rows."""
    existing = {row.country_id: row for row in db.query(models.TourismCountry).all()}
    if existing and not refresh:
        return len(existing)
    try:
        world_bank = fetch_world_bank_countries()
    except http.ProviderError:
        world_bank = []
    now = datetime.now(timezone.utc).isoformat()
    for row in world_bank:
        iso2, iso3 = (row.get('iso2Code') or '').upper(), (row.get('id') or '').upper()
        if not ISO2.match(iso2) or not ISO3.match(iso3):
            continue
        status, parent = territory_of(iso2)
        record = existing.get(iso2) or models.TourismCountry(country_id=iso2, created_at=now)
        record.country_name = row['name']
        record.iso_alpha2, record.iso_alpha3 = iso2, iso3
        record.region = classify_region(iso2, (row.get('region') or {}).get('id'))
        record.subregion = (row.get('adminregion') or {}).get('value') or None
        record.territory_status, record.parent_country = status, parent
        record.in_world_bank = True
        db.add(record)
        existing[iso2] = record
    for reference in db.query(models.CountryReferenceCatalog).all():
        iso2 = (reference.country_code or '').upper()
        if not ISO2.match(iso2) or iso2 in existing:
            continue
        status, parent = territory_of(iso2)
        record = models.TourismCountry(country_id=iso2, country_name=reference.name, iso_alpha2=iso2, iso_alpha3=None, region=REGION_BY_ISO2.get(iso2) or reference.region or 'Other',
                                       subregion=None, territory_status=status, parent_country=parent, in_world_bank=False, created_at=now)
        db.add(record)
        existing[iso2] = record
    db.commit()
    return len(existing)


def add_manual_country(db: Session, *, name: str, iso2: str, iso3: str | None, region: str, territory: bool = False, parent: str | None = None) -> models.TourismCountry:
    iso2 = (iso2 or '').strip().upper()
    iso3 = (iso3 or '').strip().upper() or None
    if not ISO2.match(iso2):
        raise ValueError('The ISO alpha-2 code must be two letters.')
    if iso3 and not ISO3.match(iso3):
        raise ValueError('The ISO alpha-3 code must be three letters.')
    if region not in REGIONS and region != 'Other':
        raise ValueError(f'Unknown region "{region}". Use one of: {", ".join(REGIONS)}.')
    if not name.strip():
        raise ValueError('The country or territory needs a name.')
    if db.get(models.TourismCountry, iso2) is not None:
        raise ValueError(f'{iso2} is already in the registry.')
    record = models.TourismCountry(country_id=iso2, country_name=name.strip(), iso_alpha2=iso2, iso_alpha3=iso3, region=region, subregion=None,
                                   territory_status='territory' if territory else 'country', parent_country=(parent or '').upper() or None, in_world_bank=False,
                                   manual=True, created_at=datetime.now(timezone.utc).isoformat())
    db.add(record)
    db.commit()
    return record


def resolve_codes(db: Session, codes: list[str]) -> tuple[list[models.TourismCountry], list[str]]:
    """Registry rows for alpha-2/alpha-3 codes; returns (found, unknown codes). Only registry members can reach a provider."""
    seed_registry(db)
    found, unknown = [], []
    for code in codes:
        code = (code or '').strip().upper()
        if not code:
            continue
        row = db.get(models.TourismCountry, code) if ISO2.match(code) else db.query(models.TourismCountry).filter_by(iso_alpha3=code).first() if ISO3.match(code) else None
        if row is None:
            unknown.append(code)
        elif row not in found:
            found.append(row)
    return found, unknown


class NameMatcher:
    """Maps provider country names to registry rows (exact normalised name, then the alias table). Unmatched names are returned to the caller."""

    def __init__(self, db: Session):
        seed_registry(db)
        self.by_name = {normalize_name(row.country_name): row for row in db.query(models.TourismCountry).all()}

    def match(self, name: str) -> models.TourismCountry | None:
        key = normalize_name(name)
        if key in self.by_name:
            return self.by_name[key]
        alias = COUNTRY_ALIASES.get(key)
        if alias:
            return self.by_name.get(normalize_name(alias))
        return None


def assign_m49(db: Session, areas: list[dict]) -> dict:
    """Stores the UN M49 area code on every registry country whose name matches a UN area name (M49 numeric codes equal the ISO 3166-1 numeric codes for
    countries). `areas` = [{code, name}] from the UN SDG API. Regions and other aggregates match nothing and are reported as unmatched, never forced.
    Returns {'matched': n, 'unmatched_areas': [names], 'conflicts': [..]} where a conflict is two areas matching the same country."""
    matcher = NameMatcher(db)
    assigned: dict[str, str] = {}
    conflicts: list[str] = []
    unmatched: list[str] = []
    present = {area['code'] for area in areas}
    forced = {code: iso2 for iso2, code in M49_OVERRIDES.items() if code in present}
    for area in areas:
        if area['code'] in forced:
            assigned[forced[area['code']]] = area['code']
            continue
        row = matcher.match(area['name'])
        if row is not None and row.country_id in M49_OVERRIDES and M49_OVERRIDES[row.country_id] in present:
            continue  # another area of the same name (a sub-area or region): the override already decided
        if row is None:
            unmatched.append(area['name'])
        elif row.country_id in assigned and assigned[row.country_id] != area['code']:
            conflicts.append(f"{row.country_name}: {assigned[row.country_id]} / {area['code']}")
        else:
            assigned[row.country_id] = area['code']
    for row in db.query(models.TourismCountry).all():
        code = assigned.get(row.country_id)
        if code and row.un_m49 != code:
            row.un_m49 = code
    db.commit()
    return {'matched': len(assigned), 'unmatched_areas': unmatched, 'conflicts': conflicts}
