import os
import time
import base64
import logging
import pickle
import imaplib
from typing import Dict, Any, List, Optional
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import config

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/gmail.compose']

class GmailDraftService:
    """
    Handles creation of drafts in Gmail / Google Workspace.
    
    Supports two connection methods:
    1. IMAP Drafts (App Password) - Easiest & fastest, no Google Cloud required!
    2. Google Cloud OAuth2 (credentials.json) - Official Google API
    3. Local HTML Preview - Fallback when credentials are not configured yet
    """

    def __init__(self):
        self.mode = "local"
        self.preview_dir = Path(config.LOCAL_DRAFTS_DIR)
        self.preview_dir.mkdir(parents=True, exist_ok=True)
        self.oauth_service = None

        # Check Method 1: App Password
        if config.EMAIL_USER and config.EMAIL_APP_PASSWORD:
            self.mode = "imap"
            logger.info(f"Using Gmail IMAP with user: {config.EMAIL_USER}")
        # Check Method 2: OAuth2
        elif config.GMAIL_ENABLED:
            if self._init_oauth_client():
                self.mode = "oauth"
        
        if self.mode == "local":
            logger.info("Using Local Drafts Preview Mode (no live email credentials configured).")

    def _init_oauth_client(self) -> bool:
        cred_path = Path(config.GMAIL_CREDENTIALS_FILE)
        token_path = Path(config.GMAIL_TOKEN_FILE)

        if not cred_path.exists() and not token_path.exists():
            return False

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            creds = None
            if token_path.exists():
                with open(token_path, 'rb') as token:
                    creds = pickle.load(token)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not cred_path.exists():
                        return False
                    flow = InstalledAppFlow.from_client_secrets_file(str(cred_path), SCOPES)
                    creds = flow.run_local_server(port=0)

                with open(token_path, 'wb') as token:
                    pickle.dump(creds, token)

            self.oauth_service = build('gmail', 'v1', credentials=creds)
            return True
        except Exception as e:
            logger.warning(f"OAuth initialization failed: {e}")
            return False

    def create_draft(self, to_email: str, subject: str, body_html: str, body_plain: str, company_name: str = "") -> str:
        """
        Creates a draft using the active mode (imap, oauth, or local).
        """
        if self.mode == "imap":
            try:
                return self._create_imap_draft(to_email, subject, body_html, body_plain)
            except Exception as e:
                logger.error(f"IMAP draft creation failed: {e}. Falling back to local preview.")
                return self._create_local_preview_draft(to_email, subject, body_html, body_plain, company_name)
        elif self.mode == "oauth" and self.oauth_service:
            try:
                return self._create_oauth_draft(to_email, subject, body_html, body_plain)
            except Exception as e:
                logger.error(f"OAuth draft creation failed: {e}. Falling back to local preview.")
                return self._create_local_preview_draft(to_email, subject, body_html, body_plain, company_name)
        else:
            return self._create_local_preview_draft(to_email, subject, body_html, body_plain, company_name)

    def _create_imap_draft(self, to_email: str, subject: str, body_html: str, body_plain: str) -> str:
        """Appends email directly into Gmail's Drafts folder via IMAP."""
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(config.EMAIL_USER, config.EMAIL_APP_PASSWORD)

        # Detect drafts folder name (Gmail uses [Gmail]/Drafts, [Gmail]/Чернетки, etc.)
        status, folder_list = imap.list()
        drafts_folder = '[Gmail]/Drafts'
        if status == 'OK':
            for folder_entry in folder_list:
                line = folder_entry.decode('utf-8', errors='ignore')
                if '\\Drafts' in line:
                    parts = line.split(' "/" ')
                    if len(parts) > 1:
                        drafts_folder = parts[-1].strip('"')
                        break

        message = MIMEMultipart("alternative")
        message['To'] = to_email
        message['From'] = f"{config.SENDER_NAME} <{config.EMAIL_USER}>"
        message['Subject'] = subject

        part1 = MIMEText(body_plain, 'plain', 'utf-8')
        part2 = MIMEText(body_html, 'html', 'utf-8')
        message.attach(part1)
        message.attach(part2)

        raw_bytes = message.as_bytes()
        internal_date = imaplib.Time2Internaldate(time.time())
        res, data = imap.append(f'"{drafts_folder}"', '\\Draft', internal_date, raw_bytes)
        imap.logout()

        draft_id = f"imap-draft-{int(time.time())}"
        logger.info(f"IMAP Draft successfully created in '{drafts_folder}' for {to_email}")
        return draft_id

    def _create_oauth_draft(self, to_email: str, subject: str, body_html: str, body_plain: str) -> str:
        """Creates draft using Google API Client."""
        message = MIMEMultipart("alternative")
        message['to'] = to_email
        message['subject'] = subject

        part1 = MIMEText(body_plain, 'plain', 'utf-8')
        part2 = MIMEText(body_html, 'html', 'utf-8')
        message.attach(part1)
        message.attach(part2)

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        body = {'message': {'raw': raw_message}}

        draft = self.oauth_service.users().drafts().create(userId='me', body=body).execute()
        draft_id = draft.get('id', '')
        logger.info(f"OAuth Gmail draft created with ID: {draft_id} for {to_email}")
        return f"gmail-draft-{draft_id}"

    def _create_local_preview_draft(self, to_email: str, subject: str, body_html: str, body_plain: str, company_name: str) -> str:
        """Saves a local visual HTML file for review."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_company = "".join(c for c in company_name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
        if not safe_company:
            safe_company = "lead"

        filename = f"draft_{timestamp}_{safe_company}.html"
        file_path = self.preview_dir / filename

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{subject}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background:#f4f6f8; padding:20px; }}
  .card {{ max-width:650px; margin:0 auto; background:#fff; border-radius:8px; box-shadow:0 2px 10px rgba(0,0,0,0.08); overflow:hidden; }}
  .header {{ background:#007001; color:#fff; padding:16px 20px; }}
  .meta {{ background:#e8f5e9; padding:12px 20px; border-bottom:1px solid #c8e6c9; font-size:13px; color:#2e7d32; }}
  .content {{ padding:24px 20px; line-height:1.6; color:#222; }}
  .badge {{ background:#ffd602; color:#222; font-weight:bold; padding:2px 8px; border-radius:4px; font-size:11px; text-transform:uppercase; }}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <h2 style="margin:0;font-size:18px;">🌱 TERAWET® Draft Email Preview</h2>
  </div>
  <div class="meta">
    <div><strong>To:</strong> {to_email} &nbsp; <span class="badge">Draft for Review</span></div>
    <div><strong>Subject:</strong> {subject}</div>
    <div><strong>Created:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
  </div>
  <div class="content">
    {body_html}
  </div>
</div>
</body>
</html>"""

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return f"preview-file-{filename}"

    def get_sent_recipients(self, limit: int = 200) -> Dict[str, Dict[str, Any]]:
        """
        Scans Gmail's Sent Mail folder via IMAP to find emails that were actually sent.
        Returns a dict mapping lowercase recipient email -> {date, subject}.
        """
        if self.mode != "imap":
            return {}

        import email
        from email.header import decode_header
        import re

        results = {}
        try:
            imap = imaplib.IMAP4_SSL("imap.gmail.com")
            imap.login(config.EMAIL_USER, config.EMAIL_APP_PASSWORD)

            status, folder_list = imap.list()
            sent_folder = None
            if status == 'OK':
                for f in folder_list:
                    line = f.decode('utf-8', errors='ignore')
                    if '\\Sent' in line:
                        parts = line.split(' "/" ')
                        if len(parts) > 1:
                            sent_folder = parts[-1].strip('"')
                            break

            if not sent_folder:
                sent_folder = '[Gmail]/Sent Mail'

            status, _ = imap.select(f'"{sent_folder}"', readonly=True)
            if status != 'OK':
                logger.warning(f"Could not open sent folder '{sent_folder}'")
                imap.logout()
                return {}

            status, messages = imap.search(None, 'ALL')
            if status == 'OK' and messages and messages[0]:
                msg_ids = messages[0].split()
                recent_ids = msg_ids[-limit:] if len(msg_ids) > limit else msg_ids
                chunk_size = 50
                for i in range(0, len(recent_ids), chunk_size):
                    chunk = recent_ids[i:i + chunk_size]
                    id_str = ','.join(m.decode('utf-8', errors='ignore') for m in chunk)
                    try:
                        res, data = imap.fetch(id_str, '(BODY.PEEK[HEADER.FIELDS (TO SUBJECT DATE)])')
                        if res == 'OK' and data:
                            for item in data:
                                if isinstance(item, tuple) and len(item) >= 2:
                                    raw_header = item[1].decode('utf-8', errors='ignore')
                                    msg = email.message_from_string(raw_header)
                                    to_raw = msg.get('To', '')
                                    found_emails = re.findall(r'[\w\.-]+@[\w\.-]+', to_raw.lower())

                                    raw_subj = msg.get('Subject', '')
                                    decoded_parts = decode_header(raw_subj)
                                    subj_str = ""
                                    for p, enc in decoded_parts:
                                        if isinstance(p, bytes):
                                            subj_str += p.decode(enc or 'utf-8', errors='ignore')
                                        else:
                                            subj_str += p

                                    date_str = msg.get('Date', '')
                                    for em in found_emails:
                                        if em not in results:
                                            results[em] = {
                                                "date": date_str,
                                                "subject": subj_str.strip()
                                            }
                    except Exception as e:
                        logger.debug(f"Error reading sent message batch: {e}")

            imap.logout()
            logger.info(f"Scanned Sent folder. Found {len(results)} sent recipients.")
        except Exception as e:
            logger.error(f"Error fetching sent messages via IMAP: {e}")

        return results

    def get_draft_recipients(self, limit: int = 100) -> Dict[str, Dict[str, Any]]:
        """
        Scans Gmail's Drafts folder via IMAP to find emails currently awaiting review.
        Returns a dict mapping lowercase recipient email -> {subject, to_raw}.
        """
        if self.mode != "imap":
            return {}

        import email
        from email.header import decode_header
        import re

        results = {}
        try:
            imap = imaplib.IMAP4_SSL("imap.gmail.com")
            imap.login(config.EMAIL_USER, config.EMAIL_APP_PASSWORD)

            status, folder_list = imap.list()
            drafts_folder = '[Gmail]/Drafts'
            if status == 'OK':
                for folder_entry in folder_list:
                    line = folder_entry.decode('utf-8', errors='ignore')
                    if '\\Drafts' in line:
                        parts = line.split(' "/" ')
                        if len(parts) > 1:
                            drafts_folder = parts[-1].strip('"')
                            break

            status, _ = imap.select(f'"{drafts_folder}"', readonly=True)
            if status != 'OK':
                imap.logout()
                return {}

            status, messages = imap.search(None, 'ALL')
            if status == 'OK' and messages and messages[0]:
                msg_ids = messages[0].split()
                recent_ids = msg_ids[-limit:] if len(msg_ids) > limit else msg_ids
                chunk_size = 50
                for i in range(0, len(recent_ids), chunk_size):
                    chunk = recent_ids[i:i + chunk_size]
                    id_str = ','.join(m.decode('utf-8', errors='ignore') for m in chunk)
                    try:
                        res, data = imap.fetch(id_str, '(BODY.PEEK[HEADER.FIELDS (TO SUBJECT DATE)])')
                        if res == 'OK' and data:
                            for item in data:
                                if isinstance(item, tuple) and len(item) >= 2:
                                    raw_header = item[1].decode('utf-8', errors='ignore')
                                    msg = email.message_from_string(raw_header)
                                    to_raw = msg.get('To', '')
                                    found_emails = re.findall(r'[\w\.-]+@[\w\.-]+', to_raw.lower())

                                    raw_subj = msg.get('Subject', '')
                                    decoded_parts = decode_header(raw_subj)
                                    subj_str = ""
                                    for p, enc in decoded_parts:
                                        if isinstance(p, bytes):
                                            subj_str += p.decode(enc or 'utf-8', errors='ignore')
                                        else:
                                            subj_str += str(p)

                                    for em in found_emails:
                                        if em not in results:
                                            results[em] = {
                                                "subject": subj_str.strip(),
                                                "to_raw": to_raw
                                            }
                    except Exception as e:
                        logger.debug(f"Error reading draft message batch: {e}")

            imap.logout()
            logger.info(f"Scanned Drafts folder. Found {len(results)} active drafts.")
        except Exception as e:
            logger.error(f"Error fetching draft messages via IMAP: {e}")

        return results

    def get_bounced_recipients(self, limit: int = 150) -> Dict[str, Dict[str, Any]]:
        """
        Scans Gmail's INBOX via IMAP for delivery failure notifications from Mailer-Daemon.
        Extracts the failed recipient email addresses.
        Returns a dict mapping lowercase bounced email -> {reason, date}.
        """
        if self.mode != "imap":
            return {}

        import email
        import re

        results = {}
        try:
            imap = imaplib.IMAP4_SSL("imap.gmail.com")
            imap.login(config.EMAIL_USER, config.EMAIL_APP_PASSWORD)

            status, _ = imap.select("INBOX", readonly=True)
            if status != 'OK':
                imap.logout()
                return {}

            status, messages = imap.search(None, '(OR FROM "mailer-daemon" FROM "Mail Delivery Subsystem")')
            if status == 'OK' and messages and messages[0]:
                msg_ids = messages[0].split()
                recent_ids = msg_ids[-limit:] if len(msg_ids) > limit else msg_ids
                chunk_size = 25
                for i in range(0, len(recent_ids), chunk_size):
                    chunk = recent_ids[i:i + chunk_size]
                    id_str = ','.join(m.decode('utf-8', errors='ignore') for m in chunk)
                    try:
                        res, data = imap.fetch(id_str, '(BODY.PEEK[HEADER] BODY.PEEK[TEXT])')
                        if res == 'OK' and data:
                            for item in data:
                                if isinstance(item, tuple) and len(item) >= 2:
                                    part_text = item[1].decode('utf-8', errors='ignore')
                                    failed_headers = re.findall(r'X-Failed-Recipients:\s*([\w\.-]+@[\w\.-]+)', part_text, re.IGNORECASE)
                                    all_emails = re.findall(r'[\w\.-]+@[\w\.-]+', part_text.lower())

                                    my_email = config.EMAIL_USER.lower() if config.EMAIL_USER else ""
                                    filtered_candidates = [
                                        e for e in (failed_headers + all_emails)
                                        if e != my_email and 'google' not in e and 'mailer-daemon' not in e and not e.endswith('.google.com') and not e.endswith('.gmail.com')
                                    ]

                                    date_match = re.search(r'Date:\s*(.+)', part_text, re.IGNORECASE)
                                    date_str = date_match.group(1).strip() if date_match else ""

                                    for em in filtered_candidates:
                                        if em not in results:
                                            results[em] = {
                                                "reason": "Gmail: Адреса не знайдена (Bounce)",
                                                "date": date_str
                                            }
                    except Exception as e:
                        logger.debug(f"Error parsing bounce message batch: {e}")

            imap.logout()
            logger.info(f"Scanned INBOX for bounces. Found {len(results)} bounced email addresses.")
        except Exception as e:
            logger.error(f"Error fetching bounced messages via IMAP: {e}")

        return results


