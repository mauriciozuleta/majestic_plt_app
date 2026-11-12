"""The keyword rules: the backup way to assign an HS code before any AI (backend/catalog_normalization/hs.py suggest_from_keywords, data/hs_keyword_rules.json). The cases are
real product names from the supermarket catalogs, including every mistake found while building the rules (a flavoured cheese read as fruit, "Banana Passionfruit", chicken hot dogs,
fish "steak" read as beef, a variety label in brackets ...). Every code must exist in Comtrade's HS reference."""

import json
import unittest

from backend import models  # noqa: F401  (registers the tables)
from backend.catalog_normalization import hs
from backend.comtrade import classification

# (name, store category, expected 6-digit code or None)
CASES = [
    # vegetables, roots and fruit
    ('Tomato (Local)', None, '070200'),
    ('Sweet Potato (Local Chicken foot)', None, '071420'),  # a variety label in brackets must not decide the commodity
    ('Yam', None, '071430'), ('Dasheen (Local)', None, '071440'), ('Eddoes', None, '071440'), ('Cassava', None, '071410'),
    ('Irish Potato', None, '070190'), ('Garlic Pre Packed 250g', None, '070320'), ('Escallion', None, '070390'),
    ('Callaloo Bush', None, '070999'), ('Carailie Perlb', None, '070999'), ('Market Special Ochro Per lb', None, '070999'), ('Pak Choi', None, '070490'),
    ('Scotch Bonnet Pepper', None, '070960'), ('Ip Pepper Orange 11Kg', None, '070960'), ('Green Peppers [per kg]', None, '070960'),
    ('Pumpkin', None, '070993'), ('Melongene (S)', None, '070930'), ('Sweet Corn', None, '070999'), ('Oyster Mushroom 113G', None, '070951'),
    ('Imported Celery Root (per KG)', None, '070690'), ('Arracacha (Peruvian Carrot)', None, None),
    ('Papaya (Melona)', None, '080720'), ('PAW PAW (Red Lady) (A)', None, '080720'), ('Plantain', None, '080310'), ('Ripe Banana', None, '080390'),
    ('Banana Passionfruit (Gulupa)', None, '081090'), ('Feijoa (Pineapple Guava)', None, '081090'), ('Pear Guava', None, '080450'), ('Julie Mango', None, '080450'),
    ('Pineapple', None, '080430'), ('Hass Avocado', None, '080440'), ('Limes', None, '080550'), ('Watermelon', None, '080711'), ('Honeydew Melon', None, '080719'),
    ('Red Seedless Grapes 2.2 Lbs. Clam Shell', None, '080610'), ('Raspberries', None, '081020'), ('Gala Apples', None, '080810'), ('Pineapple Juice', None, None),
    ('Local Fresh Mint', None, '121190'), ('Thyme (Local)', None, '091099'), ('Ginger (Imported)', None, '091011'),
    # cheese and eggs, also when a fruit or a vegetable is the flavour
    ('Kraft Philadelphia Cream Cheese Spread Strawberry', None, '040610'), ('Dutch Farms Cream Cheese 8oz Chive & Onion', None, '040610'),
    ('Cracker Barrel Baby Swiss 8Oz', None, '040690'), ('Borden Finely Shredded Mild Cheddar', None, '040690'), ('Happy Cow P/Cheese 140G Ham (Triangle)', None, '040690'),
    ('Kraft Singles Cheese 16SL Caramelized Onion', None, '040630'), ('Large White Eggs, 1 Dozen', None, '040721'),
    # cured and prepared meat, which beat the fruit or vegetable word they carry
    ('Johnsonville Jalapeno Cheddar Smoked Sausage', None, '160100'), ('Busseto Salami Chub Green Pepper 227G', None, '160100'), ('Gwaltney Chicken Hot Dogs', None, '160100'),
    ('Blue Ribbon Turkey Bacon 200gms', None, '160231'), ('Mac Foods Ham & Bacon Bits 150g', None, None), ('Fiedlers Black Forest Ham Deli 10kg', None, '160241'),
    ('Salted Pig Tail (per KG)', None, '021019'), ('Boneless Salt Beef', None, '021020'), ('Pollock Salted Fish Bits Per Lb', None, '030569'),
    # raw meat and fish: fresh by default, frozen when the name or the category says so
    ('Chicken Leg quarter with skin', None, '020713'), ('Frozen Chicken Wings', None, '020714'), ('Chicken Wings', 'Frozen Meat & Seafood', '020714'),
    ('Whole Chicken', None, '020711'), ('Beef Strip Loin - 10 oz', None, '020130'), ('Oxtail (Imported/Unbranded)', None, '020120'), ('Beef Liver', None, '020610'),
    ('Pork Tenderloin', None, '020319'), ('Victoria Farms Pork Tails, Bucket', None, '020630'), ('Lamb Chump Stew/Shank Deli Per Lb', None, '020422'),
    ('Tuna Steak Fresh', None, '030234'), ('Vasha Food Carite Steak Sliced Per lb', None, '030289'), ('Snapper Fryers (Imported/Unbranded)', None, '030289'),
    ('Shrimp', None, '030636'), ('Shrimp 21/25 Tail On', 'Frozen Seafood', '030617'), ('Atlantic Salmon Fillet', None, '030441'), ('Talipia Perlb', None, '030271'),
    ('Hake Fillet', None, None),  # a fillet of a species with no fillet code: not guessed
    # nothing a rule can honestly say
    ('Tomato Sauce', None, None), ('Strawberry Yogurt', None, None), ('Chocolate Cake', None, None), ('Wheat Flour', None, None), ('Frozen Strawberries', 'Frozen Fruits', None),
    ('Corned Beef 340g', None, None), ('Vegetable Oil', None, None), ('', None, None),
    ('Banana Cake', None, None), ('Garlic Extract', None, None),  # only the global processed-food words stop these two
]


