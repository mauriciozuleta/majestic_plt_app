"""Tables of the fuel module (all prefixed fuel_). Created by Base.metadata.create_all when the router is imported."""

from sqlalchemy import Boolean, Column, Date, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from ..database import Base


class FuelSource(Base):
    __tablename__ = 'fuel_sources'
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    url = Column(String)
    license_terms_url = Column(String)
    terms_status = Column(String, nullable=False, default='unverified')  # verified_ok | unverified | restricted
    auth_type = Column(String, default='none')
    rate_limit_notes = Column(String)
    update_frequency = Column(String)  # daily | weekly | monthly | manual
    coverage = Column(String)
    notes = Column(Text)
    adapter = Column(String)  # key into sources.ADAPTERS
    enabled = Column(Boolean, nullable=False, default=False)  # disabled until the user enables it
    terms_signed_off_by = Column(String)  # the user's explicit sign-off
    terms_signed_off_at = Column(DateTime)
    last_success_at = Column(DateTime)
    last_error = Column(Text)
    last_attempt_at = Column(DateTime)


class FuelObservation(Base):
    __tablename__ = 'fuel_observations'
    id = Column(Integer, primary_key=True)
    series_id = Column(String, nullable=False)
    series_kind = Column(String, nullable=False, default='price')  # price | driver
    driver_code = Column(String)  # brent, ... for series_kind=driver
    obs_date = Column(Date, nullable=False)
    period_type = Column(String, nullable=False, default='day')  # day | week | month
    value_usd_per_gal = Column(Float, nullable=False)  # price rows and Brent; non-price drivers live in fuel_driver_points
    value_original = Column(Float)
    unit_original = Column(String)
    currency_original = Column(String)
    geo_level = Column(String, nullable=False)
    region_code = Column(String)
    country_iso2 = Column(String)
    airport_iata = Column(String)
    operator_class = Column(String, nullable=False, default='unspecified')
    price_basis = Column(String, nullable=False)
    source_id = Column(String, nullable=False)
    retrieved_at = Column(DateTime, server_default=func.now())
    raw_ref = Column(Text)  # JSON: file/series, fx rate used, formula ...
    quality = Column(String, nullable=False, default='observed')
    confidence = Column(Float)
    __table_args__ = (
        UniqueConstraint('series_id', 'obs_date', 'operator_class', name='uq_fuel_obs'),
        Index('ix_fuel_obs_lookup', 'geo_level', 'country_iso2', 'airport_iata', 'region_code', 'operator_class', 'obs_date'),
    )


class FuelAirport(Base):
    __tablename__ = 'fuel_airports'
    iata = Column(String, primary_key=True)
    icao = Column(String)
    name = Column(String)
    city = Column(String)
    country_iso2 = Column(String, index=True)
    lat = Column(Float)
    lon = Column(Float)
    region_code = Column(String)


class FuelCountry(Base):
    __tablename__ = 'fuel_countries'
    iso2 = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    region_code = Column(String, nullable=False)


class FuelEvent(Base):
    __tablename__ = 'fuel_events'
    id = Column(Integer, primary_key=True)
    event_date = Column(Date, nullable=False)
    title = Column(String, nullable=False)
    category = Column(String)
    source_url = Column(String)
    __table_args__ = (UniqueConstraint('event_date', 'title', name='uq_fuel_event'),)


class FuelAdjustment(Base):
    """User-supplied country adjustment (taxes, into-plane fees, basis) added to the regional benchmark to build a labelled ESTIMATE."""
    __tablename__ = 'fuel_adjustments'
    id = Column(Integer, primary_key=True)
    country_iso2 = Column(String, nullable=False)
    operator_class = Column(String, nullable=False)
    add_usd_per_gal = Column(Float, nullable=False)
    note = Column(String)
    __table_args__ = (UniqueConstraint('country_iso2', 'operator_class', name='uq_fuel_adj'),)


class FuelDriverPoint(Base):
    """Non-price drivers in their own unit (stocks MBBL, utilization %, production / exports MBBL per day). Brent is a price and lives in fuel_observations."""
    __tablename__ = 'fuel_driver_points'
    id = Column(Integer, primary_key=True)
    series_id = Column(String, nullable=False)
    driver_code = Column(String, nullable=False, index=True)
    obs_date = Column(Date, nullable=False)
    period_type = Column(String, nullable=False, default='week')
    value = Column(Float, nullable=False)
    unit = Column(String, nullable=False)  # mbbl | mbbl_d | percent
    source_id = Column(String, nullable=False)
    retrieved_at = Column(DateTime, server_default=func.now())
    raw_ref = Column(Text)
    __table_args__ = (UniqueConstraint('series_id', 'obs_date', name='uq_fuel_driver_point'),)


class FuelJobRun(Base):
    """Persisted last-run state of each scheduled job (source + job key), so the scheduler can catch up after the app was down and the UI can warn when data are stale."""
    __tablename__ = 'fuel_job_runs'
    source_id = Column(String, primary_key=True)
    job_key = Column(String, primary_key=True)
    frequency = Column(String)
    last_attempt_at = Column(DateTime)
    last_success_at = Column(DateTime)
    last_error = Column(Text)
    rows_last = Column(Integer)
