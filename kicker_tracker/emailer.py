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
    msg["Subject"] = "Fantasy Kicker Tracker — " + report.stem.replace("_", " ")
    msg["From"] = address
    msg["To"] = recipient
    msg.set_content(
        "Your weekly 32-team fantasy kicker report is attached. "
        "It compares kicker opportunities and projections against Evan McPherson."
    )
    msg.add_attachment(
        report.read_bytes(),
        maintype="text",
        subtype="html",
        filename=report.name,
    )

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(address, app_password)
        smtp.send_message(msg)
    print("Weekly report accepted by Gmail for delivery.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m kicker_tracker.emailer report/latest.html")
    send(sys.argv[1])
