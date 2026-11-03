"""Regression coverage for date filtering in report generation."""
import pandas as pd
from kicker_tracker import cli
from kicker_tracker.config import TEAMS


def test_run_uses_compatible_schedule_datetime(monkeypatch, tmp_path):
    """A datetime64[ns] schedule must be comparable to --as-of's date."""
    pbp = pd.DataFrame({
        "game_date": pd.to_datetime(["2026-11-01"]),
        "game_id": ["2026_08_TEST"],
    })
    schedule = pd.DataFrame({
        "season": [2026],
        "game_type": ["REG"],
        "gameday": pd.to_datetime(["2026-11-05"]),
        "week": [9],
        "home_team": ["CIN"],
        "away_team": ["BAL"],
    })
    monkeypatch.setattr(cli, "load_pbp", lambda *_args: pbp)
    monkeypatch.setattr(cli, "load_schedule", lambda *_args: schedule)
    monkeypatch.setattr(
        cli,
        "build_team_rows",
        lambda *_args: [
            {
                "team": team,
                "fg_allowed_pg": 2.0,
                "rz_td_allowed_pct": 0.5,
            }
            for team in TEAMS
        ],
    )
    monkeypatch.setattr(
        cli, "project",
        lambda *_args: {
            "projected_fg_attempts": 2.0,
            "projected_xp": 1.5,
            "projected_points": 8.5,
        },
    )
    written = {}

    def fake_save(rows, metadata, folder):
        written["rows"] = rows
        written["metadata"] = metadata
        return tmp_path / "report.html"

    monkeypatch.setattr(cli, "save_report", fake_save)
    result = cli.run(2026, "2026-11-04", output=str(tmp_path))
    assert result.name == "report.html"
    assert written["metadata"]["target_week"] == 9
    assert len(written["rows"]) == 32
    assert next(row for row in written["rows"] if row["team"] == "CIN")["opponent"] == "BAL"
