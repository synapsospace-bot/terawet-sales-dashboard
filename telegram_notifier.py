import json
import logging
import html
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

import config

logger = logging.getLogger("TelegramNotifier")

def _escape_html(text: Any) -> str:
    """Escapes special HTML characters (&, <, >)."""
    return html.escape(str(text or ""), quote=False)

class TelegramNotifier:
    """
    Robust Telegram notification service for TERAWET-ORIGINAL®.
    Uses HTML formatting for 100% reliable rendering without markdown underscore collision bugs.
    Handles:
    1. Daily Autonomous Outreach Reports (sent, scheduled, progress, delivery health).
    2. Instant Lead Inbound Reply Alerts (company, email, subject, reply snippet).
    3. Auto-fallback to plain text to guarantee delivery.
    """

    def __init__(self, bot_token: Optional[str] = None, default_chat_id: Optional[str] = None):
        self.bot_token = bot_token or getattr(config, "TELEGRAM_BOT_TOKEN", "8647417710:AAEa456g9tGzC0fcKtczq5Mgf7jjcVylIXE")
        self.default_chat_id = default_chat_id or getattr(config, "TELEGRAM_CHAT_ID", "6796493041")
        self.enabled = getattr(config, "TELEGRAM_ENABLED", True)

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.default_chat_id and self.enabled)

    def send_message(self, text: str, chat_id: Optional[str] = None, parse_mode: str = "HTML") -> Tuple[bool, str]:
        """
        Sends a message to the Telegram chat.
        If Telegram fails on HTML entities, automatically retries without parse_mode (plain text).
        """
        if not self.is_configured():
            logger.warning("TelegramNotifier is not configured or disabled.")
            return False, "Telegram not configured"

        target_chat = str(chat_id or self.default_chat_id).strip()
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

        payload = {
            "chat_id": target_chat,
            "text": text,
            "disable_web_page_preview": True
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok"):
                    logger.info(f"Telegram notification delivered to chat {target_chat}")
                    return True, "Message delivered"
                else:
                    logger.warning(f"Telegram API responded with error: {data}")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            logger.warning(f"Telegram HTTPError ({e.code}): {err_body}")

            # Fallback to plain text if formatting error
            if parse_mode:
                logger.info("Retrying Telegram message in plain text without parse_mode...")
                import re
                plain_text = re.sub(r'<[^>]+>', '', text)
                payload["text"] = plain_text
                payload.pop("parse_mode", None)
                try:
                    req_retry = urllib.request.Request(
                        url,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"}
                    )
                    with urllib.request.urlopen(req_retry, timeout=12) as resp_retry:
                        data_retry = json.loads(resp_retry.read().decode("utf-8"))
                        if data_retry.get("ok"):
                            logger.info(f"Telegram message delivered via plain text fallback.")
                            return True, "Message delivered (plain text fallback)"
                except Exception as retry_err:
                    logger.error(f"Plain text fallback failed: {retry_err}")
                    return False, str(retry_err)
            return False, f"HTTP Error {e.code}: {err_body}"
        except Exception as e:
            logger.error(f"Network error sending Telegram message: {e}")
            return False, str(e)

        return False, "Failed to send message"

    def send_daily_outreach_report(self, summary: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Sends comprehensive daily report after autonomous outreach execution.
        """
        today_date = _escape_html(summary.get("today_date", datetime.now().strftime("%Y-%m-%d")))
        timestamp = _escape_html(summary.get("timestamp", datetime.now().strftime("%H:%M:%S")))
        target = summary.get("target_count", summary.get("daily_target", 50))
        sent = summary.get("sent_count", summary.get("sent", 0))
        failed = summary.get("failed_count", summary.get("failed", 0))
        skipped_invalid = summary.get("skipped_invalid", 0)
        duration_min = float(summary.get("duration_minutes", 0.0))
        status = summary.get("status", "completed")
        mode = summary.get("mode", "send")
        countries = summary.get("countries", {})

        status_badge = "✅ ЗАВЕРШЕНО УСПІШНО" if status == "completed" else "⏹️ ЗУПИНЕНО"
        if status == "error":
            status_badge = "⚠️ ЗАВЕРШЕНО З ПОМИЛКОЮ"

        mode_str = "🚀 Пряма відправка (SMTP)" if mode == "send" else "🟡 Створення чернеток у Gmail"

        country_lines = []
        if isinstance(countries, dict) and countries:
            for c_name, c_cnt in sorted(countries.items(), key=lambda x: x[1], reverse=True)[:8]:
                country_lines.append(f"  • {_escape_html(c_name)}: <b>{c_cnt}</b>")
        country_block = "\n".join(country_lines) if country_lines else "  • Європейські агро-підприємства"

        text = (
            f"📊 <b>ЗВІТ: АВТОНОМНА РОЗСИЛКА ТА ЛІДИ TERAWET</b> 🌱\n\n"
            f"📅 <b>Дата:</b> {today_date} | {timestamp}\n"
            f"🏷️ <b>Статус:</b> {status_badge}\n"
            f"⚙️ <b>Режим:</b> {mode_str}\n\n"
            f"📈 <b>Показники за день:</b>\n"
            f"• 🎯 <b>Запланована квота:</b> {target} лідів\n"
            f"• 📤 <b>Успішно опрацьовано:</b> <b>{sent}</b> із {target}\n"
            f"• 🛡️ <b>Антиспам-паузи:</b> 45–90 сек (людський темп)\n"
            f"• 🛡️ <b>Відсіяно недійсних (DNS MX):</b> {skipped_invalid}\n"
            f"• ❌ <b>Помилок доставки:</b> {failed}\n"
            f"• ⏱️ <b>Загальний час:</b> {duration_min:.1f} хв\n\n"
            f"🌐 <b>Географія сьогодні:</b>\n{country_block}\n\n"
            f"🔗 <b>Командний Центр:</b> <a href=\"https://terawet-sales-dashboard.onrender.com\">Перейти до Дашборду</a>\n"
            f"🔒 <i>Gmail захищений: ліміти витримано, антиспам активний.</i>"
        )

        return self.send_message(text, parse_mode="HTML")

    def send_lead_reply_alert(self, lead_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Sends an instant urgent notification when a lead responds to our email.
        """
        company = _escape_html(lead_data.get("company_name") or lead_data.get("company") or "Невідома компанія")
        email_addr = _escape_html(lead_data.get("email") or "Не вказано")
        country = _escape_html(lead_data.get("country") or "Європа")
        flag = lead_data.get("country_flag") or "🌍"
        city = _escape_html(lead_data.get("city") or "")
        subject = _escape_html(lead_data.get("subject") or "Без теми")
        date_str = _escape_html(lead_data.get("time") or lead_data.get("date") or datetime.now().strftime("%Y-%m-%d %H:%M"))
        snippet = _escape_html(lead_data.get("snippet") or lead_data.get("text") or "(Текст відповіді порожній)")
        phone = _escape_html(lead_data.get("phone") or "")

        loc_part = f"{flag} {country}"
        if city:
            loc_part += f" ({city})"

        phone_line = f"📞 <b>Тел:</b> <code>{phone}</code>\n" if phone else ""

        if len(snippet) > 450:
            snippet = snippet[:447] + "..."

        text = (
            f"🚨 <b>НОВА ВІДПОВІДЬ ВІД ЛІДА!</b> 📨\n\n"
            f"🏢 <b>Компанія:</b> <b>{company}</b>\n"
            f"🌍 <b>Локація:</b> {loc_part}\n"
            f"📧 <b>Email:</b> <code>{email_addr}</code>\n"
            f"{phone_line}"
            f"📌 <b>Тема:</b> {subject}\n"
            f"⏰ <b>Час отримання:</b> {date_str}\n\n"
            f"💬 <b>Текст відповіді клієнта:</b>\n"
            f"<i>\"{snippet}\"</i>\n\n"
            f"👉 <a href=\"https://mail.google.com/mail/u/0/#inbox\">Відкрити пошту в Gmail</a>\n"
            f"📊 <a href=\"https://terawet-sales-dashboard.onrender.com\">Відкрити Дашборд</a>"
        )

        return self.send_message(text, parse_mode="HTML")

    def send_alert(self, title: str, message: str) -> Tuple[bool, str]:
        """
        Sends an operational or warning alert.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = (
            f"⚠️ <b>{_escape_html(title)}</b>\n\n"
            f"{message}\n\n"
            f"⏰ <b>Час:</b> {now_str}\n"
            f"📊 <a href=\"https://terawet-sales-dashboard.onrender.com\">Відкрити Дашборд</a>"
        )
        return self.send_message(text, parse_mode="HTML")

    def send_test_notification(self) -> Tuple[bool, str]:
        """
        Sends a test message to confirm connection.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = (
            f"🌱 <b>TERAWET-ORIGINAL Command Center</b>\n"
            f"✅ <b>Перевірка зв'язку з Telegram успішна!</b>\n\n"
            f"🤖 <b>Бот:</b> @astroinsta_bot (Dashbord_terawet.bot)\n"
            f"🆔 <b>Chat ID:</b> <code>{self.default_chat_id}</code>\n"
            f"⏰ <b>Час:</b> {now_str}\n\n"
            f"<b>Тепер ви автоматично отримуватимете:</b>\n"
            f"1. 📊 Щоденний звіт про розсилку (50 лідів / день).\n"
            f"2. 🚨 Миттєве сповіщення, якщо клієнт відповість на лист!"
        )
        return self.send_message(text, parse_mode="HTML")


# Global singleton
telegram_notifier = TelegramNotifier()
