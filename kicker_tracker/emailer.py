"""Email the generated report through Gmail (no external Python package needed)."""
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path


def send(path: str):
    address = os.environ.get("GMAIL_ADDRESS", "").strip()
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
    missing = []
    if not address:
        missing.append("GMAIL_ADDRESS")
    if not app_password:
        missing.append("GMAIL_APP_PASSWORD")
    if missing:
        raise RuntimeError("Missing GitHub Actions secrets: " + ", ".join(missing))

    report = Path(path)
    if not report.is_file():
        raise FileNotFoundError(report)

    # By default, send the report to the same Gmail address that sends it.
    recipient = os.environ.get("EMAIL_TO", "").strip() or address
    msg = EmailMessage()
    report_dir = report.parent.name
    subjects = {
        "review": "Fantasy Football Analytics | Kickers — Tuesday Prediction Review",
        "defense-review": "Fantasy Football Analytics | D/ST — Tuesday Prediction Review",
        "alerts": "Fantasy Football Analytics | Weather & Injury Alert",
        "defense-report": "Fantasy Football Analytics | D/ST — Wednesday 32-Team Rankings",
    }
    msg["Subject"] = subjects.get(
        report_dir, "Fantasy Football Analytics | Kickers — Wednesday 32-Team Rankings"
    )
    msg["From"] = address
    msg["To"] = recipient
    msg.set_content(
        "Your weekly fantasy analysis is included in the HTML version of this email. "
        "Open this email in Gmail to view the report."
    )
    # Render the report directly in Gmail, rather than attaching raw HTML.
    # Gmail can strip embedded CSS, so the report uses inline styles.
    msg.add_alternative(report.read_text(encoding="utf-8"), subtype="html")

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(address, app_password)
        smtp.send_message(msg)
    print("Fantasy Football Analytics report accepted by Gmail for delivery.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m kicker_tracker.emailer report/latest.html")
    send(sys.argv[1])
