// Local static Spanish -> English dictionary for wholesale produce/food
// names, per spec §6 — no AI/runtime translation, since an incorrect
// product-name translation in a sourcing tool could cause a real mismatched
// purchase. Keyed by a normalized form of the name (lowercase, accents
// stripped, trailing parenthetical unit notes like "(kilo)" removed) so
// La Mayorista's and Corabastos' differently-capitalized/annotated spellings
// of the same product both resolve to one entry.
//
// Source of truth: spanish-english-product-reference.md (the canonical
// name-translation reference built from both sources' real catalogs).
// Where that document says "no direct US equivalent," the native term is
// kept with a description rather than an invented English name. Several
// entries carry a deliberate disambiguation — e.g. Ají (chili pepper) vs.
// Pimentón (bell pepper), or Habichuela (pod bean) vs. Frijol Verde (shelled
// bean) — so the app never conflates two genuinely different products.
//
// Coverage: every product name in the reference document, plus a handful of
// real raw-name variants observed in actual bulletins that the document
// doesn't spell out verbatim (unit-suffixed forms like "x tonelada", grade
// suffixes, etc.) — noted inline where added for that reason. Anything else
// falls back to the Spanish name with a visible "translation needed" marker
// (see translateProductName below) rather than guessing.

function stripAccents(value) {
  return value.normalize('NFD').replace(/[̀-ͯ]/g, '')
}

