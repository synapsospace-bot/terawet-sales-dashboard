import os
import time
import json
import random
import logging
import threading
import html
from datetime import datetime, timezone, timedelta
try:
    import zoneinfo
    try:
        KYIV_TZ = zoneinfo.ZoneInfo("Europe/Kyiv")
    except Exception:
        KYIV_TZ = zoneinfo.ZoneInfo("Europe/Kiev")
except Exception:
    KYIV_TZ = timezone(timedelta(hours=2))

def get_kyiv_now() -> datetime:
    return datetime.now(KYIV_TZ)
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import config
from sheets_service import LeadDataService, safe_atomic_write_json
from lead_deduplicator import MasterSentRegistry, extract_clean_emails, extract_corporate_domains, normalize_comp_name
from agent_brain import TerawetAgentBrain
from gmail_service import GmailDraftService
from lead_finder import LeadFinderService
from email_verifier import EmailVerifierService

logger = logging.getLogger("AutoOutreach")

OUTREACH_STATE_FILE = config.BASE_DIR / "outreach_state.json"

class AutoOutreachService:
    """
    Autonomous Daily Cold Outreach & Anti-Spam Dispatch Engine for TERAWET-ORIGINAL®.
    
    Key Features:
    1. Daily Autonomous Schedule: Automatically discovers & sends 50 leads every morning at 09:30 AM.
    2. Anti-Spam Throttling & Warming: Random jitter pauses (45-90 seconds) between sends to protect Gmail.
    3. Daily Sending Quotas: Caps daily sends to stay safely under Google Workspace / Gmail limits.
    4. DNS MX Pre-flight Shield: Pre-validates deliverability before sending to prevent bounces.
    5. Live Dashboard Reporting: Full status tracking, live countdown, progress bar, and dispatch logs.
    6. Thread-safe Emergency Controls: Real-time start, pause, and emergency stop.
    """

    def __init__(
        self,
        data_service: Optional[LeadDataService] = None,
        agent_brain: Optional[TerawetAgentBrain] = None,
        draft_service: Optional[GmailDraftService] = None,
        finder_service: Optional[LeadFinderService] = None,
        verifier_service: Optional[EmailVerifierService] = None
    ):
        self.data_service = data_service or LeadDataService()
        self.agent_brain = agent_brain or TerawetAgentBrain()
        self.draft_service = draft_service or GmailDraftService()
        self.finder_service = finder_service or LeadFinderService(data_service=self.data_service)
        self.verifier = verifier_service or EmailVerifierService()

        self._lock = threading.RLock()
        self.stop_event = threading.Event()
        self.is_running = False
        self.current_thread: Optional[threading.Thread] = None

        # Live runtime indicators
        self.current_lead_name = ""
        self.current_lead_email = ""
        self.current_step_text = ""
        self.last_step_timestamp = time.time()
        self.progress_current = 0
        self.progress_total = 0
        self.delay_remaining_sec = 0
        self.last_run_status = "idle"  # idle, running, stopped, completed, error

        # Load persisted settings & metrics
        self.state = self._load_state()

        # Start daily background scheduler loop
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        logger.info("AutoOutreachService initialized and background scheduler started.")

    def _update_step(self, text: str, cur: Optional[int] = None, tot: Optional[int] = None, lead_name: str = "", lead_email: str = ""):
        with self._lock:
            self.current_step_text = text
            self.last_step_timestamp = time.time()
            if cur is not None:
                self.progress_current = cur
            if tot is not None:
                self.progress_total = tot
            if lead_name:
                self.current_lead_name = lead_name
            if lead_email:
                self.current_lead_email = lead_email

    def _default_state(self) -> Dict[str, Any]:
        today_str = datetime.now().strftime("%Y-%m-%d")
        return {
            "enabled": True,
            "schedule_hour": 9,
            "schedule_minute": 30,
            "daily_target": 50,
            "min_delay_seconds": 45,
            "max_delay_seconds": 90,
            "send_mode": "send",  # "send" (direct dispatch via SMTP) or "draft" (create drafts for review)
            "today_date": today_str,
            "sent_today": 0,
            "last_run_date": "",
            "last_run_timestamp": "",
            "last_run_summary": {
                "discovered": 0,
                "sent": 0,
                "failed": 0,
                "skipped_invalid": 0,
                "duration_minutes": 0.0
            },
            "dispatch_log": []
        }

    def _load_state(self) -> Dict[str, Any]:
        default = self._default_state()
        bak_file = OUTREACH_STATE_FILE.with_suffix(OUTREACH_STATE_FILE.suffix + ".bak")
        for p in (OUTREACH_STATE_FILE, bak_file):
            if p.exists() and p.stat().st_size > 0:
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            default.update(data)
                            break
                except Exception as e:
                    logger.warning(f"Could not load outreach state from {p}: {e}")

        # Reset daily counter if a new day has arrived
        today_str = datetime.now().strftime("%Y-%m-%d")
        if default.get("today_date") != today_str:
            default["today_date"] = today_str
            default["sent_today"] = 0
            default["dispatch_log"] = []

        return default

    def _save_state(self):
        with self._lock:
            try:
                safe_atomic_write_json(OUTREACH_STATE_FILE, self.state)
            except Exception as e:
                logger.error(f"Failed to atomically save outreach state: {e}")

    def update_settings(self, new_settings: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            for k in ("enabled", "schedule_hour", "schedule_minute", "daily_target", "min_delay_seconds", "max_delay_seconds", "send_mode"):
                if k in new_settings:
                    val = new_settings[k]
                    if k in ("schedule_hour", "schedule_minute", "daily_target", "min_delay_seconds", "max_delay_seconds"):
                        try:
                            val = int(val)
                        except (ValueError, TypeError):
                            continue
                    elif k == "enabled":
                        val = bool(val)
                    elif k == "send_mode":
                        val = "send" if str(val).lower() == "send" else "draft"
                    self.state[k] = val

            self._save_state()
            logger.info(f"Updated outreach settings: {new_settings}")
            return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            today_str = datetime.now().strftime("%Y-%m-%d")
            if self.state.get("today_date") != today_str:
                self.state["today_date"] = today_str
                self.state["sent_today"] = 0
                self.state["dispatch_log"] = []
                self._save_state()

            return {
                "is_running": self.is_running,
                "status": self.last_run_status,
                "current_lead_name": self.current_lead_name,
                "current_lead_email": self.current_lead_email,
                "current_step_text": self.current_step_text,
                "progress_current": self.progress_current,
                "progress_total": self.progress_total,
                "delay_remaining_sec": self.delay_remaining_sec,
                "enabled": self.state.get("enabled", True),
                "schedule_hour": self.state.get("schedule_hour", 9),
                "schedule_minute": self.state.get("schedule_minute", 30),
                "daily_target": self.state.get("daily_target", 50),
                "min_delay_seconds": self.state.get("min_delay_seconds", 45),
                "max_delay_seconds": self.state.get("max_delay_seconds", 90),
                "send_mode": self.state.get("send_mode", "send"),
                "sent_today": self.state.get("sent_today", 0),
                "last_run_date": self.state.get("last_run_date", ""),
                "last_run_timestamp": self.state.get("last_run_timestamp", ""),
                "last_run_summary": self.state.get("last_run_summary", {}),
                "dispatch_log": self.state.get("dispatch_log", [])[-25:]  # Return most recent 25 items
            }

    def start_dispatch(self, count: int = 50, mode: Optional[str] = None, triggered_by: str = "manual") -> Tuple[bool, str]:
        """
        Starts the automated dispatch worker thread.
        Discovers new leads if needed, generates AI pitches, and dispatches with anti-spam pacing.
        """
        with self._lock:
            if self.is_running:
                return False, "Розсилка вже виконується"

            today_str = datetime.now().strftime("%Y-%m-%d")
            if self.state.get("today_date") != today_str:
                self.state["today_date"] = today_str
                self.state["sent_today"] = 0
                self.state["dispatch_log"] = []

            # Check daily quota
            daily_target = self.state.get("daily_target", 50)
            already_sent = self.state.get("sent_today", 0)
            if already_sent >= daily_target and triggered_by == "scheduler":
                msg = f"Денний ліміт відправки ({daily_target} листів) на сьогодні вже досягнуто."
                logger.info(msg)
                return False, msg

            effective_count = count if count > 0 else daily_target
            effective_mode = mode if mode in ("send", "draft") else self.state.get("send_mode", "send")

            self.is_running = True
            self.stop_event.clear()
            self.last_run_status = "running"
            self.progress_current = 0
            self.progress_total = effective_count
            self.current_step_text = "Ініціалізація розсилки..."

            self.current_thread = threading.Thread(
                target=self._run_dispatch_worker,
                args=(effective_count, effective_mode, triggered_by),
                daemon=True
            )
            self.current_thread.start()
            logger.info(f"🚀 Outreach dispatch worker started: target={effective_count}, mode={effective_mode}, trigger={triggered_by}")
            return True, f"Авто-розсилку запущено на {effective_count} лідів (Режим: {effective_mode.upper()})"

    def stop_dispatch(self) -> Tuple[bool, str]:
        """Gracefully aborts any ongoing dispatch."""
        with self._lock:
            if not self.is_running:
                return False, "Розсилка наразі не виконується"

            self.stop_event.set()
            self._update_step("Зупинка розсилки за запитом...")
            logger.info("🛑 Outreach stop requested by user.")
            return True, "Запит на зупинку розсилки надіслано"

    def reset_dispatch(self, reason: str = "Ручне або автоматичне скидання завислого воркера") -> Tuple[bool, str]:
        """Forces the dispatch state back to idle, releasing any stuck flags."""
        with self._lock:
            self.stop_event.set()
            self.is_running = False
            self.delay_remaining_sec = 0
            self.last_run_status = "idle"
            self.current_step_text = f"Воркер скинуто: {reason}"
            self.last_step_timestamp = time.time()
            self._save_state()
            logger.warning(f"Outreach worker forcibly reset: {reason}")
            return True, f"Статус розсилки скинуто: {reason}"

    def _sleep_with_cancel(self, duration_sec: float) -> bool:
        """
        Sleeps in 1-second chunks while updating self.delay_remaining_sec.
        Returns False if cancelled by stop_event, True if completed.
        """
        remaining = int(duration_sec)
        while remaining > 0:
            if self.stop_event.is_set():
                self.delay_remaining_sec = 0
                return False
            self.delay_remaining_sec = remaining
            time.sleep(1)
            remaining -= 1
        self.delay_remaining_sec = 0
        return True

    def _run_dispatch_worker(self, target_count: int, mode: str, triggered_by: str):
        start_time = time.time()
        discovered_count = 0
        sent_count = 0
        failed_count = 0
        skipped_invalid = 0

        try:
            logger.info(f"▶️ Starting auto-outreach run (target: {target_count}, mode: {mode})...")
            self._update_step("Синхронізація надісланих листів із Gmail...")

            # 0. Ironclad Sync: verify all sent emails directly from Gmail Sent Mail & sanitize database
            # Wrapped in a 15-second worker thread to guarantee dispatch never hangs on slow IMAP connections
            try:
                def _preflight_task():
                    try:
                        self.data_service.sync_sent_emails(self.draft_service, limit=150)
                        self.data_service.sanitize_all_databases()
                    except Exception as pe:
                        logger.warning(f"Pre-flight sync error: {pe}")
                sync_t = threading.Thread(target=_preflight_task, daemon=True)
                sync_t.start()
                sync_t.join(timeout=15)
                if sync_t.is_alive():
                    logger.warning("Pre-flight sync took longer than 15s; proceeding with outreach using cached database.")
            except Exception as sync_err:
                logger.warning(f"Pre-flight sync/sanitize warning: {sync_err}")

            # 1. Build ironclad Master Sent Registry
            sent_registry = self.data_service.get_sent_registry()
            session_registry = MasterSentRegistry()

            # 2. Fetch existing uncontacted leads with STRICT exclusion of any sent email, domain, or company
            all_leads = self.data_service.get_all_leads()
            uncontacted = []
            for l in all_leads:
                st = l.get("status", "")
                is_dup, reason = sent_registry.is_duplicate(l)
                if is_dup or "✅" in st or "💬" in st:
                    if "✅" not in st and "💬" not in st:
                        logger.info(f"Marking previously contacted lead as sent: {l.get('company_name')} ({reason})")
                        self.data_service.mark_email_sent(l, l.get("subject", ""), "")
                    continue

                if "⚪" in st or "NEW" in st.upper():
                    uncontacted.append(l)

            needed_discovery = target_count - len(uncontacted)
            if needed_discovery > 0 and not self.stop_event.is_set():
                logger.info(f"Have {len(uncontacted)} uncontacted leads in cache; searching {needed_discovery} more fresh prospects...")
                imported = self.finder_service.find_and_import_leads(
                    count=needed_discovery,
                    stop_event=self.stop_event
                )
                discovered_count = imported
                sent_registry = self.data_service.get_sent_registry()
                all_leads = self.data_service.get_all_leads()
                uncontacted = []
                for l in all_leads:
                    st = l.get("status", "")
                    is_dup, reason = sent_registry.is_duplicate(l)
                    if is_dup or "✅" in st or "💬" in st:
                        continue
                    if "⚪" in st or "NEW" in st.upper():
                        uncontacted.append(l)

            leads_to_process = uncontacted[:target_count]
            self.progress_total = len(leads_to_process)
            logger.info(f"Ready to process {len(leads_to_process)} leads with anti-spam pacing.")

            if not leads_to_process:
                logger.info("No uncontacted leads available in database.")
                with self._lock:
                    self.last_run_status = "completed"
                    self.current_step_text = "Немає лідів, що очікують відправки. Запустіть 'Пошук нових лідів'."
                return

            for i, lead in enumerate(leads_to_process, start=1):
                if self.stop_event.is_set():
                    logger.info("Outreach run aborted by user stop_event.")
                    break

                comp_name = lead.get("company_name", "Невідома компанія")
                email = lead.get("email", "").strip()
                country = lead.get("country", "")
                flag = lead.get("country_flag", "")
                lang = lead.get("language", "en")

                # In-loop deduplication check against global sent registry and this session
                is_dup, reason = sent_registry.is_duplicate(lead)
                if not is_dup:
                    is_dup, reason = session_registry.is_duplicate(lead)

                if is_dup:
                    logger.warning(f"⏩ In-loop skipping duplicate lead {comp_name} ({email}) - {reason}")
                    continue

                self.current_lead_name = comp_name
                self.current_lead_email = email
                self.progress_current = i
                self.current_step_text = f"Генерація листа для {comp_name} ({i}/{len(leads_to_process)})..."

                # Step A: DNS MX Pre-flight check
                is_valid, reason = self.verifier.verify_email(email)
                if not is_valid:
                    logger.warning(f"Skipping {comp_name} ({email}): DNS check failed: {reason}")
                    self.data_service.mark_status(email, f"⚠️ Недійсний email ({reason})")
                    skipped_invalid += 1
                    continue

                # Step B: AI Copywriter pitch generation
                try:
                    subject, body_html, body_plain = self.agent_brain.generate_pitch(lead)
                except Exception as ex:
                    logger.error(f"Error generating pitch for {comp_name}: {ex}")
                    failed_count += 1
                    continue

                # Step C: Dispatch or Draft Creation
                now_str = datetime.now().strftime("%H:%M:%S")

                # Final pre-send ironclad verification against sent_registry and session_registry
                is_dup_pre, dup_reason = sent_registry.is_duplicate(lead)
                if not is_dup_pre:
                    is_dup_pre, dup_reason = session_registry.is_duplicate(lead)
                if is_dup_pre:
                    logger.warning(f"🚨 Pre-send duplicate blocked: {comp_name} ({email}) - {dup_reason}")
                    self.data_service.mark_email_sent(lead, "Already Contacted", "")
                    skipped_invalid += 1
                    continue

                if mode == "send":
                    self.current_step_text = f"Відправка листа через Gmail до {comp_name}..."
                    ok, res = self.draft_service.send_email(
                        to_email=email,
                        subject=subject,
                        body_html=body_html,
                        body_plain=body_plain,
                        company_name=comp_name
                    )
                    if ok:
                        self.data_service.mark_email_sent(lead, subject, body_plain)
                        sent_count += 1
                        sent_registry.register_lead(lead, is_sent=True)
                        session_registry.register_lead(lead, is_sent=True)

                        with self._lock:
                            self.state["sent_today"] = self.state.get("sent_today", 0) + 1
                            self.state.setdefault("dispatch_log", []).append({
                                "time": now_str,
                                "company": comp_name,
                                "email": email,
                                "country": f"{flag} {country}".strip(),
                                "subject": subject,
                                "status": "✅ Надіслано",
                                "mode": "send"
                            })
                            self._save_state()
                        logger.info(f"[{i}/{len(leads_to_process)}] Sent email to {comp_name} ({email})")
                    else:
                        failed_count += 1
                        logger.error(f"[{i}/{len(leads_to_process)}] Failed sending to {comp_name}: {res}")
                        with self._lock:
                            self.state.setdefault("dispatch_log", []).append({
                                "time": now_str,
                                "company": comp_name,
                                "email": email,
                                "country": f"{flag} {country}".strip(),
                                "subject": subject,
                                "status": f"❌ {res[:40]}",
                                "mode": "send"
                            })
                            self._save_state()

                        # Fail-fast defense: if 2 sends fail with 0 successes, halt immediately
                        if failed_count >= 2 and sent_count == 0:
                            is_blocked = "101" in str(res) or "unreachable" in str(res).lower()
                            if is_blocked:
                                halt_reason = "Хмарний хостинг Render блокує вихідні порти SMTP (465/587). Оберіть у налаштуваннях режим 'Чернетки' (IMAP 993) або запустіть сценарій на Mac для прямої відправки."
                            else:
                                halt_reason = f"Помилка пошти Gmail: {res[:60]}"
                            logger.error(f"Halting dispatch worker: {halt_reason}")
                            with self._lock:
                                self.last_run_status = "error"
                                self.current_step_text = halt_reason
                            try:
                                from telegram_notifier import telegram_notifier
                                telegram_notifier.send_alert(
                                    "РОЗСИЛКУ ПРИЗУПИНЕНО",
                                    f"⚠️ <b>{html.escape(halt_reason)}</b>\n\n"
                                    f"👉 <b>Безпека:</b> Жоден лід не постраждав, усі 100% контактів збережені в базі зі статусом 'Очікує відправки'."
                                )
                            except Exception as tg_err:
                                logger.warning(f"Could not dispatch halt alert to Telegram: {tg_err}")
                            break
                else:
                    # Mode == draft
                    self.current_step_text = f"Створення чернетки Gmail для {comp_name}..."
                    draft_id = self.draft_service.create_draft(
                        to_email=email,
                        subject=subject,
                        body_html=body_html,
                        body_plain=body_plain,
                        company_name=comp_name
                    )
                    self.data_service.mark_draft_created(lead, draft_id, subject, body_plain)
                    sent_count += 1
                    sent_registry.register_lead(lead, is_sent=True)
                    session_registry.register_lead(lead, is_sent=True)

                    with self._lock:
                        self.state["sent_today"] = self.state.get("sent_today", 0) + 1
                        self.state.setdefault("dispatch_log", []).append({
                            "time": now_str,
                            "company": comp_name,
                            "email": email,
                            "country": f"{flag} {country}".strip(),
                            "subject": subject,
                            "status": "🟡 Чернетка",
                            "mode": "draft"
                        })
                        self._save_state()

                # Step D: Smart Jitter & Anti-Spam Pause
                # Only pause if not the last item and stop not requested
                if i < len(leads_to_process) and not self.stop_event.is_set():
                    min_d = self.state.get("min_delay_seconds", 45)
                    max_d = self.state.get("max_delay_seconds", 90)
                    jitter_delay = random.uniform(min_d, max_d)
                    self.current_step_text = f"Анти-спам пауза ({int(jitter_delay)}с) для захисту репутації Gmail..."
                    logger.info(f"Anti-spam pause: {int(jitter_delay)}s before next lead...")
                    completed = self._sleep_with_cancel(jitter_delay)
                    if not completed:
                        logger.info("Delay interrupted by user stop_event.")
                        break

            # Finish Summary
            elapsed_min = round((time.time() - start_time) / 60.0, 1)
            today_str = datetime.now().strftime("%Y-%m-%d")
            timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with self._lock:
                if self.stop_event.is_set():
                    self.last_run_status = "stopped"
                    self.current_step_text = f"Розсилку зупинено. Надіслано листів: {sent_count}"
                elif failed_count > 0 and sent_count == 0:
                    self.last_run_status = "error"
                    self.current_step_text = f"Помилка відправки (Перевірте реквізити Gmail)"
                else:
                    self.last_run_status = "completed"
                    self.current_step_text = f"Розсилку завершено! Успішно опрацьовано: {sent_count} лідів."

                self.state["last_run_date"] = today_str
                self.state["last_run_timestamp"] = timestamp_str
                self.state["last_run_summary"] = {
                    "discovered": discovered_count,
                    "sent": sent_count,
                    "failed": failed_count,
                    "skipped_invalid": skipped_invalid,
                    "duration_minutes": elapsed_min,
                    "triggered_by": triggered_by,
                    "mode": mode
                }
                self._save_state()

            logger.info(f"🎉 Outreach session finished! Sent: {sent_count}, Failed: {failed_count}, Invalid: {skipped_invalid}, Time: {elapsed_min}m")

            # Dispatch Daily Telegram Report
            try:
                from telegram_notifier import telegram_notifier
                countries_stats = {}
                for l in leads_to_process[:sent_count]:
                    c_name = l.get("country", "Європа")
                    c_flag = l.get("country_flag", "")
                    label = f"{c_flag} {c_name}".strip()
                    countries_stats[label] = countries_stats.get(label, 0) + 1

                telegram_summary = {
                    "today_date": today_str,
                    "timestamp": timestamp_str.split(" ")[1] if " " in timestamp_str else timestamp_str,
                    "target_count": target_count,
                    "sent_count": sent_count,
                    "failed_count": failed_count,
                    "skipped_invalid": skipped_invalid,
                    "duration_minutes": elapsed_min,
                    "status": self.last_run_status,
                    "mode": mode,
                    "countries": countries_stats
                }
                telegram_notifier.send_daily_outreach_report(telegram_summary)
                logger.info("Sent daily outreach report to Telegram.")
            except Exception as tg_err:
                logger.error(f"Failed sending Telegram daily outreach report: {tg_err}")

        except Exception as e:
            logger.error(f"Critical error in outreach worker: {e}", exc_info=True)
            with self._lock:
                self.last_run_status = "error"
                self.current_step_text = f"Помилка розсилки: {e}"
        finally:
            with self._lock:
                self.is_running = False
                self.delay_remaining_sec = 0

    def _scheduler_loop(self):
        """
        Runs continuously in background, checking every 30 seconds.
        Triggers daily auto-dispatch at the configured schedule_hour:schedule_minute.
        """
        logger.info("Autonomous daily scheduler loop started.")
        time.sleep(15)  # Wait for startup

        while True:
            try:
                now = get_kyiv_now()
                today_str = now.strftime("%Y-%m-%d")

                with self._lock:
                    enabled = self.state.get("enabled", True)
                    sched_hour = self.state.get("schedule_hour", 9)
                    sched_min = self.state.get("schedule_minute", 30)
                    last_run = self.state.get("last_run_date", "")
                    daily_target = self.state.get("daily_target", 50)
                    send_mode = self.state.get("send_mode", "send")
                    is_running = self.is_running

                # Watchdog check: if is_running is True, but no step progress has occurred for > 15 minutes:
                if is_running:
                    stuck_seconds = time.time() - getattr(self, "last_step_timestamp", time.time())
                    if stuck_seconds > 900:  # 15 minutes of zero activity
                        step_info = self.current_step_text or "Невідомий крок"
                        logger.error(f"🚨 [WATCHDOG RESET] Dispatch worker stalled for {int(stuck_seconds / 60)} min at '{step_info}'. Forcing reset!")
                        self.reset_dispatch(f"Скинуто Watchdog'ом (зависання {int(stuck_seconds / 60)} хв на: {step_info})")
                        try:
                            from telegram_notifier import telegram_notifier
                            import html
                            telegram_notifier.send_alert(
                                "АВТО-ВІДНОВЛЕННЯ ДЕМОНА РОЗСИЛКИ",
                                f"⚠️ <b>Воркер завис і був автоматично скинутий Watchdog'ом:</b>\n"
                                f"Крок: {html.escape(step_info)}\n"
                                f"Час зависання: {int(stuck_seconds / 60)} хв.\n\n"
                                f"✅ Статус примусово скинуто в Idle для розблокування запланованих завдань."
                            )
                        except Exception as tg_err:
                            logger.warning(f"Could not dispatch watchdog alert: {tg_err}")
                        is_running = False

                # Trigger condition:
                # 1. Enabled
                # 2. Not running
                # 3. Has not run yet today
                # 4. Current time matches or exceeds configured hour and minute
                if enabled and not is_running and last_run != today_str:
                    if (now.hour > sched_hour) or (now.hour == sched_hour and now.minute >= sched_min):
                        logger.info(f"⏰ [DAILY OUTREACH TRIGGER] Starting scheduled outreach for {daily_target} leads (Target: {sched_hour:02d}:{sched_min:02d})...")
                        self.start_dispatch(count=daily_target, mode=send_mode, triggered_by="scheduler")

            except Exception as e:
                logger.error(f"Scheduler loop exception: {e}")

            time.sleep(30)
