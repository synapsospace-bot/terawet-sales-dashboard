#!/usr/bin/env python3
"""
Deep European Agricultural Domain Harvester and Verifier.
Generates candidate domain combinations from authentic agricultural names,
surnames, regions, and terroirs across 17 European countries.
Verifies each domain via DNS MX in high-throughput parallel threads.
Saves all verified domains into verified_mega_catalog.json.
"""

import dns.resolver
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import time
from pathlib import Path

MEGA_CATALOG_FILE = Path("/Users/anastasiia/.gemini/antigravity/scratch/terawet_sales_agent/verified_mega_catalog.json")

resolver = dns.resolver.Resolver()
resolver.nameservers = ['8.8.8.8', '1.1.1.1', '8.8.4.4']
resolver.timeout = 0.8
resolver.lifetime = 1.0

def check_mx(dom: str):
    d = dom.lower().strip()
    if not d or '.' not in d:
        return d, False
    try:
        ans = resolver.resolve(d, "MX")
        if ans and len(ans) > 0:
            return d, True
    except Exception:
        pass
    return d, False

# Country datasets of authentic agricultural roots, terroirs, and family estate names
ROOTS = {
    "ES": {
        "prefixes": ["bodegas", "viveros", "finca", "almazara", "vinos"],
        "names": [
            "rioja", "ribera", "rueda", "toro", "navarra", "priorat", "penedes", "cava", "bierzo", "jumilla",
            "yecla", "bullas", "alicante", "valencia", "utiel", "requena", "cigales", "arribes", "arlanza",
            "somontano", "borja", "carinena", "calatayud", "montsant", "conca", "costers", "terralta",
            "alarcon", "alvarez", "amador", "aragon", "arenas", "arias", "arroyo", "aviles", "ayala", "barba",
            "barrera", "bello", "beltran", "bernal", "blanco", "bonilla", "bravo", "caballero", "cabrera",
            "calderon", "calvo", "campos", "cano", "carmona", "carrasco", "carrera", "carvajal", "casas",
            "castillo", "castro", "conde", "cordero", "cortes", "cruz", "cuenca", "delgado", "diaz",
            "dominguez", "duran", "espinosa", "estevez", "fernandez", "ferrer", "figueroa", "flores",
            "franco", "fuentes", "galan", "gallardo", "garcia", "garrido", "gil", "gomez", "gonzalez",
            "guerrero", "guillen", "gutierrez", "guzman", "haro", "heredia", "hernandez", "herrero",
            "hidalgo", "ibanez", "iglesias", "izquierdo", "jaen", "jimenez", "jurado", "lara", "leal",
            "leon", "linares", "lopez", "lora", "lorenzo", "lucas", "luque", "machado", "madrid", "manzano",
            "marin", "marquez", "martin", "martinez", "mateos", "medina", "mendez", "mendoza", "merino",
            "mesa", "miranda", "molina", "montero", "montes", "mora", "morales", "moreno", "moya", "munoz",
            "navarro", "nunez", "ocampo", "ochoa", "olivares", "oliver", "ordonez", "orozco", "ortega",
            "ortiz", "pacheco", "padilla", "palacios", "pardo", "paredes", "parra", "pastor", "pena",
            "perez", "pino", "pizarro", "plaza", "polo", "ponce", "pozo", "prada", "prado", "prieto",
            "puente", "pulido", "quesada", "quintero", "ramirez", "ramon", "ramos", "real", "redondo",
            "reina", "requena", "reyes", "rico", "rios", "rivas", "rivera", "robles", "roca", "rocha",
            "rodriguez", "rojas", "rojo", "roldan", "roman", "romero", "ros", "rosa", "rubio", "ruiz",
            "saavedra", "saenz", "salas", "salazar", "salgado", "salinas", "salvador", "sanchez", "sancho",
            "santiago", "santos", "sanz", "segovia", "segura", "serna", "serrano", "sevilla", "sierra",
            "silva", "solano", "soler", "solis", "soto", "suarez", "talavera", "tapia", "tejada", "tello",
            "toledo", "torres", "trujillo", "valbuena", "valdes", "valencia", "valero", "valle", "vallejo",
            "vaquero", "vargas", "vazquez", "vega", "velasco", "velazquez", "vera", "vicente", "vidal",
            "vila", "villanueva", "villar", "villarreal", "villegas", "zamora", "zaragoza"
        ],
        "tlds": [".com", ".es"]
    },
    "IT": {
        "prefixes": ["cantina", "cantine", "tenuta", "aziendaagricola", "vivaio", "frantoio"],
        "names": [
            "chianti", "barolo", "barbaresco", "brunello", "valpolicella", "soave", "bardolino", "gavi",
            "langhe", "roero", "monferrato", "franciacorta", "prosecco", "conegliano", "valdobbiadene",
            "montalcino", "montepulciano", "bolgheri", "maremma", "orvieto", "frascati", "salento",
            "manduria", "etna", "marsala", "collio", "colli", "romagna", "valtellina", "trentino",
            "alberti", "amato", "barbieri", "bellini", "berardi", "bernardi", "bianchi", "biondi",
            "boni", "bruno", "calabrese", "campana", "cantoni", "caputo", "carbone", "caruso",
            "cattaneo", "cavallaro", "colombo", "conte", "conti", "coppola", "costa", "costantini",
            "crispi", "dangelo", "damico", "damato", "deangelis", "deluca", "derosa", "donati",
            "esposito", "fabbri", "farina", "ferrara", "ferrari", "ferraro", "ferri", "fiore",
            "fontana", "franco", "galli", "gallo", "gatti", "gentile", "giordano", "giuliani",
            "grassi", "greco", "grimaldi", "guerra", "leoni", "lombardi", "lombardo", "longo",
            "mancini", "marchetti", "marini", "marino", "martini", "martino", "mazza", "messina",
            "miceli", "milani", "montanari", "monti", "morelli", "moretti", "moro", "napolitano",
            "neri", "negri", "orlandi", "pagano", "palumbo", "parisi", "pellegrini", "piccolo",
            "piras", "poli", "pozzi", "rizzi", "rizzo", "romano", "rossi", "russo", "sala",
            "santoro", "sanna", "sartori", "serra", "silvestri", "sorrentino", "testa", "valente",
            "valentini", "villa", "vitale", "volpe", "zaccaria", "zanetti"
        ],
        "tlds": [".it", ".com"]
    },
    "FR": {
        "prefixes": ["chateau-", "domaine-", "vignobles-", "pepinieres-"],
        "names": [
            "margaux", "pauillac", "saint-julien", "saint-estephe", "pomerol", "saint-emilion",
            "graves", "pessac-leognan", "sauternes", "medoc", "haut-medoc", "chablis", "meursault",
            "puligny-montrachet", "chassagne-montrachet", "corton", "beaune", "pommard", "volnay",
            "gevrey-chambertin", "morey-saint-denis", "chambolle-musigny", "vougeot", "vosne-romanee",
            "nuits-saint-georges", "sancerre", "pouilly-fume", "chinon", "bourgueil", "saumur",
            "vouvray", "muscadet", "chateauneuf-du-pape", "gigondas", "vacqueyras", "hermitage",
            "crozes-hermitage", "saint-joseph", "cote-rotie", "condrieu", "bandol", "cassis",
            "minervois", "corbieres", "fitou", "faugeres", "saint-chinian", "limoux", "cahors",
            "bernard", "blanc", "bonnet", "carpentier", "chevalier", "colin", "david", "dubois",
            "dufour", "dupont", "durand", "faure", "fontaine", "fournier", "francois", "gaillard",
            "garnier", "gautier", "girard", "giraud", "guerin", "guillaume", "henry", "hubert",
            "lambert", "laurent", "leclerc", "lefevre", "legrand", "lemaire", "leroy", "lucas",
            "marchand", "martin", "mercier", "michel", "moreau", "morel", "moulin", "nicolas",
            "perrot", "petit", "philippe", "pierre", "renaud", "renault", "reynaud", "richard",
            "robert", "robin", "roche", "roger", "rousseau", "roussel", "roux", "roy", "simon",
            "thomas", "vallet", "vidal", "vincent"
        ],
        "tlds": [".com", ".fr"]
    },
    "PT": {
        "prefixes": ["quinta-", "adega-", "herdade-", "viveiros-", "vinhos-"],
        "names": [
            "douro", "alentejo", "dao", "bairrada", "vinhoverde", "setubal", "tejo", "algarve",
            "alves", "antunes", "araujo", "barbosa", "barros", "borges", "branco", "brito",
            "cabral", "campos", "cardoso", "carvalho", "castro", "coelho", "correia", "costa",
            "cruz", "cunha", "dias", "duarte", "esteves", "faria", "fernandes", "ferreira",
            "figueiredo", "fonseca", "franco", "freitas", "garcia", "gaspar", "gomes", "goncalves",
            "guerreiro", "henriques", "jesus", "leal", "leite", "lima", "lopes", "lourenco",
            "machado", "magalhaes", "marques", "martins", "matias", "matos", "melo", "mendes",
            "miranda", "monteiro", "moraes", "morais", "moreira", "mota", "moura", "nascimento",
            "neto", "neves", "nobrega", "nogueira", "nunes", "oliveira", "pacheco", "paiva",
            "passos", "peixoto", "pereira", "pinheiro", "pinto", "pires", "ramos", "reis",
            "ribeiro", "rocha", "rodrigues", "santos", "saraiva", "silva", "simoes", "soares",
            "sousa", "tavares", "teixeira", "valente", "vaz", "vicente", "vieira"
        ],
        "tlds": [".pt", ".com"]
    },
    "DE": {
        "prefixes": ["weingut-", "weingut", "baumschule-", "obsthof-"],
        "names": [
            "mosel", "rheingau", "rheinhessen", "pfalz", "baden", "franken", "wuerttemberg",
            "nahe", "ahr", "mittelrhein", "saale-unstrut", "sachsen",
            "bauer", "becker", "berger", "braun", "fischer", "fuchs", "hartmann", "hermann",
            "hoffmann", "huber", "jung", "kaiser", "keller", "klein", "koch", "koehler",
            "koenig", "kraus", "krause", "kuehn", "lange", "maier", "mayer", "meier", "meyer",
            "moeller", "mueller", "otto", "peters", "richter", "roth", "sauer", "schaeffer",
            "schmid", "schmidt", "schmitt", "schneider", "schroeder", "schubert", "schulz",
            "schulze", "schumacher", "schuster", "schwarz", "seidel", "simon", "sommer",
            "stein", "voigt", "wagner", "walter", "weber", "weiss", "werner", "winter", "wolf", "zimmermann"
        ],
        "tlds": [".de", ".com"]
    },
    "AT": {
        "prefixes": ["weingut-", "weingut", "baumschule-"],
        "names": [
            "wachau", "kamptal", "kremstal", "burgenland", "steiermark", "weinviertel", "thermenregion",
            "carnuntum", "wagram", "traisental", "neusiedlersee", "mittelburgenland", "suedsteiermark",
            "bauer", "berger", "ebner", "fischer", "gruber", "hofer", "huber", "koller", "leitner",
            "mayer", "moser", "mueller", "pichler", "reiter", "schmid", "steiner", "wagner", "weber", "wieser"
        ],
        "tlds": [".at", ".com"]
    },
    "GR": {
        "prefixes": ["ktima-", "oinopoieio-", "fytoria-", "agro-"],
        "names": [
            "nemea", "naoussa", "santorini", "kriti", "peloponnisos", "attiki", "drama", "amyntaio",
            "kefalonia", "rhodes", "limnos", "lesvos", "samos", "kalamata", "sparta", "chania", "heraklion"
        ],
        "tlds": [".gr", ".com"]
    },
    "RO": {
        "prefixes": ["crama-", "crama", "domeniile-", "pepiniera-", "agro-"],
        "names": [
            "dealumare", "dragasani", "cotnari", "murfatlar", "recas", "panciu", "odobesti", "tarnave",
            "moldova", "oltenia", "muntenia", "dobrogea", "banat", "crisana", "maramures", "transilvania"
        ],
        "tlds": [".ro", ".com"]
    },
    "BG": {
        "prefixes": ["chateau-", "vinprom-", "razsadnik-", "agro-", "vina-"],
        "names": [
            "plovdiv", "thrace", "danube", "melnik", "rosevalley", "burgas", "varna", "starosel",
            "kolarovo", "peshtera", "svishtov", "preslav", "pleven", "sliven", "haskovo", "yambol"
        ],
        "tlds": [".bg", ".com"]
    },
    "PL": {
        "prefixes": ["winnica-", "winnica", "szkolka-", "sady-", "agro-"],
        "names": [
            "grojec", "sandomierz", "malopolska", "lubelskie", "wielkopolska", "dolnyslask", "mazowsze",
            "podkarpacie", "zielonagora", "krakow", "wroclaw", "poznan", "warszawa", "lodz", "lublin"
        ],
        "tlds": [".pl", ".com.pl"]
    },
    "HU": {
        "prefixes": ["boraszat-", "pinceszet-", "boraszat", "pinceszet", "kert-"],
        "names": [
            "tokaj", "eger", "villany", "szekszard", "balaton", "somlo", "matra", "bukk",
            "sopron", "aszar", "mor", "tolna", "hajos", "kunsag", "csongrad", "badacsony"
        ],
        "tlds": [".hu", ".com"]
    },
    "HR": {
        "prefixes": ["vina-", "vinarija-", "vina", "vinarija", "opg-"],
        "names": [
            "istra", "peljesac", "slavonija", "kutjevo", "dingac", "hvar", "korcula", "brac",
            "zadar", "sibenik", "split", "dubrovnik", "baranja", "srijem", "medimurje", "zagorje"
        ],
        "tlds": [".hr", ".com"]
    },
    "SI": {
        "prefixes": ["vina-", "klet-", "vina", "klet", "posestvo-"],
        "names": [
            "brda", "vipava", "kras", "istra", "stajerska", "jeruzalem", "krsko", "bizeljsko",
            "dolenjska", "belakrajina", "prekmurje", "maribor", "ormoz", "radgona", "koper"
        ],
        "tlds": [".si", ".com"]
    },
    "SK": {
        "prefixes": ["vinarstvo-", "vinarstvo", "sady-", "agro-", "chateau-"],
        "names": [
            "tokaj", "strekov", "modra", "pezinok", "topolcianky", "nitra", "zahorie", "hont",
            "levice", "trnava", "skalica", "svatyjur", "bela", "ruban"
        ],
        "tlds": [".sk", ".com"]
    },
    "CZ": {
        "prefixes": ["vinarstvi-", "vinarstvi", "sady-", "skolky-", "agro-"],
        "names": [
            "mikulov", "znojmo", "velkepavlovice", "slovacko", "morava", "cechy", "litomerice",
            "melnik", "valtice", "lednice", "palava", "mutenice", "cejc", "velkebilovice"
        ],
        "tlds": [".cz", ".com"]
    },
    "RS": {
        "prefixes": ["vinarija-", "podrum-", "vinarija", "podrum", "agro-"],
        "names": [
            "fruskagora", "zupa", "sumadija", "toplica", "subotica", "vrsac", "negotin",
            "knjazevac", "smederevo", "jagodina", "prokuplje", "vranje", "kosmaj", "oplenac"
        ],
        "tlds": [".rs", ".com"]
    }
}