export function normalizeProductName(nameEs) {
  return stripAccents(nameEs.toLowerCase())
    .replace(/\([^)]*\)/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

export const PRODUCT_TRANSLATIONS = {
  // Hortalizas / Vegetables
  acelga: 'Swiss Chard',
  ahuyama: 'Squash (Ahuyama type)',
  'ajo importado': 'Garlic (imported into Colombia)',
  'ajo rosado': 'Pink Garlic',
  'aji dulce': 'Sweet Chili Pepper', // disambiguation: NOT a bell pepper — see "pimenton"
  'aji picante': 'Hot Chili Pepper',
  alcachofa: 'Artichoke',
  apio: 'Celery',
  berenjena: 'Eggplant',
  brocoli: 'Broccoli',
  calabacin: 'Zucchini',
  'calabacin amarillo': 'Yellow Zucchini',
  calabaza: 'Squash/Pumpkin (general)',
  'cebolla cabezona blanca': 'White Onion',
  'cebolla cabezona roja': 'Red Onion',
  'cebolla blanca': 'White Onion',
  'cebolla roja': 'Red Onion',
  'cebolla larga': 'Green Onion / Scallion (bulb-on)',
  'cebolla junca': 'Green Onion / Scallion (bulb-on)', // La Mayorista's own spelling for the same product as "Cebolla Larga"
  'cebolla puerro': 'Leek', // disambiguation: NOT the same as Cebolla Larga/Junca
  cidra: 'Chayote', // do not confuse with "citron," an unrelated citrus fruit
  cilantro: 'Cilantro',
  coliflor: 'Cauliflower',
  espinaca: 'Spinach',
  'haba verde sabanera': 'Fresh Fava Beans',
  habichuela: 'String Beans / Green Beans (pod)', // disambiguation: the pod, not the shelled bean — see "frijol verde"
  jengibre: 'Ginger',
  lechuga: 'Lettuce (Batavia/butterhead type)',
  'lechuga batavia': 'Lettuce (Batavia/butterhead type)',
  'lechuga crespa': 'Curly/Leaf Lettuce',
  perejil: 'Parsley',
  'pepino cohombro': 'Cucumber',
  'pepino cohombro seleccion': 'Cucumber (Select grade)',
  'pepino comun': 'Cucumber (common/stuffing type)',
  'pepino rellenar': 'Cucumber (stuffing type)', // not in the reference doc; a "Pepino Comun"-style variety seen in real data
  pimenton: 'Bell Pepper', // disambiguation: sweet, not hot — see "aji dulce" / "aji picante"
  'rabano rojo': 'Red Radish',
  rabano: 'Red Radish',
  remolacha: 'Beet / Beetroot',
  repollo: 'Cabbage',
  'repollo blanco': 'Cabbage',
  'tomate chonto': 'Chonto Tomato',
  'tomate chonto regional': 'Chonto Tomato (Regional grade)',
  'tomate chonto seleccion': 'Chonto Tomato (Select grade)',
  'tomate chonto nacional': 'Chonto Tomato (Nacional grade)',
  'tomate larga vida': 'Long-Life Tomato',
  'tomate larga vida corriente': 'Long-Life Tomato (Standard grade)',
  'tomate larga vida extra': 'Long-Life Tomato (Extra grade)',
  'tomate milano': 'Milano Tomato',
  'tomate rinon': '"Kidney" Tomato',
  zanahoria: 'Carrot',

  // Frutas / Fruits
  'aguacate hass': 'Hass Avocado',
  'aguacate hass x tonelada': 'Hass Avocado (by the tonne)',
  'aguacate papelillo': 'Papelillo Avocado',
  'aguacate pieles verdes': 'Green-Skin Avocado (general)',
  'aguacate pieles verdes x tonelada': 'Green-Skin Avocado (by the tonne)',
  'banano criollo': 'Creole Banana',
  'banano uraba': 'Uraba Banana',
  breva: 'Fig (early/spring crop)', // tracked separately from "Higo" — see note there
  coco: 'Coconut',
  'coco san blas': 'San Blas Coconut',
  'curuba boyacence': 'Banana Passionfruit (Boyaca variety)',
  'curuba san bernardo': 'Banana Passionfruit (San Bernardo variety)',
  'curuba larga': 'Banana Passionfruit (Larga variety)',
  'curuba redonda': 'Banana Passionfruit (Gulupa)',
  'durazno nacional': 'Peach (local/domestic)',
  durazno: 'Peach',
  'durazno importado': 'Peach (imported into Colombia)',
  feijoa: 'Feijoa (Pineapple Guava)',
  fresa: 'Strawberry',
  granadilla: 'Granadilla (Sweet Passion Fruit)',
  guanabana: 'Soursop',
  'guanabana citrica': 'Soursop (Citrica variety)',
  guayaba: 'Guava',
  'guayaba manzana': 'Apple Guava',
  'guayaba pera': 'Pear Guava',
  higo: 'Fig (main/late crop)', // same tree as "Breva," tracked as a separate crop in the source data
  'limon comun': 'Key Lime / Common Lime',
  'limon tahiti': 'Tahiti Lime',
  'limon mandarino': 'Mandarin Lime (Rangpur)',
  lulo: 'Lulo (Naranjilla)',
  'mandarina arrayana': 'Arrayana Mandarin',
  'mandarina oneco': 'Oneco Mandarin',
  'mango chancleto': '"Chancleto" Mango',
  'mango de azucar': 'Sugar Mango',
  'mango reina': '"Reina" (Queen) Mango',
  'mango tommy': 'Tommy Atkins Mango',
  'manzana nacional': 'Apple (local/domestic)',
  manzana: 'Apple',
  'manzana roja': 'Red Apple',
  'manzana verde': 'Green Apple',
  'manzana gala': 'Gala Apple',
  maracuya: 'Passion Fruit (yellow)',
  'maracuya valluno': 'Passion Fruit (Valle del Cauca variety)',
  'maracuya regional': 'Passion Fruit (Regional variety)',
  melon: 'Cantaloupe / Muskmelon',
  'melon larga vida': 'Long-Life Melon',
  'mora de castilla': 'Andean Blackberry',
  'mora castilla': 'Andean Blackberry',
  'mora pantanillo': '"Pantanillo" Blackberry',
  'naranja armenia': 'Armenia Orange',
  'naranja grey': '"Grey" Orange',
  'naranja ombligona': 'Navel Orange',
  'naranja tangelo': 'Tangelo',
  'naranja valencia': 'Valencia Orange',
  'papaya hawaiana': 'Hawaiian Papaya',
  'papaya maradol': 'Maradol Papaya',
  'papaya melona': '"Melona" Papaya',
  'papaya redonda': 'Round Papaya',
  'papaya tainung': 'Tainung Papaya',
  patilla: 'Watermelon',
  sandia: 'Watermelon',
  'pina gold': 'Gold Pineapple',
  'pina perolera': 'Perolera Pineapple',
  'pina oro miel': '"Honey Gold" Pineapple',
  pitahaya: 'Dragon Fruit',
  'tomate de arbol': 'Tree Tomato (Tamarillo)',
  'uchuva capacho': 'Cape Gooseberry / Goldenberry (with husk)',
  'uchuva/capacho': 'Cape Gooseberry / Goldenberry (with husk)',
  uchuva: 'Cape Gooseberry / Goldenberry',
  'uva champa': '"Champa" Grape',
  'uva negra': 'Black Grape',
  'uva roja': 'Red Grape',
  'uva red globe importada': 'Red Globe Grape (imported)',
  'uva red globe nacional': 'Red Globe Grape (local)',
  kiwi: 'Kiwi',
  'pera importada': 'Pear (imported into Colombia)',
  'ciruela claudia americana': 'American Claudia Plum',
  'banano criollo cajamadera': 'Creole Banana (wooden box)',

  // Tuberculos / Tubers & Platanos / Plantains
  arracacha: 'Arracacha (Peruvian Carrot)',
  'papa capira bogotana': 'Capira Potato (Bogota grade)',
  'papa capira mediana seleccionada': 'Capira Potato (Medium Select)',
  'papa capira regional': 'Capira Potato (Regional grade)',
  'papa capira seleccion': 'Capira Potato (Select grade)',
  'papa criolla': 'Creole Potato',
  'papa criolla lavada': 'Creole Potato, Washed',
  'papa criolla sucia': 'Creole Potato, Unwashed',
  'papa nevada': '"Nevada" Potato',
  'papa pastusa': 'Pastusa Potato',
  'papa purace': 'Purace Potato',
  'papa r12 industrial': 'R12 Potato (Industrial grade)',
  'papa r12 negra': 'R12 Potato (Black-skin)',
  'papa r12 roja': 'R12 Potato (Red-skin)',
  'papa sabanera': 'Sabanera Potato',
  'papa suprema': '"Suprema" Potato',
  'papa tocarre': '"Tocarre" Potato',
  'platano colicero': '"Colicero" Plantain',
  'platano harton': 'Harton Plantain',
  'platano guineo': 'Guineo Banana', // disambiguation: a dessert banana, NOT a plantain
  'yuca armenia': 'Cassava / Yuca (Armenia grade)',
  'yuca llanera': 'Cassava / Yuca (Llanera grade)',
  yuca: 'Cassava / Yuca',

  // Carnicos / Beef, Pollo / Poultry, Pescados y Mariscos / Fish & Seafood
  cadera: 'Top Sirloin / Rump',
  'carne de cerdo': 'Pork (generic)',
  'carne de res': 'Beef (generic)',
  chatas: 'Flank / Flat Rib Cut',
  costilla: 'Beef Ribs',
  'higado res': 'Beef Liver',
  lomo: 'Beef Loin / Tenderloin',
  pierna: 'Beef Leg (Round)',
  sobrebarriga: 'Flank Steak',
  'visceras res': 'Beef Offal (general)',
  'alas de pollo': 'Chicken Wings',
  menudencias: 'Chicken Giblets',
  'pechuga de pollo': 'Chicken Breast',
  'pernil de pollo': 'Chicken Leg Quarter',
  'perniles de pollo': 'Chicken Leg Quarter',
  'pollo entero': 'Whole Chicken',
  'pollo sin viceras': 'Whole Chicken (eviscerated)',
  'bagre dorado': 'Golden Catfish',
  'bagre pintado': 'Spotted Catfish',
  'bagre en rodajas': 'Catfish (sliced)',
  'blanquillo gallego': 'Blanquillo Catfish',
  'boca chico': 'Bocachico',
  'pescado bocachico': 'Bocachico',
  cachama: 'Cachama (Pacu)',
  cajaro: 'Cajaro Catfish',
  'camaron tigre': 'Tiger Shrimp',
  'camaron titi': 'Titi Shrimp',
  capaceta: 'Capaceta (regional fish name)',
  'caracol almeja': 'Clam',
  corvina: 'Corvina / White Sea Bass',
  cucha: '"Cucha" (armored catfish)',
  doncella: 'Doncella Catfish',
  'filete de merluza': 'Hake Fillet',
  'pescado merluza': 'Hake',
  'filete de robalo': 'Snook Fillet',
  gualajo: 'Gualajo (regional fish name)',
  'mojarra de mar': 'Sea Bream (saltwater mojarra)',
  'mojarra o tilapia roja': 'Red Tilapia',
  'pescado tilapia': 'Red Tilapia',
  nicuro: 'Nicuro Catfish',
  paleton: '"Paleton" Catfish',
  pelada: '"Pelada" Fish',
  'pescado basa': 'Basa Fish',
  'pescado seco': 'Dried/Salted Fish',
  'pez mero o pollito de mar': 'Grouper',
  'pira boton': '"Pira Boton" (regional fish name)',
  sierra: 'Kingfish (Spanish Mackerel)',
  'toyo tiburon peque': 'Small Shark',
  'tiburon peque': 'Small Shark',
  'trucha arco iris': 'Rainbow Trout',
  valenton: '"Valenton" Catfish',

  // Huevos / Eggs, Lacteos / Dairy
  'huevo a': 'Eggs, Grade A', // La Mayorista's A/AA/AAA scale
  'huevo aa': 'Eggs, Grade AA',
  'huevo aaa': 'Eggs, Grade AAA',
  'huevo a unidad': 'Eggs, Grade A (each)',
  'huevo aa unidad': 'Eggs, Grade AA (each)',
  'huevo aaa unidad': 'Eggs, Grade AAA (each)',
  'huevo blanco a': 'White Eggs, Grade A', // Corabastos' own A/AA/B/Extra scale — not the same scale as La Mayorista's above
  'huevo blanco aa': 'White Eggs, Grade AA',
  'huevo blanco b': 'White Eggs, Grade B',
  'huevo blanco extra': 'White Eggs, Grade Extra',
  'huevo rojo a': 'Brown Eggs, Grade A',
  'huevo rojo aa': 'Brown Eggs, Grade AA',
  'huevo rojo b': 'Brown Eggs, Grade B',
  'huevo rojo extra': 'Brown Eggs, Grade Extra',
  cuajada: 'Fresh Curd Cheese',
  quesito: '"Quesito"',
  'queso campesino': "Farmer's Cheese",
  'queso costeno': 'Coastal Cheese ("Queso Costeno")',
  'queso coste': 'Coastal Cheese ("Queso Costeno")',
  'queso doble crema': 'Double Cream Cheese',
  'queso paipa': 'Paipa Cheese',
  'queso pera': '"Pera" Cheese',
  'leche liquida': 'Liquid Milk (1L bag)',
  'leche polvo 400 gr': 'Powdered Milk (400g)',

  // Granos y Procesados / Grains & Processed Goods
  'aceite vegetal 500 cm3': 'Vegetable Oil (500ml bottle)',
  'aceite vegetal 1000 cm3': 'Vegetable Oil (1L bottle)',
  'aceite vegetal 3000 cm3': 'Vegetable Oil (3L jug)',
  aceite: 'Vegetable Oil',
  'aceite galon': 'Vegetable Oil (gallon jug)',
  arroz: 'Rice (by arroba)', // "arroba" is a weight unit, not a rice variety
  'arroz corriente': 'Regular Rice',
  'arroz oryzica': 'Oryzica Rice',
  'arroz sopa cristal': '"Crystal" Soup Rice',
  'arveja verde': 'Green Peas', // La Mayorista's generic name for the same product as Corabastos' "Arveja Verde Sabanera"
  'arveja verde sabanera': 'Fresh Green Peas (Sabanera)',
  'arveja verde seca': 'Dried Green Peas',
  'arveja seca': 'Dried Green Peas',
  'avena hojuela': 'Rolled Oats',
  'avena molida': 'Ground Oats',
  'azucar empacada': 'Packaged Sugar',
  'azucar sulfitada': 'Sulfited Sugar',
  azucar: 'Sugar (50kg sack)',
  cebada: 'Barley',
  'cafe 500gr': 'Coffee (500g)', // not in the reference doc; a real Granos y Procesados item
  chocolate: 'Drinking Chocolate (by the pound)', // solid drinking-chocolate tablets, NOT a chocolate bar/candy
  'chocolate dulce': 'Sweet Drinking Chocolate',
  'cuchuco de cebada': 'Barley Cuchuco',
  'cuchuco de maiz': 'Corn Cuchuco',
  'cuchuco de trigo': 'Wheat Cuchuco',
  'frijol cargamanto blanco': 'White Cargamanto Beans',
  'frijol cargamanto rojo': 'Red Cargamanto Beans',
  'frijol nima calima': 'Calima Beans (Nima brand)',
  'frijol radical': '"Radical" Beans',
  'frijol verde': 'Fresh Green (Shelling) Beans', // disambiguation: the shelled bean, not the pod — see "habichuela"
  garbanzo: 'Chickpeas',
  'harina de trigo': 'Wheat Flour',
  'harina de maiz': 'Corn Flour',
  lenteja: 'Lentils',
  'maiz amarillo duro /rocol': 'Hard Yellow Corn (Rocol variety)',
  'maiz amarillo retrillado': 'Cracked Yellow Corn',
  'maiz blanco duro': 'Hard White Corn',
  'maiz blanco retrillado': 'Cracked White Corn',
  'maiz trillado peto': 'Hulled Dried Corn ("Peto" style)',
  'maiz cascara amarillo importado': 'Yellow Corn, In-Husk (imported)',
  'maiz cascara amarillo valluno': 'Yellow Corn, In-Husk (Valle del Cauca variety)',
  'maiz cascara blanco': 'White Corn, In-Husk',
  'chocolo mazorca': 'Corn on the Cob', // not in the reference doc; La Mayorista's join target for Corabastos' "Mazorca"
  mazorca: 'Corn on the Cob',
  'manteca hidrogenada': 'Hydrogenated Lard',
  margarina: 'Margarine',
  panela: 'Panela',
  'panela pastusa': 'Panela, Pastusa style',
  'panela regional': 'Panela, Regional style',
  'panela valluna': 'Panela, Valluna style',
  'pastas alimenticias': 'Pasta',
  sal: 'Salt',
}

/** Returns { text, isTranslated } — falls back to the Spanish name with
 * isTranslated:false rather than guessing, per spec §6. */
// `overrides` are user-submitted translations fetched from the backend
// (see priceComparisonFetchers.fetchTranslationOverrides) for products the
// static dictionary above doesn't cover yet — keyed the same way, so they
// slot into the same lookup. An override wins over the static dictionary,
// letting a user correct a wrong static entry too.
export function translateProductName(nameEs, overrides = {}) {
  const key = normalizeProductName(nameEs)
  const translated = overrides[key] || PRODUCT_TRANSLATIONS[key]
  return translated ? { text: translated, isTranslated: true } : { text: nameEs, isTranslated: false }
}
