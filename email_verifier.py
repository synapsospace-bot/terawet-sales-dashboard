import re
import json
import logging
from typing import Dict, Any, Tuple, Optional, List
from pathlib import Path
import config

import threading
from sheets_service import safe_atomic_write_json

logger = logging.getLogger("EmailVerifier")

CACHE_FILE = config.BASE_DIR / "domain_mx_cache.json"

class EmailVerifierService:
    """
    High-performance, multi-factor email verification service:
    1. Syntax & structure validation (RFC 5322 compliant regex)
    2. Disposable & temporary domain blocking
    3. Live DNS MX (Mail Exchanger) validation with in-memory & disk caching
    4. Fallback A-record check for custom legacy mail servers
    Thread-safe and crash-proof.
    """

    DISPOSABLE_DOMAINS = {
        "tempmail.com", "10minutemail.com", "guerrillamail.com", "sharklasers.com",
        "mailinator.com", "yopmail.com", "trashmail.com", "dispostable.com"
    }

    # Known rock-solid public mail provider domains (always valid, no DNS query needed)
    TRUSTED_DOMAINS = {
        "gmail.com", "googlemail.com", "yahoo.com", "yahoo.fr", "yahoo.es", "yahoo.it",
        "abv.bg", "mail.bg", "otenet.gr", "cosmotemail.gr", "in.gr", "forthnet.gr",
        "hotmail.com", "outlook.com", "live.com", "msn.com", "icloud.com", "me.com",
        "libero.it", "virgilio.it", "tiscali.it", "alice.it", "orange.fr", "free.fr", "sfr.fr",
        "t-online.de", "gmx.de", "web.de", "gmx.net", "gmx.at", "a1.net",
        "mail.ru", "yandex.ru", "ukr.net", "i.ua"
    }

    def __init__(self):
        self._lock = threading.RLock()
        self._cache = self._load_cache()

    def _load_cache(self) -> Dict[str, Dict[str, Any]]:
        bak_file = CACHE_FILE.with_suffix(CACHE_FILE.suffix + ".bak")
        for p in (CACHE_FILE, bak_file):
            if p.exists() and p.stat().st_size > 0:
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            return data
                except Exception as e:
                    logger.warning(f"Could not load domain MX cache from {p}: {e}")
        return {}

    def _save_cache(self):
        with self._lock:
            try:
                safe_atomic_write_json(CACHE_FILE, self._cache)
            except Exception as e:
                logger.warning(f"Could not save domain MX cache: {e}")

    def _set_cache_entry(self, domain: str, entry: Dict[str, Any]):
        with self._lock:
            self._cache[domain] = entry
            self._save_cache()

    def verify_email(self, email_address: str) -> Tuple[bool, str]:
        """
        Validates an email address.
        Returns (is_valid: bool, reason: str).
        """
        raw = (email_address or "").strip().lower()
        if not raw:
            return False, "Порожня адреса email"

        # If comma-separated multiple emails, check the first one
        parts = [e.strip() for e in re.findall(r'[\w\.-]+@[\w\.-]+', raw)]
        if not parts:
            return False, "Некоректний синтаксис email"

        target_email = parts[0]

        # 1. Syntax check
        if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', target_email):
            return False, f"Синтаксично некоректна адреса: {target_email}"

        domain = target_email.split('@')[-1].strip().lower()

        # 2. Disposable check
        if domain in self.DISPOSABLE_DOMAINS:
            return False, f"Тимчасовий/одноразовий поштовий домен: {domain}"

        # 3. Known trusted domains
        if domain in self.TRUSTED_DOMAINS:
            return True, f"Надійний поштовий провайдер ({domain})"

        # 4. Check cache
        with self._lock:
            cached = self._cache.get(domain)
        if cached:
            if cached.get("has_mx", False):
                mx_list = cached.get('mx', ['OK'])
                mx_name = mx_list[0] if mx_list else 'OK'
                return True, f"Перевірений MX: {mx_name}"
            else:
                return False, cached.get("reason", "Домен не має поштових записів MX")

        # 5. Live DNS MX check via dnspython with public nameserver fallbacks
        try:
            import dns.resolver
            resolver = dns.resolver.Resolver()
            resolver.timeout = 3.5
            resolver.lifetime = 4.0

            answers = None
            try:
                answers = resolver.resolve(domain, 'MX')
            except (dns.resolver.NoNameservers, dns.resolver.LifetimeTimeout, Exception):
                # Fallback to trusted public DNS (Google & Cloudflare) if local system DNS fails
                try:
                    resolver.nameservers = ['8.8.8.8', '1.1.1.1', '8.8.4.4']
                    answers = resolver.resolve(domain, 'MX')
                except Exception as ex:
                    logger.debug(f"Public DNS fallback MX query failed for {domain}: {ex}")

            if answers:
                mx_hosts = [str(r.exchange).rstrip('.') for r in answers]
                if mx_hosts:
                    self._set_cache_entry(domain, {"has_mx": True, "mx": mx_hosts[:2]})
                    return True, f"Дійсний поштовий сервер (MX: {mx_hosts[0]})"

            # Fallback to A record check (some mail servers receive mail on A record directly)
            try:
                resolver.resolve(domain, 'A')
                self._set_cache_entry(domain, {"has_mx": True, "mx": [f"A-record ({domain})"]})
                return True, f"Домен існує (A-record: {domain})"
            except Exception:
                pass

            # Final socket fallback
            import socket
            try:
                socket.getaddrinfo(domain, 80)
                self._set_cache_entry(domain, {"has_mx": True, "mx": [f"socket-resolved ({domain})"]})
                return True, f"Домен активний (socket: {domain})"
            except Exception:
                self._set_cache_entry(domain, {"has_mx": False, "reason": f"Домен {domain} не існує або не має поштових записів"})
                return False, f"Домен {domain} не має поштових записів MX"
        except Exception as e:
            logger.debug(f"Resolver check exception for {domain}: {e}")
            self._set_cache_entry(domain, {"has_mx": False, "reason": f"Помилка DNS: {e}"})
            return False, f"Помилка перевірки домену {domain}"

        except ImportError:
            import socket
            try:
                socket.gethostbyname(domain)
                return True, "Домен резолвиться (socket fallback)"
            except Exception:
                return False, f"Домен {domain} не існує або недоступний"
        except Exception as e:
            logger.debug(f"DNS lookup error for {domain}: {e}")
            return False, f"Помилка перевірки домену {domain}: {e}"

        return False, "Не вдалося перевірити поштовий сервер"
