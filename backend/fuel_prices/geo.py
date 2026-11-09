"""Reference data: countries -> IATA regions, and airports (OurAirports, public domain: https://ourairports.com/data/ — the CSV was trimmed to airports with an IATA code).

ASSUMPTION: IATA does not publish its country lists with the price monitor that I could verify, so the mapping below follows IATA's region names with
common-sense placement (Mexico in Latin America, Turkey in Europe & CIS, Egypt in Africa ...). Correct it in the fuel_countries table if IATA differs.
"""

import csv
from pathlib import Path

from sqlalchemy.orm import Session

from . import models as m

DATA = Path(__file__).parent / 'data'

REGIONS = {
    'NA': 'North America',
    'LAC': 'Latin America & Caribbean',
    'EUR': 'Europe & CIS',
    'ME': 'Middle East',
    'AF': 'Africa',
    'APAC': 'Asia-Pacific',
}

_COUNTRIES = {
    'NA': 'US:United States|CA:Canada|BM:Bermuda|GL:Greenland|PM:Saint Pierre and Miquelon',
    'LAC': ('MX:Mexico|GT:Guatemala|BZ:Belize|SV:El Salvador|HN:Honduras|NI:Nicaragua|CR:Costa Rica|PA:Panama|CO:Colombia|VE:Venezuela|GY:Guyana|SR:Suriname|GF:French Guiana|'
            'EC:Ecuador|PE:Peru|BO:Bolivia|BR:Brazil|PY:Paraguay|UY:Uruguay|AR:Argentina|CL:Chile|FK:Falkland Islands|CU:Cuba|JM:Jamaica|HT:Haiti|DO:Dominican Republic|'
            'BS:Bahamas|TC:Turks and Caicos Islands|KY:Cayman Islands|BB:Barbados|TT:Trinidad and Tobago|GD:Grenada|LC:Saint Lucia|VC:Saint Vincent and the Grenadines|'
            'DM:Dominica|AG:Antigua and Barbuda|KN:Saint Kitts and Nevis|AI:Anguilla|MS:Montserrat|VG:British Virgin Islands|VI:U.S. Virgin Islands|PR:Puerto Rico|'
            'AW:Aruba|CW:Curacao|SX:Sint Maarten|BQ:Bonaire, Sint Eustatius and Saba|MF:Saint Martin|BL:Saint Barthelemy|GP:Guadeloupe|MQ:Martinique'),
    'EUR': ('GB:United Kingdom|IE:Ireland|FR:France|DE:Germany|ES:Spain|PT:Portugal|IT:Italy|NL:Netherlands|BE:Belgium|LU:Luxembourg|CH:Switzerland|AT:Austria|DK:Denmark|NO:Norway|'
            'SE:Sweden|FI:Finland|IS:Iceland|PL:Poland|CZ:Czechia|SK:Slovakia|HU:Hungary|RO:Romania|BG:Bulgaria|GR:Greece|CY:Cyprus|MT:Malta|HR:Croatia|SI:Slovenia|'
            'RS:Serbia|BA:Bosnia and Herzegovina|ME:Montenegro|MK:North Macedonia|AL:Albania|XK:Kosovo|EE:Estonia|LV:Latvia|LT:Lithuania|BY:Belarus|UA:Ukraine|MD:Moldova|'
            'RU:Russia|GE:Georgia|AM:Armenia|AZ:Azerbaijan|KZ:Kazakhstan|UZ:Uzbekistan|TM:Turkmenistan|KG:Kyrgyzstan|TJ:Tajikistan|TR:Turkey|AD:Andorra|MC:Monaco|'
            'SM:San Marino|LI:Liechtenstein|VA:Vatican City|GI:Gibraltar|FO:Faroe Islands|JE:Jersey|GG:Guernsey|IM:Isle of Man|AX:Aland Islands|SJ:Svalbard and Jan Mayen'),
    'ME': 'AE:United Arab Emirates|SA:Saudi Arabia|QA:Qatar|KW:Kuwait|BH:Bahrain|OM:Oman|YE:Yemen|IQ:Iraq|IR:Iran|IL:Israel|JO:Jordan|LB:Lebanon|SY:Syria|PS:Palestine',
    'AF': ("EG:Egypt|LY:Libya|TN:Tunisia|DZ:Algeria|MA:Morocco|EH:Western Sahara|MR:Mauritania|SN:Senegal|GM:Gambia|GW:Guinea-Bissau|GN:Guinea|SL:Sierra Leone|LR:Liberia|CI:Cote d'Ivoire|"
           'GH:Ghana|TG:Togo|BJ:Benin|NG:Nigeria|NE:Niger|ML:Mali|BF:Burkina Faso|CV:Cabo Verde|ST:Sao Tome and Principe|GQ:Equatorial Guinea|GA:Gabon|CG:Congo|CD:DR Congo|'
           'CM:Cameroon|CF:Central African Republic|TD:Chad|SD:Sudan|SS:South Sudan|ER:Eritrea|DJ:Djibouti|ET:Ethiopia|SO:Somalia|KE:Kenya|UG:Uganda|RW:Rwanda|BI:Burundi|'
           'TZ:Tanzania|MZ:Mozambique|MW:Malawi|ZM:Zambia|ZW:Zimbabwe|AO:Angola|NA:Namibia|BW:Botswana|ZA:South Africa|LS:Lesotho|SZ:Eswatini|MG:Madagascar|MU:Mauritius|'
           'SC:Seychelles|KM:Comoros|RE:Reunion|YT:Mayotte|SH:Saint Helena'),
    'APAC': ('CN:China|HK:Hong Kong|MO:Macao|TW:Taiwan|JP:Japan|KR:South Korea|KP:North Korea|MN:Mongolia|IN:India|PK:Pakistan|BD:Bangladesh|LK:Sri Lanka|NP:Nepal|BT:Bhutan|'
             'MV:Maldives|AF:Afghanistan|MM:Myanmar|TH:Thailand|LA:Laos|KH:Cambodia|VN:Vietnam|MY:Malaysia|SG:Singapore|ID:Indonesia|BN:Brunei|PH:Philippines|TL:Timor-Leste|'
             'AU:Australia|NZ:New Zealand|PG:Papua New Guinea|FJ:Fiji|NC:New Caledonia|PF:French Polynesia|WS:Samoa|TO:Tonga|VU:Vanuatu|SB:Solomon Islands|GU:Guam|MP:Northern Mariana Islands|'
             'PW:Palau|FM:Micronesia|MH:Marshall Islands|KI:Kiribati|NR:Nauru|TV:Tuvalu|CK:Cook Islands|AS:American Samoa|NU:Niue|WF:Wallis and Futuna|NF:Norfolk Island'),
}


