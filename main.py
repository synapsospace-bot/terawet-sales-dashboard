import sys
import argparse
import logging
from pathlib import Path
import config
from agent_brain import TerawetAgentBrain
from gmail_service import GmailDraftService
from sheets_service import LeadDataService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("TerawetPipeline")

def reset_leads():
    """Resets local sample leads back to NEW."""
    csv_path = Path(config.CSV_FILE_PATH)
    if not csv_path.exists():
        print(f"Error: {csv_path} not found.")
        return

    import csv
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    for r in rows:
        r["status"] = "NEW"
        r["draft_id"] = ""
        r["generated_subject"] = ""

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"🔄 All {len(rows)} local leads have been reset to 'NEW'.")

def run_pipeline(limit: int = 0):
    print("=" * 65)
    print("  🌱 TERAWET® Automated Outreach & Sales Agent")
    print("  Website: https://tera-wet.com | Phone: +359 888 516501")
    print("=" * 65)

    data_service = LeadDataService()
    agent_brain = TerawetAgentBrain()
    draft_service = GmailDraftService()

    # Automatically sync any emails sent from Gmail
    try:
        synced_sent = data_service.sync_sent_emails(draft_service)
        if synced_sent > 0:
            print(f"📥 Detected {synced_sent} sent emails in Gmail! Updated status -> '✅ Лист відправлено'")
    except Exception as e:
        logger.debug(f"Sync sent error: {e}")

    new_leads = data_service.get_new_leads()

    if not new_leads:
        print("\n✨ No unprocessed leads found (all leads have drafts or were sent).")
        return

    total_leads = len(new_leads)
    if limit > 0:
        new_leads = new_leads[:limit]
        print(f"\nFound {total_leads} unprocessed leads. Processing first {limit} (limit applied)...")
    else:
        print(f"\nFound {total_leads} unprocessed leads in Google Sheet to process...")

    mode_labels = {
        "imap": f"Gmail Direct Drafts (synapso.space@gmail.com)",
        "oauth": "Gmail Direct Drafts (Google Cloud OAuth2)",
        "local": "Local HTML Preview Directory"
    }

    print(f"Data Source: Live Google Sheet (91 rows, {total_leads} pending)")
    print(f"Draft Mode:  {mode_labels.get(draft_service.mode, 'Local Preview')}")
    print("-" * 65)

    processed_count = 0

    for i, lead in enumerate(new_leads, 1):
        company = lead.get("company_name", "Unknown")
        country = lead.get("country", "")
        lang = lead.get("language", "en").upper()
        crops = lead.get("crops", "")
        email = lead.get("email", "")
        row_num = lead.get("_row_number", "")

        print(f"\n[{i}/{len(new_leads)}] 🏢 {company} (Row {row_num} | {country} | {lang})")
        print(f"    🌱 Niche/City: {crops}")
        print(f"    ✉️  Email: {email}")

        try:
            # 1. Generate Pitch
            print("    ⚙️  Generating personalized offer with AI Agent Brain...")
            subject, body_html, body_plain = agent_brain.generate_pitch(lead)
            print(f"    📌 Subject: {subject}")

            # 2. Create Draft in Gmail
            print("    📝 Creating draft in Gmail for review...")
            draft_id = draft_service.create_draft(
                to_email=email,
                subject=subject,
                body_html=body_html,
                body_plain=body_plain,
                company_name=company
            )

            # 3. Update Status in Sheet
            data_service.mark_draft_created(lead, draft_id, subject, body_plain)
            print(f"    ✅ Success! Status -> '🟡 Чернетка на перевірці' (ID: {draft_id})")
            processed_count += 1

        except Exception as e:
            logger.error(f"Failed to process lead {company}: {e}", exc_info=True)

    print("\n" + "=" * 65)
    print(f"🎉 Completed! Processed {processed_count}/{len(new_leads)} leads from Google Sheet.")
    if draft_service.mode == "local":
        print(f"📂 HTML draft previews saved in: {config.LOCAL_DRAFTS_DIR}/")
    else:
        print(f"📬 Drafts are sitting in your Gmail 'Drafts' folder (synapso.space@gmail.com) ready to review & send!")
    print("=" * 65)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TeraWet Lead & Sales Outreach Agent")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of leads to process")
    parser.add_argument("--reset", action="store_true", help="Reset all leads back to status 'NEW'")
    args = parser.parse_args()

    if args.reset:
        reset_leads()
    else:
        run_pipeline(limit=args.limit)
