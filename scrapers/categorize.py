"""Map German / French product text onto a single English category set.

Only categories are translated. Product names stay in the original language,
because that is what you actually read off the shelf label in the store.
"""
from __future__ import annotations

import re
import unicodedata

# Display order in the UI.
CATEGORIES = [
    "Fruits & Vegetables",
    "Meat & Poultry",
    "Fish & Seafood",
    "Dairy & Eggs",
    "Bread & Bakery",
    "Pantry & Dry Goods",
    "Frozen",
    "Snacks & Sweets",
    "Beverages",
    "Alcohol",
    "Household",
    "Health & Beauty",
    "Baby & Kids",
    "Pet",
    "Non-food & Other",
]

# Keyword -> category. Checked longest-first so "rindfleisch" beats "reis".
# Keys are lowercase, accent-stripped; both DE and FR terms are mixed in.
_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Fruits & Vegetables": (
        "obst", "gemuse", "fruits", "legumes", "salat", "salade", "tomate",
        "gurke", "concombre", "karotte", "carotte", "rueebli", "zwiebel",
        "oignon", "kartoffel", "pomme de terre", "patate", "apfel", "pomme",
        "birne", "poire", "banane", "orange", "zitrone", "citron", "traube",
        "raisin", "erdbeere", "fraise", "himbeere", "framboise", "beeren",
        "melone", "avocado", "paprika", "poivron", "broccoli", "brocoli",
        "blumenkohl", "chou", "kohl", "spinat", "epinard", "pilz",
        "champignon", "lauch", "poireau", "sellerie", "celeri", "kurbis",
        "courge", "zucchetti", "courgette", "aubergine", "bohnen", "haricot",
        "erbsen", "petits pois", "kraut", "herbes", "basilikum", "basilic",
        "pfirsich", "peche", "aprikose", "abricot", "kiwi", "mango", "ananas",
        "nektarine", "pflaume", "prune", "kirsche", "cerise", "feige",
        "butternuss", "butternut", "fleischtomate", "clementine", "mandarine",
        "grapefruit", "pampelmousse", "pomelo", "limette", "lime", "papaya",
        "granatapfel", "grenade", "heidelbeere", "myrtille", "brombeere",
        "mure", "johannisbeere", "stachelbeere", "rhabarber", "rhubarbe",
        "chicoree", "endivie", "rucola", "roquette", "nusslisalat", "mais",
        "sellerie stange", "staudensellerie", "kefen", "zuckerschote",
        "datteln", "rande", "betterave", "radieschen", "radis", "fenchel",
        "fenouil", "spargel", "asperge", "artischocke", "artichaut", "lattich",
    ),
    "Meat & Poultry": (
        "rindfleisch", "rind", "boeuf", "kalbfleisch", "kalb", "veau",
        "schweinefleisch", "schwein", "porc", "lamm", "agneau", "poulet",
        "huhn", "hahnchen", "pouletbrust", "truthahn", "dinde", "ente",
        "canard", "fleisch", "viande", "steak", "entrecote", "filet",
        "plätzli", "schnitzel", "hackfleisch", "hache", "gehacktes",
        "wurst", "saucisse", "saucisson", "cervelas", "salami", "schinken", "jambon",
        "speck", "lard", "bacon", "braten", "roti", "voressen", "ragout",
        "geschnetzeltes", "spareribs", "chipolata", "bratwurst", "landjager",
        "trockenfleisch", "mostbrockli", "charcuterie", "aufschnitt",
        "grillwurst", "hamburger", "burger", "nuggets", "cordon bleu",
    ),
    "Fish & Seafood": (
        "fisch", "poisson", "lachs", "saumon", "thunfisch", "thon", "forelle",
        "truite", "crevette", "garnele", "shrimp", "scampi", "muschel",
        "moule", "tintenfisch", "calamar", "kabeljau", "cabillaud", "dorsch",
        "zander", "egli", "felchen", "sardine", "hering", "makrele",
        "maquereau", "fruits de mer", "meeresfruchte", "surimi", "pangasius",
        "fischstabchen", "seelachs", "hecht", "dorade", "loup de mer", "branzino",
        "fillet", "basa", "tilapia", "wolfsbarsch", "rotbarsch", "heilbutt",
        "rouget", "omble", "lotte", "raie", "espadon", "bar ", "anchois",
        "flet", "scholle", "limande", "merlu", "colin", "lieu noir",
    ),
    "Dairy & Eggs": (
        "eiersalat", "gouda", "cheddar", "edamer", "gorgonzola", "taleggio", "pecorino",
        "manchego", "halloumi", "burrata", "chaschuechli", "kaseschnitte",
        "streichkase", "frischkase", "hartkase", "weichkase", "rahmkase",
        "milch", "lait", "kase", "fromage", "joghurt", "yogourt", "yaourt",
        "butter", "beurre", "rahm", "creme", "sahne", "quark", "seré",
        "sere", "mozzarella", "gruyere", "emmentaler", "appenzeller",
        "raclette", "fondue", "camembert", "brie", "parmesan", "feta",
        "ricotta", "mascarpone", "huttenkase", "cottage", "eier", "oeufs",
        "ei ", "tete de moine", "tilsiter", "vacherin", "sbrinz", "halbrahm",
        "vollrahm", "milchdrink", "buttermilch", "kefir", "skyr", "creme fraiche",
    ),
    "Bread & Bakery": (
        "brot", "pain", "brotchen", "weggli", "gipfeli", "croissant",
        "zopf", "tresse", "baguette", "toast", "sandwich", "backwaren",
        "boulangerie", "patisserie", "kuchen", "gateau", "torte", "tarte",
        "guetzli", "biscuit", "cake", "muffin", "donut", "brezel", "bretzel",
        "tartelette", "wahe", "cheesecake", "brownie", "crumble",
        "butterzopf", "buttergipfeli", "milchbrotchen", "kasekuchen",
        "knackerli", "zwieback", "crackers", "waffeln", "gaufre", "blatterteig",
        "pate feuilletee", "teig", "vollkornbrot", "ruchbrot", "burli",
    ),
    "Pantry & Dry Goods": (
        "teigwaren", "pates", "pasta", "spaghetti", "penne", "nudeln",
        "reis", "riz", "risotto", "mehl", "farine", "zucker", "sucre",
        "salz", "sel", "pfeffer", "poivre", "gewurz", "epice", "ol ",
        "huile", "olivenol", "essig", "vinaigre", "sauce", "ketchup",
        "mayonnaise", "senf", "moutarde", "konserve", "conserve", "dose",
        "bouillon", "suppe", "soupe", "aromat", "streuwurze", "honig",
        "miel", "konfiture", "confiture", "marmelade", "nutella",
        "erdnussbutter", "muesli", "birchermuesli", "cornflakes", "cereales",
        "hornli", "gnocchi", "ravioli", "tortellini", "fiori", "farfalle",
        "fusilli", "tagliatelle", "lasagne", "cannelloni", "spatzli", "knopfli",
        "kellogg", "cerealien", "cruesli", "granola", "porridge",
        "milchreis", "erdnussbutter", "kokosmilch", "haferflocken",
        "flocons", "linsen", "lentille", "kichererbsen",
        "pois chiche", "polenta", "couscous", "quinoa", "tofu", "seitan",
        "kokosmilch", "tomatenpuree", "pelati", "backpulver", "vanille",
    ),
    "Frozen": (
        "tiefkuhl", "surgele", "surgeles", "glace", "glacé", "eiscreme",
        "speiseeis", "ben & jerry", "magnum", "pizza", "pommes frites",
        "frites", "gemuse tiefgekuhlt", "tiefgefroren", "mövenpick glace",
    ),
    "Snacks & Sweets": (
        "schokolade", "chocolat", "chocolade", "bonbon", "sussigkeit",
        "confiserie", "chips", "snack", "nusse", "noix", "mandeln",
        "amande", "cashew", "pistazien", "popcorn", "salzstangen",
        "riegel", "barre", "kaugummi", "chewing", "gummibarchen",
        "lindt", "toblerone", "kagi", "branche", "ragusa", "frey",
        "haribo", "oreo", "kitkat", "m&m", "pringles", "zweifel",
        "apero", "salzgeback", "praline", "dessert", "pudding",
    ),
    "Beverages": (
        "wasser", "eau", "mineralwasser", "saft", "jus", "orangensaft",
        "getrank", "boisson", "cola", "coca", "rivella", "sinalco",
        "eistee", "ice tea", "the froid", "kaffee", "cafe", "nespresso",
        "tee", "the ", "sirup", "sirop", "energy drink", "red bull",
        "limonade", "schweppes", "tonic", "smoothie", "kakao", "ovomaltine",
        "henniez", "valser", "evian", "vittel", "san pellegrino", "elmer",
        "caffe", "latte macchiato", "cappuccino", "espresso", "milchkaffee",
        "eau minerale", "mineral", "softdrink", "fanta", "sprite", "pepsi",
    ),
    "Alcohol": (
        "wein", "vin", "rotwein", "vin rouge", "weisswein", "vin blanc",
        "rose", "prosecco", "champagne", "schaumwein", "cremant", "sekt",
        "bier", "biere", "beer", "feldschlosschen", "calanda", "heineken",
        "corona", "quollfrisch", "whisky", "whiskey", "vodka", "wodka",
        "gin", "rum", "likor", "liqueur", "aperol", "campari", "spirituose",
        "cognac", "grappa", "schnaps", "cocktail", "barolo", "chianti",
        "merlot", "pinot", "chasselas", "fendant", "dole", "amarone",
        "gran reserva", "crianza", "rioja", "carinena", "ribera", "tempranillo",
        "cabernet", "syrah", "shiraz", "malbec", "primitivo", "montepulciano",
        "valpolicella", "bordeaux", "beaujolais", "cotes du rhone", "sangiovese",
        "gamay", "riesling", "sauvignon", "chardonnay", "grauburgunder",
    ),
    "Household": (
        "waschmittel", "lessive", "reinig", "nettoyant", "putzmittel",
        "spulmittel", "produit vaisselle", "abwaschmittel", "wc-", "wc ",
        "toilettenpapier", "papier toilette", "haushaltpapier", "essuie-tout",
        "taschentuch", "mouchoir", "mullsack", "sac poubelle", "abfallsack",
        "alufolie", "frischhaltefolie", "backpapier", "servietten",
        "serviette", "kerze", "bougie", "batterie", "pile", "gluhbirne",
        "ampoule", "persil", "ariel", "omo", "potz", "ajax", "cif",
        "weichspuler", "assouplissant", "handschuhe", "schwamm", "eponge",
        "mr proper", "mr. proper", "meister proper", "antikal", "anticalcaire",
        "entkalker", "degrais", "degraissant", "desinfect", "desinfekt",
        "alustar", "alufolie", "haushaltfolie", "klarsichtfolie", "wc-ente",
        "javel", "bleach", "scheuermittel", "glasreiniger", "nettoyant vitres",
    ),
    "Health & Beauty": (
        "shampoo", "shampooing", "duschgel", "gel douche", "seife", "savon",
        "zahnpasta", "dentifrice", "zahnburste", "brosse a dents", "deo",
        "deodorant", "rasier", "rasoir", "creme gesicht", "hautcreme",
        "bodylotion", "korperlotion", "make-up", "maybelline", "l'oreal",
        "loreal", "nivea", "dove", "garnier", "elmex", "candida", "signal",
        "sonnencreme", "solaire", "parfum", "haarfarbe", "coloration",
        "binden", "tampon", "damenhygiene", "vitamin", "medikament",
        "pflaster", "apotheke", "handcreme", "lippenpflege", "kosmetik",
        "brosse a dents", "br. a dents", "br.dent", "br. dents", "zahnbuerste",
        "trisa", "interdental", "mundspulung",
        "mascara", "lippenstift", "rouge a levres", "nagellack", "vernis",
        "foundation", "concealer", "lidschatten", "eyeliner", "gesichtspflege",
        "haarspray", "haargel", "conditioner", "spulung", "wattestabchen",
        "manner", "intimpflege", "mundwasser", "zahnseide", "fil dentaire",
    ),
    "Baby & Kids": (
        "baby", "bebe", "windel", "couche", "pampers", "milupa", "hipp",
        "babynahrung", "schoppen", "nuggi", "sutine", "kinder", "enfant",
        "spielzeug", "jouet", "feuchttucher", "lingettes",
    ),
    "Pet": (
        "hund", "chien", "katze", "chat", "tiernahrung", "tierfutter",
        "nourriture pour", "whiskas", "sheba", "pedigree", "felix",
        "purina", "katzenstreu", "litiere", "vogelfutter", "aquarium",
    ),
}

