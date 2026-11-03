"""Send report by authenticated SMTP only when configured."""
import os
from pathlib import Path
from email.message import EmailMessage
import smtplib

def send(path: str):
    required=['SMTP_HOST','SMTP_PORT','SMTP_USERNAME','SMTP_PASSWORD','EMAIL_TO','EMAIL_FROM']
    missing=[k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError('Missing email environment variables: '+', '.join(missing))
    p=Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    msg=EmailMessage()
    msg['Subject']='Fantasy kicker analysis — '+p.stem.replace('_',' ')
    msg['From']=os.environ['EMAIL_FROM']
    msg['To']=os.environ['EMAIL_TO']
    msg.set_content('This week’s full 32-team kicker report is attached as HTML. The rankings include offensive and opponent field-goal opportunity, recency, and your McPherson comparison.')
    msg.add_attachment(p.read_bytes(),maintype='text',subtype='html',filename=p.name)
    with smtplib.SMTP(os.environ['SMTP_HOST'],int(os.environ['SMTP_PORT']),timeout=30) as smtp:
        smtp.starttls()
        smtp.login(os.environ['SMTP_USERNAME'],os.environ['SMTP_PASSWORD'])
        smtp.send_message(msg)
    print('Email accepted by configured SMTP server.')

if __name__=='__main__':
    from sys import argv
    if len(argv)!=2:
        raise SystemExit('usage: python -m kicker_tracker.emailer report/latest.html')
    send(argv[1])
