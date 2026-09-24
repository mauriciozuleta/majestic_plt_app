// The 97 HS chapters (2-digit) grouped into their 21 sections (I–XXI) — the
// WCO's own fixed nomenclature, not derived from any live Comtrade query.
// Static because it basically never changes (HS revisions happen roughly
// every 5 years and touch individual chapter contents, not the section
// structure itself) — no reason to fetch or cache this like the live trade
// figures in services/globalTradeData.js do. Order matches the official
// section sequence; each row keeps that order within its section too.
export const HS_CHAPTERS = [
  { hs_chapter: '01', chapter_name: 'Live animals', hs_section: 'I' },
  { hs_chapter: '02', chapter_name: 'Meat and edible meat offal', hs_section: 'I' },
  { hs_chapter: '03', chapter_name: 'Fish, crustaceans, molluscs and other aquatic invertebrates', hs_section: 'I' },
  { hs_chapter: '04', chapter_name: 'Dairy produce; eggs; honey; edible animal products n.e.s.', hs_section: 'I' },
  { hs_chapter: '05', chapter_name: 'Products of animal origin, n.e.s.', hs_section: 'I' },
  { hs_chapter: '06', chapter_name: 'Live trees, plants, bulbs, roots, cut flowers, ornamental foliage', hs_section: 'II' },
  { hs_chapter: '07', chapter_name: 'Edible vegetables and certain roots and tubers', hs_section: 'II' },
  { hs_chapter: '08', chapter_name: 'Edible fruit and nuts; peel of citrus fruit or melons', hs_section: 'II' },
  { hs_chapter: '09', chapter_name: 'Coffee, tea, mate and spices', hs_section: 'II' },
  { hs_chapter: '10', chapter_name: 'Cereals', hs_section: 'II' },
  { hs_chapter: '11', chapter_name: 'Milling products; malt; starches; wheat gluten', hs_section: 'II' },
  { hs_chapter: '12', chapter_name: 'Oil seeds, oleaginous fruits, misc. grains/seeds, industrial/medicinal plants', hs_section: 'II' },
  { hs_chapter: '13', chapter_name: 'Lac, gums, resins and other vegetable saps and extracts', hs_section: 'II' },
  { hs_chapter: '14', chapter_name: 'Vegetable plaiting materials; vegetable products n.e.s.', hs_section: 'II' },
  { hs_chapter: '15', chapter_name: 'Animal, vegetable or microbial fats and oils; prepared edible fats; waxes', hs_section: 'III' },
  { hs_chapter: '16', chapter_name: 'Preparations of meat, fish, crustaceans, molluscs or insects', hs_section: 'IV' },
  { hs_chapter: '17', chapter_name: 'Sugars and sugar confectionery', hs_section: 'IV' },
  { hs_chapter: '18', chapter_name: 'Cocoa and cocoa preparations', hs_section: 'IV' },
  { hs_chapter: '19', chapter_name: "Preparations of cereals, flour, starch or milk; pastrycooks' products", hs_section: 'IV' },
  { hs_chapter: '20', chapter_name: 'Preparations of vegetables, fruit, nuts or other plant parts', hs_section: 'IV' },
  { hs_chapter: '21', chapter_name: 'Miscellaneous edible preparations', hs_section: 'IV' },
  { hs_chapter: '22', chapter_name: 'Beverages, spirits and vinegar', hs_section: 'IV' },
  { hs_chapter: '23', chapter_name: 'Residues and waste from the food industries; prepared animal fodder', hs_section: 'IV' },
  { hs_chapter: '24', chapter_name: 'Tobacco and manufactured tobacco substitutes', hs_section: 'IV' },
  { hs_chapter: '25', chapter_name: 'Salt; sulphur; earths and stone; plastering materials, lime and cement', hs_section: 'V' },
  { hs_chapter: '26', chapter_name: 'Ores, slag and ash', hs_section: 'V' },
  {
    hs_chapter: '27',
    chapter_name: 'Mineral fuels, mineral oils and products of their distillation; bituminous substances; mineral waxes',
    hs_section: 'V',
  },
  { hs_chapter: '28', chapter_name: 'Inorganic chemicals', hs_section: 'VI' },
  { hs_chapter: '29', chapter_name: 'Organic chemicals', hs_section: 'VI' },
  { hs_chapter: '30', chapter_name: 'Pharmaceutical products', hs_section: 'VI' },
  { hs_chapter: '31', chapter_name: 'Fertilisers', hs_section: 'VI' },
  { hs_chapter: '32', chapter_name: 'Tanning/dyeing extracts; dyes, pigments, paints, varnishes, inks', hs_section: 'VI' },
  { hs_chapter: '33', chapter_name: 'Essential oils, perfumery, cosmetics, toilet preparations', hs_section: 'VI' },
  { hs_chapter: '34', chapter_name: 'Soap, washing preparations, lubricants, waxes, candles, dental preparations', hs_section: 'VI' },
  { hs_chapter: '35', chapter_name: 'Albuminoidal substances; modified starches; glues; enzymes', hs_section: 'VI' },
  { hs_chapter: '36', chapter_name: 'Explosives; pyrotechnics; matches; pyrophoric alloys', hs_section: 'VI' },
  { hs_chapter: '37', chapter_name: 'Photographic or cinematographic goods', hs_section: 'VI' },
  { hs_chapter: '38', chapter_name: 'Miscellaneous chemical products', hs_section: 'VI' },
  { hs_chapter: '39', chapter_name: 'Plastics and articles thereof', hs_section: 'VII' },
  { hs_chapter: '40', chapter_name: 'Rubber and articles thereof', hs_section: 'VII' },
  { hs_chapter: '41', chapter_name: 'Raw hides and skins (other than furskins) and leather', hs_section: 'VIII' },
  { hs_chapter: '42', chapter_name: 'Articles of leather; saddlery; travel goods; handbags', hs_section: 'VIII' },
  { hs_chapter: '43', chapter_name: 'Furskins and artificial fur; manufactures thereof', hs_section: 'VIII' },
  { hs_chapter: '44', chapter_name: 'Wood and articles of wood; wood charcoal', hs_section: 'IX' },
  { hs_chapter: '45', chapter_name: 'Cork and articles of cork', hs_section: 'IX' },
  {
    hs_chapter: '46',
    chapter_name: 'Manufactures of straw, esparto, other plaiting materials; basketware, wickerwork',
    hs_section: 'IX',
  },
  { hs_chapter: '47', chapter_name: 'Pulp of wood/other fibrous cellulosic material; recovered paper', hs_section: 'X' },
  { hs_chapter: '48', chapter_name: 'Paper and paperboard; articles thereof', hs_section: 'X' },
  { hs_chapter: '49', chapter_name: 'Printed books, newspapers, pictures; manuscripts, typescripts, plans', hs_section: 'X' },
  { hs_chapter: '50', chapter_name: 'Silk', hs_section: 'XI' },
  { hs_chapter: '51', chapter_name: 'Wool, fine or coarse animal hair; horsehair yarn and fabric', hs_section: 'XI' },
  { hs_chapter: '52', chapter_name: 'Cotton', hs_section: 'XI' },
  { hs_chapter: '53', chapter_name: 'Other vegetable textile fibres; paper yarn and woven fabrics', hs_section: 'XI' },
  { hs_chapter: '54', chapter_name: 'Man-made filaments; strip and the like of man-made textile materials', hs_section: 'XI' },
  { hs_chapter: '55', chapter_name: 'Man-made staple fibres', hs_section: 'XI' },
  { hs_chapter: '56', chapter_name: 'Wadding, felt, nonwovens; special yarns; twine, cordage, ropes, cables', hs_section: 'XI' },
  { hs_chapter: '57', chapter_name: 'Carpets and other textile floor coverings', hs_section: 'XI' },
  {
    hs_chapter: '58',
    chapter_name: 'Special woven fabrics; tufted textile fabrics; lace; tapestries; trimmings; embroidery',
    hs_section: 'XI',
  },
  { hs_chapter: '59', chapter_name: 'Impregnated, coated, covered or laminated textile fabrics', hs_section: 'XI' },
  { hs_chapter: '60', chapter_name: 'Knitted or crocheted fabrics', hs_section: 'XI' },
  { hs_chapter: '61', chapter_name: 'Articles of apparel and clothing accessories, knitted or crocheted', hs_section: 'XI' },
  { hs_chapter: '62', chapter_name: 'Articles of apparel and clothing accessories, not knitted or crocheted', hs_section: 'XI' },
  { hs_chapter: '63', chapter_name: 'Other made-up textile articles; sets; worn clothing; rags', hs_section: 'XI' },
  { hs_chapter: '64', chapter_name: 'Footwear, gaiters and the like; parts thereof', hs_section: 'XII' },
  { hs_chapter: '65', chapter_name: 'Headgear and parts thereof', hs_section: 'XII' },
  { hs_chapter: '66', chapter_name: 'Umbrellas, walking sticks, whips, riding-crops; parts thereof', hs_section: 'XII' },
  { hs_chapter: '67', chapter_name: 'Prepared feathers/down; artificial flowers; human hair articles', hs_section: 'XII' },
  {
    hs_chapter: '68',
    chapter_name: 'Articles of stone, plaster, cement, asbestos, mica or similar materials',
    hs_section: 'XIII',
  },
  { hs_chapter: '69', chapter_name: 'Ceramic products', hs_section: 'XIII' },
  { hs_chapter: '70', chapter_name: 'Glass and glassware', hs_section: 'XIII' },
  {
    hs_chapter: '71',
    chapter_name: 'Natural/cultured pearls, precious/semi-precious stones, precious metals, jewellery, coin',
    hs_section: 'XIV',
  },
  { hs_chapter: '72', chapter_name: 'Iron and steel', hs_section: 'XV' },
  { hs_chapter: '73', chapter_name: 'Articles of iron or steel', hs_section: 'XV' },
  { hs_chapter: '74', chapter_name: 'Copper and articles thereof', hs_section: 'XV' },
  { hs_chapter: '75', chapter_name: 'Nickel and articles thereof', hs_section: 'XV' },
  { hs_chapter: '76', chapter_name: 'Aluminium and articles thereof', hs_section: 'XV' },
  { hs_chapter: '77', chapter_name: '(Reserved for possible future use)', hs_section: 'XV' },
  { hs_chapter: '78', chapter_name: 'Lead and articles thereof', hs_section: 'XV' },
  { hs_chapter: '79', chapter_name: 'Zinc and articles thereof', hs_section: 'XV' },
  { hs_chapter: '80', chapter_name: 'Tin and articles thereof', hs_section: 'XV' },
  { hs_chapter: '81', chapter_name: 'Other base metals; cermets; articles thereof', hs_section: 'XV' },
  { hs_chapter: '82', chapter_name: 'Tools, implements, cutlery, spoons and forks, of base metal', hs_section: 'XV' },
  { hs_chapter: '83', chapter_name: 'Miscellaneous articles of base metal', hs_section: 'XV' },
  {
    hs_chapter: '84',
    chapter_name: 'Nuclear reactors, boilers, machinery and mechanical appliances; parts thereof',
    hs_section: 'XVI',
  },
  { hs_chapter: '85', chapter_name: 'Electrical machinery/equipment; sound/TV recorders/reproducers; parts', hs_section: 'XVI' },
  {
    hs_chapter: '86',
    chapter_name: 'Railway/tramway locomotives, rolling stock; track fixtures/fittings',
    hs_section: 'XVII',
  },
  { hs_chapter: '87', chapter_name: 'Vehicles other than railway/tramway rolling stock; parts and accessories', hs_section: 'XVII' },
  { hs_chapter: '88', chapter_name: 'Aircraft, spacecraft, and parts thereof', hs_section: 'XVII' },
  { hs_chapter: '89', chapter_name: 'Ships, boats and floating structures', hs_section: 'XVII' },
  {
    hs_chapter: '90',
    chapter_name: 'Optical, photographic, cinematographic, measuring, checking, precision, medical/surgical instruments',
    hs_section: 'XVIII',
  },
  { hs_chapter: '91', chapter_name: 'Clocks and watches and parts thereof', hs_section: 'XVIII' },
  { hs_chapter: '92', chapter_name: 'Musical instruments; parts and accessories thereof', hs_section: 'XVIII' },
  { hs_chapter: '93', chapter_name: 'Arms and ammunition; parts and accessories thereof', hs_section: 'XIX' },
  {
    hs_chapter: '94',
    chapter_name: 'Furniture; bedding, mattresses, lamps and lighting fittings; prefabricated buildings',
    hs_section: 'XX',
  },
  { hs_chapter: '95', chapter_name: 'Toys, games and sports requisites; parts and accessories', hs_section: 'XX' },
  { hs_chapter: '96', chapter_name: 'Miscellaneous manufactured articles', hs_section: 'XX' },
  { hs_chapter: '97', chapter_name: "Works of art, collectors' pieces and antiques", hs_section: 'XXI' },
]

// One entry per section, in order, derived from HS_CHAPTERS itself rather
// than hand-maintained separately — {section, chapters: [...]}, plus the
// chapter-number range each section spans (e.g. "01–05") since the CSV
// carries no section title, only the roman numeral.
export const HS_SECTIONS = HS_CHAPTERS.reduce((sections, row) => {
  const last = sections[sections.length - 1]
  if (last && last.section === row.hs_section) {
    last.chapters.push(row)
  } else {
    sections.push({ section: row.hs_section, chapters: [row] })
  }
  return sections
}, [])