# Category names the retailers themselves use, mapped straight across.
_NATIVE_CATEGORY_MAP = {
    "fruits & legumes": "Fruits & Vegetables",
    "fruchte & gemuse": "Fruits & Vegetables",
    "fruits and vegetables": "Fruits & Vegetables",
    "fleisch & fisch": "Meat & Poultry",
    "viande & poisson": "Meat & Poultry",
    "meat & fish": "Meat & Poultry",
    "milchprodukte & eier": "Dairy & Eggs",
    "produits laitiers": "Dairy & Eggs",
    "brot & backwaren": "Bread & Bakery",
    "pain & patisserie": "Bread & Bakery",
    "vorrat": "Pantry & Dry Goods",
    "provisions": "Pantry & Dry Goods",
    "tiefkuhlprodukte": "Frozen",
    "surgeles": "Frozen",
    "sussigkeiten & snacks": "Snacks & Sweets",
    "sucreries & snacks": "Snacks & Sweets",
    "getranke": "Beverages",
    "boissons": "Beverages",
    "wein & spirituosen": "Alcohol",
    "vins & spiritueux": "Alcohol",
    "haushalt": "Household",
    "menage": "Household",
    "beauty & gesundheit": "Health & Beauty",
    "beaute & sante": "Health & Beauty",
    "schonheit & gesundheit": "Health & Beauty",
    "baby & kind": "Baby & Kids",
    "tier": "Pet",
    "animaux": "Pet",
}

