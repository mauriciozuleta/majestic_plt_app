"""Constants of the Global Tourism & Economic Dependency module: indicator definitions, source priority and the app's own country grouping.

Indicator codes are the module's stable ids. Three of them are easily confused and must never be substituted for each other:
  TOURISM_GDP_TOTAL_PCT   WTTC "total contribution of travel & tourism to GDP" (direct + indirect + induced), % of GDP
  TOURISM_GDP_DIRECT_PCT  UN SDG 8.9.1 (series ST_GDP_ZS): tourism DIRECT GDP as a proportion of total GDP, %
  TOURISM_DEPENDENCY      international tourism receipts / GDP x 100 (calculated here)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Indicator:
    code: str
    label: str
    unit: str  # '%', 'USD', 'persons'
    source_priority: tuple[str, ...]  # providers allowed for this indicator, in order
    definition: str


TOURISM_GDP_TOTAL = 'TOURISM_GDP_TOTAL_PCT'
TOURISM_GDP_DIRECT = 'TOURISM_GDP_DIRECT_PCT'
LEGACY_TOURISM_GDP_CODE = 'TOURISM_GDP'  # the code stored before the total/direct split (it always meant the WTTC total)
TOURISM_EMPLOYMENT = 'TOURISM_EMPLOYMENT'
TOURISM_RECEIPTS = 'TOURISM_RECEIPTS'
TOURISM_DEPENDENCY = 'TOURISM_DEPENDENCY'
POPULATION = 'POPULATION'
GDP_USD = 'GDP_USD'  # supporting field of the dependency calculation, not one of the five displayed indicators

WORLD_BANK = 'WORLD_BANK'
IDB = 'IDB'
WTTC = 'WTTC'
STATISTA = 'STATISTA'
UNSD = 'UNSD'
CALCULATED = 'CALCULATED'

INDICATORS: dict[str, Indicator] = {
    TOURISM_GDP_TOTAL: Indicator(TOURISM_GDP_TOTAL, 'Total contribution of travel & tourism to GDP', '%', (WTTC, STATISTA),
                                 'Total (direct + indirect + induced) contribution of travel and tourism to GDP, % of GDP. NOT the direct contribution.'),
    TOURISM_GDP_DIRECT: Indicator(TOURISM_GDP_DIRECT, 'Tourism direct GDP as a proportion of total GDP', '%', (UNSD,),
                                  'SDG indicator 8.9.1, series ST_GDP_ZS (UN Statistics Division): tourism direct gross domestic product as a % of total GDP. NOT the total contribution.'),
    TOURISM_EMPLOYMENT: Indicator(TOURISM_EMPLOYMENT, 'Total contribution of travel & tourism to employment', '%', (WTTC, STATISTA),
                                  'Total contribution of travel and tourism to employment, % of total employment. A count of jobs is not accepted without its denominator.'),
    TOURISM_RECEIPTS: Indicator(TOURISM_RECEIPTS, 'International tourism receipts', 'USD', (WORLD_BANK, IDB, STATISTA),
                                'International tourism, receipts (current US$) — expenditure by inbound visitors. Visitor arrivals are not receipts.'),
    TOURISM_DEPENDENCY: Indicator(TOURISM_DEPENDENCY, 'Tourism receipts / GDP', '%', (CALCULATED,),
                                  'International tourism receipts / GDP (current US$) x 100, same country and same year. Calculated here; not WTTC\'s tourism GDP contribution.'),
    POPULATION: Indicator(POPULATION, 'Population', 'persons', (WORLD_BANK, IDB, STATISTA), 'Total population (SP.POP.TOTL).'),
    GDP_USD: Indicator(GDP_USD, 'GDP (current US$)', 'USD', (WORLD_BANK, IDB, STATISTA), 'Gross domestic product, current US$ (NY.GDP.MKTP.CD). Denominator of the dependency ratio.'),
}
DISPLAY_INDICATORS = (TOURISM_GDP_TOTAL, TOURISM_GDP_DIRECT, TOURISM_EMPLOYMENT, TOURISM_RECEIPTS, TOURISM_DEPENDENCY, POPULATION)

# UN SDG API (https://unstats.un.org/SDGAPI/swagger/)
UNSD_SERIES = {TOURISM_GDP_DIRECT: 'ST_GDP_ZS'}

# World Bank indicator ids (https://api.worldbank.org/v2/)
WORLD_BANK_INDICATORS = {
    TOURISM_RECEIPTS: 'ST.INT.RCPT.CD',
    GDP_USD: 'NY.GDP.MKTP.CD',
    POPULATION: 'SP.POP.TOTL',
}

# data-quality labels
VERIFIED, CALCULATED_STATUS, ESTIMATED, HISTORICAL, MISSING, REQUIRES_REVIEW = 'Verified', 'Calculated', 'Estimated', 'Historical', 'Missing', 'Requires Review'
HISTORICAL_AFTER_YEARS = 5  # an observation older than this many years before the current year is labelled Historical

REGIONS = ('Caribbean', 'North America', 'Central America', 'South America', 'Europe', 'Africa', 'Middle East', 'Asia', 'Oceania')

# The app's own grouping (the World Bank regions are too coarse): by ISO alpha-2. Anything not listed falls back to the World Bank region.
_REGION_SETS = {
    'Caribbean': 'AG AI AW BB BS BQ CU CW DM DO GD GP HT JM KN KY LC MF MQ MS PR SX TC TT VC VG VI',
    'Central America': 'BZ CR GT HN NI PA SV',
    'South America': 'AR BO BR CL CO EC FK GF GY PE PY SR UY VE',
    'North America': 'US CA MX BM GL PM',
    'Oceania': 'AS AU CK FJ FM GU KI MH MP NC NR NU NZ PF PG PW SB TK TO TV VU WF WS',
    'Africa': 'DZ EG LY MA TN DJ SD',  # North Africa / Djibouti sit in the World Bank's Middle East & North Africa region
    'Asia': 'AM AZ GE KZ KG TJ TM UZ',  # Caucasus / Central Asia sit in the World Bank's Europe & Central Asia region
}
REGION_BY_ISO2 = {code: region for region, codes in _REGION_SETS.items() for code in codes.split()}
WORLD_BANK_REGION_TO_APP = {
    'EAS': 'Asia', 'SAS': 'Asia', 'ECS': 'Europe', 'MEA': 'Middle East', 'SSF': 'Africa', 'NAC': 'North America', 'LCN': 'South America',
}

# Dependent territories and special regions (alpha-2 -> parent alpha-2, or None). Everything else from the World Bank list is a sovereign country.
TERRITORIES = {
    'AI': 'GB', 'AS': 'US', 'AW': 'NL', 'BM': 'GB', 'CW': 'NL', 'FO': 'DK', 'GI': 'GB', 'GL': 'DK', 'GU': 'US', 'HK': 'CN', 'IM': 'GB',
    'KY': 'GB', 'MF': 'FR', 'MO': 'CN', 'MP': 'US', 'NC': 'FR', 'PF': 'FR', 'PR': 'US', 'SX': 'NL', 'TC': 'GB', 'VG': 'GB', 'VI': 'US',
    'PS': None, 'MQ': 'FR', 'GP': 'FR', 'GF': 'FR', 'BQ': 'NL', 'FK': 'GB', 'PM': 'FR', 'CK': 'NZ', 'NU': 'NZ', 'TK': 'NZ', 'WF': 'FR', 'MS': 'GB',
}

# name variants seen in provider files -> the registry's (World Bank) name; compared after normalisation (see registry.normalize_name)
COUNTRY_ALIASES = {
    'somalia': 'Somalia, Fed. Rep.',
    # official UN names (UNSD SDG API area list) -> World Bank names
    'democratic republic of the congo': 'Congo, Dem. Rep.', 'united republic of tanzania': 'Tanzania', 'democratic people s republic of korea': "Korea, Dem. People's Rep.",
    'lao people s democratic republic': 'Lao PDR', 'republic of moldova': 'Moldova', 'state of palestine': 'West Bank and Gaza',
    'united kingdom of great britain and northern ireland': 'United Kingdom', 'china hong kong special administrative region': 'Hong Kong SAR, China',
    'china macao special administrative region': 'Macao SAR, China', 'united states of america': 'United States', 'netherlands kingdom of the': 'Netherlands',
    'usa': 'United States', 'us': 'United States', 'united states of america': 'United States', 'uk': 'United Kingdom', 'great britain': 'United Kingdom',
    'bahamas the': 'Bahamas, The', 'bahamas': 'Bahamas, The', 'the bahamas': 'Bahamas, The', 'gambia': 'Gambia, The', 'the gambia': 'Gambia, The',
    'czech republic': 'Czechia', 'turkey': 'Turkiye', 'turkiye': 'Turkiye', 'russia': 'Russian Federation', 'south korea': 'Korea, Rep.',
    'republic of korea': 'Korea, Rep.', 'korea south': 'Korea, Rep.', 'north korea': "Korea, Dem. People's Rep.", 'egypt': 'Egypt, Arab Rep.',
    'iran': 'Iran, Islamic Rep.', 'venezuela': 'Venezuela, RB', 'syria': 'Syrian Arab Republic', 'laos': 'Lao PDR', 'vietnam': 'Viet Nam',
    'yemen': 'Yemen, Rep.', 'kyrgyzstan': 'Kyrgyz Republic', 'slovakia': 'Slovak Republic', 'saint lucia': 'St. Lucia', 'st lucia': 'St. Lucia',
    'saint kitts and nevis': 'St. Kitts and Nevis', 'st kitts and nevis': 'St. Kitts and Nevis', 'saint vincent and the grenadines': 'St. Vincent and the Grenadines',
    'st vincent and the grenadines': 'St. Vincent and the Grenadines', 'hong kong': 'Hong Kong SAR, China', 'macao': 'Macao SAR, China', 'macau': 'Macao SAR, China',
    'saint martin french part': 'St. Martin (French part)', 'saint martin': 'St. Martin (French part)', 'sint maarten': 'Sint Maarten (Dutch part)',
    'cape verde': 'Cabo Verde', 'ivory coast': "Cote d'Ivoire", 'congo democratic republic': 'Congo, Dem. Rep.', 'dr congo': 'Congo, Dem. Rep.',
    'congo': 'Congo, Rep.', 'brunei': 'Brunei Darussalam', 'micronesia': 'Micronesia, Fed. Sts.', 'east timor': 'Timor-Leste', 'swaziland': 'Eswatini',
    'burma': 'Myanmar', 'curacao': 'Curacao', 'puerto rico': 'Puerto Rico (US)', 'british virgin islands': 'British Virgin Islands',
    'us virgin islands': 'Virgin Islands (U.S.)', 'united states virgin islands': 'Virgin Islands (U.S.)', 'turks and caicos': 'Turks and Caicos Islands',
}

# UN M49 area codes of countries whose name is shared by a sub-area or a region in the UN area list (United Kingdom 826/827/828/829, Iraq 368/369/370,
# Tanzania 834/835/836, Micronesia 583 vs the region 57). M49 numeric codes of countries equal their ISO 3166-1 numeric codes. An override is used only if the
# code is present in the UN area list.
M49_OVERRIDES = {'GB': '826', 'IQ': '368', 'TZ': '834', 'FM': '583'}

CACHE_TTL_HOURS = 24
COUNTRY_LIST_TTL_DAYS = 7
