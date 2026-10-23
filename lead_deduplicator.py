"""
lead_deduplicator.py
Centralized, ironclad anti-duplicate engine for TeraWet Sales Agent.
Ensures ZERO duplicate outreach across:
- Email addresses
- Corporate domains (from email and website)
- Phone numbers
- Exact company names
- Substring company names
- Parenthetical brands / group owners (e.g. '(Sierra Cantabria)')
- Brand token intersection (fuzzy matching)
"""

import re
import unicodedata
from typing import Dict, Any, List, Set, Tuple, Optional

# Generic public email providers where domain matching must NOT be applied
GENERIC_DOMAINS = {
    'gmail.com', 'yahoo.com', 'abv.bg', 'mail.bg', 'otenet.gr', 'mail.ru', 
    'yandex.ru', 'hotmail.com', 'outlook.com', 'icloud.com', 'proton.me', 
    'protonmail.com', 'zoho.com', 'aol.com', 'gmx.de', 'web.de', 'libero.it',
    'alice.it', 'virgilio.it', 'orange.fr', 'free.fr', 'sfr.fr', 'wanadoo.fr',
    't-online.de', 'web.de', 'freenet.de', 'posteo.de', 'example.com', 'culture.gr'
}

# Stop words in multiple European languages for agricultural company names
STOP_WORDS = {
    # Legal corporate suffixes
    'sa', 'sl', 'srl', 'spa', 'gmbh', 'ltd', 'llc', 'eood', 'ood', 'dd', 'doo', 'd.o.o.',
    's.a.', 's.l.', 's.r.l.', 's.p.a.', 'ag', 'coop', 'cooperativa', 'consorzio', 'syndicat',
    'sas', 's.a.s.', 'sarl', 's.a.r.l.', 'cie', 'snc', 'kft', 'zrt', 's.r.o.', 'sro',
    
    # Industry / Estate types
    'bodega', 'bodegas', 'celler', 'cellers', 'adega', 'adegas', 'vina', 'vinos', 'vinedos',
    'viña', 'viñedos', 'winery', 'wines', 'wine', 'estate', 'estates', 'domaine', 'domaines',
    'chateau', 'château', 'tenuta', 'tenute', 'cantina', 'cantine', 'azienda', 'aziende',
    'agricola', 'agricole', 'agricolo', 'podere', 'poderi', 'fattoria', 'fattorie', 'weingut',
    'weinguter', 'klet', 'vinarija', 'podrum', 'podrumi', 'crama', 'cramele', 'vivero', 'viveros',
    'nursery', 'nurseries', 'organic', 'bio', 'quinta', 'quintas', 'herdade', 'herdades',
    'clos', 'castello', 'schloss', 'finca', 'fincas', 'hacienda', 'haciendas', 'cortijo',
    'casale', 'casali', 'baglio', 'palacio', 'conac', 'birtok', 'pincészet', 'masia', 'mas',
    
    # Agricultural activities & crops
    'viticoltore', 'viticoltori', 'vigneron', 'vignerons', 'vineyard', 'vineyards', 'vigneti',
    'vignobles', 'vignes', 'vinogradi', 'loza', 'olives', 'olive', 'olivar', 'elaiwnes', 'elies',
    'orchard', 'orchards', 'fruits', 'frutales', 'citrus', 'agrumi', 'rozovarna', 'razsadnik',
    'plant', 'plants', 'plante', 'sadjarstvo', 'kmetija', 'pepiniere', 'destilerija', 'distillery',
    
    # Common geographic & directional prefixes
    'valle', 'valley', 'vallee', 'vallée', 'monte', 'mont', 'colle', 'hills', 'rio',
    'nord', 'sud', 'est', 'ouest', 'north', 'south', 'east', 'west', 'alto', 'alta',
    'basso', 'bassa', 'haut', 'haute', 'bas', 'norte', 'sur',
    
    # Common religious, patronymic & noble title prefixes
    'san', 'santa', 'santo', 'saint', 'sainte', 'jean', 'pierre', 'louis',
    'marques', 'marquesa', 'marquese', 'marchesi', 'marchese', 'conde', 'condesa',
    'comte', 'comtesse', 'baron', 'barone', 'baronessa', 'duc', 'duca', 'duchesse',
    'prince', 'principe',
    
    # Articles, prepositions & conjunctions
    'de', 'del', 'della', 'delle', 'dei', 'degli', 'di', 'da', 'do', 'dos', 'das',
    'la', 'il', 'lo', 'le', 'i', 'gli', 'el', 'los', 'las', 'du', 'des', 'von', 'van',
    'und', 'and', 'et', 'y', 'en', 'al', 'der', 'die', 'das', 'den', 'dem'
}