# Tier 1 of 3. Non-food products whose names contain a food word: "Canard-WC"
# is a toilet cleaner, not duck; "Carton a Pizza" is a pizza box; "Bougie
# Citronnelle" is a candle; "Savon Amande" is soap. Substring matching cannot
# tell these apart on length alone, so they are decided before anything else.
_OVERRIDE: tuple[tuple[str, str], ...] = (
    # cleaning / home
    ("canard-wc", "Household"),
    ("canard wc", "Household"),
    ("wc canard", "Household"),
    ("wc ente", "Household"),
    ("wc-ente", "Household"),
    ("wc gel", "Household"),
    ("wc-gel", "Household"),
    ("bougie", "Household"),
    ("citronnelle", "Household"),
    ("citronelle", "Household"),
    ("glade", "Household"),
    ("air wick", "Household"),
    ("febreze", "Household"),
    ("torchon", "Household"),
    ("essuie-tout", "Household"),
    ("essuie tout", "Household"),
    # body care that collides with food scents
    ("savon", "Health & Beauty"),
    ("gel douche", "Health & Beauty"),
    ("creme mains", "Health & Beauty"),
    # catering disposables and packaging
    ("carton a pizza", "Non-food & Other"),
    ("boite a pizza", "Non-food & Other"),
    ("carton a ", "Non-food & Other"),
    ("assiette", "Non-food & Other"),
    ("nappe", "Non-food & Other"),
    ("couvert jetable", "Non-food & Other"),
    ("barquette vide", "Non-food & Other"),
    ("emballage", "Non-food & Other"),
    ("sac poubelle", "Household"),
    ("sachet vide", "Non-food & Other"),
)

