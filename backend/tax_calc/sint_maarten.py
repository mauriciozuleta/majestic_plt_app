"""Sint Maarten (Dutch part): import duty under the Landsverordening tarief van invoerrechten (National Ordinance Tariff of Import Duties, CVDR142349).

The law is short on rates: Art. 2(2) sets the import duty on goods imported into Sint Maarten at NAf 0 (zero), and the tariff annex (the list of goods, with
the general rules of interpretation) is kept for inspection at the Customs Inspectorate (Art. 5) and is not part of the published text. So every tariff line
of Sint Maarten carries the same duty: 0. There is therefore ONE uniform line, which the product mapping uses for every HS code (see mapping.lines_for_hs).

What the calculator does NOT include, and says so in every result:
  - the excise on unleaded gasoline, the only charge Customs collects according to the Government of Sint Maarten (not in this law);
  - the turnover tax (BBO, 5% - business-to-business) which is charged on SALES in the island, not on the import;
  - exemptions (Chapter III), refunds (Chapter IV), the flat-rate tariff for travellers' baggage and small consignments (Art. 2(4), set by decree),
    and import licences or health permits.
The full law in English is in documents/knowledge_base/ ("Sint Maarten - National Ordinance Tariff of Import Duties (English translation)").
"""

from .base import Calculator, Inputs, Result, Tax

LINE = {
    'code': '0000.00',
    'description': 'All goods (the duty is the same for every tariff line)',
    'path': 'All goods',
    'units': None,
    'summary': 'Import duty NAf 0 (Art. 2(2)) - no duty on any goods',
}


class SintMaartenCalculator(Calculator):
    name = 'Sint Maarten (Dutch part)'
    currency = 'USD'
    uniform = True  # one duty for every tariff line: mapping.lines_for_hs returns `lines` for any HS code

    def __init__(self):
        self.lines: list[dict] = [LINE]
        self.by_code: dict[str, dict] = {LINE['code']: LINE}

    def info(self) -> dict:
        return {
            'country': self.name,
            'ready': True,
            'lines': 1,
            'source': 'Landsverordening tarief van invoerrechten (CVDR142349), Art. 2(2): import duty NAf 0',
            'data_date': None,
            'can_refresh': False,
            'refresh_note': 'Nothing to refresh: the rule is written in the law itself (a uniform zero duty).',
            'currency': self.currency,
        }

    def refresh(self) -> dict:
        return self.info()

    def signature(self, line: dict):
        return ('0',)

    def search(self, query: str, limit: int = 30) -> list[dict]:
        return [LINE]

    def get(self, code: str) -> dict | None:
        return LINE

    def calculate(self, code: str, inputs: Inputs) -> Result:
        goods = inputs.goods_value_usd
        result = Result(
            country=self.name,
            line=LINE,
            inputs=inputs.__dict__.copy(),
            value_basis={'name': 'Value of the goods (customs value)', 'amount_usd': round(goods, 2), 'formula': 'duty is zero whatever the value, so the value method (Chapter II) does not change the result'},
            sources=['Landsverordening tarief van invoerrechten, Art. 2(2); Art. 5 (the tariff annex is at the Customs Inspectorate)'],
        )
        result.taxes.append(Tax('Import duty', 0.0, 'NAf 0', 'all goods', 'duty set at zero by Art. 2(2)', note='The law sets the import duty on goods imported into Sint Maarten at NAf 0.'))
        result.notes.append('Sint Maarten charges no import duty on goods (National Ordinance Tariff of Import Duties, Art. 2(2)); the duty is the same for every product, so no tariff line has to be chosen.')
        result.notes.append('The Government of Sint Maarten states that Customs collects only the excise on unleaded gasoline; everything else enters free of duty.')
        if inputs.origin:
            result.notes.append(f'Origin ({inputs.origin}) does not matter: the zero duty applies to goods of any origin.')
        result.warnings.append('Not included: the excise on unleaded gasoline (set outside this law; not computed), exemptions, refunds and the flat-rate tariff for travellers and small consignments (Art. 2(4), set by decree), '
                               'import licences, health and phytosanitary permits, and the turnover tax (BBO, 5%) which is charged on sales in the island, not on the import.')
        result.warnings.append('The tariff annex (list of goods) is not in the published text of the law; the duty is zero under Art. 2(2), but the Council of Ministers may change amounts or percentages by decree (Art. 4(2)) or set temporary exemptions (Art. 4(6)). Confirm with the Customs Inspectorate before relying on it for a large shipment.')
        return result
