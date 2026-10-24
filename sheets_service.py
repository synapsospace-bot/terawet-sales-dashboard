import os
import time
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

def safe_atomic_write_json(target_path: Path, data: Any):
    """
    Atomically writes JSON to disk using a temporary file, keeps a .bak copy,
    and performs an atomic os.replace.
    Guarantees 100% zero data corruption or 0-byte truncation on crash or power loss.
    """
    target_path = Path(target_path)
    tmp_path = target_path.with_suffix(f".tmp_{os.getpid()}_{int(time.time()*1000)}")
    bak_path = target_path.with_suffix(target_path.suffix + ".bak")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if target_path.exists() and target_path.stat().st_size > 0:
            try:
                import shutil
                shutil.copy2(target_path, bak_path)
            except Exception:
                pass
        os.replace(tmp_path, target_path)
    except Exception as e:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        raise e

def sanitize_csv_field(val: Any) -> Any:
    """
    Escapes formula injection characters (=, +, -, @) to protect spreadsheet users.
    """
    if isinstance(val, str) and val and val[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + val
    return val

def safe_atomic_write_csv(target_path: Path, fieldnames: List[str], rows: List[Dict[str, Any]]):
    """
    Atomically writes CSV with formula injection protection.
    """
    target_path = Path(target_path)
    tmp_path = target_path.with_suffix(f".tmp_{os.getpid()}_{int(time.time()*1000)}")
    try:
        with open(tmp_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                cleaned = {fn: sanitize_csv_field(r.get(fn, "")) for fn in fieldnames}
                writer.writerow(cleaned)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target_path)
    except Exception as e:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        raise e

from lead_deduplicator import (
    MasterSentRegistry,
    extract_clean_emails,
    extract_corporate_domains,
    clean_phone_digits,
    clean_tokens,
    clean_core_slug,
    GENERIC_DOMAINS
)

def normalize_comp_name(name_str: Any) -> str:
    if not name_str:
        return ""
    return clean_core_slug(name_str)

class LeadDataService:
    """
    Manages reading from the user's live Google Sheet and tracking sync state locally.
    Saves 'updated_google_sheet.csv' ready for 1-click import into Google Sheets.
    Thread-safe and crash-proof with atomic persistence and RLock.
    """

    def __init__(self):
        self._lock = threading.RLock()
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
        bak_file = STATE_FILE.with_suffix(STATE_FILE.suffix + ".bak")
        for p in (STATE_FILE, bak_file):
            if p.exists() and p.stat().st_size > 0:
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            return data
                except Exception as e:
                    logger.warning(f"Could not load state from {p}: {e}")
        return {}

    def _save_state(self):
        with self._lock:
            self.invalidate_cache()
            try:
                safe_atomic_write_json(STATE_FILE, self.state)
            except Exception as e:
                logger.error(f"Failed to atomically save state: {e}")

    def _load_imported_leads(self) -> List[Dict[str, str]]:
        bak_file = IMPORTED_LEADS_FILE.with_suffix(IMPORTED_LEADS_FILE.suffix + ".bak")
        for p in (IMPORTED_LEADS_FILE, bak_file):
            if p.exists() and p.stat().st_size > 0:
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            return data
                except Exception as e:
                    logger.warning(f"Could not load imported leads from {p}: {e}")
        return []

    def _save_imported_leads(self, leads: List[Dict[str, str]]):
        with self._lock:
            try:
                safe_atomic_write_json(IMPORTED_LEADS_FILE, leads)
            except Exception as e:
                logger.error(f"Failed to atomically save imported leads: {e}")

    def _merge_imported_leads(self):
        with self._lock:
            imported = self._load_imported_leads()
    def get_sent_registry(self) -> MasterSentRegistry:
        """
        Builds a comprehensive, ironclad MasterSentRegistry of ALL contacted leads
        across raw_rows, state (leads_state.json), and imported_leads.
        """
        registry = MasterSentRegistry()
        with self._lock:
            # 1. From raw_rows
            for r in self.raw_rows:
                st = r.get("status", "")
                if "✅" in st or "💬" in st:
                    registry.register_lead({
                        "name": r.get("name") or r.get("company_name"),
                        "email": r.get("email"),
                        "website": r.get("website"),
                        "phone": r.get("phone")
                    }, is_sent=True)

            # 2. From self.state (leads_state.json)
            for k, v in self.state.items():
                if isinstance(v, dict):
                    st = v.get("status", "")
                    if "✅" in st or "💬" in st:
                        lead_info = {
                            "name": v.get("company_name") or v.get("name"),
                            "email": v.get("email") or (k if "@" in k else ""),
                            "website": v.get("website") or (f"https://{k.replace('domain_', '')}" if k.startswith("domain_") else ""),
                            "phone": v.get("phone")
                        }
                        registry.register_lead(lead_info, is_sent=True)

                        # Explicit indexation for domain_ and @ keys
                        if k.startswith("domain_"):
                            d_clean = k.replace("domain_", "").lower().strip()
                            if d_clean not in GENERIC_DOMAINS and "." in d_clean:
                                registry.domains.add(d_clean)
                        elif "@" in k:
                            e_clean = k.lower().strip()
                            registry.emails.add(e_clean)
                            if "." in e_clean.split("@")[-1]:
                                d_part = e_clean.split("@")[-1]
                                if d_part not in GENERIC_DOMAINS:
                                    registry.domains.add(d_part)
                        elif k.startswith("name_"):
                            n_clean = k.replace("name_", "").lower().strip()
                            if n_clean:
                                registry.exact_names.add(n_clean)
                                registry.core_slugs.add(n_clean)

            # 3. From imported_leads if marked sent
            for imp in self._load_imported_leads():
                st = imp.get("status", "")
                if "✅" in st or "💬" in st:
                    registry.register_lead(imp, is_sent=True)

        return registry

    def sanitize_all_databases(self) -> int:
        """
        Scans imported_leads.json, leads_state.json, and raw_rows.
        Identifies any uncontacted lead that matches any contacted lead (email, domain, phone, or company name)
        and updates its status to '✅ Лист відправлено' so that duplicate emails can NEVER be sent.
        Returns the number of sanitized duplicate leads.
        """
        with self._lock:
            registry = self.get_sent_registry()
            imported = self._load_imported_leads()
            updated_count = 0

            for imp in imported:
                st = imp.get("status", "")
                if "✅" in st or "💬" in st:
                    continue
                is_dup, reason = registry.is_duplicate(imp)
                if is_dup:
                    logger.info(f"Sanitizing duplicate lead '{imp.get('name')}': {reason} -> ✅ Лист відправлено")
                    imp["status"] = "✅ Лист відправлено"
                    updated_count += 1
                    em_list = extract_clean_emails(imp.get("email"))
                    if em_list:
                        self.state[em_list[0]] = {
                            "status": "✅ Лист відправлено",
                            "name": imp.get("name"),
                            "company_name": imp.get("name"),
                            "date": imp.get("date") or datetime.now().strftime("%Y-%m-%d")
                        }

            if updated_count > 0:
                self._save_imported_leads(imported)
                self._save_state()
                self._load_local_csv()
                self._merge_imported_leads()
                self.invalidate_cache()
                self.export_updated_csv()
                logger.info(f"Sanitized and synchronized {updated_count} duplicate leads to '✅ Лист відправлено'.")

            return updated_count

    def _merge_imported_leads(self):
        with self._lock:
            imported = self._load_imported_leads()
            if not imported:
                return
            
            registry = self.get_sent_registry()
            existing_emails = set(r.get("email", "").strip().lower() for r in self.raw_rows if r.get("email"))
            existing_names = set(r.get("name", "").strip().lower() for r in self.raw_rows if r.get("name"))

            for imp in imported:
                email = imp.get("email", "").strip().lower()
                name = imp.get("name", "").strip().lower()
                
                # Check if this imported lead matches an already sent lead
                is_dup, reason = registry.is_duplicate(imp)
                if is_dup and "✅" not in imp.get("status", "") and "💬" not in imp.get("status", ""):
                    imp["status"] = "✅ Лист відправлено"

                if (email and email in existing_emails) or (name and name in existing_names):
                    continue
                self.raw_rows.append(imp)
                if email:
                    existing_emails.add(email)
                if name:
                    existing_names.add(name)

    def reload(self):
        """Forces a clean reload of local CSV and imported leads."""
        with self._lock:
            self.invalidate_cache()
            self._load_local_csv()
            self._merge_imported_leads()

    def add_imported_leads(self, new_items: List[Dict[str, str]]) -> int:
        """
        Appends newly discovered prospects to imported_leads.json and active memory.
        Guarantees thread-safety and that duplicates are strictly rejected.
        """
        with self._lock:
            current_imported = self._load_imported_leads()
            registry = self.get_sent_registry()

            # Also register all existing uncontacted leads to prevent intra-batch duplicates
            for src in (current_imported, self.raw_rows):
                for l in src:
                    registry.register_lead(l, is_sent=True)

            fieldnames = self.raw_headers if self.raw_headers else [
                "name", "country", "category", "culture", "adress", "city", "zip", "website", "phone", "coordinates", "email", "instagram", "crop", "status", "generation sheet", "date"
            ]

            added_count = 0
            today = datetime.now().strftime("%Y-%m-%d")

            for item in new_items:
                is_dup, reason = registry.is_duplicate(item)
                if is_dup:
                    logger.warning(f"⏩ Dropping duplicate candidate '{item.get('name')}' ({item.get('email')}): {reason}")
                    continue

                new_lead = {fn: "" for fn in fieldnames}
                new_lead["name"] = item.get("name", "").strip()
                new_lead["country"] = item.get("country", "")
                new_lead["category"] = item.get("category", "")
                new_lead["culture"] = item.get("culture", "")
                new_lead["city"] = item.get("city", "")
                new_lead["adress"] = item.get("adress", "")
                new_lead["website"] = item.get("website", "")
                new_lead["phone"] = item.get("phone", "")
                new_lead["email"] = item.get("email", "")
                new_lead["status"] = item.get("status") or "⚪ Очікує відправки"
                new_lead["date"] = today

                current_imported.append(new_lead)
                self.raw_rows.append(new_lead)
                registry.register_lead(new_lead, is_sent=True)
                added_count += 1

            if added_count > 0:
                self._save_imported_leads(current_imported)
                self.invalidate_cache()
                self.export_updated_csv()
                logger.info(f"Appended {added_count} unique non-duplicate leads to active memory & disk.")

            return added_count

    def _sync_live_sheet(self):
        with self._lock:
            sheet_id = self._extract_sheet_id()
            export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

            try:
                req = urllib.request.Request(export_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    content = resp.read().decode("utf-8")

                # Defense against Google sign-in / outage HTML pages
                if "<html" in content.lower() or "<!doctype" in content.lower():
                    logger.warning("Live Google Sheet returned HTML instead of CSV. Skipping sync to protect cache.")
                    return

                reader = csv.DictReader(io.StringIO(content))
                new_headers = reader.fieldnames or []

                # Validate essential columns exist
                normalized_headers = [h.strip().lower() for h in new_headers]
                if not any(k in normalized_headers for k in ["email", "name", "city", "phone", "website"]):
                    logger.warning("Live Google Sheet headers missing essential columns. Skipping sync to protect cache.")
                    return

                sheet_rows = list(reader)

                # Filter out empty ghost rows and known bounced/dead leads from Google Sheet
                clean_sheet_rows = []
                for r in sheet_rows:
                    if not any(r.get(k, "").strip() for k in ["name", "email", "phone", "city", "website"]):
                        continue
                    em = r.get("email", "").strip().lower()
                    st = self.state.get(em, {}).get("status", "")
                    if "❌" in st or "⚠️" in st:
                        continue
                    clean_sheet_rows.append(r)

                if not clean_sheet_rows and self.raw_rows:
                    logger.warning("Live Google Sheet returned 0 valid rows. Retaining cached rows.")
                    return

                # Merge with locally discovered verified leads so they are NEVER erased by live sync
                imported_leads = self._load_imported_leads()
                existing_emails = set(r.get("email", "").strip().lower() for r in clean_sheet_rows if r.get("email"))
                existing_names = set(r.get("name", "").strip().lower() for r in clean_sheet_rows if r.get("name"))

                merged_rows = list(clean_sheet_rows)
                for imp in imported_leads:
                    imp_email = imp.get("email", "").strip().lower()
                    imp_name = imp.get("name", "").strip().lower()
                    if not imp_email:
                        continue
                    st = self.state.get(imp_email, {}).get("status", "")
                    if "❌" in st or "⚠️" in st:
                        continue
                    if (imp_email in existing_emails) or (imp_name and imp_name in existing_names):
                        continue
                    merged_rows.append(imp)
                    existing_emails.add(imp_email)
                    if imp_name:
                        existing_names.add(imp_name)

                if merged_rows:
                    # Only write to CSV and bust cache if the data actually changed
                    if self.raw_rows != merged_rows or (new_headers and new_headers != self.raw_headers):
                        if new_headers:
                            self.raw_headers = new_headers
                        self.raw_rows = merged_rows
                        self.invalidate_cache()
                        logger.info(f"Synced live sheet: {len(clean_sheet_rows)} sheet leads + {len(imported_leads)} imported leads ({len(self.raw_rows)} total).")
                        self.export_updated_csv()
            except Exception as e:
                logger.warning(f"Live Google Sheet sync notice (retaining {len(self.raw_rows)} cached rows): {e}")
                if not self.raw_rows:
                    self._load_local_csv()
                    self._merge_imported_leads()

    def get_all_leads(self, include_bounced: bool = False) -> List[Dict[str, Any]]:
        with self._lock:
            if self._cached_leads is not None and not include_bounced:
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

                # Skip ghost rows, test addresses, or rows without valid emails
                if not any([name, email, phone, city, website]):
                    continue
                if not email or "example.com" in email.lower() or "test@" in email.lower():
                    continue

                company_name = name or "Valued Partner"

                cand_emails = extract_clean_emails(email)
                cand_domains = extract_corporate_domains(email) or extract_corporate_domains(website)
                norm_name = normalize_comp_name(company_name)

                # Collect all matching cached keys, prioritizing sent (✅) and replied (💬)
                cached = {}
                keys_to_search = cand_emails + [email.lower()]
                for d in cand_domains:
                    keys_to_search.append(f"domain_{d}")
                if norm_name:
                    keys_to_search.append(f"name_{norm_name}")

                for k in keys_to_search:
                    if k in self.state:
                        c_candidate = self.state[k]
                        c_st = c_candidate.get("status", "")
                        if "✅" in c_st or "💬" in c_st:
                            cached = c_candidate
                            break
                        elif "❌" in c_st or "⚠️" in c_st:
                            if not cached or ("✅" not in cached.get("status", "") and "💬" not in cached.get("status", "")):
                                cached = c_candidate
                        elif not cached:
                            cached = c_candidate

                raw_status = cached.get("status") or r.get("status", "").strip()
                if not raw_status or raw_status.strip().upper() in ("NEW", "PENDING"):
                    status = "⚪ Очікує відправки"
                else:
                    status = raw_status.strip()

                # Exclude bounced/dead leads so only deliverable active prospects appear on dashboard
                if not include_bounced and ("❌" in status or "⚠️" in status):
                    lead_idx += 1
                    continue

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

                # Safety guard: if both leads have distinct email addresses with zero overlap,
                # never merge them unless they share the exact company domain
                if e1 and e2 and not (e1 & e2):
                    if not domain_match:
                        continue

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
        if phone_clean.startswith(("+351", "00351", "351")):
            return "pt"
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
        if _has_tld(".pt"):
            return "pt"
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
        # Portugal
        pt_keywords = [
            "portugal", "portuguesa", "lisboa", "lisbon", "porto", "douro", "alentejo", "dão", "dao",
            "minho", "vinho verde", "setúbal", "setubal", "bairrada", "algarve", "tejo", "ribatejo",
            "trás-os-montes", "tras-os-montes", "beira interior", "madeira", "açores", "acores",
            "adega", "quinta", "herdade", "sociedade agrícola", "agricola", "olival", "olivicultura",
            "pomar", "fruticultura", "vitivinícola", "vitivinicola", "enologia", "vinhos", "évora", "evora"
        ]
        if any(k in text for k in pt_keywords):
            return "pt"

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

        if "portug" in text or ".pt" in text:
            return "pt"
        if "españ" in text or "spain" in text or ".es" in text:
            return "es"
        if "ital" in text or ".it" in text:
            return "it"
        if "bulgar" in text or ".bg" in text:
            return "bg"
        return "el"

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

        if "portug" in rc or "португ" in rc or "portugal" in text or ".pt" in web_clean or phone_clean.startswith(("+351", "00351", "351")) or lang == "pt":
            return {"code": "PT", "name_uk": "Португалія", "name_bg": "Португалия", "name_en": "Portugal", "flag": "🇵🇹"}

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
            "pt": {"code": "PT", "name_uk": "Португалія", "name_bg": "Португалия", "name_en": "Portugal", "flag": "🇵🇹"},
            "sr": {"code": "SR", "name_uk": "Сербія", "name_bg": "Сърбия", "name_en": "Serbia", "flag": "🇷🇸"},
            "hr": {"code": "HR", "name_uk": "Хорватія", "name_bg": "Хърватия", "name_en": "Croatia", "flag": "🇭🇷"}
        }
        return lang_country_map.get(lang, {"code": "EU", "name_uk": "ЄС", "name_bg": "ЕС", "name_en": "EU", "flag": "🇪🇺"})

    def mark_draft_created(self, lead: Dict[str, Any], draft_id: str, subject: str, body_plain: str):
        with self._lock:
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
            comp_name = re.sub(r'[\W_]+', '', lead.get("company_name", "").lower())
            if comp_name:
                self.state[f"name_{comp_name}"] = cached_data

            self._save_state()
            logger.info(f"Updated lead {lead.get('company_name')} -> '🟡 Чернетка на перевірці' in local database.")
            self.export_updated_csv()

    def mark_email_sent(self, lead: Dict[str, Any], subject: str, body_plain: str):
        """
        Marks lead as definitively sent ('✅ Лист відправлено') in state, memory, and CSV.
        Thread-safe and atomic.
        """
        with self._lock:
            raw_email = lead.get("email", "").strip()
            row_num = lead.get("row_number", 0)
            today = datetime.now().strftime("%Y-%m-%d")

            cached_data = {
                "status": "✅ Лист відправлено",
                "date": today,
                "subject": subject,
                "generation_sheet": f"Subject: {subject}\n\n{body_plain}"
            }
            cand_emails = extract_clean_emails(raw_email)
            cand_domains = extract_corporate_domains(raw_email) or extract_corporate_domains(lead.get("website"))
            comp_name = normalize_comp_name(lead.get("company_name") or lead.get("name"))

            if raw_email:
                self.state[raw_email.lower()] = cached_data
            for em in cand_emails:
                self.state[em] = cached_data
            for dom in cand_domains:
                self.state[f"domain_{dom}"] = cached_data
            if comp_name:
                self.state[f"name_{comp_name}"] = cached_data

            # Keep imported_leads.json in sync
            try:
                imported = self._load_imported_leads()
                imp_updated = False
                for imp in imported:
                    i_emails = extract_clean_emails(imp.get("email"))
                    i_domains = extract_corporate_domains(imp.get("email")) or extract_corporate_domains(imp.get("website"))
                    i_name = normalize_comp_name(imp.get("name") or imp.get("company_name"))
                    if any(e in cand_emails for e in i_emails) or any(d in cand_domains for d in i_domains) or (comp_name and comp_name == i_name):
                        imp["status"] = "✅ Лист відправлено"
                        imp["date"] = today
                        imp_updated = True
                if imp_updated:
                    self._save_imported_leads(imported)
            except Exception as e:
                logger.warning(f"Notice syncing imported_leads on send: {e}")

            # Keep raw_rows in sync
            for r in self.raw_rows:
                r_emails = extract_clean_emails(r.get("email"))
                r_domains = extract_corporate_domains(r.get("email")) or extract_corporate_domains(r.get("website"))
                r_name = normalize_comp_name(r.get("name") or r.get("company_name"))
                if any(e in cand_emails for e in r_emails) or any(d in cand_domains for d in r_domains) or (comp_name and comp_name == r_name):
                    r["status"] = "✅ Лист відправлено"
                    r["date"] = today

            self._save_state()
            logger.info(f"Updated lead {lead.get('company_name')} -> '✅ Лист відправлено' in local database.")
            self.export_updated_csv()

    def mark_lead_replied(self, lead: Dict[str, Any], subject: str, snippet: str, reply_date: str = ""):
        """
        Marks lead as having replied ('💬 Отримано відповідь') in state, memory, and CSV.
        Thread-safe and atomic.
        """
        with self._lock:
            raw_email = lead.get("email", "").strip()
            today = reply_date or datetime.now().strftime("%Y-%m-%d")

            cached_data = {
                "status": "💬 Отримано відповідь",
                "date": today,
                "subject": subject,
                "generation_sheet": f"Subject: {subject}\n\n[ВІДПОВІДЬ КЛІЄНТА]:\n{snippet}"
            }
            if raw_email:
                self.state[raw_email.lower()] = cached_data
                for em in re.findall(r'[\w\.-]+@[\w\.-]+', raw_email.lower()):
                    self.state[em] = cached_data
            comp_name = re.sub(r'[\W_]+', '', lead.get("company_name", "").lower())
            if comp_name:
                self.state[f"name_{comp_name}"] = cached_data

            self._save_state()
            logger.info(f"Updated lead {lead.get('company_name')} -> '💬 Отримано відповідь' in local database.")
            self.export_updated_csv()

    def export_updated_csv(self) -> Path:
        """
        Exports the updated sheet into updated_google_sheet.csv with deduplication and formula injection protection.
        Thread-safe and atomic with POSIX replace.
        """
        with self._lock:
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

            try:
                safe_atomic_write_csv(UPDATED_CSV_FILE, self.raw_headers, updated_rows)
            except Exception as e:
                logger.error(f"Failed to atomically export updated CSV: {e}")

            return UPDATED_CSV_FILE

    def sync_sent_emails(self, gmail_service: Any, limit: int = 150) -> int:
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
                draft_recipients = gmail_service.get_draft_recipients(limit=min(limit, 100))
            except Exception as e:
                logger.warning(f"Notice getting draft recipients: {e}")

        # 2. Fetch Sent Emails from Gmail (bounded scan to prevent latency/stalls)
        sent_recipients = {}
        try:
            sent_recipients = gmail_service.get_sent_recipients(limit=limit)
        except Exception as e:
            logger.warning(f"Notice getting sent recipients: {e}")

        # 3. Fetch Bounced Emails from Gmail (Mailer-Daemon delivery failures)
        bounced_recipients = {}
        if hasattr(gmail_service, "get_bounced_recipients"):
            try:
                bounced_recipients = gmail_service.get_bounced_recipients(limit=min(limit, 100))
            except Exception as e:
                logger.warning(f"Notice getting bounced recipients: {e}")

        if not sent_recipients and not draft_recipients and not bounced_recipients:
            return 0

        # Build corporate domains set from all sent recipients
        sent_domains_map = {}
        for s_em, s_info in sent_recipients.items():
            if '@' in s_em:
                s_dom = s_em.split('@')[1].lower()
                if s_dom not in GENERIC_DOMAINS and '.' in s_dom:
                    sent_domains_map[s_dom] = s_info

        with self._lock:
            # Step A: Directly register EVERY sent email & corporate domain from Gmail into self.state
            for s_em, s_info in sent_recipients.items():
                s_em_clean = s_em.strip().lower()
                if not s_em_clean or "@" not in s_em_clean:
                    continue
                s_date = s_info.get("date") or today
                s_subj = s_info.get("subject", "")
                cached_sent = {
                    "status": "✅ Лист відправлено",
                    "date": s_date,
                    "subject": s_subj
                }
                if s_em_clean not in self.state or "✅" not in self.state[s_em_clean].get("status", ""):
                    self.state[s_em_clean] = cached_sent
                    updated_count += 1

                s_dom = s_em_clean.split("@")[-1].lower().strip()
                if s_dom not in GENERIC_DOMAINS and "." in s_dom and len(s_dom) > 4:
                    dom_key = f"domain_{s_dom}"
                    if dom_key not in self.state or "✅" not in self.state[dom_key].get("status", ""):
                        self.state[dom_key] = cached_sent

            # Step B: Mark matched leads in imported_leads.json as sent
            try:
                imported = self._load_imported_leads()
                imp_changed = False
                for imp in imported:
                    if "✅" in imp.get("status", ""):
                        continue
                    i_emails = extract_clean_emails(imp.get("email"))
                    i_doms = extract_corporate_domains(imp.get("email")) | extract_corporate_domains(imp.get("website"))
                    if any(e in sent_recipients for e in i_emails) or any(d in sent_domains_map for d in i_doms):
                        imp["status"] = "✅ Лист відправлено"
                        imp["date"] = today
                        imp_changed = True
                        updated_count += 1
                if imp_changed:
                    self._save_imported_leads(imported)
            except Exception as e:
                logger.warning(f"Notice updating imported leads in sync_sent: {e}")

            # Step C: Mark matched leads in raw_rows as sent
            for r in self.raw_rows:
                if "✅" in r.get("status", ""):
                    continue
                r_emails = extract_clean_emails(r.get("email"))
                r_doms = extract_corporate_domains(r.get("email")) | extract_corporate_domains(r.get("website"))
                if any(e in sent_recipients for e in r_emails) or any(d in sent_domains_map for d in r_doms):
                    r["status"] = "✅ Лист відправлено"
                    r["date"] = today
                    updated_count += 1

            all_leads = self.get_all_leads()

            for lead in all_leads:
                raw_email = lead.get("email", "").strip()
                if not raw_email:
                    continue

                lead_emails = extract_clean_emails(raw_email)
                if not lead_emails:
                    continue

                lead_domains = extract_corporate_domains(raw_email) or extract_corporate_domains(lead.get("website"))
                current_status = lead.get("status", "")
                comp_name = normalize_comp_name(lead.get("company_name") or lead.get("name"))

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
                        if comp_name:
                            self.state[f"name_{comp_name}"] = cached_data
                        for em in lead_emails:
                            self.state[em] = cached_data
                        for dom in lead_domains:
                            self.state[f"domain_{dom}"] = cached_data

                        updated_count += 1
                        logger.info(f"Detected BOUNCED email for {lead.get('company_name')} ({matched_bounced})! Status -> '❌ Помилка доставки (Email не існує)'")
                    continue

                # Priority 2: Check if SENT (either by email match or corporate domain match)
                matched_sent = next((e for e in lead_emails if e in sent_recipients), None)
                matched_dom = next((d for d in lead_domains if d in sent_domains_map), None)

                if matched_sent or matched_dom:
                    if "✅" not in current_status and "❌" not in current_status:
                        sent_info = sent_recipients.get(matched_sent) or sent_domains_map.get(matched_dom, {})
                        cached_data = {
                            "status": "✅ Лист відправлено",
                            "date": today,
                            "subject": sent_info.get("subject", "")
                        }
                        self.state[raw_email.lower()] = cached_data
                        if comp_name:
                            self.state[f"name_{comp_name}"] = cached_data
                        for em in lead_emails:
                            self.state[em] = cached_data
                        for dom in lead_domains:
                            self.state[f"domain_{dom}"] = cached_data

                        updated_count += 1
                        match_reason = matched_sent if matched_sent else f"domain @{matched_dom}"
                        logger.info(f"Detected sent email for {lead.get('company_name')} ({match_reason})! Status -> '✅ Лист відправлено'")
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

        with self._lock:
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
        with self._lock:
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

