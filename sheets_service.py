import csv
import io
import re
import json
import logging
import threading
import urllib.request
from typing import List, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime
import config

logger = logging.getLogger(__name__)

STATE_FILE = config.BASE_DIR / "leads_state.json"
UPDATED_CSV_FILE = config.BASE_DIR / "updated_google_sheet.csv"
IMPORTED_LEADS_FILE = config.BASE_DIR / "imported_leads.json"

class LeadDataService:
    """
    Manages reading from the user's live Google Sheet and tracking sync state locally.
    Saves 'updated_google_sheet.csv' ready for 1-click import into Google Sheets.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._cached_leads = None
        self.sheet_url = config.GOOGLE_SHEET_URL
        self.state = self._load_state()
        self.raw_headers = []
        self.raw_rows = []
        # Immediately load local CSV cache so leads are always available instantly
        self._load_local_csv()
        # Ensure any imported leads are merged
        self._merge_imported_leads()
        # Attempt live sync in background or on startup
        try:
            self._sync_live_sheet()
        except Exception as e:
            logger.warning(f"Startup sheet sync warning: {e}")

    def invalidate_cache(self):
        with self._lock:
            self._cached_leads = None

    def _load_local_csv(self):
        if UPDATED_CSV_FILE.exists():
            try:
                with open(UPDATED_CSV_FILE, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    self.raw_headers = reader.fieldnames or []
                    rows = list(reader)
                    # Filter out ghost rows where all identifying fields are blank
                    self.raw_rows = [
                        r for r in rows
                        if any(r.get(k, "").strip() for k in ["name", "email", "phone", "city", "website"])
                    ]
                    self.invalidate_cache()
                    logger.info(f"Loaded {len(self.raw_rows)} valid rows from local CSV cache.")
            except Exception as e:
                logger.error(f"Failed to load local CSV fallback: {e}")

    def _extract_sheet_id(self) -> str:
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', self.sheet_url)
        return match.group(1) if match else "1E5w61jpITa3DgnmnhbJBmLhllTVLabUYYZMlke4CljY"

    def _load_state(self) -> Dict[str, Any]:
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_state(self):
        self.invalidate_cache()
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def _load_imported_leads(self) -> List[Dict[str, str]]:
        if IMPORTED_LEADS_FILE.exists():
            try:
                with open(IMPORTED_LEADS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load imported leads: {e}")
                return []
        return []

    def _save_imported_leads(self, leads: List[Dict[str, str]]):
        try:
            with open(IMPORTED_LEADS_FILE, "w", encoding="utf-8") as f:
                json.dump(leads, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save imported leads: {e}")

    def _merge_imported_leads(self):
        imported = self._load_imported_leads()
        if not imported:
            return
        existing_emails = set(r.get("email", "").strip().lower() for r in self.raw_rows if r.get("email"))
        existing_names = set(r.get("name", "").strip().lower() for r in self.raw_rows if r.get("name"))

        for imp in imported:
            email = imp.get("email", "").strip().lower()
            name = imp.get("name", "").strip().lower()
            if (email and email in existing_emails) or (name and name in existing_names):
                continue
            self.raw_rows.append(imp)
            if email:
                existing_emails.add(email)
            if name:
                existing_names.add(name)

    def reload(self):
        """Forces a clean reload of local CSV and imported leads."""
        self.invalidate_cache()
        self._load_local_csv()
        self._merge_imported_leads()

    def add_imported_leads(self, new_items: List[Dict[str, str]]) -> int:
        """
        Appends newly discovered prospects to imported_leads.json and active memory.
        Guarantees that Google Sheet sync will never overwrite or erase them.
        """
        current_imported = self._load_imported_leads()
        imported_emails = set(l.get("email", "").strip().lower() for l in current_imported if l.get("email"))
        imported_names = set(l.get("name", "").strip().lower() for l in current_imported if l.get("name"))

        existing_emails = set(l.get("email", "").strip().lower() for l in self.raw_rows if l.get("email"))
        existing_names = set(l.get("name", "").strip().lower() for l in self.raw_rows if l.get("name"))

        fieldnames = self.raw_headers if self.raw_headers else [
            "name", "country", "category", "culture", "adress", "city", "zip", "website", "phone", "coordinates", "email", "instagram", "crop", "status", "generation sheet", "date"
        ]

        added_count = 0
        today = datetime.now().strftime("%Y-%m-%d")

        for item in new_items:
            email = item.get("email", "").strip().lower()
            name = item.get("name", "").strip()
            if (email and (email in imported_emails or email in existing_emails)) or (name and (name.lower() in imported_names or name.lower() in existing_names)):
                continue

            new_lead = {fn: "" for fn in fieldnames}
            new_lead["name"] = name
            new_lead["country"] = item.get("country", "")
            new_lead["category"] = item.get("category", "")
            new_lead["culture"] = item.get("culture", "")
            new_lead["city"] = item.get("city", "")
            new_lead["adress"] = item.get("adress", "")
            new_lead["website"] = item.get("website", "")
            new_lead["phone"] = item.get("phone", "")
            new_lead["email"] = item.get("email", "")
            new_lead["status"] = "NEW"
            new_lead["date"] = today

            current_imported.append(new_lead)
            self.raw_rows.append(new_lead)
            if email:
                imported_emails.add(email)
                existing_emails.add(email)
            if name:
                imported_names.add(name.lower())
                existing_names.add(name.lower())
            added_count += 1

        if added_count > 0:
            self._save_imported_leads(current_imported)
            self.invalidate_cache()
            self.export_updated_csv()
            logger.info(f"Appended {added_count} imported leads to active memory & disk.")

        return added_count

    def _sync_live_sheet(self):
        sheet_id = self._extract_sheet_id()
        export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

        try:
            req = urllib.request.Request(export_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                content = resp.read().decode("utf-8")

            reader = csv.DictReader(io.StringIO(content))
            new_headers = reader.fieldnames or []
            sheet_rows = list(reader)

            # Filter out empty ghost rows from Google Sheet
            valid_sheet_rows = [
                r for r in sheet_rows
                if any(r.get(k, "").strip() for k in ["name", "email", "phone", "city", "website"])
            ]

            # Merge with locally discovered leads so they are NEVER erased by live sync
            imported_leads = self._load_imported_leads()
            existing_emails = set(r.get("email", "").strip().lower() for r in valid_sheet_rows if r.get("email"))
            existing_names = set(r.get("name", "").strip().lower() for r in valid_sheet_rows if r.get("name"))

            merged_rows = list(valid_sheet_rows)
            for imp in imported_leads:
                imp_email = imp.get("email", "").strip().lower()
                imp_name = imp.get("name", "").strip().lower()
                if (imp_email and imp_email in existing_emails) or (imp_name and imp_name in existing_names):
                    continue
                merged_rows.append(imp)

            if merged_rows:
                # Only write to CSV and bust cache if the data actually changed
                if self.raw_rows != merged_rows or (new_headers and new_headers != self.raw_headers):
                    if new_headers:
                        self.raw_headers = new_headers
                    self.raw_rows = merged_rows
                    self.invalidate_cache()
                    logger.info(f"Synced live sheet: {len(valid_sheet_rows)} sheet leads + {len(imported_leads)} imported leads ({len(self.raw_rows)} total).")
                    self.export_updated_csv()
        except Exception as e:
            logger.warning(f"Live Google Sheet sync notice (retaining {len(self.raw_rows)} cached rows): {e}")
            if not self.raw_rows:
                self._load_local_csv()
                self._merge_imported_leads()

    def get_all_leads(self) -> List[Dict[str, Any]]:
        with self._lock:
            if self._cached_leads is not None:
                return [dict(x) for x in self._cached_leads]

            leads = []
            lead_idx = 2
            for r in self.raw_rows:
                email = r.get("email", "").strip()
                name = r.get("name", "").strip()
                category = r.get("category", "").strip() or r.get("culture", "").strip()
                city = r.get("city", "").strip()
                website = r.get("website", "").strip()
                phone = r.get("phone", "").strip()
                address = r.get("adress", "").strip() or r.get("address", "").strip()

                # Skip ghost rows that contain no meaningful identifying data
                if not any([name, email, phone, city, website]):
                    continue

                company_name = name or "Valued Partner"

                # Merge with local state
                key = email.lower() if email else f"row_{lead_idx}"
                cached = self.state.get(key, {})
                if not cached and email:
                    for em in re.findall(r'[\w\.-]+@[\w\.-]+', email.lower()):
                        if em in self.state:
                            cached = self.state[em]
                            break
                norm_name = re.sub(r'[\W_]+', '', company_name.lower())
                if not cached and norm_name:
                    cached = self.state.get(f"name_{norm_name}", {})
                if not cached:
                    cached = self.state.get(f"row_{lead_idx}", {})

                status = cached.get("status") or r.get("status", "").strip() or "⚪ Очікує"
                gen_sheet = cached.get("generation_sheet") or r.get("generation sheet", "").strip()
                date = cached.get("date") or r.get("date", "").strip()

                lang = self._detect_language(
                    city=city,
                    address=address,
                    website=website,
                    phone=phone,
                    email=email,
                    name=company_name
                )

                country_info = self._detect_country(
                    city=city,
                    address=address,
                    website=website,
                    phone=phone,
                    email=email,
                    name=company_name,
                    raw_country=r.get("country", ""),
                    lang=lang
                )

                leads.append({
                    "row_number": lead_idx,
                    "company_name": company_name,
                    "country": country_info["name_uk"],
                    "country_bg": country_info["name_bg"],
                    "country_en": country_info["name_en"],
                    "country_code": country_info["code"],
                    "country_flag": country_info["flag"],
                    "category": category,
                    "city": city,
                    "website": website,
                    "phone": phone,
                    "email": email,
                    "language": lang,
                    "status": status,
                    "generation_sheet": gen_sheet,
                    "date": date,
                    "crops": f"{category} ({city})" if city else category,
                    "_raw": r
                })
                lead_idx += 1

            deduped = self._deduplicate_leads(leads)
            self._cached_leads = deduped
            return [dict(x) for x in deduped]

    def get_new_leads(self) -> List[Dict[str, Any]]:
        all_leads = self.get_all_leads()
        new_leads = []
        seen_emails = set()
        for l in all_leads:
            raw_em = l.get("email", "").strip()
            if not raw_em:
                continue
            st = l.get("status", "")
            if "🟡" in st or "✅" in st or "DRAFT_CREATED" in st:
                continue
            em_list = tuple(sorted(re.findall(r'[\w\.-]+@[\w\.-]+', raw_em.lower())))
            if em_list and em_list in seen_emails:
                continue
            if em_list:
                seen_emails.add(em_list)
            new_leads.append(l)
        return new_leads

    def _deduplicate_leads(self, leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merges duplicate leads based on:
        1. Matching email addresses
        2. Exact matching normalized company name
        3. Same specific website domain (e.g. villayustina.com)
        4. Same city AND matching base company name (e.g. Crama Panciu, Cegledi Gyumolcs, etc.)
        5. Same city AND matching phone number
        Preserves the highest priority status (✅ Sent > 🟡 Draft > ⚪ Pending/New),
        retains all enriched data (phones, websites, drafts), and re-indexes row numbers sequentially.
        """
        GENERIC_DOMAINS = {"gmail.com", "yahoo.com", "abv.bg", "otenet.gr", "hotmail.com", "mail.ru", "yandex.ru", "outlook.com", "icloud.com", "example.com", "culture.gr"}

        def normalize_name(n: str) -> str:
            return re.sub(r'[\W_]+', '', (n or '').lower())

        def extract_emails(em_str: str) -> set:
            return set(re.findall(r'[\w\.-]+@[\w\.-]+', (em_str or '').lower()))

        def base_name(n: str) -> str:
            s = re.sub(r'\b\d+\b', '', n or '')
            s = re.sub(r'\b(Gold|Bio|Reserve|Agro|Kft|SAS|OPG|Terroir|Estate|Farma|Hacienda|Agrícola|Еко|Тероар|Резерва|Голд|д\.о\.о\.|d\.o\.o\.|SRL|Sady|Viticola|Cantina|Azienda|Posestvo|Družstvo|Exploitation|Hof|Selektion|Vina|Organic|Groves|Fresh)\b', '', s, flags=re.I)
            return re.sub(r'[\W_]+', '', s.lower())

        def clean_city(c: str) -> str:
            return re.sub(r'[\W_]+', '', (c or '').lower())

        def clean_phone(p: str) -> str:
            d = re.sub(r'\D', '', p or '')
            return d[-8:] if len(d) >= 8 else ''

        def clean_domain(w: str) -> str:
            w_clean = re.sub(r'^https?://(www\.)?', '', (w or '').lower().strip().rstrip('/'))
            w_dom = w_clean.split('/')[0] if w_clean else ''
            if w_dom and w_dom not in GENERIC_DOMAINS and len(w_dom) > 4:
                return w_dom
            return ''

        def status_score(st: str) -> int:
            if not st:
                return 0
            if "✅" in st or "SENT" in st:
                return 3
            if "🟡" in st or "DRAFT" in st:
                return 2
            return 1

        # Precompute features once per lead to avoid expensive regexes in O(N^2) comparison loop
        features = []
        for l in leads:
            c_name = l.get("company_name", "")
            features.append({
                "n": normalize_name(c_name),
                "bn": base_name(c_name),
                "c": clean_city(l.get("city", "")),
                "e": extract_emails(l.get("email", "")),
                "p": clean_phone(l.get("phone", "")),
                "dom": clean_domain(l.get("website", ""))
            })

        groups = []
        visited = set()

        for i in range(len(leads)):
            if i in visited:
                continue
            grp = [i]
            visited.add(i)

            f1 = features[i]
            n1 = f1["n"]
            bn1 = f1["bn"]
            c1 = f1["c"]
            e1 = f1["e"]
            p1 = f1["p"]
            dom1 = f1["dom"]

            for j in range(i + 1, len(leads)):
                if j in visited:
                    continue
                f2 = features[j]
                n2 = f2["n"]
                bn2 = f2["bn"]
                c2 = f2["c"]
                e2 = f2["e"]
                p2 = f2["p"]
                dom2 = f2["dom"]

                email_match = bool(e1 and e2 and (e1 & e2))
                exact_name_match = bool(n1 and n2 and n1 == n2 and len(n1) > 3)
                domain_match = bool(dom1 and dom2 and dom1 == dom2)

                same_city = bool(c1 and c2 and (c1 in c2 or c2 in c1))
                city_basename_match = bool(same_city and bn1 and bn2 and bn1 == bn2 and len(bn1) > 3)
                city_phone_match = bool(same_city and p1 and p2 and p1 == p2)
                yustina_match = bool("yustina" in (n1 + dom1) and "yustina" in (n2 + dom2))

                if email_match or exact_name_match or domain_match or city_basename_match or city_phone_match or yustina_match:
                    grp.append(j)
                    visited.add(j)

            groups.append(grp)

        deduped = []
        for new_idx, grp in enumerate(groups, start=1):
            items = [leads[idx] for idx in grp]
            items.sort(key=lambda x: (
                status_score(x.get("status", "")),
                1 if x.get("generation_sheet") else 0,
                len(x.get("email", "")),
                len(x.get("phone", ""))
            ), reverse=True)

            best = dict(items[0])
            best["row_number"] = new_idx

            # Merge any missing fields from others in group
            for other_idx in grp[1:]:
                other = leads[other_idx]
                for f in ["website", "phone", "city", "adress", "generation_sheet", "date", "category"]:
                    if not best.get(f) and other.get(f):
                        best[f] = other[f]
                # Merge emails if not present
                best_emails = features[grp[0]]["e"]
                other_emails = features[other_idx]["e"]
                missing = other_emails - best_emails
                if missing:
                    best["email"] = best["email"] + ", " + ", ".join(sorted(missing))

            deduped.append(best)

        return deduped

    def _detect_language(self, city: str, address: str, website: str, phone: str = "", email: str = "", name: str = "") -> str:
        """
        Deep multi-factor language detection for TeraWet leads across 10 European target markets:
        Bulgaria (bg), Greece (el), Romania (ro), Hungary (hu), Italy (it),
        Slovenia (sl), Slovakia (sk), France (fr), Austria (de), Spain (es).
        """
        text = f"{name} {city} {address} {website} {email}".lower()
        phone_clean = re.sub(r'[\s\-\(\)\.]', '', phone)
        web_clean = (website or "").lower().strip()
        email_clean = (email or "").lower().strip()

        # 1. Phone country codes (Direct, infallible indicator)
        if phone_clean.startswith(("+359", "00359", "359")):
            return "bg"
        if phone_clean.startswith(("+30", "0030", "30")):
            return "el"
        if phone_clean.startswith(("+40", "0040", "40")):
            return "ro"
        if phone_clean.startswith(("+36", "0036", "36")):
            return "hu"
        if phone_clean.startswith(("+39", "0039", "39")):
            return "it"
        if phone_clean.startswith(("+386", "00386", "386")):
            return "sl"
        if phone_clean.startswith(("+421", "00421", "421")):
            return "sk"
        if phone_clean.startswith(("+33", "0033", "33")):
            return "fr"
        if phone_clean.startswith(("+43", "0043", "43")):
            return "de"
        if phone_clean.startswith(("+34", "0034", "34")):
            return "es"
        if phone_clean.startswith(("+381", "00381", "381")):
            return "sr"
        if phone_clean.startswith(("+385", "00385", "385")):
            return "hr"

        # 2. Domain / TLD / Email provider matching
        def _has_tld(tld: str) -> bool:
            return email_clean.endswith(tld) or bool(re.search(rf'{re.escape(tld)}(/|\?|$)', web_clean))

        if any(ext in text for ext in ["@abv.bg", "@mail.bg", "@dir.bg", "@gbg.bg"]) or _has_tld(".bg"):
            return "bg"
        if _has_tld(".gr") or _has_tld(".el"):
            return "el"
        if _has_tld(".ro"):
            return "ro"
        if _has_tld(".hu"):
            return "hu"
        if _has_tld(".it"):
            return "it"
        if _has_tld(".si"):
            return "sl"
        if _has_tld(".sk"):
            return "sk"
        if _has_tld(".fr"):
            return "fr"
        if _has_tld(".at"):
            return "de"
        if _has_tld(".es"):
            return "es"
        if _has_tld(".rs"):
            return "sr"
        if _has_tld(".hr"):
            return "hr"

        # 3. Greek Alphabet Characters
        if any(c in text for c in "αβγδεζηθικλμνξοπρστυφχψωάέήίόύώ"):
            return "el"

        # 4. Serbian specific Cyrillic
        if any(c in text for c in "ђјљњћџ"):
            return "sr"

        # 5. Cyrillic Characters (Bulgarian target market)
        if any(c in text for c in "абвгдежзийклмнопрстуфхцчшщъьюя"):
            if any(k in text for k in ["србиј", "београд", "нови сад", "војводин", "чачак", "нишу", "топол"]):
                return "sr"
            return "bg"

        # 6. Country & Regional City Keywords
        # Serbia
        sr_keywords = [
            "serbia", "srbija", "србија", "beograd", "belgrade", "novi sad", "нови сад", "vojvodina",
            "војводина", "fruška gora", "fruska gora", "фрушка гора", "subotica", "суботица", "šumadija",
            "sumadija", "шумадија", "topola", "топола", "negotin", "неготин", "župa", "zupa", "жупа",
            "aleksandrovac", "александровац", "čačak", "cacak", "чачак", "smederevo", "смедерево",
            "pančevo", "pancevo", "панчево", "kruševac", "krusevac", "крушевац", "sremski karlovci"
        ]
        if any(k in text for k in sr_keywords):
            return "sr"

        # Croatia
        hr_keywords = [
            "croatia", "hrvatska", "zagreb", "split", "rijeka", "osijek", "istra", "istria", "poreč",
            "porec", "rovinj", "motovun", "pelješac", "peljesac", "dingač", "dingac", "kutjevo",
            "slavonija", "baranja", "ilok", "zadar", "šibenik", "sibenik", "neretva", "opuzen",
            "metković", "metkovic", "vukovar", "kaštela", "kastela", "lučko"
        ]
        if any(k in text for k in hr_keywords):
            return "hr"

        # Hungary
        hu_keywords = [
            "hungary", "magyarország", "magyar", "budapest", "debrecen", "szeged", "miskolc", "pécs", "győr",
            "kecskemét", "székesfehérvár", "eger", "tokaj", "villány", "balaton", "sopron", "szekszárd",
            "bács-kiskun", "szabolcs", "nyíregyháza", "cegléd", "gönc", "badacsony", "mád"
        ]
        if any(k in text for k in hu_keywords):
            return "hu"

        # Slovenia
        sl_keywords = [
            "slovenia", "slovenija", "ljubljana", "maribor", "kranj", "celje", "koper", "novo mesto",
            "velenje", "nova gorica", "krško", "brda", "vipava", "goriška brda", "šentjernej", "ptuj",
            "ormož", "ajdovščina", "slovenska istra", "dobrovo", "bizeljsko", "posavje"
        ]
        if any(k in text for k in sl_keywords):
            return "sl"

        # Slovakia
        sk_keywords = [
            "slovakia", "slovensko", "bratislava", "košice", "prešov", "žilina", "banská bystrica", "nitra",
            "trnava", "martin", "trenčín", "poprad", "tokajská", "malokarpatská", "pezinok", "modra",
            "dunajská streda", "dunajská lužná", "komárno", "strekov", "piešťany", "levice", "malá tŕňa"
        ]
        if any(k in text for k in sk_keywords):
            return "sk"

        # Italy
        it_keywords = [
            "italy", "italia", "roma", "rome", "milano", "milan", "napoli", "torino", "palermo", "bologna",
            "firenze", "florence", "verona", "bari", "catania", "venezia", "toscana", "puglia", "sicilia",
            "veneto", "piemonte", "chianti", "barolo", "prosecco", "modena", "emilia-romagna", "foggia",
            "salento", "taranto", "langhe", "marsala", "montalcino", "etna", "pistoia", "cesena"
        ]
        if any(k in text for k in it_keywords):
            return "it"

        # France
        fr_keywords = [
            "france", "paris", "marseille", "lyon", "toulouse", "nice", "nantes", "montpellier", "strasbourg",
            "bordeaux", "gironde", "reims", "bourgogne", "provence", "champagne", "languedoc", "rhone",
            "rhône", "alsace", "cognac", "avignon", "nimes", "perpignan", "saint-émilion", "vaucluse",
            "cavaillon", "minervois", "beaune", "arboriculture"
        ]
        if any(k in text for k in fr_keywords):
            return "fr"

        # Austria
        de_keywords = [
            "austria", "österreich", "oesterreich", "wien", "vienna", "graz", "linz", "salzburg", "innsbruck",
            "klagenfurt", "wachau", "burgenland", "steiermark", "niederösterreich", "krems", "neusiedl",
            "gols", "gamlitz", "kamptal", "langenlois", "weinviertel", "retz", "weiz", "tulln"
        ]
        if any(k in text for k in de_keywords):
            return "de"

        # Romania
        ro_keywords = [
            "romania", "românia", "bucuresti", "bucharest", "cluj", "timisoara", "iasi", "constanta",
            "craiova", "brasov", "oradea", "vrancea", "focsani", "focșani", "dealu mare", "prahova",
            "cotnari", "murfatlar", "recas", "recaș", "drăgășani", "dragasani", "panciu", "voinesti"
        ]
        if any(k in text for k in ro_keywords):
            return "ro"

        # Spain
        es_keywords = [
            "spain", "españa", "espana", "madrid", "barcelona", "valencia", "sevilla", "seville", "zaragoza",
            "malaga", "murcia", "cordoba", "córdoba", "jerez", "andalucia", "andalucía", "rioja", "la mancha",
            "alicante", "almeria", "almería", "jaen", "jaén", "ubeda", "úbeda", "tomelloso", "cieza", "el ejido"
        ]
        if any(k in text for k in es_keywords):
            return "es"

        # Bulgarian Cities & Keywords
        bg_keywords = [
            "bulgaria", "българия", "българ",
            "plovdiv", "sofia", "varna", "burgas", "bourgas", "stara zagora", "ruse", "rousse", "pleven",
            "sliven", "dobrich", "shumen", "pernik", "haskovo", "yambol", "pazardzhik", "blagoevgrad",
            "veliko tarnovo", "gabrovo", "vratsa", "vidin", "asenovgrad", "kazanlak", "kyustendil",
            "kardzhali", "montana", "dimitrovgrad", "lovech", "silistra", "targovishte", "razgrad",
            "smolyan", "brestovitsa", "ustina", "pomorie", "nesebar", "sozopol", "karlovo", "sandanski",
            "petrich", "bansko", "razlog", "gotse delchev", "chirpan", "karnobat", "balchik", "svishtov",
            "gorna oryahovitsa", "sevlievo", "troyan", "panagyurishte", "peshtera", "velingrad", "septemvri",
            "harmanli", "svilengrad", "lyubimets", "suhindol", "ognyanovo", "parvomay"
        ]
        if any(k in text for k in bg_keywords):
            return "bg"

        # Greek Cities & Regions
        gr_keywords = [
            "greece", "hellas", "ellada", "athens", "athina", "thessaloniki", "larissa", "larisa",
            "patras", "patra", "heraklion", "irakleio", "chania", "rethymno", "rhodes", "rodos",
            "kalamata", "corinth", "korinthos", "sparta", "sparti", "trikala", "karditsa",
            "volos", "halkidiki", "chalkidiki", "kassandra", "sithonia", "drama", "kavala",
            "naoussa", "nemea", "argos", "messinia", "peloponnese", "thessaly", "crete", "epanomi"
        ]
        if any(k in text for k in gr_keywords):
            return "el"

        return "bg" if ("bulgar" in text or ".bg" in text) else "el"

    def _detect_country(self, city: str = "", address: str = "", website: str = "", phone: str = "", email: str = "", name: str = "", raw_country: str = "", lang: str = "") -> Dict[str, str]:
        """
        Determines the country name (Ukrainian, Bulgarian, English) and ISO code (2-letter)
        along with the national flag emoji for any lead.
        """
        rc = (raw_country or "").lower().strip()
        text = f"{rc} {name} {city} {address} {website} {email}".lower()
        phone_clean = re.sub(r'[\s\-\(\)\.]', '', phone or "")
        web_clean = (website or "").lower().strip()

        # Check explicit indicators & phone prefixes
        if "srb" in rc or "серб" in rc or "србиј" in text or "srbij" in text or ".rs" in web_clean or phone_clean.startswith(("+381", "00381", "381")) or lang == "sr":
            return {"code": "SR", "name_uk": "Сербія", "name_bg": "Сърбия", "name_en": "Serbia", "flag": "🇷🇸"}

        if "hrv" in rc or "хорв" in rc or "хърв" in rc or "hrvatska" in text or "croatia" in rc or ".hr" in web_clean or phone_clean.startswith(("+385", "00385", "385")) or lang == "hr":
            return {"code": "HR", "name_uk": "Хорватія", "name_bg": "Хърватия", "name_en": "Croatia", "flag": "🇭🇷"}

        if "rom" in rc or "рум" in rc or "românia" in text or "romania" in text or ".ro" in web_clean or phone_clean.startswith(("+40", "0040", "40")) or lang == "ro":
            return {"code": "RO", "name_uk": "Румунія", "name_bg": "Румъния", "name_en": "Romania", "flag": "🇷🇴"}

        if "magy" in rc or "угор" in rc or "унгар" in rc or "hungary" in rc or "magyarország" in text or ".hu" in web_clean or phone_clean.startswith(("+36", "0036", "36")) or lang == "hu":
            return {"code": "HU", "name_uk": "Угорщина", "name_bg": "Унгария", "name_en": "Hungary", "flag": "🇭🇺"}

        if "ita" in rc or "італ" in rc or "итал" in rc or "italia" in text or "italy" in rc or ".it" in web_clean or phone_clean.startswith(("+39", "0039", "39")) or lang == "it":
            return {"code": "IT", "name_uk": "Італія", "name_bg": "Италия", "name_en": "Italy", "flag": "🇮🇹"}

        if "slovensk" in rc or "словач" in rc or "словашка" in rc or "slovakia" in rc or "slovensko" in text or ".sk" in web_clean or phone_clean.startswith(("+421", "00421", "421")) or lang == "sk":
            return {"code": "SK", "name_uk": "Словаччина", "name_bg": "Словакия", "name_en": "Slovakia", "flag": "🇸🇰"}

        if "slovenij" in rc or "словен" in rc or "slovenia" in rc or "slovenija" in text or ".si" in web_clean or phone_clean.startswith(("+386", "00386", "386")) or lang == "sl":
            return {"code": "SL", "name_uk": "Словенія", "name_bg": "Словения", "name_en": "Slovenia", "flag": "🇸🇮"}

        if "fran" in rc or "фран" in rc or "france" in text or ".fr" in web_clean or phone_clean.startswith(("+33", "0033", "33")) or lang == "fr":
            return {"code": "FR", "name_uk": "Франція", "name_bg": "Франция", "name_en": "France", "flag": "🇫🇷"}

        if "österreich" in text or "austria" in rc or "австр" in rc or ".at" in web_clean or phone_clean.startswith(("+43", "0043", "43")):
            return {"code": "AT", "name_uk": "Австрія", "name_bg": "Австрия", "name_en": "Austria", "flag": "🇦🇹"}

        if "deutsch" in text or "germany" in rc or "німеч" in rc or "герман" in rc or ".de" in web_clean or phone_clean.startswith(("+49", "0049", "49")):
            return {"code": "DE", "name_uk": "Німеччина", "name_bg": "Германия", "name_en": "Germany", "flag": "🇩🇪"}

        if "espa" in rc or "іспан" in rc or "испан" in rc or "spain" in rc or "españa" in text or ".es" in web_clean or phone_clean.startswith(("+34", "0034", "34")) or lang == "es":
            return {"code": "ES", "name_uk": "Іспанія", "name_bg": "Испания", "name_en": "Spain", "flag": "🇪🇸"}

        if "бълг" in rc or "болг" in rc or "bulgaria" in rc or "българия" in text or ".bg" in web_clean or phone_clean.startswith(("+359", "00359", "359")) or lang == "bg":
            return {"code": "BG", "name_uk": "Болгарія", "name_bg": "България", "name_en": "Bulgaria", "flag": "🇧🇬"}

        if "ελλ" in rc or "грец" in rc or "гръц" in rc or "greece" in rc or "ελλάδα" in text or ".gr" in web_clean or phone_clean.startswith(("+30", "0030", "30")) or lang == "el":
            return {"code": "EL", "name_uk": "Греція", "name_bg": "Гърция", "name_en": "Greece", "flag": "🇬🇷"}

        # Fallback to language
        lang_country_map = {
            "el": {"code": "EL", "name_uk": "Греція", "name_bg": "Гърция", "name_en": "Greece", "flag": "🇬🇷"},
            "bg": {"code": "BG", "name_uk": "Болгарія", "name_bg": "България", "name_en": "Bulgaria", "flag": "🇧🇬"},
            "ro": {"code": "RO", "name_uk": "Румунія", "name_bg": "Румъния", "name_en": "Romania", "flag": "🇷🇴"},
            "es": {"code": "ES", "name_uk": "Іспанія", "name_bg": "Испания", "name_en": "Spain", "flag": "🇪🇸"},
            "it": {"code": "IT", "name_uk": "Італія", "name_bg": "Италия", "name_en": "Italy", "flag": "🇮🇹"},
            "fr": {"code": "FR", "name_uk": "Франція", "name_bg": "Франция", "name_en": "France", "flag": "🇫🇷"},
            "de": {"code": "AT", "name_uk": "Австрія", "name_bg": "Австрия", "name_en": "Austria", "flag": "🇦🇹"},
            "hu": {"code": "HU", "name_uk": "Угорщина", "name_bg": "Унгария", "name_en": "Hungary", "flag": "🇭🇺"},
            "sl": {"code": "SL", "name_uk": "Словенія", "name_bg": "Словения", "name_en": "Slovenia", "flag": "🇸🇮"},
            "sk": {"code": "SK", "name_uk": "Словаччина", "name_bg": "Словакия", "name_en": "Slovakia", "flag": "🇸🇰"},
            "sr": {"code": "SR", "name_uk": "Сербія", "name_bg": "Сърбия", "name_en": "Serbia", "flag": "🇷🇸"},
            "hr": {"code": "HR", "name_uk": "Хорватія", "name_bg": "Хърватия", "name_en": "Croatia", "flag": "🇭🇷"}
        }
        return lang_country_map.get(lang, {"code": "EU", "name_uk": "ЄС", "name_bg": "ЕС", "name_en": "EU", "flag": "🇪🇺"})

    def mark_draft_created(self, lead: Dict[str, Any], draft_id: str, subject: str, body_plain: str):
        raw_email = lead.get("email", "").strip()
        row_num = lead.get("row_number", 0)
        today = datetime.now().strftime("%Y-%m-%d")

        cached_data = {
            "status": "🟡 Чернетка на перевірці",
            "draft_id": draft_id,
            "date": today,
            "subject": subject,
            "generation_sheet": f"Subject: {subject}\n\n{body_plain}"
        }
        if raw_email:
            self.state[raw_email.lower()] = cached_data
            for em in re.findall(r'[\w\.-]+@[\w\.-]+', raw_email.lower()):
                self.state[em] = cached_data
        if row_num:
            self.state[f"row_{row_num}"] = cached_data
        comp_name = re.sub(r'[\W_]+', '', lead.get("company_name", "").lower())
        if comp_name:
            self.state[f"name_{comp_name}"] = cached_data

        self._save_state()
        logger.info(f"Updated lead {lead.get('company_name')} -> '🟡 Чернетка на перевірці' in local database.")
        self.export_updated_csv()

    def export_updated_csv(self) -> Path:
        """
        Exports the updated sheet into updated_google_sheet.csv with deduplication.
        """
        if not self.raw_headers:
            return UPDATED_CSV_FILE

        leads = self.get_all_leads()
        updated_rows = []
        for l in leads:
            raw = l.get("_raw", {})
            row_copy = {fn: raw.get(fn, "") for fn in self.raw_headers}
            row_copy["name"] = l.get("company_name", "")
            row_copy["email"] = l.get("email", "")
            row_copy["phone"] = l.get("phone", "")
            row_copy["website"] = l.get("website", "")
            row_copy["city"] = l.get("city", "")
            row_copy["status"] = l.get("status", "")
            row_copy["date"] = l.get("date", "")
            row_copy["generation sheet"] = l.get("generation_sheet", "")
            if "country" in self.raw_headers:
                row_copy["country"] = l.get("country", "")
            updated_rows.append(row_copy)

        with open(UPDATED_CSV_FILE, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.raw_headers)
            writer.writeheader()
            writer.writerows(updated_rows)

        return UPDATED_CSV_FILE

    def sync_sent_emails(self, gmail_service: Any) -> int:
        """
        Synchronizes lead statuses against both Gmail Sent Mail and Gmail Drafts folders.
        1. Multi-email support: splits comma/semicolon-separated addresses.
        2. Draft sync: detects active drafts directly from Gmail.
        3. Sent sync: detects actually sent emails and sets status to '✅ Лист відправлено'.
        """
        if not gmail_service or not hasattr(gmail_service, "get_sent_recipients"):
            return 0

        updated_count = 0
        today = datetime.now().strftime("%Y-%m-%d")

        # 1. Fetch Drafts from Gmail
        draft_recipients = {}
        if hasattr(gmail_service, "get_draft_recipients"):
            try:
                draft_recipients = gmail_service.get_draft_recipients(limit=100)
            except Exception as e:
                logger.warning(f"Notice getting draft recipients: {e}")

        # 2. Fetch Sent Emails from Gmail
        sent_recipients = {}
        try:
            sent_recipients = gmail_service.get_sent_recipients(limit=250)
        except Exception as e:
            logger.warning(f"Notice getting sent recipients: {e}")

        # 3. Fetch Bounced Emails from Gmail (Mailer-Daemon delivery failures)
        bounced_recipients = {}
        if hasattr(gmail_service, "get_bounced_recipients"):
            try:
                bounced_recipients = gmail_service.get_bounced_recipients(limit=150)
            except Exception as e:
                logger.warning(f"Notice getting bounced recipients: {e}")

        if not sent_recipients and not draft_recipients and not bounced_recipients:
            return 0

        all_leads = self.get_all_leads()

        for lead in all_leads:
            raw_email = lead.get("email", "").strip()
            if not raw_email:
                continue

            lead_emails = [e.lower() for e in re.findall(r'[\w\.-]+@[\w\.-]+', raw_email)]
            if not lead_emails:
                continue

            current_status = lead.get("status", "")
            lead_row = lead.get("row_number")
            comp_name = re.sub(r'[\W_]+', '', lead.get("company_name", "").lower())

            # Priority 1: Check if BOUNCED (Mailer-Daemon delivery failure: address does not exist)
            matched_bounced = next((e for e in lead_emails if e in bounced_recipients), None)
            if matched_bounced:
                if "❌" not in current_status:
                    bounce_info = bounced_recipients[matched_bounced]
                    cached_data = {
                        "status": "❌ Помилка доставки (Email не існує)",
                        "date": today,
                        "subject": bounce_info.get("reason", "Gmail: Адреса не знайдена")
                    }
                    self.state[raw_email.lower()] = cached_data
                    if lead_row:
                        self.state[f"row_{lead_row}"] = cached_data
                    if comp_name:
                        self.state[f"name_{comp_name}"] = cached_data
                    for em in lead_emails:
                        self.state[em] = cached_data

                    updated_count += 1
                    logger.info(f"Detected BOUNCED email for {lead.get('company_name')} ({matched_bounced})! Status -> '❌ Помилка доставки (Email не існує)'")
                continue

            # Priority 2: Check if SENT
            matched_sent = next((e for e in lead_emails if e in sent_recipients), None)
            if matched_sent:
                if "✅" not in current_status and "❌" not in current_status:
                    sent_info = sent_recipients[matched_sent]
                    cached_data = {
                        "status": "✅ Лист відправлено",
                        "date": today,
                        "subject": sent_info.get("subject", "")
                    }
                    self.state[raw_email.lower()] = cached_data
                    if lead_row:
                        self.state[f"row_{lead_row}"] = cached_data
                    if comp_name:
                        self.state[f"name_{comp_name}"] = cached_data
                    for em in lead_emails:
                        self.state[em] = cached_data

                    updated_count += 1
                    logger.info(f"Detected sent email for {lead.get('company_name')} ({matched_sent})! Status -> '✅ Лист відправлено'")
                continue

            # Priority 3: Check if DRAFT in Gmail
            matched_draft = next((e for e in lead_emails if e in draft_recipients), None)
            if matched_draft:
                if "✅" not in current_status and "🟡" not in current_status and "❌" not in current_status:
                    draft_info = draft_recipients[matched_draft]
                    cached_data = {
                        "status": "🟡 Чернетка на перевірці",
                        "date": today,
                        "subject": draft_info.get("subject", ""),
                        "generation_sheet": f"Subject: {draft_info.get('subject', '')}"
                    }
                    self.state[raw_email.lower()] = cached_data
                    if lead_row:
                        self.state[f"row_{lead_row}"] = cached_data
                    if comp_name:
                        self.state[f"name_{comp_name}"] = cached_data
                    for em in lead_emails:
                        self.state[em] = cached_data

                    updated_count += 1
                    logger.info(f"Detected active Gmail draft for {lead.get('company_name')} ({matched_draft})! Status -> '🟡 Чернетка на перевірці'")

        if updated_count > 0:
            self._save_state()
            self.export_updated_csv()

        return updated_count

    def verify_all_leads_domains(self) -> int:
        """
        Runs DNS MX verification across all leads in database.
        Marks dead domains with status '⚠️ Недійсний email (Домен не існує)'
        (only for leads that aren't already confirmed sent or bounced).
        Returns count of newly flagged leads.
        """
        from email_verifier import EmailVerifierService
        verifier = EmailVerifierService()

        all_leads = self.get_all_leads()
        flagged_count = 0
        today = datetime.now().strftime("%Y-%m-%d")

        for lead in all_leads:
            raw_email = lead.get("email", "").strip()
            if not raw_email:
                continue

            current_status = lead.get("status", "")
            # Don't touch leads that are confirmed sent or already flagged as bounced/invalid
            if "✅" in current_status or "❌" in current_status or "⚠️" in current_status:
                continue

            lead_emails = [e.lower() for e in re.findall(r'[\w\.-]+@[\w\.-]+', raw_email)]
            if not lead_emails:
                continue

            is_valid, reason = verifier.verify_email(lead_emails[0])
            if not is_valid:
                lead_row = lead.get("row_number")
                comp_name = re.sub(r'[\W_]+', '', lead.get("company_name", "").lower())
                cached_data = {
                    "status": "⚠️ Недійсний email (Домен не існує)",
                    "date": today,
                    "subject": reason
                }
                self.state[raw_email.lower()] = cached_data
                if lead_row:
                    self.state[f"row_{lead_row}"] = cached_data
                if comp_name:
                    self.state[f"name_{comp_name}"] = cached_data
                for em in lead_emails:
                    self.state[em] = cached_data

                flagged_count += 1

        if flagged_count > 0:
            self._save_state()
            self.export_updated_csv()
            logger.info(f"Flagged {flagged_count} leads with invalid/dead email domains.")

        return flagged_count

    def mark_status(self, key: str, new_status: str):
        """Manually overrides status for a lead key."""
        today = datetime.now().strftime("%Y-%m-%d")
        cached = self.state.get(key, {})
        cached["status"] = new_status
        cached["date"] = today
        self.state[key] = cached
        if "@" in key:
            self.state[key.lower()] = cached
            for em in re.findall(r'[\w\.-]+@[\w\.-]+', key.lower()):
                self.state[em] = cached
        self._save_state()
        self.export_updated_csv()

