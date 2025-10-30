import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import json
from jinja2 import Template
from dotenv import load_dotenv
import os
from apscheduler.schedulers.background import BackgroundScheduler
import time

# Load environment variables
load_dotenv()

# Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_NAME = os.getenv("SENDER_NAME")
COMPANY_NAME = os.getenv("COMPANY_NAME")
PRODUCT_NAME = os.getenv("PRODUCT_NAME")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# File paths
CONTACTS_FILE = "contacts.json"
TRACKING_FILE = "email_tracking.json"
TEMPLATE_FILE = "email_template.html"

# Reminder configuration
DEFAULT_REMINDER_INTERVAL_MINUTES = 1  # Default reminder interval in minutes
MAX_REMINDERS = 3  # Maximum number of reminders per contact


def load_json(filename):
    """Load JSON file"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_json(filename, data):
    """Save data to JSON file"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_email_template():
    """Load HTML email template"""
    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        return f.read()


def send_email(contact):
    """Send email to a single contact"""
    try:
        # Load template
        template_content = load_email_template()
        template = Template(template_content)
        
        # Generate tracking links
        interested_link = f"{BASE_URL}/interested/{contact['id']}"
        not_interested_link = f"{BASE_URL}/not-interested/{contact['id']}"
        
        # Render template with contact data
        html_content = template.render(
            contact_name=contact['name'],
            contact_email=contact['email'],
            contact_company=contact.get('company', 'your organization'),
            company_name=COMPANY_NAME,
            product_name=PRODUCT_NAME,
            sender_name=SENDER_NAME,
            interested_link=interested_link,
            not_interested_link=not_interested_link
        )
        
        # Create email message
        message = MIMEMultipart('alternative')
        message['Subject'] = f"Let's Schedule a Demo - {COMPANY_NAME}"
        message['From'] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
        message['To'] = contact['email']
        
        # Attach HTML content
        html_part = MIMEText(html_content, 'html')
        message.attach(html_part)
        
        # Connect to SMTP server and send email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)
        
        # Track email sent
        tracking = load_json(TRACKING_FILE)
        tracking.append({
            "contact_id": contact['id'],
            "contact_name": contact['name'],
            "contact_email": contact['email'],
            "action": "email_sent",
            "timestamp": datetime.now().isoformat()
        })
        save_json(TRACKING_FILE, tracking)
        
        print(f"✅ Email sent successfully to {contact['name']} ({contact['email']})")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send email to {contact['name']}: {str(e)}")
        return False


