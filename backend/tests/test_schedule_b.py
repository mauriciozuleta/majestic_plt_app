"""The Schedule B reference: the parser of the Census chapter files and the lookup of 10-digit lines and units. Agrees with HS 2022 on every six-digit code it carries."""
import json
import unittest

from backend.catalog_normalization import schedule_b
from backend.comtrade.data import build_schedule_b

CHAPTER = """
### Structured Schedule B records

| Code | Description | Parent context | Unit | Second unit | PDF pages |
| --- | --- | --- | --- | --- | --- |
| 07 | Edible Vegetables | | | | 3 |
| 0702 | Tomatoes, fresh or chilled: | Edible Vegetables | | | 3 |
| 0702.00.0015 | Cherry | Edible Vegetables > Tomatoes, fresh or chilled > Certified organic | kg | | 3 |
|  | Other: | Edible Vegetables > Tomatoes, fresh or chilled | | | 3 |
| 0702.00.0065 | Other | Edible Vegetables > Tomatoes, fresh or chilled > Other | kg | | 3 |
| 0106.11.0000 | Primates | Live animals | No. | kg | 3 |
"""


class ScheduleBTest(unittest.TestCase):
    def test_the_parser_keeps_coded_lines_only(self):
        rows = build_schedule_b.parse_chapter(CHAPTER)
        self.assertEqual([row['code'] for row in rows], ['07', '0702', '0702000015', '0702000065', '0106110000'])
        self.assertEqual(rows[2], {'code': '0702000015', 'description': 'Cherry', 'path': 'Edible Vegetables > Tomatoes, fresh or chilled > Certified organic', 'unit': 'kg', 'unit2': None})
        self.assertEqual(rows[4]['unit2'], 'kg')  # a second unit is kept

    def test_lines_and_units_of_a_code(self):
        self.assertEqual([line['description'] for line in schedule_b.lines_for('0702.00.0015')], ['Cherry'])
        self.assertEqual(len(schedule_b.lines_for('070200')), 6)  # 3 organic + 3 other tomato lines
        self.assertGreater(len(schedule_b.lines_for('0702')), 5)
        self.assertEqual(schedule_b.unit_for('070200'), ('kg', None))
        self.assertEqual(schedule_b.unit_for('0302'), ('kg', None))
        self.assertEqual(schedule_b.unit_for('999999'), (None, None))
        self.assertEqual(schedule_b.lines_for(None), [])

    def test_every_six_digit_code_is_in_hs_2022(self):
        hs = json.loads((build_schedule_b.OUT.parent / 'hs_2022.json').read_text(encoding='utf-8'))
        outside = {line['code'][:6] for line in schedule_b._lines() if int(line['code'][:2]) < 98} - set(hs)
        self.assertEqual(outside, set())  # only the US chapters 98-99 (special provisions) are outside the HS


if __name__ == '__main__':
    unittest.main()
