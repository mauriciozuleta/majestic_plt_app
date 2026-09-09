"""
Corabastos' bulletin already sorts products into the 10 canonical categories
one per PDF page. La Mayorista only has 5 broad categories (Verduras y
Hortalizas, Frutas, Procesados y Granos, Carnicos y Lacteos, Frutas
Importadas), so its two mixed buckets need keyword-based sub-classification
into the same 10-category set the rest of the app uses, per the spec's §5
category-alignment note.
"""

TUBERCULO_KEYWORDS = ('papa', 'yuca', 'arracacha', 'name', 'ñame')
PLATANO_KEYWORDS = ('platano', 'plátano')
POLLO_KEYWORDS = ('pollo',)
PESCADO_KEYWORDS = ('pescado', 'bagre', 'tilapia', 'merluza', 'bocachico', 'basa', 'camaron', 'camarón', 'mojarra', 'trucha')
LACTEO_KEYWORDS = ('leche', 'queso', 'cuajada', 'quesito', 'yogur', 'kumis')
HUEVO_KEYWORDS = ('huevo',)


def refine_hortalizas_block(name):
    """La Mayorista's 'Verduras y Hortalizas' block also contains tubers and
    plantains that Corabastos tracks as their own categories."""
    lname = name.lower()
    if any(keyword in lname for keyword in TUBERCULO_KEYWORDS):
        return 'tuberculos'
    if any(keyword in lname for keyword in PLATANO_KEYWORDS):
        return 'platanos'
    return 'hortalizas'


def refine_carnicos_lacteos_block(name):
    """La Mayorista's 'Carnicos y Lacteos' block also contains poultry, fish,
    eggs, and dairy that Corabastos tracks as their own categories."""
    lname = name.lower()
    if any(keyword in lname for keyword in POLLO_KEYWORDS):
        return 'pollo'
    if any(keyword in lname for keyword in PESCADO_KEYWORDS):
        return 'pescados_mariscos'
    if any(keyword in lname for keyword in HUEVO_KEYWORDS):
        return 'huevos'
    if any(keyword in lname for keyword in LACTEO_KEYWORDS):
        return 'lacteos'
    return 'carnicos'