def send_reminder_email(contact_id, reminder_interval_minutes=None):
    """Send reminder email to a specific contact"""
    if reminder_interval_minutes is None:
        reminder_interval_minutes = DEFAULT_REMINDER_INTERVAL_MINUTES

    contacts = load_json(CONTACTS_FILE)
    contact = next((c for c in contacts if c['id'] == contact_id), None)

    if not contact or contact.get('status') != 'pending':
        print(f"⚠️ Contact {contact_id} not found or not pending")
        return

    # Check if we've already sent max reminders
    reminder_count = contact.get('reminder_count', 0)
    if reminder_count >= MAX_REMINDERS:
        # Auto-mark as not_interested after max reminders
        contact['status'] = 'not_interested'
        contact['updated_at'] = datetime.now().isoformat()
        save_json(CONTACTS_FILE, contacts)
        print(f"🚫 Max reminders ({MAX_REMINDERS}) reached for {contact['name']} - Marked as not_interested")
        return

    # Send reminder email
    try:
        # Load template
        template_content = load_email_template()
        template = Template(template_content)

        # Generate tracking links
        interested_link = f"{BASE_URL}/interested/{contact['id']}"
        not_interested_link = f"{BASE_URL}/not-interested/{contact['id']}"

        # Render template with contact data (add reminder note)
        html_content = template.render(
            contact_name=contact['name'],
            contact_email=contact['email'],
            contact_company=contact.get('company', 'your organization'),
            company_name=COMPANY_NAME,
            product_name=PRODUCT_NAME,
            sender_name=SENDER_NAME,
            interested_link=interested_link,
            not_interested_link=not_interested_link,
            is_reminder=True,
            reminder_number=reminder_count + 1
        )

        # Create email message
        message = MIMEMultipart('alternative')
        message['Subject'] = f"🔔 Reminder: Let's Schedule a Demo - {COMPANY_NAME}"
        message['From'] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
        message['To'] = contact['email']

        # Attach HTML content
        html_part = MIMEText(html_content, 'html')
        message.attach(html_part)

        # Connect to SMTP server and send email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)

        # Update reminder count and timestamp
        new_reminder_count = reminder_count + 1
        current_time = datetime.now()
        contact['reminder_count'] = new_reminder_count
        contact['last_reminder_sent'] = current_time.isoformat()
        contact['updated_at'] = current_time.isoformat()

        # Track reminder sent
        tracking = load_json(TRACKING_FILE)
        tracking.append({
            "contact_id": contact['id'],
            "contact_name": contact['name'],
            "contact_email": contact['email'],
            "action": f"reminder_{new_reminder_count}_sent",
            "timestamp": current_time.isoformat()
        })
        save_json(TRACKING_FILE, tracking)
        save_json(CONTACTS_FILE, contacts)

        print(f"🔔 Reminder {new_reminder_count} sent to {contact['name']} ({contact['email']})")

        # Schedule next reminder if under limit
        if new_reminder_count < MAX_REMINDERS:
            # Get scheduler from global scope (will be set when scheduler starts)
            global reminder_scheduler
            if 'reminder_scheduler' in globals() and reminder_scheduler:
                next_reminder_time = current_time + timedelta(minutes=reminder_interval_minutes)
                job_id = f"reminder_{contact['id']}_{new_reminder_count + 1}"

                reminder_scheduler.add_job(
                    send_reminder_email,
                    'date',
                    run_date=next_reminder_time,
                    args=[contact['id'], reminder_interval_minutes],
                    id=job_id
                )
                print(f"⏰ Next reminder for {contact['name']} scheduled at {next_reminder_time.strftime('%H:%M:%S')} (in {reminder_interval_minutes} min)")

    except Exception as e:
        print(f"❌ Failed to send reminder to {contact['name']}: {str(e)}")


