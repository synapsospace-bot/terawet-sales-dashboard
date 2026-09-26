import sys
import logging
from pathlib import Path
import config
from gmail_service import GmailDraftService

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def test_connection():
    print("=" * 65)
    print("  📬 Тестування підключення пошти для створення чернеток Gmail")
    print("=" * 65)

    if not config.EMAIL_USER or not config.EMAIL_APP_PASSWORD:
        if not config.GMAIL_ENABLED or not Path(config.GMAIL_CREDENTIALS_FILE).exists():
            print("\n⚠️  Поштові реквізити ще не налаштовані у файлі .env")
            print("-" * 65)
            print("💡 Як підключити Gmail за 30 секунд (Найпростіший спосіб):")
            print("1. Відкрийте сторінку паролів додатків Google:")
            print("   👉 https://myaccount.google.com/apppasswords")
            print("2. Введіть назву додатку: 'TeraWet'")
            print("3. Google згенерує 16-значний пароль (наприклад: abcd efgh ijkl mnop)")
            print("4. Відкрийте файл .env і додайте рядки:")
            print("   EMAIL_USER=vash_email@gmail.com")
            print("   EMAIL_APP_PASSWORD=abcd efgh ijkl mnop")
            print("5. Запустіть цей тест знову: python3 test_email_connection.py")
            print("-" * 65)
            print("📁 Поки що система працює в режимі збереження чернеток у HTML-папку:")
            print(f"   {config.LOCAL_DRAFTS_DIR}/")
            print("=" * 65)
            return

    service = GmailDraftService()
    print(f"\nАктивний режим: {service.mode.upper()}")

    test_to = config.EMAIL_USER if config.EMAIL_USER else "client@example.com"
    subject = "🌱 [Тест TeraWet] Перевірка підключення чернеток Gmail"
    body_html = "<p>Це тестова чернетка від <strong>TeraWet Sales Agent</strong>.</p><p>Якщо ви бачите цей лист у папці <strong>'Чернетки' (Drafts)</strong> свого Gmail — інтеграція працює на 100%!</p>"
    body_plain = "Це тестова чернетка від TeraWet Sales Agent. Інтеграція працює успішно!"

    print(f"Спроба створення тестової чернетки для: {test_to}...")
    try:
        draft_id = service.create_draft(test_to, subject, body_html, body_plain, "TestCompany")
        print(f"\n✅ Успішно створено чернетку!")
        print(f"   Ідентифікатор: {draft_id}")
        if service.mode == "imap":
            print(f"   📬 Відкрийте додаток Gmail або пошту в браузері ({config.EMAIL_USER})")
            print("   і загляньте в папку 'Чернетки' (Drafts) — там щойно з'явився цей лист!")
        elif service.mode == "oauth":
            print(f"   📬 Чернетка створена через Google OAuth у вашому Gmail!")
        else:
            print(f"   📂 Чернетка збережена як HTML у {config.LOCAL_DRAFTS_DIR}/")
    except Exception as e:
        print(f"\n❌ Помилка при підключенні: {e}")

    print("=" * 65)

if __name__ == "__main__":
    test_connection()
