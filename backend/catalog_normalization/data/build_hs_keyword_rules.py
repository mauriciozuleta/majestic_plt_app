"""Builds data/hs_keyword_rules.json from the table below (run: python backend/catalog_normalization/data/build_hs_keyword_rules.py).

The table is the editable source: each row is (id, words, code, frozen_code, confidence, note, extra `not` words). `words` are plain words or phrases (matched as whole words, plural
optional, case-insensitive) in the product's English name; the first row that matches wins, so specific rows come before general ones ("sweet potato" before "potato"). `code` is the
6-digit HS code of the FRESH / chilled product; `frozen_code` the one when the name or the store category says frozen (None: a frozen product is not suggested at all: frozen produce
is another heading and outside the catalog scope). Codes were checked against Comtrade's HS reference (tests) and, where unsure, against HMRC's Trade Tariff search."""

import json
from pathlib import Path

# confidence: 'high' = the name always means this commodity; 'medium' = the heading is certain but the subheading depends on a detail the name may not give (species, cut,
# fresh vs frozen) or the commodity is classed differently by some tariffs: a person should look.
H, M = 'high', 'medium'

ROWS = [
    # ---------------------------------------------------------------- roots, tubers and bulbs (0703, 0706, 0714)
    ('sweet_potato', ['sweet potato', 'sweet potatoes'], '071420', None, H, 'Sweet potatoes, fresh', []),
    ('yam', ['yam', 'yams', 'yampi', 'yampee', 'negro yam', 'lucea yam'], '071430', None, H, 'Yams, fresh', []),
    ('cassava', ['cassava', 'yuca', 'manioc', 'tapioca root', 'bitter cassava', 'sweet cassava'], '071410', None, H, 'Cassava, fresh', ['flour', 'starch', 'bread', 'chips']),
    ('taro', ['dasheen', 'eddo', 'eddoes', 'eddoe', 'taro', 'malanga'], '071440', None, M, 'Taro (dasheen, eddo), fresh', []),
    ('yautia', ['coco', 'cocoyam', 'yautia', 'tannia', 'tania'], '071450', None, M, 'Yautia (cocoyam), fresh', ['coconut', 'cocoa', 'cocoa powder']),
    ('potato', ['irish potato', 'potato', 'russet', 'idaho', 'white potato'], '070190', None, H, 'Potatoes, fresh', ['sweet', 'chips', 'fries', 'mashed', 'instant', 'flakes', 'salad']),
    ('garlic', ['garlic'], '070320', None, H, 'Garlic, fresh', ['powder', 'salt', 'bread', 'sauce', 'minced', 'paste', 'granules']),
    ('onion', ['onion', 'shallot'], '070310', None, H, 'Onions and shallots, fresh', ['green', 'spring', 'ring', 'rings', 'powder', 'soup', 'dip', 'crispy', 'fried']),
    ('scallion', ['scallion', 'escallion', 'green onion', 'spring onion', 'leek', 'chive', 'chives'], '070390', None, M, 'Leeks and other alliaceous vegetables (scallions, chives), fresh', ['dip', 'cream cheese']),
    ('carrot', ['carrot'], '070610', None, H, 'Carrots and turnips, fresh', ['cake', 'juice', 'baby food']),
    ('beet_radish', ['beetroot', 'beet', 'radish', 'turnip', 'salsify', 'celeriac', 'celery root'], '070690', None, H, 'Salad beetroot, radishes and similar roots, fresh', ['pickled', 'sugar']),
    # ---------------------------------------------------------------- vegetables (0702, 0704, 0705, 0707 - 0709)
    ('tomato', ['tomato', 'cherry tomato', 'plum tomato', 'roma'], '070200', None, H, 'Tomatoes, fresh', ['sauce', 'paste', 'ketchup', 'juice', 'soup', 'sun dried', 'tree tomato']),
    ('cauliflower_broccoli', ['cauliflower', 'broccoli', 'broccolini'], '070410', None, H, 'Cauliflowers and headed broccoli, fresh', ['soup']),
    ('brussels', ['brussels sprout', 'brussel sprout'], '070420', None, H, 'Brussels sprouts, fresh', []),
    ('cabbage_family', ['cabbage', 'kale', 'pak choi', 'bok choy', 'pak choy', 'kohlrabi', 'collard', 'collards', 'chinese cabbage', 'savoy'], '070490', None, H, 'Cabbages, kale, pak choi and similar brassicas, fresh', ['slaw', 'sauerkraut', 'kimchi', 'roll', 'rolls']),
    ('lettuce_head', ['iceberg', 'head lettuce', 'butter lettuce', 'butterhead'], '070511', None, M, 'Cabbage lettuce (head), fresh', []),
    ('lettuce', ['lettuce', 'romaine', 'caesar kit', 'salad mix', 'spring mix', 'mesclun'], '070519', None, M, 'Lettuce (other), fresh', ['dressing', 'wrap', 'wraps']),
    ('chicory', ['chicory', 'endive', 'radicchio', 'frisee'], '070529', None, M, 'Chicory and endive, fresh', ['coffee']),
    ('cucumber', ['cucumber', 'gherkin'], '070700', None, H, 'Cucumbers and gherkins, fresh', ['pickle', 'pickled', 'sea cucumber', 'juice']),
    ('peas', ['green pea', 'garden pea', 'snow pea', 'sugar snap', 'snap pea', 'peas in pod', 'fresh peas'], '070810', None, M, 'Peas, fresh', ['split', 'dried', 'pigeon', 'black eye', 'blackeye', 'chick']),
    ('beans', ['green bean', 'string bean', 'french bean', 'long bean', 'wax bean', 'snap bean', 'haricot vert', 'bodi', 'bora'], '070820', None, M, 'Green beans, fresh', ['baked', 'canned', 'dried']),
    ('celery', ['celery'], '070940', None, H, 'Celery, fresh', ['salt', 'seed', 'celeriac', 'celery root']),
    ('mushroom_agaricus', ['mushroom', 'button mushroom', 'baby bella', 'portobello', 'cremini'], '070951', None, M, 'Mushrooms (Agaricus), fresh', ['soup', 'sauce', 'dried', 'canned']),
    ('asparagus', ['asparagus'], '070920', None, H, 'Asparagus, fresh', ['canned', 'soup']),
    ('spinach', ['spinach'], '070970', None, H, 'Spinach, fresh', ['dip', 'artichoke']),
    ('eggplant', ['eggplant', 'aubergine', 'melongene', 'baigan', 'brinjal'], '070930', None, H, 'Aubergines (eggplants), fresh', []),
    ('capsicum', ['pepper orange', 'pepper red', 'pepper yellow', 'pepper green', 'pepper mixed', 'sweet pepper', 'bell pepper', 'hot pepper', 'seasoning pepper', 'scotch bonnet', 'habanero', 'jalapeno', 'capsicum', 'pimento', 'pimiento', 'chili', 'chilli', 'chile', 'wiri wiri',
                  'cayenne', 'banana pepper', 'cubanelle', 'poblano', 'serrano', 'caribbean red', 'green pepper', 'red pepper', 'yellow pepper', 'orange pepper', 'peppers'], '070960', None, H,
     'Fruits of the genus Capsicum or Pimenta (peppers), fresh', ['black', 'ground', 'powder', 'sauce', 'flake', 'flakes', 'dried', 'crushed', 'roasted', 'stuffed', 'jar', 'pickled', 'seasoning salt', 'jack']),
    ('pumpkin_squash', ['pumpkin', 'squash', 'calabaza', 'butternut', 'courgette', 'zucchini', 'marrow', 'chayote', 'christophene', 'cho cho', 'cucuzza', 'bottle gourd', 'gourd'], '070993', None, M,
     'Pumpkins, squash and gourds, fresh', ['seed', 'seeds', 'pie', 'puree', 'canned', 'spice']),
    ('sweet_corn', ['sweet corn', 'corn on the cob', 'corn on cob'], '070999', None, M, 'Sweet corn, fresh (heading 0709, other vegetables)', ['canned', 'cream', 'chips', 'frozen', 'oil', 'starch']),
    ('okra', ['okra', 'ochro', 'ladies finger', 'ladies fingers'], '070999', None, H, 'Okra, fresh (heading 0709, other vegetables)', []),
    ('callaloo', ['callaloo', 'caraillie', 'carailli', 'carailie', 'caraili', 'carailly', 'bhaji', 'amaranth', 'dasheen bush', 'taro leaves', 'spinach bush', 'pak choi bush'], '070999', None, M, 'Callaloo and other leafy vegetables, fresh (heading 0709, other vegetables)', ['canned']),
    ('rocket_herbs_veg', ['arugula', 'rocket', 'parsley', 'cilantro', 'culantro', 'chadon beni', 'coriander leaf', 'watercress', 'cress', 'chard', 'swiss chard', 'acelga'], '070999', None, M,
     'Parsley, cilantro, rocket and similar fresh leafy vegetables (heading 0709, other vegetables)', ['seed', 'seeds', 'ground', 'powder', 'dried']),
    ('artichoke', ['artichoke'], '070991', None, M, 'Globe artichokes, fresh', ['dip', 'canned', 'jar', 'marinated']),
    ('olives_fresh', ['fresh olive', 'fresh olives'], '070992', None, M, 'Olives, fresh', []),
    ('breadfruit_veg', ['breadfruit'], '081090', None, M, 'Breadfruit and other edible tropical fruit, fresh', []),
    # ---------------------------------------------------------------- fruit (0801 - 0810)
    ('plantain', ['plantain', 'green banana', 'cooking banana', 'bluggoe'], '080310', None, H, 'Plantains, fresh', ['chips', 'flour']),
    ('banana', ['banana', 'bananas', 'ripe banana', 'fig banana', 'finger banana'], '080390', None, H, 'Bananas, fresh', ['chips', 'bread', 'pepper', 'passion', 'passionfruit', 'passion fruit', 'split', 'muffin', 'yogurt', 'gulupa', 'curuba']),
    ('coconut', ['coconut', 'dry coconut', 'water coconut', 'jelly coconut'], '080119', None, M, 'Coconuts, fresh (other)', ['milk', 'water', 'oil', 'cream', 'shredded', 'sliced', 'desiccated', 'flour', 'sugar', 'bread']),
    ('pineapple', ['pineapple', 'pineapples'], '080430', None, H, 'Pineapples, fresh', ['juice', 'tidbits', 'chunks', 'rings', 'canned', 'cream cheese', 'crushed', 'upside', 'feijoa', 'guava']),
    ('avocado', ['avocado', 'pear avocado', 'hass'], '080440', None, H, 'Avocados, fresh', ['oil', 'dip', 'guacamole', 'toast']),
    ('guava_mango', ['guava', 'mango', 'mangoes', 'mangosteen', 'julie mango', 'tommy atkins', 'kent mango', 'keitt'], '080450', None, H, 'Guavas, mangoes and mangosteens, fresh', ['juice', 'pulp', 'jam', 'jelly', 'chutney', 'dried', 'nectar', 'passion']),
    ('dates_figs', ['date', 'dates', 'fig', 'figs'], '080410', None, M, 'Dates, fresh or dried', ['stuffed', 'paste', 'chopped', 'syrup']),
    ('orange', ['orange', 'navel', 'valencia', 'sweet orange'], '080510', None, M, 'Oranges, fresh', ['juice', 'marmalade', 'bitter', 'peel', 'chicken', 'sauce', 'drink', 'soda', 'flavour', 'flavor']),
    ('mandarin', ['mandarin', 'tangerine', 'satsuma', 'tangelo', 'ortanique', 'ugli'], '080529', None, M, 'Mandarins, tangerines and hybrids, fresh', ['juice', 'canned']),
    ('clementine', ['clementine'], '080522', None, M, 'Clementines, fresh', ['juice']),
    ('grapefruit', ['grapefruit', 'pomelo', 'shaddock'], '080540', None, H, 'Grapefruit and pomelos, fresh', ['juice']),
    ('lemon_lime', ['lemon', 'lime', 'limes', 'key lime', 'persian lime'], '080550', None, H, 'Lemons and limes, fresh', ['juice', 'cordial', 'pie', 'soda', 'drink', 'dressing', 'pepper', 'seasoning', 'sherbet', 'lemonade', 'grass', 'lemongrass']),
    ('melon_water', ['watermelon'], '080711', None, H, 'Watermelons, fresh', ['juice', 'drink', 'candy']),
    ('melon_other', ['cantaloupe', 'honeydew', 'honey dew', 'melon', 'rock melon', 'galia', 'musk melon', 'muskmelon'], '080719', None, H, 'Melons (other than watermelons), fresh', ['juice', 'drink', 'bitter']),
    ('papaya', ['papaya', 'paw paw', 'pawpaw', 'papaw', 'melona'], '080720', None, H, 'Papayas (papaws), fresh', ['juice']),
    ('grapes', ['grape', 'grapes', 'red globe', 'thompson'], '080610', None, H, 'Grapes, fresh', ['juice', 'wine', 'jelly', 'jam', 'seed oil', 'raisin', 'dried', 'grapefruit', 'tomato']),
    ('apple', ['apple', 'apples', 'gala', 'granny smith', 'fuji', 'red delicious', 'golden delicious', 'honeycrisp', 'pink lady'], '080810', None, H, 'Apples, fresh', ['juice', 'sauce', 'cider', 'pie', 'custard', 'sugar apple', 'pineapple', 'star apple', 'custard apple', 'rose apple', 'june plum', 'jam', 'vinegar', 'butter', 'chips', 'crisp', 'sparkling', 'candy', 'caramel', 'cinnamon']),
    ('pear', ['pear', 'pears', 'anjou', 'bartlett', 'bosc', 'comice'], '080830', None, H, 'Pears, fresh', ['juice', 'avocado', 'prickly', 'canned', 'cider']),
    ('apricot_cherry', ['apricot'], '080910', None, H, 'Apricots, fresh', ['dried', 'jam', 'juice']),
    ('cherry', ['cherry', 'cherries'], '080929', None, M, 'Cherries, fresh', ['tomato', 'juice', 'cola', 'pie', 'jam', 'dried', 'vanilla', 'flavour', 'flavor', 'drink', 'soda', 'candy']),
    ('peach', ['peach', 'peaches', 'nectarine'], '080930', None, H, 'Peaches and nectarines, fresh', ['juice', 'canned', 'jam', 'tea', 'drink']),
    ('plum', ['plum', 'plums', 'prune'], '080940', None, M, 'Plums and sloes, fresh', ['sauce', 'juice', 'tomato', 'dried', 'jam', 'june plum', 'jamaican plum', 'cake']),
    ('strawberry', ['strawberry', 'strawberries'], '081010', None, H, 'Strawberries, fresh', ['jam', 'yogurt', 'juice', 'drink', 'flavour', 'flavor', 'sauce', 'syrup', 'milk', 'dried', 'ice cream']),
    ('raspberry_blackberry', ['raspberry', 'raspberries', 'blackberry', 'blackberries', 'mulberry', 'loganberry'], '081020', None, H, 'Raspberries, blackberries and mulberries, fresh', ['jam', 'yogurt', 'juice', 'drink', 'flavour', 'flavor', 'sauce', 'syrup', 'dried', 'vinegar']),
    ('blueberry', ['blueberry', 'blueberries', 'bilberry', 'cranberry', 'cranberries'], '081040', None, M, 'Blueberries, cranberries and similar berries, fresh', ['juice', 'jam', 'yogurt', 'muffin', 'drink', 'flavour', 'flavor', 'dried', 'sauce', 'sparkling']),
    ('kiwi', ['kiwi', 'kiwifruit', 'kiwi fruit'], '081050', None, H, 'Kiwifruit, fresh', ['juice', 'drink']),
    ('other_tropical_fruit', ['passion fruit', 'passionfruit', 'granadilla', 'gulupa', 'soursop', 'sour sop', 'pomegranate', 'tamarind', 'sugar apple', 'sweetsop', 'custard apple', 'star apple', 'carambola', 'starfruit',
                              'star fruit', 'dragon fruit', 'pitaya', 'lychee', 'litchi', 'rambutan', 'longan', 'ackee', 'guinep', 'genip', 'june plum', 'pommecythere', 'ambarella', 'sapodilla', 'sapote',
                              'jackfruit', 'durian', 'persimmon', 'physalis', 'cape gooseberry', 'gooseberry', 'otaheite', 'noni', 'jujube', 'fruit mix', 'tree tomato', 'tamarillo', 'lulo', 'feijoa', 'cherimoya',
                              'chironja', 'uchuva', 'pitahaya', 'maracuya', 'curuba', 'mamoncillo', 'zapote', 'nispero', 'borojo', 'caimito', 'mamey', 'sorrel fruit'], '081090', None, M,
     'Other fresh fruit (passion fruit, soursop, tamarind, ackee, lychee and similar), fresh', ['juice', 'pulp', 'jam', 'drink', 'nectar', 'concentrate', 'flavour', 'flavor', 'sparkling', 'syrup', 'candy', 'wine']),
    # ---------------------------------------------------------------- roots used as spices, fresh herbs (chapter 09 and 12)
    ('ginger', ['ginger'], '091011', None, M, 'Ginger, neither crushed nor ground (fresh root)', ['ale', 'beer', 'powder', 'ground', 'snap', 'bread', 'tea', 'candy', 'syrup', 'juice', 'chews', 'cookies']),
    ('turmeric', ['turmeric'], '091030', None, M, 'Turmeric (curcuma)', ['powder', 'ground', 'capsule', 'tea', 'latte']),
    ('thyme_bay', ['thyme', 'bay leaf', 'bay leaves', 'marjoram', 'oregano'], '091099', None, M, 'Thyme, bay leaves and similar herbs (heading 0910, other spices)', ['ground', 'powder', 'seasoning', 'dried', 'rubbed']),
    ('basil_mint', ['basil', 'mint', 'rosemary', 'sage', 'tarragon', 'dill', 'lemongrass', 'lemon grass', 'fever grass', 'sorrel leaves', 'moringa'], '121190', None, M,
     'Basil, mint, rosemary and similar plants (heading 1211, plants used in pharmacy or perfumery; some tariffs class fresh culinary herbs elsewhere)', ['tea', 'oil', 'pesto', 'sauce', 'dried', 'mojito', 'candy', 'chocolate', 'gum', 'toothpaste']),
    # ---------------------------------------------------------------- eggs and cheese (0407, 0406)
    ('eggs', ['egg', 'eggs', 'white eggs', 'brown eggs', 'dozen eggs', 'hen eggs'], '040721', None, M, 'Hen eggs in shell, fresh', ['plant', 'noodle', 'noodles', 'roll', 'rolls', 'nog', 'salad', 'mayo', 'liquid', 'whites', 'powder', 'substitute', 'beater', 'beaters', 'sandwich', 'sausage']),
    ('cheese_grated', ['grated cheese', 'shredded cheese', 'parmesan', 'grated parmesan', 'powdered cheese'], '040620', None, M, 'Cheese, grated or powdered', ['pizza', 'snack', 'puffs']),
    ('cheese_fresh', ['cream cheese', 'cottage cheese', 'mozzarella', 'ricotta', 'feta', 'halloumi', 'paneer', 'queso fresco', 'philadelphia', 'cream cheeses', 'mascarpone', 'cheese curd', 'cheese curds', 'burrata', 'fromage frais'], '040610', None, M,
     'Fresh cheese (cream cheese, cottage cheese, mozzarella, feta ...), unripened', ['pizza', 'snack', 'bagel', 'dip', 'cake', 'cracker', 'puff']),
    ('cheese_processed', ['processed cheese', 'cheese slice', 'cheese slices', 'singles', 'cheese spread', 'cheese wiz', 'velveeta', 'american cheese', 'cheese food'], '040630', None, M, 'Processed cheese', ['pizza', 'snack']),
    ('cheese_blue', ['blue cheese', 'roquefort', 'gorgonzola', 'stilton', 'danish blue'], '040640', None, M, 'Blue-veined cheese', ['dressing', 'dip']),
    ('cheese_other', ['cheese', 'cheddar', 'gouda', 'edam', 'swiss', 'brie', 'camembert', 'provolone', 'colby', 'monterey', 'pepper jack', 'havarti', 'gruyere', 'emmental', 'jarlsberg', 'manchego', 'queso',
                      'fromage', 'romano', 'asiago', 'muenster', 'edam'], '040690', None, M, 'Other cheese', ['pizza', 'snack', 'puffs', 'sauce', 'dip', 'cake', 'macaroni', 'mac', 'sandwich', 'noodles', 'bagel', 'popcorn', 'curls', 'balls', 'sticks', 'flavour', 'flavor', 'chips', 'chard', 'cheese crackers', 'cheese cracker']),
    # ---------------------------------------------------------------- meat (chapter 02): fresh code, frozen code
    ('chicken_whole', ['whole chicken', 'chicken whole', 'whole fryer', 'whole broiler', 'whole bird', 'best dressed', 'roasting chicken'], '020711', '020712', M, 'Whole chickens, not cut in pieces', ['nugget', 'nuggets', 'soup', 'flavour', 'flavor', 'seasoned', 'curry', 'jerk', 'sausage']),
    ('chicken_cuts', ['chicken', 'chickens', 'wings', 'drumstick', 'drumsticks', 'thigh', 'thighs', 'leg quarter', 'leg quarters', 'gizzard', 'gizzards', 'chicken fryer', 'broiler', 'broilers'], '020713', '020714', M, 'Chicken cuts and offal',
     ['nugget', 'nuggets', 'patty', 'patties', 'soup', 'flavour', 'flavor', 'seasoning', 'bouillon', 'curry', 'jerk', 'sausage', 'franks', 'frank', 'salami', 'ham', 'bacon', 'deli', 'roll', 'slices', 'stew',
      'meal', 'tikka', 'masala', 'strips', 'breaded', 'cooked', 'smoked', 'cat food', 'dog food', 'fried', 'popcorn', 'back bacon', 'broth', 'stock', 'noodle', 'noodles', 'pie', 'pot pie', 'sandwich', 'burger', 'beef', 'pork', 'turkey', 'hot dogs', 'hot dog', 'tenders', 'tender', 'chubb']),
    ('turkey_cuts', ['turkey', 'turkey wings', 'turkey neck', 'turkey legs', 'turkey breast', 'turkey drumstick'], '020726', '020727', M, 'Turkey cuts and offal', ['ham', 'bacon', 'sausage', 'franks', 'frank', 'deli', 'loaf', 'slices', 'salami', 'breakfast', 'burger', 'patty', 'strips', 'smoked', 'cooked', 'pepperoni', 'bologna', 'roast beef', 'jerky', 'nuggets', 'soup', 'stock', 'roasted', 'baked', 'oven', 'golden brown']),
    ('beef_offal', ['beef offal', 'offal general', 'beef liver', 'beef tongue', 'beef heart', 'beef kidney', 'tripe', 'cow heel', 'beef tripe', 'ox tail meat', 'cow foot'], '020610', '020621', M, 'Edible offal of bovine animals', []),
    ('beef_bone_in', ['short rib', 'short ribs', 'beef ribs', 'oxtail', 'shank', 'beef shank', 'bone in beef', 'bone-in beef', 'soup bone', 'soup bones', 'beef bones'], '020120', '020220', M, 'Beef cuts with bone in', ['broth', 'stock', 'bouillon', 'dog', 'lamb', 'pork', 'chicken', 'turkey', 'goat', 'veal']),
    ('beef_boneless', ['beef', 'steak', 'ribeye', 'rib eye', 'sirloin', 'tenderloin', 'strip loin', 'flank', 'brisket', 'chuck', 'round roast', 'eye round', 'ground beef', 'minced beef', 'mince beef', 'stew beef',
                       'beef cubes', 'rump', 'beef stew', 'skirt', 'tri tip', 'tri-tip', 'angus', 'filet mignon', 'london broil', 'new york strip', 't-bone', 'porterhouse'], '020130', '020230', M, 'Boneless beef cuts and minced beef',
     ['soup', 'broth', 'stock', 'bouillon', 'flavour', 'flavor', 'noodle', 'noodles', 'seasoning', 'jerky', 'franks', 'frank', 'sausage', 'burger', 'burgers', 'patty', 'patties', 'meatball', 'meatballs', 'canned', 'corned',
      'deli', 'sliced', 'slices', 'bacon', 'ham', 'salami', 'pepperoni', 'dog food', 'cat food', 'pot pie', 'pie', 'stew meal', 'dinner', 'bites', 'cooked', 'smoked', 'tikka', 'curry',
      'pork', 'chicken', 'turkey', 'lamb', 'tuna', 'salmon', 'fish', 'swordfish', 'shark', 'halibut', 'mahi', 'tilapia', 'goat', 'veal']),
    ('pork_hams_fresh', ['pork leg', 'fresh ham', 'pork shoulder', 'pork shoulders', 'pork butt', 'picnic shoulder'], '020312', '020322', M, 'Pork hams and shoulders, fresh', ['smoked', 'cooked', 'cured']),
    ('beef_salted', ['salted beef', 'salt beef', 'pickled beef', 'boneless salt beef', 'brisket salted', 'salted brisket'], '021020', '021020', M, 'Beef, salted, in brine, dried or smoked', ['canned', 'corned beef canned', 'sauce']),
    ('pork_salted', ['salted pig tail', 'salted pig tails', 'pickled pig tail', 'cured pig tail', 'salted pork', 'salt pork', 'pickled pork', 'corned pork', 'salted pork tail', 'salted pork tails', 'salted pigtail', 'smoked pork',
                     'smoked pig tail', 'smoked pork bones', 'smoked pork neck', 'salted pig feet', 'pickled pig feet', 'pickled pigtail', 'pickled pigtails', 'salted pigtails'], '021019', '021019', M, 'Pork, salted, in brine, dried or smoked (other than hams and bellies)', ['sausage', 'ham', 'bacon', 'canned']),
    ('pork_offal', ['pig tail', 'pigtail', 'pig tails', 'pigtails', 'pig feet', 'pig foot', 'pigs feet', 'trotters', 'pig snout', 'pig ear', 'pig ears', 'pork liver', 'pork kidney', 'pork tail', 'pork tails', 'pork neck bones',
                    'pork bones', 'pork skin', 'pork rind', 'pork belly offal'], '020630', '020649', M, 'Edible offal of swine (tails, feet, ears), fresh or chilled', ['rinds', 'chicharron', 'snack', 'canned']),
    ('pork_cuts', ['pork', 'pork chop', 'pork chops', 'pork loin', 'pork ribs', 'spare ribs', 'spareribs', 'baby back ribs', 'pork belly', 'pork tenderloin', 'ground pork', 'minced pork', 'pork cubes', 'pork steak',
                   'pork sirloin', 'pork flap', 'pork strips', 'pork roast'], '020319', '020329', M, 'Other cuts of pork, fresh or chilled',
     ['sausage', 'franks', 'frank', 'ham', 'bacon', 'deli', 'salami', 'pepperoni', 'canned', 'beans', 'soup', 'broth', 'stock', 'bouillon', 'flavour', 'flavor', 'seasoning', 'rinds', 'dumpling', 'dumplings', 'bun', 'buns',
      'sauce', 'noodle', 'noodles', 'pie', 'cooked', 'smoked', 'meatball', 'meatballs', 'patty', 'patties', 'luncheon', 'jerky', 'dog food', 'cat food']),
    ('lamb_cuts', ['lamb', 'lamb chop', 'lamb chops', 'lamb leg', 'lamb shoulder', 'lamb ribs', 'lamb stew', 'lamb loin', 'rack of lamb', 'minced lamb', 'ground lamb', 'mutton', 'lamb shank'], '020422', '020442', M,
     'Lamb and mutton cuts', ['soup', 'broth', 'stock', 'flavour', 'flavor', 'seasoning', 'curry', 'sausage', 'canned', 'dog food', 'cat food', 'gyro']),
    ('goat', ['goat', 'curry goat', 'goat meat', 'chevon', 'cabrito'], '020450', '020450', M, 'Goat meat', ['curry sauce', 'cheese', 'milk', 'soap']),
    ('rabbit_other_meat', ['rabbit', 'duck', 'duckling', 'goose', 'quail', 'guinea fowl', 'pigeon meat'], '020745', '020745', M, 'Other poultry meat (duck, goose, guinea fowl) or rabbit meat (check the exact heading)', ['sauce', 'soup', 'pate']),
    # ---------------------------------------------------------------- cured and cooked meat that needs the cold chain (0210, 1601, 1602)
    ('bacon', ['bacon', 'pancetta', 'streaky', 'side bacon', 'back bacon', 'pork belly bacon'], '021012', '021012', M, 'Bacon (bellies, smoked or salted)', ['bits', 'bit', 'bacon bits', 'flavour', 'flavor', 'dressing', 'cheese', 'jam', 'seasoning', 'burger sauce', 'turkey', 'chicken', 'beef']),
    ('ham_cured', ['ham', 'smoked ham', 'leg ham', 'black forest ham', 'gammon', 'prosciutto', 'serrano ham', 'jambon', 'picnic ham', 'cured ham', 'honey ham', 'virginia ham', 'country ham'], '021011', '021011', M, 'Hams, shoulders and cuts, salted, in brine, dried or smoked',
     ['bits', 'bit', 'primal', 'fresh ham', 'cooked', 'sliced', 'slices', 'shaved', 'deli', 'chopped', 'luncheon', 'turkey', 'chicken', 'canned', 'spread', 'sandwich', 'pocket', 'hawaiian', 'bone', 'hock', 'hocks', 'flavour', 'flavor', 'bouillon', 'omelette', 'steak']),
    ('sausage_franks', ['sausage', 'sausages', 'saucisse', 'franks', 'frank', 'frankfurter', 'hot dog', 'hot dogs', 'wiener', 'wieners', 'bratwurst', 'kielbasa', 'chorizo', 'salami', 'pepperoni', 'bologna', 'mortadella', 'saucisson',
                        'summer sausage', 'smoked sausage', 'breakfast sausage', 'andouille', 'blood sausage'], '160100', '160100', M, 'Sausages and similar products of meat',
     ['canned', 'vienna', 'plant', 'vegan', 'vegetarian', 'meatless', 'bun', 'buns', 'bread', 'pizza', 'sandwich', 'roll', 'rolls', 'pocket', 'pie', 'seasoning', 'flavour', 'flavor', 'chips', 'dog food', 'cat food']),
    ('chicken_prepared', ['chicken nuggets', 'nuggets', 'chicken patties', 'chicken strips', 'chicken tenders breaded', 'breaded chicken', 'chicken burger', 'chicken franks', 'cooked chicken', 'rotisserie', 'chicken breast sliced', 'deli chicken',
                          'chicken ham', 'chicken loaf', 'smoked chicken', 'chicken roll'], '160232', '160232', M, 'Prepared or preserved chicken (breaded, cooked, smoked)', ['canned', 'soup', 'flavour', 'flavor', 'noodle', 'noodles', 'pot pie']),
    ('turkey_prepared', ['turkey ham', 'turkey bacon', 'oven roasted turkey', 'roasted turkey', 'baked turkey', 'golden brown turkey', 'turkey breast sliced', 'deli turkey', 'smoked turkey', 'turkey loaf', 'turkey slices', 'turkey franks', 'turkey sausage', 'turkey breakfast strips', 'turkey roll', 'turkey pastrami'], '160231', '160231', M,
     'Prepared or preserved turkey (cooked, smoked, sliced)', ['canned']),
    ('beef_prepared', ['roast beef sliced', 'deli roast beef', 'roast beef', 'pastrami', 'beef patties', 'beef burgers', 'beef burger', 'beef patty', 'hamburger', 'hamburgers', 'meatballs', 'beef meatballs', 'cooked beef', 'smoked beef', 'beef jerky bites',
                       'quarter pound beef', 'beef slices', 'beef franks'], '160250', '160250', M, 'Prepared or preserved beef (patties, cooked, sliced)', ['canned', 'corned', 'soup', 'plant', 'vegan', 'vegetarian', 'meatless', 'veggie']),
    ('pork_prepared', ['cooked pork', 'pork roast chinese', 'chinese style pork', 'char siu', 'luncheon pork', 'cooked ham', 'chopped ham', 'sliced ham', 'ham slices', 'ham deli', 'deli ham', 'shaved ham', 'ham steak'], '160241', '160241', M,
     'Prepared or preserved pork hams and cuts (cooked, sliced)', ['canned', 'tin', 'luncheon meat', 'spam']),
    # ---------------------------------------------------------------- fish and shellfish (chapter 03): fresh code, frozen code
    ('fish_salted', ['salted fish', 'salt fish', 'saltfish', 'salted cod', 'salted pollock', 'pollock salted', 'salted mackerel', 'mackerel salted', 'salted salmon', 'salmon salted', 'salted herring', 'herring salted',
                     'salted snapper', 'bacalao', 'bluefish salted', 'salted bluefish', 'cured fish', 'pickled fish'], '030569', '030569', M, 'Fish, salted or in brine (not dried or smoked)', ['canned', 'sauce', 'dried']),
    ('shrimp', ['shrimp', 'shrimps', 'prawn', 'prawns', 'langoustine'], '030636', '030617', M, 'Shrimps and prawns', ['cocktail', 'sauce', 'chips', 'crackers', 'flavour', 'flavor', 'paste', 'noodle', 'noodles', 'breaded', 'burger', 'burgers', 'dumpling', 'dumplings', 'canned', 'hargow', 'seasoning', 'ramen']),
    ('lobster_spiny', ['spiny lobster', 'rock lobster', 'lobster tail', 'lobster tails', 'langosta'], '030631', '030611', M, 'Rock lobster and other sea crawfish', ['bisque', 'sauce', 'ravioli', 'roll', 'mac']),
    ('lobster', ['lobster', 'lobsters'], '030632', '030612', M, 'Lobsters', ['bisque', 'sauce', 'ravioli', 'roll', 'mac', 'flavour', 'flavor']),
    ('crab', ['crab', 'crabs', 'crab meat', 'crabmeat', 'snow crab', 'king crab', 'blue crab', 'land crab', 'crab legs'], '030633', '030614', M, 'Crabs', ['cake', 'cakes', 'sauce', 'stick', 'sticks', 'imitation', 'immitation', 'surimi', 'flavour', 'flavor', 'dip', 'rangoon', 'apple', 'canned']),
    ('conch', ['conch', 'conchs', 'lambi', 'whelk'], '030788', '030784', M, 'Stromboid conchs', ['fritter', 'fritters', 'chowder', 'salad']),
    ('squid_octopus', ['squid', 'calamari', 'octopus', 'cuttlefish'], '030749', '030743', M, 'Cuttlefish and squid (check octopus: 0307.5x)', ['ink', 'fried', 'breaded', 'rings breaded']),
    ('mussels_oysters', ['mussel', 'mussels', 'oyster', 'oysters', 'clam', 'clams', 'scallop', 'scallops'], '030719', '030719', M, 'Molluscs (mussels, oysters, clams, scallops: the subheading depends on the species)', ['sauce', 'chowder', 'smoked', 'canned', 'mushroom', 'clam shell', 'clamshell', 'shell']),
    ('salmon', ['salmon'], '030214', '030313', M, 'Atlantic and Danube salmon', ['smoked', 'canned', 'lox', 'spread', 'burger', 'patty', 'cake', 'dip', 'sushi', 'jerky', 'pate', 'pink salmon', 'sockeye canned', 'cream cheese']),
    ('tilapia', ['tilapia', 'talipia', 'telapia'], '030271', '030323', M, 'Tilapia', ['seasoned', 'breaded', 'canned', 'cake']),
    ('catfish', ['catfish', 'cat fish', 'pangasius', 'basa', 'swai'], '030249', '030324', M, 'Catfish (check the species)', ['breaded', 'canned']),
    ('tuna', ['tuna', 'yellowfin', 'tuna steak', 'bigeye', 'albacore'], '030234', '030342', M, 'Tuna (yellowfin by default)', ['canned', 'can', 'pouch', 'salad', 'sandwich', 'jerky', 'melt', 'sushi', 'in oil', 'in water', 'flavour', 'flavor']),
    ('cod_whitefish', ['cod', 'haddock', 'pollock', 'hake', 'whiting', 'saltfish', 'salt fish', 'bacalao'], '030259', '030369', M, 'Cod, haddock, pollock and similar white fish (check the species)', ['canned', 'liver oil', 'breaded', 'fish sticks', 'fish fingers', 'cake', 'cakes', 'chowder']),
    ('fish_generic_marine', ['snapper', 'red snapper', 'kingfish', 'king fish', 'mahi', 'mahi mahi', 'dorado', 'dolphin fish', 'grouper', 'carite', 'wahoo', 'barracuda', 'swordfish', 'sea bass', 'seabass', 'bream', 'jack fish',
                            'parrot fish', 'bluefish', 'blue fish', 'mackerel', 'sardine fresh', 'herring', 'shark', 'flying fish', 'bonito', 'marlin', 'sailfish', 'trout', 'cavalli', 'cavali', 'bill fish', 'billfish', 'red fish', 'brochet', 'lionfish', 'rockfish', 'redfish'],
     '030289', '030389', M, 'Other marine fish (the subheading depends on the species)', ['canned', 'smoked', 'breaded', 'sauce', 'tin', 'sardines canned', 'cat food', 'dog food', 'jerky', 'oil', 'flakes']),
]

