"""Every selector and visible label the DIAN provider relies on. The JSF component ids are generated (`vistaX:formY:…`), so they are matched by
their stable ENDING only, and rows/links are found by visible text — never by position."""

MENU_URL = 'https://muisca.dian.gov.co/WebArancel/DefMenuConsultas.faces'

# menu entries (visible text, accent-insensitive prefix match)
MENU_BY_CODE = 'Por código de nomenclatura'

# the search form (the same pattern on the "General" and "Por código" pages)
CODE_INPUT = 'input[id$="codNomenclatura"]'
SEARCH_BUTTON = 'input[id$="btConsultarNomenclatura"]'

# the product profile
MEASURES_TABLE_ID_SUFFIX = 'tblconsParametrosMedidas'
IMPORT_BUTTON_ID_SUFFIX = ':btBImpo'
MEASURE_GRAVAMEN = 'Gravamen'
MEASURE_IVA = 'IVA'

# the in-place "unknown code" answer (folded: no accents, lowercase)
NOT_FOUND_TEXT = 'no existen nomenclaturas'

# timeouts (ms)
NAVIGATION_TIMEOUT_MS = 45000
POPUP_TIMEOUT_MS = 15000
