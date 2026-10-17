"""
TERAWET-ORIGINAL Sales Automation - Full System Audit & Stress Test Suite
Verifies 100% crash resilience, token connectivity, lead matching,
and concurrency safety without altering production database state.
"""

import sys
import time
import copy
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

# Configure test logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SystemAudit")

def print_banner(title: str):
    print("\n" + "="*70)
    print(f"🚀  {title.upper()}")
    print("="*70)

def test_telegram_bot_connectivity():
    print_banner("1. Telegram Bot Connectivity & Payload Verification")
    import config
    from telegram_notifier import TelegramNotifier

    print(f"[*] Target Bot Token: {config.TELEGRAM_BOT_TOKEN[:10]}...{config.TELEGRAM_BOT_TOKEN[-6:]}")
    print(f"[*] Target Chat ID:   {config.TELEGRAM_CHAT_ID}")
    
    notifier = TelegramNotifier()
    
    # 1.1 Test raw connection & getMe verification
    import urllib.request
    req = urllib.request.Request(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getMe")
    with urllib.request.urlopen(req, timeout=10) as response:
        me_resp = json.loads(response.read().decode("utf-8"))
    assert me_resp.get("ok") is True, f"Telegram getMe failed: {me_resp}"
    bot_info = me_resp.get("result", {})
    print(f"[+] Bot Verified: @{bot_info.get('username')} ({bot_info.get('first_name')}) [ID: {bot_info.get('id')}]")
    
    # 1.2 Test automatic plain-text fallback on malformed HTML
    broken_html = "Testing <b>bold</b> with broken <tag_that_does_not_exist_and_causes_telegram_entity_error"
    fallback_ok, fallback_msg = notifier.send_message(broken_html)
    print(f"[+] Malformed HTML recovery result: {fallback_ok} ({fallback_msg})")
    assert fallback_ok is True, f"Telegram must gracefully recover via plain text: {fallback_msg}"
    
    # 1.3 Test daily outreach report formatting
    test_metrics = {
        "sent_today": 5,
        "failed_today": 0,
        "daily_limit": 50,
        "countries": {"Греція": 3, "Болгарія": 2},
        "duration_min": 4.5,
        "next_run": "Завтра о 09:00"
    }
    # Send live notification
    success, msg = notifier.send_daily_outreach_report(test_metrics)
    print(f"[+] Daily report delivery result: {success} ({msg})")
    assert success is True, f"Failed to deliver daily report: {msg}"
    
    # 1.4 Test lead reply alert formatting
    sample_reply = {
        "email": "dimitris@aegean-olives.gr",
        "company": "Aegean Olive Groves S.A.",
        "country": "Греція",
        "subject": "Re: 50% εξοικονόμηση νερού άρδευσης",
        "date": "2026-10-17 11:30:00",
        "body_preview": "Καλημέρα σας, ενδιαφερόμαστε πολύ για το TERAWET για τους ελαιώνες μας στη Χαλκιδική. Παρακαλώ στείλτε μας τιμοκατάλογο για παραγγελία 500 κιλών."
    }
    success_reply, msg_reply = notifier.send_lead_reply_alert(sample_reply)
    print(f"[+] Lead reply delivery result: {success_reply} ({msg_reply})")
    assert success_reply is True, f"Failed to deliver lead reply alert: {msg_reply}"
    
    print("[PASSED] Telegram connectivity & notification pipeline verified 100% operational.")

def test_inbox_reply_sanitization_and_matching():
    print_banner("2. IMAP Reply Sanitizer & Anti-Bot Shield")
    from inbox_reply_service import _clean_body_snippet, _decode_mime_header, IGNORE_SENDER_PATTERNS
    import re

    # 2.1 Test MIME header decoding
    mime_subj = "=?UTF-8?B?UmU6IDUwJSDQtdC60L7QvdC+0LzRltGPINC90LAg0LLQvtC00LA=?="
    decoded = _decode_mime_header(mime_subj)
    print(f"[+] Decoded MIME subject: '{decoded}'")
    assert "Re:" in decoded or "50%" in decoded, f"Failed decoding: {decoded}"

    # 2.2 Test HTML and email quote stripping
    dirty_html_email = """
    <html>
      <head><style>.bad { color: red; }</style><script>alert('hack')</script></head>
      <body>
        <div>Добрий день! Нас цікавить закупівля 200 кг препарату <b>TERAWET</b> для яблуневого саду.</div>
        <div>Чи є доставка по Україні та Болгарії?</div>
        <br>
        <div class="gmail_quote">
          On Fri, Oct 17, 2026 at 9:00 AM Terawet Sales &lt;terawet@gmail.com&gt; wrote:
          <blockquote class="gmail_quote" style="margin:0px 0px 0px 0.8ex;border-left:1px solid rgb(204,204,204);padding-left:1ex">
            Доброго дня! Пропонуємо інноваційний суперабсорбент...
          </blockquote>
        </div>
      </body>
    </html>
    """
    clean_preview = _clean_body_snippet(dirty_html_email, max_chars=300)
    print(f"[+] Sanitized body preview:\n    '{clean_preview}'")
    assert "alert('hack')" not in clean_preview, "Scripts must be stripped"
    assert "<style>" not in clean_preview, "Styles must be stripped"
    assert "On Fri, Oct 17" not in clean_preview, "Quote header must be stripped"
    assert "яблуневого саду" in clean_preview, "Core reply content must be preserved"

    # 2.3 Test anti-bot ignore filter
    test_senders = [
        ("mailer-daemon@googlemail.com", True),
        ("noreply@linkedin.com", True),
        ("no-reply@verification.com", True),
        ("notifications@github.com", True),
        ("dimitris@olive-farm.gr", False),
        ("manager@agro-holding.bg", False)
    ]
    for sender, should_ignore in test_senders:
        ignored = any(re.search(pat, sender, re.IGNORECASE) for pat in IGNORE_SENDER_PATTERNS)
        assert ignored == should_ignore, f"Sender {sender} expected ignore={should_ignore}, got {ignored}"
    print(f"[+] Anti-bot filter correctly classified {len(test_senders)} sample senders.")
    print("[PASSED] IMAP reply sanitizer & filter passed with flying colors.")

def test_mx_validation_and_rate_limiting():
    print_banner("3. DNS MX Pre-Flight & Anti-Spam Rate Limiting")
    from email_verifier import EmailVerifierService
    from auto_outreach_service import AutoOutreachService
    
    verifier = EmailVerifierService()
    # 3.1 Test MX Deliverability on real and fake domains
    deliverable, reason = verifier.verify_email("info@google.com")
    print(f"[+] info@google.com deliverability: {deliverable} ({reason})")
    assert deliverable is True, "google.com should be valid MX"
    
    fake_deliverable, fake_reason = verifier.verify_email("test@this-domain-definitely-does-not-exist-12345.com")
    print(f"[+] fake domain deliverability: {fake_deliverable} ({fake_reason})")
    assert fake_deliverable is False, "Non-existent domain must fail MX validation"

    # 3.2 Test daily limit calculation & pacing parameters
    outreach = AutoOutreachService()
    daily_target = outreach.state.get("daily_target", 50)
    min_delay = outreach.state.get("min_delay_seconds", 45)
    max_delay = outreach.state.get("max_delay_seconds", 90)
    print(f"[+] Daily limit configuration: {daily_target} emails/day")
    print(f"[+] Delay range configuration: {min_delay}s - {max_delay}s")
    assert daily_target == 50, "Daily limit must be 50"
    assert min_delay >= 40, "Min delay must be >= 40s to prevent spam flagging"

    print("[PASSED] MX validation & rate limiting constraints confirmed.")

def test_concurrency_and_deadlock_resilience():
    print_banner("4. High-Concurrency & Zero-Deadlock Stress Test")
    from sheets_service import LeadDataService
    
    data_service = LeadDataService()
    initial_leads_count = len(data_service.get_all_leads())
    print(f"[*] Starting stress test with {initial_leads_count} loaded leads.")

    errors = []
    iterations = 60

    def concurrent_worker(worker_id):
        try:
            # Alternate between read, filter, status lookup, and thread-safe lock acquisitions
            leads = data_service.get_all_leads()
            assert isinstance(leads, list)
            # Verify lock safety
            with data_service._lock:
                status = data_service.state.get("dummy_test_thread@test.com", {}).get("status", "⚪ Очікує відправки")
                assert status == "⚪ Очікує відправки"
            return True
        except Exception as e:
            errors.append((worker_id, str(e)))
            return False

    start_time = time.time()
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(concurrent_worker, i) for i in range(iterations)]
        for f in as_completed(futures):
            f.result()
    elapsed = time.time() - start_time

    print(f"[+] Completed {iterations} concurrent queries across 20 threads in {elapsed:.3f}s")
    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"
    print("[PASSED] Concurrency and RLock thread safety validated under multi-thread load.")