# Generic words that should not trigger single-token duplicates on their own
COMMON_NON_DISTINCTIVE = {
    'agro', 'vini', 'farm', 'crop', 'land', 'tree', 'seed', 'good', 'best', 'plus', 'gold', 
    'star', 'rose', 'blue', 'sole', 'real', 'nova', 'novo', 'green', 'center', 'garden',
    'family', 'group', 'select', 'reserve', 'reserva', 'classic', 'modern', 'terroir',
    'premier', 'grand', 'cru', 'special', 'original', 'nature', 'pura', 'puro'
}


def strip_accents(text: str) -> str:
    """Removes diacritical marks from letters (e.g. é -> e, ñ -> n, ü -> u)."""
    if not text:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", str(text)) if unicodedata.category(c) != "Mn")


def extract_clean_emails(email_val: Any) -> List[str]:
    """Extracts all valid lowercase email addresses from string or list."""
    if not email_val:
        return []
    text = str(email_val).lower()
    return [e.strip() for e in re.findall(r'[\w\.-]+@[\w\.-]+', text) if '.' in e.split('@')[-1]]


def extract_corporate_domains(val: Any) -> Set[str]:
    """Extracts non-generic second-level corporate domains from email or website URL."""
    domains = set()
    if not val:
        return domains
    text = str(val).lower()
    
    # 1. From emails
    for em in extract_clean_emails(text):
        if "@" in em:
            d = em.split("@")[-1].strip()
            if d and d not in GENERIC_DOMAINS and "." in d and len(d) > 4:
                domains.add(d)
                
    # 2. From URLs
    urls = re.findall(r'https?://[^\s/$.?#].[^\s,;]*', text) or [text]
    for u in urls:
        clean_u = re.sub(r'^https?://(www\.)?', '', u.strip().rstrip('/'))
        dom = clean_u.split('/')[0].split(':')[0]
        if dom and dom not in GENERIC_DOMAINS and '.' in dom and len(dom) > 4:
            domains.add(dom)
            
    return domains


def clean_phone_digits(phone_val: Any) -> str:
    """Normalizes phone number to last 8-9 digits for international deduplication."""
    if not phone_val:
        return ""
    digits = re.sub(r'\D', '', str(phone_val))
    return digits[-8:] if len(digits) >= 8 else ""


def clean_tokens(name_val: Any) -> Set[str]:
    """Extracts meaningful brand tokens stripped of stop words and accents."""
    if not name_val:
        return set()
    cleaned = strip_accents(str(name_val).lower())
    words = re.findall(r'[a-zA-Z\u0400-\u04FF]+', cleaned)
    return {w for w in words if len(w) >= 3 and w not in STOP_WORDS}


def clean_core_slug(name_val: Any) -> str:
    """Generates an alphanumeric slug of sorted core tokens."""
    toks = sorted(list(clean_tokens(name_val)))
    return "".join(toks)

normalize_comp_name = clean_core_slug


def extract_parenthetical_brands(name_val: Any) -> List[str]:
    """Extracts aliases or brand owners inside parentheses, e.g. '(Sierra Cantabria)'."""
    if not name_val:
        return []
    return [p.strip() for p in re.findall(r'\((.*?)\)', str(name_val)) if len(p.strip()) >= 3]


