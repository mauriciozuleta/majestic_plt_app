"""Source registry: the rows seeded into fuel_sources (all DISABLED, terms never marked verified_ok by code) and the adapter behind each."""

from .eia_fred import EiaFredAdapter
from .stubs import AirNavStub, ArgusStub, PlattsStub

ADAPTERS = {'eia_fred': EiaFredAdapter, 'platts_stub': PlattsStub, 'argus_stub': ArgusStub, 'airnav_stub': AirNavStub}

SEED_SOURCES = [
    dict(id='eia_fred', name='EIA via FRED (US Gulf Coast jet spot + Brent)', url='https://fred.stlouisfed.org/series/DJFUELUSGULF',
         license_terms_url='https://fred.stlouisfed.org/legal/', terms_status='unverified', auth_type='none', rate_limit_notes='robots.txt crawl-delay 1 s',
         update_frequency='daily', coverage='US Gulf Coast jet fuel (country US, scheduled-type spot) and global Brent', adapter='eia_fred',
         notes='EIA data is US-government data; FRED republishes it under its own terms page. Read them before enabling.'),
    dict(id='bts_p12', name='BTS Form 41 Schedule P-12(a)', url='https://www.transtats.bts.gov/', license_terms_url='https://www.bts.gov/', terms_status='unverified',
         auth_type='none', update_frequency='manual', coverage='US carriers, monthly airline-paid price, scheduled and non-scheduled', adapter=None,
         notes='File import only (download the CSV yourself). Column names are not verified; see sources/bts_p12.py.'),
    dict(id='iata_regional', name='IATA Jet Fuel Price Monitor (IATA-Platts)', url='https://www.iata.org/en/publications/economics/fuel-monitor/', license_terms_url=None,
         terms_status='unverified', auth_type='none', update_frequency='weekly', coverage='Global + 6 regions', adapter=None,
         notes='Licensing/downloadability NOT confirmed; CSV import only. Price basis (spot vs into-plane) not stated.'),
    dict(id='manual_csv', name='Manual CSV import', url=None, license_terms_url=None, terms_status='verified_ok', auth_type='none', update_frequency='manual',
         coverage='Anything you supply (country, airport, region)', adapter=None, notes='Your own data; you are responsible for having the right to use it.'),
    dict(id='platts_stub', name='S&P Global Platts (paid, not implemented)', url='https://www.spglobal.com/commodityinsights/', terms_status='unverified', auth_type='licence',
         update_frequency='daily', coverage='Global spot assessments', adapter='platts_stub', notes='Stub only.'),
    dict(id='argus_stub', name='Argus Media (paid, not implemented)', url='https://www.argusmedia.com/', terms_status='unverified', auth_type='licence',
         update_frequency='daily', coverage='Global spot and into-plane', adapter='argus_stub', notes='Stub only.'),
    dict(id='airnav_stub', name='AirNav FBO prices (no terms found — do not scrape)', url='https://www.airnav.com/fuel/', terms_status='restricted', auth_type='none',
         update_frequency='daily', coverage='US FBO posted retail (non-scheduled)', adapter='airnav_stub', notes='No terms or API found. Contact AirNav for a feed or permission.'),
]
