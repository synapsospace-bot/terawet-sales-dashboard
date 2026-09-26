import csv
import io
import re
import json
import logging
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
            "name", "category", "culture", "adress", "city", "zip", "website", "phone", "coordinates", "email", "instagram", "crop", "status", "generation sheet", "date"
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
                if new_headers:
                    self.raw_headers = new_headers
                self.raw_rows = merged_rows
                logger.info(f"Synced live sheet: {len(valid_sheet_rows)} sheet leads + {len(imported_leads)} imported leads ({len(self.raw_rows)} total).")
                self.export_updated_csv()
        except Exception as e:
            logger.warning(f"Live Google Sheet sync notice (retaining {len(self.raw_rows)} cached rows): {e}")
            if not self.raw_rows:
                self._load_local_csv()
                self._merge_imported_leads()

    def get_all_leads(self) -> List[Dict[str, Any]]:
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

            leads.append({
                "row_number": lead_idx,
                "company_name": company_name,
                "category": category,
                "city": city,
                "website": website,
                "phone": phone,
                "email": email,
                "language": lang,
                "status": status,
                "generation_sheet": gen_sheet,
                "date": date,
                "crops": f"{category} ({city})" if city else category
            })
            lead_idx += 1
        return leads

    def get_new_leads(self) -> List[Dict[str, Any]]:
        all_leads = self.get_all_leads()
        new_leads = []
        for l in all_leads:
            if not l["email"]:
                continue
            st = l["status"]
            if "🟡" not in st and "✅" not in st and "DRAFT_CREATED" not in st:
                new_leads.append(l)
        return new_leads

    def _detect_language(self, city: str, address: str, website: str, phone: str = "", email: str = "", name: str = "") -> str:
        """
        Deep multi-factor language detection for TeraWet leads.
        Properly identifies Bulgarian leads (Latin/Cyrillic cities like Plovdiv, +359 phones, .bg domains),
        Greek leads (+30, .gr, Greek alphabet, Greek regions), Romanian, Spanish, etc.
        """
        text = f"{name} {city} {address} {website} {email}".lower()
        phone_clean = re.sub(r'[\s\-\(\)\.]', '', phone)

        # 1. Phone country codes
        if phone_clean.startswith("+359") or phone_clean.startswith("00359") or phone_clean.startswith("359"):
            return "bg"
        if phone_clean.startswith("+30") or phone_clean.startswith("0030") or phone_clean.startswith("30"):
            return "el"
        if phone_clean.startswith("+40") or phone_clean.startswith("0040") or phone_clean.startswith("40"):
            return "ro"
        if phone_clean.startswith("+34") or phone_clean.startswith("0034") or phone_clean.startswith("34"):
            return "es"
        if phone_clean.startswith("+39") or phone_clean.startswith("0039") or phone_clean.startswith("39"):
            return "it"

        # 2. Domain / TLD / Provider matching
        if any(ext in text for ext in [".bg", "@abv.bg", "@mail.bg", "@dir.bg", "@gbg.bg"]):
            return "bg"
        if any(ext in text for ext in [".gr", ".el"]):
            return "el"
        if any(ext in text for ext in [".ro"]):
            return "ro"
        if any(ext in text for ext in [".es"]):
            return "es"

        # 3. Greek Alphabet Characters
        if any(c in text for c in "αβγδεζηθικλμνξοπρστυφχψω"):
            return "el"

        # 4. Bulgarian Cities & Keywords (both Latin and Cyrillic)
        bg_keywords = [
            "bulgaria", "българия", "българ",
            "plovdiv", "пловдив", "sofia", "софия", "varna", "варна", "burgas", "bourgas", "бургас",
            "stara zagora", "стара загора", "ruse", "rousse", "русе", "pleven", "плевен",
            "sliven", "сливен", "dobrich", "добрич", "shumen", "шумен", "pernik", "перник",
            "haskovo", "хасково", "yambol", "ямбол", "pazardzhik", "пазарджик",
            "blagoevgrad", "благоевград", "veliko tarnovo", "търново", "gabrovo", "габрово",
            "vratsa", "враца", "vidin", "видин", "asenovgrad", "асеновград",
            "kazanlak", "казанлък", "kyustendil", "кюстендил", "kardzhali", "кърджали",
            "montana", "монтана", "dimitrovgrad", "димитровград", "lovech", "ловеч",
            "silistra", "силистра", "targovishte", "търговище", "razgrad", "разград",
            "smolyan", "смолян", "brestovitsa", "брестовица", "ustina", "устина",
            "momin prohod", "момин проход", "pomorie", "поморие", "nesebar", "несебър",
            "sozopol", "созопол", "karlovo", "карлово", "sopot", "сопот",
            "sandanski", "сандански", "petrich", "петрич", "bansko", "банско",
            "razlog", "разлог", "gotse delchev", "гоце делчев", "chirpan", "чирпан",
            "karnobat", "карнобат", "balchik", "балчик", "kavarna", "каварна",
            "svishtov", "свищов", "gorna oryahovitsa", "горна оряховица",
            "sevlievo", "севлиево", "troyan", "троян", "panagyurishte", "панагюрище",
            "peshtera", "пещера", "velingrad", "велинград", "septemvri", "септември",
            "harmanli", "харманли", "svilengrad", "свиленград", "любимец", "lyubimets",
            "suhindol", "сухиндол", "огняново", "ognyanovo", "първомай", "parvomay", "parvomai"
        ]
        if any(k in text for k in bg_keywords):
            return "bg"

        # 5. Cyrillic Characters (Bulgarian target market)
        if any(c in text for c in "абвгдежзийклмнопрстуфхцчшщъьюя"):
            return "bg"

        # 6. Greek Cities & Regions (Latin)
        gr_keywords = [
            "greece", "hellas", "ellada", "athens", "athina", "thessaloniki", "larissa", "larisa",
            "patras", "patra", "heraklion", "irakleio", "chania", "rethymno", "rhodes", "rodos",
            "kalamata", "corinth", "korinthos", "sparta", "sparti", "trikala", "karditsa",
            "volos", "halkidiki", "chalkidiki", "kassandra", "kassandreia", "sithonia",
            "drama", "kavala", "naoussa", "nemea", "argos", "messinia", "peloponnese",
            "thessaly", "crete", "mati", "marathoussa", "monopigado", "epanomi", "petralona"
        ]
        if any(k in text for k in gr_keywords):
            return "el"

        # 7. Romanian / Spanish keywords
        ro_keywords = ["romania", "bucuresti", "bucharest", "cluj", "timisoara", "iasi", "constanta", "craiova", "brasov"]
        if any(k in text for k in ro_keywords):
            return "ro"

        es_keywords = ["spain", "españa", "madrid", "barcelona", "valencia", "sevilla", "seville", "zaragoza", "malaga", "murcia", "cordoba", "jerez", "andalucia"]
        if any(k in text for k in es_keywords):
            return "es"

        return "bg" if ("bulgar" in text or "bg" in text) else "el"

    def mark_draft_created(self, lead: Dict[str, Any], draft_id: str, subject: str, body_plain: str):
        email = lead.get("email", "")
        row_num = lead.get("row_number", 0)
        today = datetime.now().strftime("%Y-%m-%d")

        key = email if email else f"row_{row_num}"
        self.state[key] = {
            "status": "🟡 Чернетка на перевірці",
            "draft_id": draft_id,
            "date": today,
            "subject": subject,
            "generation_sheet": f"Subject: {subject}\n\n{body_plain}"
        }
        self._save_state()
        logger.info(f"Updated lead {lead.get('company_name')} -> '🟡 Чернетка на перевірці' in local database.")
        self.export_updated_csv()

    def export_updated_csv(self) -> Path:
        """
        Exports the updated sheet into updated_google_sheet.csv.
        """
        if not self.raw_headers:
            return UPDATED_CSV_FILE

        updated_rows = []
        lead_num = 2
        for r in self.raw_rows:
            if not any(r.get(k, "").strip() for k in ["name", "email", "phone", "city", "website"]):
                continue
            row_copy = {fn: r.get(fn, "") for fn in self.raw_headers}
            email = row_copy.get("email", "").strip().lower()
            key = email if email else f"row_{lead_num}"
            cached = self.state.get(key)

            if cached:
                row_copy["status"] = cached.get("status", row_copy.get("status", ""))
                row_copy["date"] = cached.get("date", row_copy.get("date", ""))
                row_copy["generation sheet"] = cached.get("generation_sheet", row_copy.get("generation sheet", ""))

            updated_rows.append(row_copy)
            lead_num += 1

        with open(UPDATED_CSV_FILE, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.raw_headers)
            writer.writeheader()
            writer.writerows(updated_rows)

        return UPDATED_CSV_FILE

    def sync_sent_emails(self, gmail_service: Any) -> int:
        """
        Queries sent emails from Gmail IMAP and updates lead status to '✅ Лист відправлено'.
        """
        if not gmail_service or not hasattr(gmail_service, "get_sent_recipients"):
            return 0

        sent_recipients = gmail_service.get_sent_recipients(limit=250)
        if not sent_recipients:
            return 0

        updated_count = 0
        all_leads = self.get_all_leads()

        for lead in all_leads:
            email = lead.get("email", "").strip().lower()
            if not email:
                continue

            if email in sent_recipients:
                current_status = lead.get("status", "")
                if "✅" not in current_status:
                    sent_info = sent_recipients[email]
                    today = datetime.now().strftime("%Y-%m-%d")
                    key = email

                    cached = self.state.get(key, {})
                    cached["status"] = "✅ Лист відправлено"
                    cached["date"] = today
                    if "subject" not in cached and sent_info.get("subject"):
                        cached["subject"] = sent_info["subject"]
                    self.state[key] = cached
                    updated_count += 1
                    logger.info(f"Detected sent email to {email}! Status -> '✅ Лист відправлено'")

        if updated_count > 0:
            self._save_state()
            self.export_updated_csv()

        return updated_count

    def mark_status(self, key: str, new_status: str):
        """Manually overrides status for a lead key."""
        today = datetime.now().strftime("%Y-%m-%d")
        cached = self.state.get(key, {})
        cached["status"] = new_status
        cached["date"] = today
        self.state[key] = cached
        self._save_state()
        self.export_updated_csv()