def send_emails_to_all(reminder_interval_minutes=None):
    """Send emails to all pending contacts"""
    if reminder_interval_minutes is None:
        reminder_interval_minutes = DEFAULT_REMINDER_INTERVAL_MINUTES

    contacts = load_json(CONTACTS_FILE)
    pending_contacts = [c for c in contacts if c.get('status') == 'pending']

    if not pending_contacts:
        print("No pending contacts to send emails to.")
        return

    print(f"\n📧 Starting email campaign to {len(pending_contacts)} contacts...")
    print(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔔 Reminder interval: {reminder_interval_minutes} minutes\n")

    success_count = 0
    failed_count = 0

    for contact in pending_contacts:
        if send_email(contact):
            success_count += 1
            current_time = datetime.now()
            # Update contact with initial email info
            contact['sent_at'] = current_time.isoformat()
            contact['updated_at'] = current_time.isoformat()
            # Initialize reminder fields if not present
            if 'reminder_count' not in contact:
                contact['reminder_count'] = 0
            if 'last_reminder_sent' not in contact:
                contact['last_reminder_sent'] = None

            # Schedule first reminder exactly N minutes from now
            global reminder_scheduler
            if 'reminder_scheduler' in globals() and reminder_scheduler:
                first_reminder_time = current_time + timedelta(minutes=reminder_interval_minutes)
                job_id = f"reminder_{contact['id']}_1"

                reminder_scheduler.add_job(
                    send_reminder_email,
                    'date',
                    run_date=first_reminder_time,
                    args=[contact['id'], reminder_interval_minutes],
                    id=job_id
                )
                print(f"⏰ First reminder for {contact['name']} scheduled at {first_reminder_time.strftime('%H:%M:%S')} (in {reminder_interval_minutes} min)")

        else:
            failed_count += 1

        # Small delay to avoid rate limiting
        time.sleep(1)

    # Save updated contacts
    save_json(CONTACTS_FILE, contacts)

    print(f"\n📊 Campaign Summary:")
    print(f"   ✅ Successfully sent: {success_count}")
    print(f"   ❌ Failed: {failed_count}")
    print(f"   📈 Total: {len(pending_contacts)}\n")

    return pending_contacts  # Return for reminder scheduling


# Note: check_and_send_reminders function removed - now using individual precise timers


def schedule_emails(day_of_week='thu', hour=9, minute=0, reminder_interval_minutes=None):
    """
    Schedule emails to be sent at specific time with precise reminder timing

    Args:
        day_of_week: 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'
        hour: Hour in 24-hour format (0-23)
        minute: Minute (0-59)
        reminder_interval_minutes: Minutes between reminders (default: 5)
    """
    if reminder_interval_minutes is None:
        reminder_interval_minutes = DEFAULT_REMINDER_INTERVAL_MINUTES

    global reminder_scheduler
    reminder_scheduler = BackgroundScheduler()

    # Schedule the main email campaign
    reminder_scheduler.add_job(
        send_emails_to_all,
        'cron',
        day_of_week=day_of_week,
        hour=hour,
        minute=minute,
        args=[reminder_interval_minutes],
        id='email_campaign'
    )

    reminder_scheduler.start()

    print(f"📅 Email scheduler started!")
    print(f"   📧 Main Campaign: Every {day_of_week.upper()} at {hour:02d}:{minute:02d}")
    print(f"   🔔 Reminders: Every {reminder_interval_minutes} minutes (individual timers)")
    print(f"   ⚡ Max Reminders: {MAX_REMINDERS} per contact")
    print(f"   🚫 Auto-mark as 'not_interested' after {MAX_REMINDERS} reminders")
    print(f"   Press Ctrl+C to stop\n")

    try:
        # Keep the script running
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        reminder_scheduler.shutdown()
        print("\n👋 Scheduler stopped.")


def send_now(reminder_interval_minutes=None):
    """Send emails immediately to all pending contacts"""
    if reminder_interval_minutes is None:
        reminder_interval_minutes = DEFAULT_REMINDER_INTERVAL_MINUTES
    print("🚀 Sending emails immediately...\n")

    # Set up a temporary scheduler for reminders
    global reminder_scheduler
    reminder_scheduler = BackgroundScheduler()
    reminder_scheduler.start()

    send_emails_to_all(reminder_interval_minutes)


if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("📧 EMAIL SCHEDULER BOT - MindLinks Inc")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "now":
            # Send immediately
            send_now()
        elif sys.argv[1] == "schedule":
            # Schedule emails
            if len(sys.argv) >= 4:
                day = sys.argv[2]  # e.g., 'mon', 'tue'
                hour = int(sys.argv[3])  # e.g., 9 for 9 AM
                minute = int(sys.argv[4]) if len(sys.argv) > 4 else 0
                reminder_interval = int(sys.argv[5]) if len(sys.argv) > 5 else DEFAULT_REMINDER_INTERVAL_MINUTES
                schedule_emails(day_of_week=day, hour=hour, minute=minute, reminder_interval_minutes=reminder_interval)
            else:
                print("Usage: python scheduler.py schedule <day> <hour> [minute] [reminder_interval]")
                print("Example: python scheduler.py schedule mon 9 0 5    # 5-minute reminders")
                print("Example: python scheduler.py schedule wed 14 30 2  # 2-minute reminders")
        else:
            print("Unknown command. Use 'now' or 'schedule'")
    else:
        print("\nUsage:")
        print("  python scheduler.py now                              # Send emails immediately")
        print("  python scheduler.py schedule mon 9 0                 # Schedule for Monday 9:00 AM (5-min reminders)")
        print("  python scheduler.py schedule wed 14 30 2             # Schedule for Wednesday 2:30 PM (2-min reminders)")
        print("  python scheduler.py schedule fri 10 0 1              # Schedule for Friday 10:00 AM (1-min reminders)")
        print("\nParameters:")
        print("  <day>              : mon, tue, wed, thu, fri, sat, sun")
        print("  <hour>             : 0-23 (24-hour format)")
        print("  [minute]           : 0-59 (optional, default: 0)")
        print("  [reminder_interval]: Minutes between reminders (optional, default: 5)")