# Brands and unambiguous product nouns. These are matched before the generic
# sweep: "Zweifel Chips Paprika" is a bag of crisps, not a vegetable, and
# length alone would hand it to "paprika".
_STRONG = frozenset((
    # snacks & sweets
    "chips", "zweifel", "lindt", "toblerone", "haribo", "oreo", "kitkat",
    "pringles", "kagi", "ragusa", "branche", "popcorn", "praline",
    "schokolade", "chocolat", "riegel", "kaugummi",
    # beverages
    "coca", "cola", "rivella", "sinalco", "red bull", "schweppes", "eistee",
    "ice tea", "nespresso", "ovomaltine", "henniez", "valser", "evian",
    "san pellegrino", "smoothie", "sirup", "sirop",
    # alcohol
    "feldschlosschen", "calanda", "heineken", "corona", "quollfrisch",
    "aperol", "campari", "prosecco", "champagne", "barolo", "chianti",
    "amarone", "whisky", "whiskey", "vodka", "wodka", "grappa",
    # frozen
    "tiefkuhl", "surgele", "surgeles", "glace", "eiscreme", "pizza",
    "ben & jerry", "magnum", "pommes frites", "frites",
    # household
    "persil", "ariel", "potz", "ajax", "cif", "waschmittel", "lessive",
    "toilettenpapier", "papier toilette", "abfallsack", "sac poubelle",
    # health & beauty
    "nivea", "dove", "garnier", "loreal", "l'oreal", "maybelline", "elmex",
    "candida", "signal", "shampoo", "shampooing", "mascara", "deodorant",
    "zahnpasta", "dentifrice", "duschgel", "gel douche",
    # baby & pet
    "pampers", "milupa", "hipp", "windel", "couche", "whiskas", "sheba",
    "pedigree", "felix", "purina", "katzenstreu", "litiere",
    "tarte", "torte", "kuchen", "gateau", "cake", "muffin", "donut",
    "tartelette", "wahe", "cheesecake", "brownie", "crumble",
    # meat cuts that contain other category words
    "cordon bleu", "hamburger", "bratwurst", "cervelas", "salami",
    "merlu", "cabillaud", "colin", "lieu noir", "dorade", "rouget", "omble",
    "truite", "saumon", "thon", "sardine", "anchois", "maquereau", "bar ",
    "lotte", "raie", "espadon", "saucisson",
    "mr proper", "mr. proper", "antikal", "alustar", "trisa", "kellogg",
    "gran reserva", "chaschuechli", "gouda", "gnocchi", "hornli",
    # compound nouns whose first half belongs to another category
    "butternuss", "butternut", "fleischtomate", "milchreis", "eiersalat",
    "kasekuchen", "fischstabchen", "erdnussbutter", "kokosmilch",
    "butterzopf", "buttergipfeli", "milchbrotchen",
))

