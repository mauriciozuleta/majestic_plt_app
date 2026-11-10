"""Source registry: the rows seeded into fuel_sources (all DISABLED until the user signs off, except the user's own CSV channel) and the adapter behind each."""

from .bts_socrata import BtsSocrataAdapter
from .bts_monthly import BtsMonthlyAdapter
from .eia_api import EiaApiAdapter
from .stubs import AirNavStub, ArgusStub, PlattsStub

ADAPTERS = {'eia_api': EiaApiAdapter, 'bts_socrata': BtsSocrataAdapter, 'bts_p12': BtsMonthlyAdapter, 'platts_stub': PlattsStub, 'argus_stub': ArgusStub, 'airnav_stub': AirNavStub}
STUB_ADAPTERS = ('platts_stub', 'argus_stub', 'airnav_stub')

# shown next to every price/chart that uses the source (EIA asks for this acknowledgment; BTS lists this attribution on data.bts.gov)
ATTRIBUTION = {
    'eia_api': 'Source: U.S. Energy Information Administration (eia.gov)',
    'bts_socrata': 'Source: U.S. DOT / Bureau of Transportation Statistics (data.bts.gov)',
    'bts_p12': 'Source: U.S. DOT / Bureau of Transportation Statistics, Form 41 Schedule P-12(a)',
}

EIA_TERMS = ('Reviewed 2026-11-09: you may build a service that retrieves, stores for analysis and displays EIA data; name "EIA" / "U.S. Energy Information Administration" as the source; '
             'do not imply EIA endorsement; the EIA logo needs written permission; do not modify content and still claim it is EIA\'s; EIA may limit or block calls that exceed '
             'or circumvent its limits (no number published). US-government data are public domain.')

SEED_SOURCES = [
    dict(id='eia_api', name='U.S. Energy Information Administration (API v2)', url='https://www.eia.gov/opendata/', license_terms_url='https://www.eia.gov/opendata/terms-of-service.php',
         terms_status='unverified', auth_type='api_key (EIA_API_KEY in .env)', rate_limit_notes='5000 rows per request; no published call limit; ~0.6 s pause between calls, backoff on 429/5xx',
         update_frequency='daily', coverage='US Gulf Coast jet spot (daily/weekly/monthly), Brent spot, jet and distillate stocks, refinery utilization, jet production and exports',
         adapter='eia_api', notes=EIA_TERMS + ' Awaiting your sign-off.'),
    dict(id='bts_socrata', name='BTS P-12(a) annual fuel (data.bts.gov)', url='https://data.bts.gov/', license_terms_url='https://www.usa.gov/government-works', terms_status='unverified',
         auth_type='none', rate_limit_notes='robots.txt crawl-delay 1 s', update_frequency='weekly', coverage='US carriers, ANNUAL airline-paid price by carrier group (1990 -> latest year)',
         adapter='bts_socrata', notes='Datasets navd-gpqa (cost) and 33xp-y9fx (gallons), license "Public Domain U.S. Government", attribution U.S. DOT/BTS. Annual only; scheduled/non-scheduled not stated. '
                                       'Awaiting your sign-off.'),
    dict(id='bts_p12', name='BTS P-12(a) monthly fuel (TranStats)', url='https://www.transtats.bts.gov/fuel.asp', license_terms_url='https://www.bts.gov/ntl/policies',
         terms_status='unverified', auth_type='none', update_frequency='daily', coverage='US scheduled carriers, monthly airline-paid price, domestic + international (2000 onward)', adapter='bts_p12',
         notes='Checks the public monthly history table daily and reconciles revisions. Published USD/US gallon; not an airport or retail price. CSV/drop-folder import remains available.'),
    dict(id='iata_regional', name='IATA Jet Fuel Price Monitor (IATA-Platts)', url='https://www.iata.org/en/publications/economics/fuel-monitor/', license_terms_url=None,
         terms_status='unverified', auth_type='none', update_frequency='weekly', coverage='Global + 6 regions', adapter=None,
         notes='Licensing/downloadability NOT confirmed; CSV import only. Price basis (spot vs into-plane) not stated.'),
    dict(id='manual_csv', name='Manual CSV import', url=None, license_terms_url=None, terms_status='verified_ok', auth_type='none', update_frequency='manual',
         coverage='Anything you supply (country, airport, region)', adapter=None, notes='Your own data; you are responsible for having the right to use it.'),
    dict(id='eia_fred', name='FRED (RESTRICTED: terms bar scraping and database storage)', url='https://fred.stlouisfed.org/', license_terms_url='https://fred.stlouisfed.org/legal/',
         terms_status='restricted', auth_type='none', update_frequency='manual', coverage='Superseded by the EIA API source', adapter=None,
         notes='Do not use. Replaced by eia_api; any rows it stored are removed.'),
    dict(id='platts_stub', name='S&P Global Platts (paid, not implemented)', url='https://www.spglobal.com/commodityinsights/', terms_status='unverified', auth_type='licence',
         update_frequency='daily', coverage='Global spot assessments', adapter='platts_stub', notes='Stub only.'),
    dict(id='argus_stub', name='Argus Media (paid, not implemented)', url='https://www.argusmedia.com/', terms_status='unverified', auth_type='licence',
         update_frequency='daily', coverage='Global spot and into-plane', adapter='argus_stub', notes='Stub only.'),
    dict(id='airnav_stub', name='AirNav FBO prices (no terms found — do not scrape)', url='https://www.airnav.com/fuel/', terms_status='restricted', auth_type='none',
         update_frequency='daily', coverage='US FBO posted retail (non-scheduled)', adapter='airnav_stub', notes='No terms or API found. Contact AirNav for a feed or permission.'),
]
