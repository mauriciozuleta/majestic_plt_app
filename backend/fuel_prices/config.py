"""Central settings of the fuel module. Nothing here is a secret; API keys are read from the environment only (see sources/eia_fred.py)."""

import os

LITRES_PER_US_GALLON = 3.785411784
GALLONS_PER_BARREL = 42.0
# Barrels per metric ton of jet fuel. ASSUMPTION (typical density ~0.80 kg/L gives ~7.9): confirm against IATA's own published $/bbl and $/mt pairs once its sheet is imported.
BBL_PER_METRIC_TON = float(os.environ.get('FUEL_BBL_PER_MT', '7.9'))

OPERATOR_CLASSES = ('scheduled', 'non_scheduled', 'unspecified')
GEO_LEVELS = ('global', 'region', 'country', 'airport')
PRICE_BASES = ('spot', 'index', 'airline_paid', 'posted_retail', 'into_plane', 'estimate')
QUALITIES = ('observed', 'derived', 'estimated', 'manual')
TERMS_STATUSES = ('verified_ok', 'unverified', 'restricted')

# Fewest observations a statistic needs before it is computed at all (otherwise it refuses and says why).
MIN_POINTS = {'descriptive': 5, 'volatility': 20, 'seasonality': 24, 'regression': 30, 'lag': 30, 'half_life': 40, 'event': 4, 'passthrough': 12}