GLOBAL_NOT = ['natural herbs', 'sauce', 'paste', 'ketchup', 'juice', 'soup', 'jam', 'jelly', 'canned', 'tinned', 'dried', 'powder', 'seasoning', 'flavour', 'flavor', 'flavoured', 'flavored', 'oil', 'pickled', 'chips', 'fries',
              'smoothie', 'drink', 'soda', 'yogurt', 'yoghurt', 'ice cream', 'cake', 'cookie', 'cookies', 'biscuit', 'bread', 'pizza', 'cereal', 'candy', 'dressing', 'dip', 'syrup', 'concentrate', 'nectar', 'vinegar', 'extract']


# A name is first tried against the cheese / egg rules, then the cured and prepared meat rules, then fish, then raw meat, then fruit and vegetables: "Philadelphia Cream Cheese Strawberry" is
# a cheese, "Salami with green pepper" a sausage, "Chicken hot dogs" a sausage, whatever fruit or vegetable word they carry.
FAMILY = {
    'eggs': 0, 'cheese_grated': 0, 'cheese_processed': 0, 'cheese_blue': 0, 'cheese_fresh': 0, 'cheese_other': 0,
    'bacon': 1, 'ham_cured': 1, 'sausage_franks': 1, 'chicken_prepared': 1, 'turkey_prepared': 1, 'beef_prepared': 1, 'pork_prepared': 1, 'pork_salted': 1, 'beef_salted': 1, 'fish_salted': 2,
    'shrimp': 2, 'lobster_spiny': 2, 'lobster': 2, 'crab': 2, 'conch': 2, 'squid_octopus': 2, 'mussels_oysters': 2, 'salmon': 2, 'tilapia': 2, 'catfish': 2, 'tuna': 2,
    'cod_whitefish': 2, 'fish_generic_marine': 2,
    'chicken_whole': 3, 'chicken_cuts': 3, 'turkey_cuts': 3, 'beef_offal': 3, 'beef_bone_in': 3, 'beef_boneless': 3, 'pork_hams_fresh': 3, 'pork_offal': 3, 'pork_cuts': 3, 'lamb_cuts': 3, 'goat': 3,
    'rabbit_other_meat': 3,
}
# fillets are another heading (0304): only these species have a fillet code (fresh, frozen); any other fish "fillet" is not suggested
FILLETS = {'salmon': ('030441', '030481'), 'tilapia': ('030431', '030461'), 'catfish': ('030432', '030462')}
FISH = {'shrimp', 'lobster_spiny', 'lobster', 'crab', 'conch', 'squid_octopus', 'mussels_oysters', 'salmon', 'tilapia', 'catfish', 'tuna', 'cod_whitefish', 'fish_generic_marine'}


