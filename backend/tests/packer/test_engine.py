import random
import unittest
from backend.packer.models import Plan, Contour, Deck, Allocation
from backend.packer.seed import seed_aircraft
from backend.packer.plan import pack_plan
from backend.packer.packer import pack_position, support, density
from backend.packer.geometry import area, min_width
from backend.packer.orient import fits_door, orientations
from backend.packer.blocks import variants
from pydantic import ValidationError


def carton(l=60,w=40,h=25,kg=14):
    return dict(name='Carton',l=l,w=w,h=h,kg=kg,upright=True,max_layers=30)


def plan_for(deck='main', boxes=None, qty=None, lean=True):
    plan = Plan(company_id='test',box_types=boxes or [carton()],
                alloc={deck:{'P1' if deck=='main' else 'F1':{'0':{'on':True,'qty':qty}}}})
    plan.settings.lower.lean = lean
    return plan


def invariants(test, result, items, opts, points):
    boxes = result['boxes']
    types = {i['type_index']:i for i in items}
    tops = {}
    for b in boxes:
        tops.setdefault(round(b['z']+b['dz'],2),[]).append(b)
    for i,b in enumerate(boxes):
        hw = min_width(points,b['z'],b['z']+b['dz'])/2-opts['side_clearance']
        half_l = opts['L']/2-opts['end_clearance']
        test.assertGreaterEqual(b['x']+1e-6,-hw)
        test.assertLessEqual(b['x']+b['dx'],hw+1e-6)
        test.assertGreaterEqual(b['y']+1e-6,-half_l)
        test.assertLessEqual(b['y']+b['dy'],half_l+1e-6)
        ok, lean = support(b,b['z'],tops,points,opts)
        test.assertTrue(ok)
        test.assertEqual(bool(lean),b['leans'])
        for other in boxes[i+1:]:
            overlap = all(min(b[k]+b['d'+k],other[k]+other['d'+k])-max(b[k],other[k])>1e-6 for k in ['x','y','z'])
            test.assertFalse(overlap, (b,other))
        if opts['strict']:
            for other in boxes:
                if b['z'] >= other['z']+other['dz']-1e-6:
                    test.assertLessEqual(density(types[b['type_index']]),density(types[other['type_index']])*1.0001+1e-6)
    test.assertLessEqual(result['kg'],opts['max_kg']+1e-6)
    for item in items:
        placed = [b for b in boxes if b['type_index']==item['type_index']]
        if item['qty'] is not None:
            test.assertLessEqual(len(placed),item['qty'])
        test.assertLessEqual(len({b['layer'] for b in placed}),item['max_layers'])


class EngineTests(unittest.TestCase):
    def test_contour_volumes(self):
        aircraft = seed_aircraft()
        for name, expected in [('main',13.06),('lower',3.90)]:
            d = aircraft.decks[name]
            self.assertAlmostEqual(area(d.contours[d.default_contour].points)*d.position_length_cm/1e6,expected,delta=.03)

    def test_main_reference(self):
        p = plan_for(boxes=[carton(),dict(name='Flower',l=100,w=50,h=30,kg=12)],qty=60)
        p.alloc['main']['P1']['1'] = Allocation(on=True)
        p = Plan.model_validate(p.model_dump())
        r = pack_plan(p,seed_aircraft())
        pos = r['positions'][0]
        self.assertEqual(len(pos['boxes']),96)
        self.assertEqual(pos['kg'],1252)
        self.assertEqual(pos['height'],200)
        self.assertEqual([len(l['main'])+sum(len(f['boxes']) for f in l['fills']) for l in pos['layers']],[25,25,12,12,10,8,4])
        self.assertEqual(r['type_weights'][1]['volume_kg'],25)
        self.assertEqual(r['type_weights'][1]['chargeable_kg'],25)

    def test_lower_references(self):
        for box,lean,count,leans in [(carton(),True,38,11),(carton(),False,28,0),(carton(40,30,20,5),True,96,None),(carton(40,30,20,5),False,75,0)]:
            r = pack_plan(plan_for('lower',[box],lean=lean),seed_aircraft())
            pos = next(p for p in r['positions'] if p['position']=='F1')
            self.assertEqual(len(pos['boxes']),count)
            if leans is not None:
                self.assertEqual(sum(b['leans'] for b in pos['boxes']),leans)

    def test_door_ids_and_balance(self):
        p = plan_for('lower',[carton(150,150,20,5)])
        r = pack_plan(p,seed_aircraft())
        self.assertEqual(r['totals']['boxes'],0)
        self.assertIn('excluded',next(x for x in r['positions'] if x['position']=='F1')['messages'][0])
        p = plan_for(qty=4)
        p.alloc['lower'] = {'F1':{'0':Allocation(on=True,qty=3)}}
        p = Plan.model_validate(p.model_dump())
        a = seed_aircraft()
        r = pack_plan(p,a)
        self.assertEqual([b['box_id'] for b in r['boxes']],[f'BOX-{i:04d}' for i in range(1,8)])
        self.assertEqual(r['wb']['cg_pct_mac'],None)
        a.decks['main'].positions[0].arm = None
        self.assertIsNone(pack_plan(p,a)['wb']['centroid_m'])
        a.decks['main'].positions[0].arm = 8.5
        a.wb.dow_kg,a.wb.dow_arm_m,a.wb.lemac_m,a.wb.mac_m = 40000,15,13,4
        self.assertIsNotNone(pack_plan(p,a)['wb']['cg_pct_mac'])

    def test_validation_and_orientation(self):
        for points in [[[1,10],[2,20]],[[0,10],[0,20]],[[0,0],[2,0]],[[0,10],[2,-1]]]:
            with self.assertRaises(ValidationError):
                Contour(points=points)
        d = seed_aircraft().decks['main'].model_dump()
        d['positions'].append(d['positions'][0])
        with self.assertRaises(ValidationError):
            Deck.model_validate(d)
        self.assertEqual(len(orientations(carton())),2)
        self.assertEqual(len(orientations(dict(carton(),upright=False))),6)
        self.assertTrue(fits_door(carton(),seed_aircraft().decks['lower'].door))
        self.assertEqual(variants(120,80,60,40)[0]['count'],4)

    def test_200_random_contours_and_mixes(self):
        rng = random.Random(78103)
        for case in range(200):
            points = [[0,rng.uniform(90,240)],[rng.uniform(35,70),rng.uniform(90,250)],[rng.uniform(110,180),rng.uniform(50,240)]]
            opts = dict(L=rng.uniform(100,230),side_clearance=rng.uniform(0,5),end_clearance=2,
                        max_kg=rng.uniform(50,1000),min_support=.8,interlock=bool(case%2),order='heavy' if case%3 else 'space',
                        strict=bool(case%4),lean=bool(case%2),lean_min=.5)
            items = [dict(type_index=i,l=rng.randint(25,70),w=rng.randint(20,60),h=rng.randint(15,45),
                          kg=rng.choice([0,rng.uniform(1,30)]),upright=bool(case%2),max_layers=rng.randint(1,8),
                          qty=rng.choice([None,rng.randint(1,70)])) for i in range(rng.randint(1,4))]
            with self.subTest(case=case):
                invariants(self,pack_position(items,opts,points),items,opts,points)


if __name__ == '__main__':
    unittest.main()