class MasterSentRegistry:
    """
    Central in-memory index of ALL contacted or known prospects.
    Thread-safe and fast O(1) lookups for emails, domains, phones, and brand tokens.
    """

    def __init__(self):
        self.emails: Set[str] = set()
        self.domains: Set[str] = set()
        self.phones: Set[str] = set()
        self.exact_names: Set[str] = set()
        self.core_slugs: Set[str] = set()
        self.distinctive_tokens: Set[str] = set()
        self.raw_lead_names: List[str] = []

    def register_lead(self, lead: Dict[str, Any], is_sent: bool = True):
        """Registers a lead into the sent/contacted index."""
        if not lead or not is_sent:
            return

        # 1. Emails
        for em in extract_clean_emails(lead.get("email")):
            self.emails.add(em)
            if "@" in em:
                dom = em.split("@")[-1]
                if dom not in GENERIC_DOMAINS and "." in dom:
                    self.domains.add(dom)

        # 2. Domains from website
        for dom in extract_corporate_domains(lead.get("website")):
            self.domains.add(dom)

        # 3. Phone
        ph = clean_phone_digits(lead.get("phone"))
        if ph:
            self.phones.add(ph)

        # 4. Company Names & Aliases
        c_name = lead.get("company_name") or lead.get("name") or ""
        if c_name:
            self.raw_lead_names.append(c_name)
            self.exact_names.add(strip_accents(c_name.lower().strip()))
            
            slug = clean_core_slug(c_name)
            if slug:
                self.core_slugs.add(slug)

            toks = clean_tokens(c_name)
            for t in toks:
                if len(t) >= 4 and t not in COMMON_NON_DISTINCTIVE:
                    self.distinctive_tokens.add(t)

            # Parenthetical sub-brands
            for paren in extract_parenthetical_brands(c_name):
                p_slug = clean_core_slug(paren)
                if p_slug:
                    self.core_slugs.add(p_slug)
                for pt in clean_tokens(paren):
                    if len(pt) >= 4 and pt not in COMMON_NON_DISTINCTIVE:
                        self.distinctive_tokens.add(pt)

    def is_duplicate(self, candidate: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Comprehensive check against the sent registry.
        Returns (True, reason) if candidate matches any sent lead.
        """
        c_emails = extract_clean_emails(candidate.get("email"))
        c_domains = extract_corporate_domains(candidate.get("email")) | extract_corporate_domains(candidate.get("website"))
        c_phone = clean_phone_digits(candidate.get("phone"))
        c_name = candidate.get("company_name") or candidate.get("name") or ""

        # 1. Email exact match
        for em in c_emails:
            if em in self.emails:
                return True, f"Email address '{em}' already contacted"

        # 2. Corporate Domain match
        for d in c_domains:
            if d in self.domains:
                return True, f"Corporate domain '{d}' already contacted"

        # 3. Phone number match
        if c_phone and c_phone in self.phones:
            return True, f"Phone digits '...{c_phone}' already contacted"

        # 4. Company name match
        if c_name:
            c_norm = strip_accents(c_name.lower().strip())
            if c_norm in self.exact_names:
                return True, f"Company name '{c_name}' already contacted"

            c_slug = clean_core_slug(c_name)
            if c_slug and c_slug in self.core_slugs:
                return True, f"Company core slug '{c_slug}' matches previously contacted company"

            # Substring slug match for brands with 6+ chars
            if len(c_slug) >= 6:
                for sent_slug in self.core_slugs:
                    if len(sent_slug) >= 6 and (c_slug in sent_slug or sent_slug in c_slug):
                        return True, f"Company brand slug '{c_slug}' overlaps with contacted '{sent_slug}'"

            # Brand tokens intersection
            c_tokens = clean_tokens(c_name)
            inter = c_tokens & self.distinctive_tokens
            if len(inter) >= 2:
                return True, f"Brand tokens {inter} match previously contacted company"
            elif len(inter) == 1:
                word = list(inter)[0]
                if len(word) >= 5 and word not in COMMON_NON_DISTINCTIVE:
                    return True, f"Distinctive brand word '{word}' already contacted"

            # Check parenthetical aliases in candidate
            for paren in extract_parenthetical_brands(c_name):
                p_slug = clean_core_slug(paren)
                if p_slug and p_slug in self.core_slugs:
                    return True, f"Parenthetical group '{paren}' matches previously contacted company"
                p_toks = clean_tokens(paren)
                p_inter = p_toks & self.distinctive_tokens
                if len(p_inter) >= 1:
                    word = list(p_inter)[0]
                    if len(word) >= 5 and word not in COMMON_NON_DISTINCTIVE:
                        return True, f"Parenthetical brand word '{word}' matches previously contacted company"

        return False, ""