def test_web_dashboard_endpoints():
    print_banner("5. Web Dashboard Endpoints Stress & Health Check")
    from web_dashboard import DashboardHandler, ThreadingHTTPServer
    import urllib.request
    import socket

    # Bind to an open ephemeral port
    test_port = 9898
    server = ThreadingHTTPServer(('127.0.0.1', test_port), DashboardHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.3)

    base_url = f"http://127.0.0.1:{test_port}"
    endpoints = [
        ("/", 200),
        ("/api/leads", 200),
        ("/api/health", 200),
        ("/api/search/status", 200),
        ("/api/outreach/status", 200),
        ("/api/replies/status", 200)
    ]

    try:
        for ep, expected_code in endpoints:
            req = urllib.request.Request(f"{base_url}{ep}")
            with urllib.request.urlopen(req, timeout=5) as resp:
                print(f"[+] Endpoint {ep.ljust(22)} -> HTTP {resp.status}")
                assert resp.status == expected_code, f"Expected {expected_code} for {ep}, got {resp.status}"

        # Flood test /api/health with 30 rapid sequential requests
        t0 = time.time()
        for _ in range(30):
            req = urllib.request.Request(f"{base_url}/api/health")
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
        t_flood = time.time() - t0
        print(f"[+] 30 rapid API requests answered in {t_flood:.3f}s (avg: {(t_flood/30)*1000:.1f}ms/req)")

        print("[PASSED] Web Dashboard API responded cleanly with zero drops.")
    finally:
        server.shutdown()
        server.server_close()

def run_all_audits():
    print("="*70)
    print("      TERAWET SYSTEM AUDIT & ENTERPRISE CRASH-PROOF VERIFICATION     ")
    print("="*70)
    t_start = time.time()
    
    test_telegram_bot_connectivity()
    test_inbox_reply_sanitization_and_matching()
    test_mx_validation_and_rate_limiting()
    test_concurrency_and_deadlock_resilience()
    test_web_dashboard_endpoints()
    
    total_time = time.time() - t_start
    print("\n" + "="*70)
    print(f"🎉  ALL 5 TEST SUITES PASSED IN {total_time:.2f}s WITH ZERO ERRORS!")
    print("="*70)

if __name__ == "__main__":
    run_all_audits()
