"""Common adapter interface. An adapter turns one source into a list of Observation; storing them is the service's job (idempotent upsert)."""

from dataclasses import dataclass, field
from datetime import date
import json


@dataclass
class Observation:
    series_id: str
    obs_date: date
    value_usd_per_gal: float | None
    geo_level: str
    price_basis: str
    source_id: str
    operator_class: str = 'unspecified'
    period_type: str = 'day'  # day | week | month | year
    series_kind: str = 'price'  # price | driver
    driver_code: str | None = None
    value_original: float | None = None
    unit_original: str | None = None
    currency_original: str | None = None
    region_code: str | None = None
    country_iso2: str | None = None
    airport_iata: str | None = None
    quality: str = 'observed'
    confidence: float | None = None
    raw_ref: dict = field(default_factory=dict)
    # Non-price drivers (stocks, utilization, exports ...) keep their own unit: set value_native/native_unit and leave value_usd_per_gal None.
    value_native: float | None = None
    native_unit: str | None = None

    @property
    def is_native_driver(self) -> bool:
        return self.value_native is not None

    def raw_ref_json(self) -> str:
        return json.dumps(self.raw_ref, sort_keys=True, default=str)


@dataclass(frozen=True)
class Job:
    """One independently scheduled piece of a source (e.g. EIA jet price DAILY vs a WEEKLY stocks series)."""
    key: str
    frequency: str  # daily | weekly | monthly
    label: str = ''
    series_id: str | None = None  # the series this job keeps current: lets the scheduler fetch only what is new and judge staleness


class SourceAdapter:
    """`fetch(since)` returns every observation the source holds from `since` on (None = everything). Adapters never write to the database and never read secrets
    from anywhere but environment variables. A source with several update rhythms lists them in `jobs()`; the scheduler runs each when due and calls `fetch_job`.
    File/manual adapters have `automatic = False` and are fed through `parse(...)` instead."""

    source_id: str = ''
    automatic: bool = False

    def jobs(self) -> list[Job]:
        return [Job('all', 'daily', 'all series')]

    def fetch_job(self, key: str, since: date | None = None) -> list[Observation]:
        return self.fetch(since)

    def fetch(self, since: date | None = None) -> list[Observation]:
        raise NotImplementedError(f'{self.source_id} is not an automatic source')
