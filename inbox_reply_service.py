import os
import re
import json
import time
import email
import html
import logging
import imaplib
import socket
import threading
from datetime import datetime
from email.header import decode_header
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

socket.setdefaulttimeout(20)

import config
from sheets_service import LeadDataService, safe_atomic_write_json
from telegram_notifier import TelegramNotifier, telegram_notifier

logger = logging.getLogger("InboxReplyService")

REPLIES_STATE_FILE = config.BASE_DIR / "replies_state.json"

# Common keywords that indicate a reply to our TERAWET outreach
TERAWET_SUBJECT_KEYWORDS = [
    "terawet", "tera-wet", "тераует", "тера-ует", "суперабсорбент",
    "вологоутримувач", "хидрогел", "напояване", "полимер", "полімер", "полив"
]

# Automated senders and domains to ignore
IGNORE_SENDER_PATTERNS = [
    r"mailer-daemon",
    r"mail delivery subsystem",
    r"postmaster@",
    r"noreply@",
    r"no-reply@",
    r"notifications?@",
    r"support@google\.com",
    r"@google\.com",
    r"@github\.com",
    r"@pinterest\.com",
    r"@freelancehunt\.com",
    r"@bitrix24\.com",
    r"@pipedrive\.com",
    r"@linkedin\.com",
    r"@facebookmail\.com"
]

def _decode_mime_header(raw_header: Optional[str]) -> str:
    """Decodes MIME encoded headers like =?UTF-8?B?...?= or =?utf-8?Q?...?="""
    if not raw_header:
        return ""
    try:
        parts = decode_header(raw_header)
        result = ""
        for p, enc in parts:
            if isinstance(p, bytes):
                result += p.decode(enc or "utf-8", errors="ignore")
            else:
                result += str(p)
        return result.strip()
    except Exception:
        return str(raw_header).strip()

def _clean_body_snippet(text: str, max_chars: int = 400) -> str:
    """
    Cleans raw email text: converts HTML breaks to newlines, strips HTML,
    strips quoted replies ('>' or 'On ... wrote:'), and normalizes whitespace into a punchy readable preview.
    """
    if not text:
        return ""
    # Strip script and style blocks entirely
    clean = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', text)
    # Convert block tags and breaks to newlines
    clean = re.sub(r'(?i)<(br|/p|/div|/tr|/h\d)\s*/?>', '\n', clean)
    # Strip remaining HTML tags
    clean = re.sub(r'<[^>]+>', ' ', clean)
    clean = html.unescape(clean)

    # Cut off standard email quote headers (On [date] wrote:, От: ..., etc.)
    quote_markers = [
        r"(?i)\n\s*on\s+.+wrote\s*:",
        r"(?i)\n\s*в\s+.+написал\(а\)\s*:",
        r"(?i)\n\s*на\s+.+написа\s*:",
        r"(?i)\n\s*-+\s*original message\s*-+",
        r"(?i)\n\s*-+\s*исходное сообщение\s*-+",
        r"(?i)\n\s*from:\s*.+\nsent:\s*",
        r"(?i)\n\s*от:\s*.+\nотправлено:\s*"
    ]
    for marker in quote_markers:
        parts = re.split(marker, clean, maxsplit=1)
        if len(parts) > 1:
            clean = parts[0]

    # Remove lines starting with '>' or '&gt;'
    lines = [line.strip() for line in clean.splitlines() if line.strip() and not line.strip().startswith('>') and not line.strip().startswith('&gt;')]
    clean = " ".join(lines)
    # Collapse multiple whitespaces
    clean = re.sub(r'\s+', ' ', clean).strip()

    if len(clean) > max_chars:
        clean = clean[:max_chars - 3] + "..."
    return clean