_ALL_PAIRS = [(kw, cat) for cat, kws in _KEYWORDS.items() for kw in kws]

# _STRONG only reorders _ALL_PAIRS, so a word listed there but missing from
# _KEYWORDS would never match anything. That failure is invisible at runtime,
# so catch it at import.
# French product names lead with the head noun, so a name *starting* with one
# of these is the article itself, not a food sold in it. Anchoring to the start
# keeps "Mozzarella di Bufala Gobelet" (cheese in a cup) in Dairy.
_HEAD_NOUN: tuple[tuple[str, str], ...] = (
    ("gobelet", "Non-food & Other"),
    ("couvercle", "Non-food & Other"),
    ("barquette", "Non-food & Other"),
    ("plateau", "Non-food & Other"),
    ("boite", "Non-food & Other"),
    ("sachet", "Non-food & Other"),
    ("film", "Non-food & Other"),
    ("papier", "Household"),
    ("serviette", "Household"),
    ("sac", "Household"),
)

_OVERRIDE_ORDERED = sorted(_OVERRIDE, key=lambda kv: -len(kv[0]))
_STRONG_ORDERED = sorted(
    ((kw, cat) for cat, kws in _KEYWORDS.items() for kw in kws if kw in _STRONG),
    key=lambda kv: -len(kv[0]),
)


def _word_start(kw: str, blob: str) -> bool:
    """True when kw appears at the start of a word in blob."""
    i = blob.find(kw)
    while i != -1:
        if i == 0 or not blob[i - 1].isalnum():
            return True
        i = blob.find(kw, i + 1)
    return False

_bad = {cat for _, cat in _OVERRIDE + _HEAD_NOUN} - set(CATEGORIES)
if _bad:
    raise AssertionError(
        f"_OVERRIDE/_HEAD_NOUN point at unknown categories: {sorted(_bad)}"
    )

_orphans = _STRONG - {kw for kw, _ in _ALL_PAIRS}
if _orphans:
    raise AssertionError(
        f"_STRONG entries missing from _KEYWORDS (they would never match): "
        f"{sorted(_orphans)}"
    )

# Strong keywords first; within each tier, longest keyword wins.
_ORDERED = sorted(
    _ALL_PAIRS,
    key=lambda kv: (kv[0] not in _STRONG, -len(kv[0])),
)


def _norm(s: str) -> str:
    """Lowercase, strip accents and umlauts so 'Gemüse' matches 'gemuse'."""
    s = (s or "").lower()
    s = s.replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s)


def categorize(*texts: str, native: str = "") -> str:
    """Pick an English category from product text, optionally helped by the
    retailer's own category label (which is trusted first when recognised)."""
    if native:
        n = _norm(native)
        for key, cat in _NATIVE_CATEGORY_MAP.items():
            if key in n:
                return cat

    blob = _norm(" ".join(t for t in texts if t))
    if not blob.strip():
        return "Non-food & Other"

    # Tier 1: non-food products named after food. Longest first so
    # "carton a pizza" wins over the generic "carton a ".
    for kw, cat in _OVERRIDE_ORDERED:
        if kw in blob:
            return cat
    # Tier 1b: the name begins with the article's own head noun.
    for kw, cat in _HEAD_NOUN:
        if blob.startswith(kw + " ") or blob.startswith(kw + "s "):
            return cat
    # Tier 2: brands and whole-word nouns, anchored to a word start.
    for kw, cat in _STRONG_ORDERED:
        if _word_start(kw, blob):
            return cat
    # Tier 3: plain substring, which is what German compounds need -
    # "Vollmilch" carries its head noun at the end, not at a word boundary.
    for kw, cat in _ORDERED:
        if kw in blob:
            return cat
    return "Non-food & Other"