class KeywordRuleTests(unittest.TestCase):
    def test_real_names(self):
        wrong = []
        for name, category, expected in CASES:
            found = hs.suggest_from_keywords(name, category)
            got = found['code'] if found else None
            if got != expected:
                wrong.append((name, category, expected, got, found and found['note']))
        self.assertEqual(wrong, [])

    def test_a_suggestion_says_which_word_matched_and_how_sure_it_is(self):
        found = hs.suggest_from_keywords('Tomato (Local)')
        self.assertEqual((found['code'], found['method'], found['confidence']), ('070200', 'rule', 'high'))
        self.assertIn('tomato', found['note'].lower())
        self.assertIn('(frozen)', hs.suggest_from_keywords('Chicken Wings', 'Frozen Meat')['note'])
        self.assertEqual(hs.suggest_from_keywords('Hass Avocado')['confidence'], 'high')
        self.assertEqual(hs.suggest_from_keywords('Pak Choi')['confidence'], 'high')
        self.assertEqual(hs.suggest_from_keywords('Atlantic Salmon')['confidence'], 'medium')  # the subheading depends on the species

    def test_every_code_of_every_rule_is_a_real_6_digit_code_of_hs_2022(self):
        current = classification.current_codes()
        self.assertGreater(len(current), 6900)  # the committed HS 2022 file: no network, no skip
        bad = []
        for rule in hs._keyword_rules()['rules']:
            for key in ('code', 'frozen_code', 'fillet_code', 'fillet_frozen_code'):
                code = rule.get(key)
                if code and (len(code) != 6 or code not in current):
                    bad.append((rule['id'], key, code))
        self.assertEqual(bad, [])

    def test_the_rule_file_is_clean(self):
        data = json.loads(hs.KEYWORD_RULES_FILE.read_text(encoding='utf-8'))
        ids = [rule['id'] for rule in data['rules']]
        self.assertEqual(len(ids), len(set(ids)))
        for rule in data['rules']:
            self.assertTrue(rule['words'], rule['id'])
            self.assertRegex(rule['code'], r'^\d{6}$')
            for text in [*rule['words'], *rule['not'], rule['note']]:
                self.assertFalse(any(ord(ch) < 32 for ch in text), (rule['id'], text))

    def test_a_code_a_person_confirmed_elsewhere_outranks_the_keyword_rules_which_outrank_an_unconfirmed_peer(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from backend.database import Base

        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        self.addCleanup(db.close)
        db.add_all([models.ProductHsAssignment(country='Colombia', product_key='dasheen', hs_code='071450', hs_level=6, status='confirmed'),  # a person says yautia
                    models.ProductHsAssignment(country='Colombia', product_key='yam', hs_code='071490', hs_level=6, status='suggested')])  # an AI guess
        db.commit()
        out = hs.suggest(db, [{'country': 'Jamaica', 'name': 'Dasheen'}, {'country': 'Jamaica', 'name': 'Yam'}])
        dasheen, yam = (row['suggestion'] for row in out['results'])
        self.assertEqual((dasheen['code'], dasheen['method']), ('071450', 'peer'))  # the person's choice beats the rule (071440)
        self.assertEqual((yam['code'], yam['method']), ('071430', 'rule'))  # the keyword rule beats an unconfirmed guess
        db.add(models.ProductHsAssignment(country='Colombia', product_key='mystery fruit', hs_code='081090', hs_level=6, status='suggested'))
        db.commit()
        mystery = hs.suggest(db, [{'country': 'Jamaica', 'name': 'Mystery Fruit'}])['results'][0]['suggestion']
        self.assertEqual((mystery['code'], mystery['method']), ('081090', 'peer'))  # no rule knows it: the unconfirmed peer is better than nothing

    def test_the_keyword_step_runs_after_the_exact_rules_and_before_the_peers_and_the_models(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from backend.database import Base

        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        self.addCleanup(db.close)
        out = hs.suggest(db, [{'country': 'Jamaica', 'name': 'Raspberries', 'category': 'PRODUCE'}, {'country': 'Jamaica', 'name': 'Kraft Mac & Cheese Dinner'}])
        first, second = out['results']
        self.assertEqual(first['tried'][:2], ['rule', 'keyword'])  # no peer exists here, so the order is the exact rule, then the keyword rules
        self.assertEqual((first['suggestion']['code'], first['suggestion']['method']), ('081020', 'rule'))
        self.assertIn(first['validation']['status'], ('ok', 'warning'))  # checked like every suggestion
        self.assertIsNone(second['suggestion'])  # nothing a rule can say: left for the next step


if __name__ == '__main__':
    unittest.main()