def country_rows() -> list[tuple[str, str, str]]:
    rows = []
    for region, text in _COUNTRIES.items():
        for item in text.split('|'):
            iso2, name = item.split(':', 1)
            rows.append((iso2, name, region))
    return rows


def seed_reference(db: Session) -> None:
    """Idempotent: fills fuel_countries and fuel_airports when empty."""
    if db.query(m.FuelCountry).count() == 0:
        db.add_all([m.FuelCountry(iso2=i, name=n, region_code=r) for i, n, r in country_rows()])
        db.commit()
    if db.query(m.FuelAirport).count() == 0:
        regions = {c.iso2: c.region_code for c in db.query(m.FuelCountry).all()}
        seen, unique = set(), []
        with open(DATA / 'airports.csv', encoding='utf-8', newline='') as handle:
            for row in csv.DictReader(handle):
                iata = row['iata'].upper()
                if iata in seen:
                    continue
                seen.add(iata)
                unique.append(m.FuelAirport(iata=iata, icao=row['icao'], name=row['name'], city=row['city'], country_iso2=row['country_iso2'],
                                            lat=float(row['lat'] or 0), lon=float(row['lon'] or 0), region_code=regions.get(row['country_iso2'])))
        db.add_all(unique)
        db.commit()


def region_of(db: Session, iso2: str | None) -> str | None:
    if not iso2:
        return None
    row = db.get(m.FuelCountry, iso2.upper())
    return row.region_code if row else None
