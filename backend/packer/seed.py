from .models import Aircraft


def seed_aircraft() -> Aircraft:
    return Aircraft.model_validate({
        'id': 'a321p2f', 'name': 'Airbus A321P2F (EFW conversion)', 'builtin': True,
        'notes': "Main deck: 14 positions of 88 × 125 in, cargo door 142 × 85 in, contour calibrated to the published AAY external volume. Lower deck: 10 AKH (LD3-45W) containers, 5 forward and 5 aft, base 60.4 × 61.5 in, 96 in wide at the top, 45 in high, both sides angled, door 143 × 109 cm, 1,134 kg per AKH on the A321 (1,587 kg structural). Balance arms are evenly spaced estimates. Replace everything with the aircraft's Weight & Balance Manual.",
        'decks': {
            'main': {'uld': '88 × 125 in pallet (PAG / AAY)', 'kind': 'pallet', 'position_length_cm': 223.5,
                     'door': {'width': 360.7, 'height': 215.9}, 'default_contour': 'arc',
                     'contours': {
                         'arc': {'name': 'Fuselage arc, container 79.7 in (est.)', 'points': [[0,317.5],[125,317.5],[145,288.6],[165,250.2],[180,212],[192,171.8],[202.4,123.4]]},
                         'cham': {'name': 'Two-chamfer Y contour (est.)', 'points': [[0,317.5],[125,317.5],[175,250],[202.4,123.4]]},
                         'net82': {'name': 'Netted pallet to 82 in (est.)', 'points': [[0,317.5],[127,317.5],[147,288.6],[168,250.2],[184,212],[197,171.8],[208,123.4]]}},
                     'positions': [{'id': f'P{i+1}', 'arm': round(8.50+2.26*i,2), 'max_kg': 2494} for i in range(14)]},
            'lower': {'uld': 'AKH (LD3-45W) container', 'kind': 'container', 'position_length_cm': 153.4,
                      'door': {'width': 143, 'height': 109}, 'default_contour': 'akh',
                      'contours': {'akh': {'name': 'AKH container, double contour (est.)', 'points': [[0,156.2],[56,243.8],[114.3,243.8]]}},
                      'positions': [{'id': f'{prefix}{i+1}', 'arm': round(start+1.6*i,2), 'max_kg': 1134} for prefix, start in [('F',10.9),('A',25)] for i in range(5)]}},
        'wb': {'max_payload_kg': 28000}})