class InboxReplyService:
    """
    Monitors Gmail INBOX via IMAP for incoming replies from prospective clients.
    When a lead responds:
    1. Identifies the lead against local database.
    2. Marks lead's status as '💬 Отримано відповідь'.
    3. Sends an immediate Telegram push notification with lead details & text preview.
    4. Records event to replies_state.json to prevent duplicate alerts.
    """

    def __init__(self, data_service: Optional[LeadDataService] = None, notifier: Optional[TelegramNotifier] = None):
        self.data_service = data_service or LeadDataService()
        self.notifier = notifier or telegram_notifier
        self._lock = threading.RLock()
        self.is_running = False
        self.background_thread: Optional[threading.Thread] = None
        self.state = self._load_state()

    def _default_state(self) -> Dict[str, Any]:
        return {
            "last_checked_uid": 0,
            "processed_uids": [],
            "replies_history": [],
            "last_check_timestamp": "",
            "total_replies_detected": 0
        }

    def _load_state(self) -> Dict[str, Any]:
        default = self._default_state()
        bak_file = REPLIES_STATE_FILE.with_suffix(REPLIES_STATE_FILE.suffix + ".bak")
        for p in (REPLIES_STATE_FILE, bak_file):
            if p.exists() and p.stat().st_size > 0:
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            default.update(data)
                            return default
                except Exception as e:
                    logger.warning(f"Error reading replies state from {p}: {e}")
        return default

    def _save_state(self):
        with self._lock:
            # Keep history trimmed to last 200 entries to prevent file bloating
            if len(self.state.get("processed_uids", [])) > 500:
                self.state["processed_uids"] = self.state["processed_uids"][-400:]
            if len(self.state.get("replies_history", [])) > 200:
                self.state["replies_history"] = self.state["replies_history"][-150:]
            safe_atomic_write_json(REPLIES_STATE_FILE, self.state)

    def _is_ignored_sender(self, sender_email: str) -> bool:
        low = (sender_email or "").strip().lower()
        if not low or low == config.EMAIL_USER.lower():
            return True
        for pattern in IGNORE_SENDER_PATTERNS:
            if re.search(pattern, low, re.IGNORECASE):
                return True
        return False

    def check_inbox_for_replies(self, limit_search: int = 50) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Connects to Gmail INBOX via IMAP and scans for unhandled replies from prospective leads.
        Returns (count_of_new_replies, list_of_new_reply_objects).
        """
        with self._lock:
            new_replies = []
            if not config.EMAIL_USER or not config.EMAIL_APP_PASSWORD:
                logger.debug("Gmail credentials not provided; skipping inbox check.")
                return 0, []

            try:
                imap = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=15)
                imap.login(config.EMAIL_USER, config.EMAIL_APP_PASSWORD)
                status, _ = imap.select("INBOX", readonly=True)
                if status != "OK":
                    logger.warning("Could not open Gmail INBOX.")
                    imap.logout()
                    return 0, []

                # Find all message UIDs in INBOX
                res, data = imap.uid("SEARCH", None, "ALL")
                if res != "OK" or not data or not data[0]:
                    imap.logout()
                    return 0, []

                all_uids = [int(u) for u in data[0].split() if u.isdigit()]
                if not all_uids:
                    imap.logout()
                    return 0, []

                last_checked_uid = self.state.get("last_checked_uid", 0)

                # First run initialization: set last_checked_uid to the highest UID to avoid alerting on historical spam
                if last_checked_uid == 0:
                    self.state["last_checked_uid"] = max(all_uids)
                    self._save_state()
                    logger.info(f"Initialized inbox reply monitoring from UID: {self.state['last_checked_uid']}")
                    imap.logout()
                    return 0, []

                # Find candidate UIDs that are higher than last checked
                target_uids = [u for u in all_uids if u > last_checked_uid]

                # Fallback: also check the last few messages in case of re-checks
                if not target_uids and limit_search > 0:
                    recent = all_uids[-limit_search:]
                    processed_set = set(self.state.get("processed_uids", []))
                    target_uids = [u for u in recent if u not in processed_set]

                if not target_uids:
                    self.state["last_check_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self._save_state()
                    imap.logout()
                    return 0, []

                logger.info(f"Checking {len(target_uids)} candidate message UIDs in INBOX for lead replies...")

                # Build lookup maps of our database leads
                leads = self.data_service.get_all_leads()
                lead_by_email: Dict[str, Dict[str, Any]] = {}
                lead_by_domain: Dict[str, Dict[str, Any]] = {}

                for l in leads:
                    em = (l.get("email") or "").strip().lower()
                    if em:
                        lead_by_email[em] = l
                        for single_em in re.findall(r'[\w\.-]+@[\w\.-]+', em):
                            lead_by_email[single_em] = l
                            if "@" in single_em:
                                domain = single_em.split("@", 1)[1]
                                if domain not in ("gmail.com", "yahoo.com", "hotmail.com", "abv.bg", "mail.ru", "ukr.net"):
                                    lead_by_domain[domain] = l

                for uid in target_uids:
                    try:
                        r, mdata = imap.uid("FETCH", str(uid), "(BODY.PEEK[])")
                        if r != "OK" or not mdata:
                            continue

                        raw_email_bytes = None
                        for item in mdata:
                            if isinstance(item, tuple) and len(item) >= 2:
                                raw_email_bytes = item[1]
                                break

                        if not raw_email_bytes:
                            continue

                        msg = email.message_from_bytes(raw_email_bytes)

                        # Parse headers
                        from_raw = msg.get("From", "")
                        from_emails = re.findall(r'[\w\.-]+@[\w\.-]+', from_raw.lower())
                        sender_email = from_emails[0] if from_emails else ""

                        if not sender_email or self._is_ignored_sender(sender_email):
                            self.state.setdefault("processed_uids", []).append(uid)
                            continue

                        from_name = _decode_mime_header(from_raw.split("<")[0]) if "<" in from_raw else from_raw
                        subject = _decode_mime_header(msg.get("Subject", ""))
                        date_str = msg.get("Date", "")

                        # Extract text payload
                        body_text = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                ctype = part.get_content_type()
                                cdisp = str(part.get("Content-Disposition", ""))
                                if "attachment" in cdisp:
                                    continue
                                if ctype == "text/plain":
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        body_text = payload.decode("utf-8", errors="ignore")
                                        break
                                elif ctype == "text/html" and not body_text:
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        body_text = payload.decode("utf-8", errors="ignore")
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                body_text = payload.decode("utf-8", errors="ignore")

                        snippet = _clean_body_snippet(body_text)

                        # Determine if this message is a lead reply:
                        # 1. Direct email match
                        matched_lead = lead_by_email.get(sender_email)
                        # 2. Domain match
                        if not matched_lead and "@" in sender_email:
                            snd_domain = sender_email.split("@", 1)[1]
                            matched_lead = lead_by_domain.get(snd_domain)
                        # 3. Subject-based detection (Re: + Terawet keywords)
                        is_subject_reply = False
                        subj_low = subject.lower()
                        if "re:" in subj_low or "fwd:" in subj_low:
                            for kw in TERAWET_SUBJECT_KEYWORDS:
                                if kw in subj_low:
                                    is_subject_reply = True
                                    break

                        if matched_lead or is_subject_reply:
                            lead_company = matched_lead.get("company_name", from_name or sender_email) if matched_lead else (from_name or sender_email)
                            lead_country = matched_lead.get("country", "") if matched_lead else "Європа"
                            lead_flag = matched_lead.get("country_flag", "🌍") if matched_lead else "🌍"
                            lead_city = matched_lead.get("city", "") if matched_lead else ""
                            lead_phone = matched_lead.get("phone", "") if matched_lead else ""

                            reply_info = {
                                "uid": uid,
                                "email": sender_email,
                                "company_name": lead_company,
                                "country": lead_country,
                                "country_flag": lead_flag,
                                "city": lead_city,
                                "phone": lead_phone,
                                "subject": subject,
                                "date": date_str,
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "snippet": snippet
                            }

                            logger.info(f"🚨 Lead reply detected from {sender_email} ({lead_company}): '{subject}'")

                            # 1. Update lead status in local database
                            target_lead = matched_lead or {
                                "email": sender_email,
                                "company_name": lead_company,
                                "country": lead_country,
                                "country_flag": lead_flag,
                                "city": lead_city
                            }
                            self.data_service.mark_lead_replied(
                                lead=target_lead,
                                subject=subject,
                                snippet=snippet
                            )

                            # 2. Dispatch instant alert to Telegram
                            self.notifier.send_lead_reply_alert(reply_info)

                            # 3. Store in history
                            self.state.setdefault("replies_history", []).append(reply_info)
                            self.state["total_replies_detected"] = self.state.get("total_replies_detected", 0) + 1
                            new_replies.append(reply_info)

                        self.state.setdefault("processed_uids", []).append(uid)

                    except Exception as msg_err:
                        logger.error(f"Error processing INBOX UID {uid}: {msg_err}")
                        self.state.setdefault("processed_uids", []).append(uid)

                # Update watermark UID
                if target_uids:
                    self.state["last_checked_uid"] = max(self.state.get("last_checked_uid", 0), max(target_uids))
                self.state["last_check_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._save_state()

                imap.logout()

            except Exception as e:
                logger.error(f"InboxReplyService error: {e}", exc_info=True)

            return len(new_replies), new_replies

    def get_status(self) -> Dict[str, Any]:
        """Returns live statistics of detected inbound replies."""
        with self._lock:
            return {
                "total_replies_detected": self.state.get("total_replies_detected", 0),
                "last_check_timestamp": self.state.get("last_check_timestamp", "Не виконувався"),
                "latest_replies": (self.state.get("replies_history", []))[-10:],
                "telegram_connected": self.notifier.is_configured()
            }

    def start_background_scanner(self, interval_sec: int = 90):
        """Starts periodic background scanning thread."""
        with self._lock:
            if self.is_running:
                return
            self.is_running = True

            def _scanner_worker():
                logger.info(f"InboxReplyService background monitor started (polling every {interval_sec}s).")
                # Wait 15 seconds after initial launch before first scan
                time.sleep(15)
                while self.is_running:
                    try:
                        self.check_inbox_for_replies()
                    except Exception as e:
                        logger.debug(f"Background inbox check notice: {e}")
                    time.sleep(interval_sec)

            self.background_thread = threading.Thread(target=_scanner_worker, daemon=True)
            self.background_thread.start()
