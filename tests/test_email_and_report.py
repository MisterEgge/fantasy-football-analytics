"""Email rendering and impartial ranking regression tests."""
from email.message import EmailMessage
from pathlib import Path

from kicker_tracker import emailer
from kicker_tracker.report import build_html


def test_report_ranks_all_teams_without_special_kicker():
    rows = [
        {
            "team": "CIN", "opponent": "BAL", "projected_points": 5.0,
            "fg_attempts_pg": 2.0, "fg_last3_pg": 1.0,
            "opp_fg_allowed_pg": 2.0, "opp_rz_td_allowed_pct": 0.5,
            "form": {"kicker": "Evan McPherson", "median_ppg": 7.0, "last3_ppg": 5.0,
                     "weekly": [{"points": 4}, {"points": 6}]},
        },
        {
            "team": "SEA", "opponent": "ARI", "projected_points": 9.0,
            "fg_attempts_pg": 2.5, "fg_last3_pg": 3.0,
            "opp_fg_allowed_pg": 2.7, "opp_rz_td_allowed_pct": 0.4,
            "form": {"kicker": "Other Kicker", "median_ppg": 8.0, "last3_ppg": 10.0,
                     "weekly": [{"points": 8}, {"points": 11}]},
        },
    ]
    html = build_html(rows, {"season": 2026, "target_week": 9, "as_of": "2026-11-04"})
    assert "All 32 teams" in html
    assert "Evan McPherson" in html  # Listed as an ordinary kicker.
    assert "Other Kicker" in html
    assert "vs CIN" not in html
    assert "Cincinnati baseline" not in html
    assert "vs McPherson" not in html
    assert html.index("Other Kicker") < html.index("Evan McPherson")


def test_gmail_message_has_inline_html_not_attachment(monkeypatch, tmp_path):
    report = tmp_path / "latest.html"
    report.write_text("<html><body><h1>Rankings</h1></body></html>", encoding="utf-8")
    monkeypatch.setenv("GMAIL_ADDRESS", "sender@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "test-password")

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert (host, port) == ("smtp.gmail.com", 587)
            self.sent = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def ehlo(self):
            pass

        def starttls(self, context):
            assert context is not None

        def login(self, username, password):
            assert (username, password) == ("sender@example.com", "test-password")

        def send_message(self, msg):
            self.sent = msg
            captured.append(msg)

    captured = []
    monkeypatch.setattr(emailer.smtplib, "SMTP", FakeSMTP)
    emailer.send(str(report))

    assert len(captured) == 1
    msg = captured[0]
    assert isinstance(msg, EmailMessage)
    assert msg["To"] == "sender@example.com"
    assert not list(msg.iter_attachments())
    assert msg.get_body(preferencelist=("html",)).get_content().find("<h1>Rankings</h1>") >= 0
    assert "McPherson" not in msg.get_body(preferencelist=("plain",)).get_content()