def harvest_deep_catalog(max_workers=60):
    candidates_by_country = {}
    total_candidates = 0

    for c_code, cfg in ROOTS.items():
        dom_set = set()
        pfxs = cfg.get("prefixes", [])
        names = cfg.get("names", [])
        tlds = cfg.get("tlds", [".com"])
        for p in pfxs:
            for n in names:
                for tld in tlds:
                    dom_set.add(f"{p}{n}{tld}".lower().strip())
        candidates_by_country[c_code] = list(dom_set)
        total_candidates += len(dom_set)

    print(f"Generated {total_candidates} candidate domains across 17 European countries.")
    print("Initiating high-throughput parallel DNS MX validation...")
    
    # Load current catalog
    current_catalog = {}
    if MEGA_CATALOG_FILE.exists():
        with open(MEGA_CATALOG_FILE, "r", encoding="utf-8") as f:
            current_catalog = json.load(f)

    # Flatten unique candidates not already in catalog
    existing_all = set()
    for v in current_catalog.values():
        existing_all.update(d.lower().strip() for d in v)

    all_to_check = []
    country_map = {}
    for c_code, doms in candidates_by_country.items():
        for d in doms:
            if d not in existing_all:
                all_to_check.append(d)
                country_map.setdefault(d, []).append(c_code)

    all_to_check = list(set(all_to_check))
    print(f"Checking {len(all_to_check)} brand-new candidate domains (skipping {len(existing_all)} existing)...")

    start_time = time.time()
    valid_new = set()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for dom, is_valid in executor.map(check_mx, all_to_check):
            if is_valid:
                valid_new.add(dom)

    elapsed = time.time() - start_time
    print(f"DNS MX scanning finished in {elapsed:.2f}s! Found {len(valid_new)} working active mail domains.")

    # Merge into catalog
    added_count = 0
    for dom in valid_new:
        c_codes = country_map.get(dom, ["ES"])
        for c_code in c_codes:
            cur = current_catalog.setdefault(c_code, [])
            if dom not in cur:
                cur.append(dom)
                added_count += 1

    # Save merged catalog
    with open(MEGA_CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(current_catalog, f, indent=2, ensure_ascii=False)

    print("\nUpdated Mega Catalog summary:")
    total = 0
    for k, v in sorted(current_catalog.items()):
        print(f"  {k}: {len(v)} domains")
        total += len(v)

    print(f"\nSUCCESS! Catalog expanded to {total} verified European agribusiness domains! (+{added_count} new)")

if __name__ == "__main__":
    harvest_deep_catalog()