def main() -> None:
    meat_words = ['sausage', 'franks', 'frank', 'hot dog', 'salami', 'pepperoni', 'burger', 'meatball']
    rules = []
    seen = set()
    for rule_id, words, code, frozen_code, confidence, note, extra_not in sorted(ROWS, key=lambda row: FAMILY.get(row[0], 4)):  # stable: the table order is kept inside a family
        if rule_id in seen:
            raise SystemExit(f'duplicate rule id {rule_id}')
        seen.add(rule_id)
        if rule_id.startswith('cheese'):
            extra_not = list(extra_not) + meat_words
        family = {0: 'dairy', 1: 'prepared_meat', 2: 'fish', 3: 'meat'}.get(FAMILY.get(rule_id, 4), 'produce')
        rule = {'id': rule_id, 'family': family, 'words': words, 'not': extra_not, 'code': code, 'frozen_code': frozen_code, 'confidence': confidence, 'note': note}
        if rule_id in FISH:
            rule['fillet_code'], rule['fillet_frozen_code'] = FILLETS.get(rule_id, (None, None))
        rules.append(rule)
    out = {
        '_about': ('Keyword rules: the backup way to assign an HS code before any AI. A rule fires when ONE of its `words` appears (whole word, plural optional) in the English product name and none of its `not` words '
                   'or of `global_not` does; the first matching rule wins, so specific rules come first. `code` is the 6-digit code of the fresh / chilled product, `frozen_code` the one when the name or the store category '
                   'says "frozen" (null: not suggested when frozen). A suggestion is never saved by itself: a person confirms it. The codes are checked against Comtrade\'s HS reference by the tests. '
                   'Edit hs keyword rules in data/build_hs_keyword_rules.py (the editable table) and rebuild, or edit this file directly.'),
        'global_not': GLOBAL_NOT,
        'rules': rules,
    }
    target = Path(__file__).resolve().parent / 'hs_keyword_rules.json'
    target.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding='utf-8')
    print(f'{len(rules)} rules written to {target.name}')


if __name__ == '__main__':
    main()
