"""Regression tests for immutable pregame backtests and guarded learning."""
import json

import pandas as pd
import pytest

from kicker_tracker.calibration import choose_calibration, apply_calibration
from kicker_tracker.review import grade_forecast, build_review_html


def _snapshot():
    return {
        "metadata": {"season": 2026, "target_week": 9, "as_of": "2026-11-04"},
        "teams": [
            {"team": team, "opponent": opponent, "projected_fg_attempts": 2.0,
             "projected_points": 8.0, "projected_xp": 2.0,
             "form": {"kicker": player}}
            for team, opponent, player in [
                ("CIN", "BAL", "E. McPherson"), ("BAL", "CIN", "T. Loop")
            ]
        ],
    }


def _week_game():
    date = pd.Timestamp("2026-11-08")
    return pd.DataFrame([
        # CIN made a 50 yarder and an extra point.
        {"season": 2026, "week": 9, "game_date": date, "game_id": "g9",
         "posteam": "CIN", "defteam": "BAL", "field_goal_attempt": 1,
         "field_goal_result": "made", "kick_distance": 50,
         "extra_point_attempt": 0, "extra_point_result": None,
         "kicker_player_name": "E. McPherson"},
        {"season": 2026, "week": 9, "game_date": date, "game_id": "g9",
         "posteam": "CIN", "defteam": "BAL", "field_goal_attempt": 0,
         "field_goal_result": None, "kick_distance": None,
         "extra_point_attempt": 1, "extra_point_result": "good",
         "kicker_player_name": "E. McPherson"},
        # BAL missed the only field-goal attempt.
        {"season": 2026, "week": 9, "game_date": date, "game_id": "g9",
         "posteam": "BAL", "defteam": "CIN", "field_goal_attempt": 1,
         "field_goal_result": "missed", "kick_distance": 42,
         "extra_point_attempt": 0, "extra_point_result": None,
         "kicker_player_name": "T. Loop"},
    ])


def _schedule():
    return pd.DataFrame([{
        "season": 2026, "week": 9, "game_type": "REG",
        "gameday": pd.Timestamp("2026-11-08"),
        "home_team": "CIN", "away_team": "BAL",
    }])


def test_grade_exact_fantasy_points_and_no_reconstructed_predictions():
    review = grade_forecast(_snapshot(), _week_game(), _schedule(), "2026-11-10")
    by_team = {r["team"]: r for r in review["teams"]}
    assert review["summary"]["graded_teams"] == 2
    assert by_team["CIN"]["predicted_points"] == 8
    assert by_team["CIN"]["actual_points"] == 6  # 50-yard FG + XP
    assert by_team["CIN"]["points_error"] == 2
    assert by_team["CIN"]["actual_fg_attempts"] == 1
    assert by_team["BAL"]["actual_points"] == -1
    assert by_team["BAL"]["points_error"] == 9
    html = build_review_html(review)
    assert "Predicted vs. Actual" in html
    assert "E. McPherson" in html


def test_missing_game_fails_closed():
    with pytest.raises(RuntimeError, match="No play-by-play"):
        grade_forecast(_snapshot(), _week_game().iloc[0:0], _schedule(), "2026-11-10")


def test_early_review_or_postgame_forecast_is_rejected():
    with pytest.raises(ValueError, match="Tuesday"):
        grade_forecast(_snapshot(), _week_game(), _schedule(), "2026-11-09")
    snap = _snapshot()
    snap["metadata"]["as_of"] = "2026-11-10"
    with pytest.raises(ValueError, match="predate"):
        grade_forecast(snap, _week_game(), _schedule(), "2026-11-10")


def _review(week, predicted, actual):
    return {
        "metadata": {"season": 2026, "week": week},
        "teams": [
            {"team": str(i), "raw_projected_fg_attempts": float(predicted),
             "actual_fg_attempts": float(actual)}
            for i in range(32)
        ],
    }


def test_walk_forward_needs_three_reviews(tmp_path):
    root = tmp_path / "reviews" / "2026"
    root.mkdir(parents=True)
    for week in [9, 10]:
        (root / f"week_{week:02}.json").write_text(
            json.dumps(_review(week, 2.0, 2.2)), encoding="utf-8"
        )
    assert choose_calibration(tmp_path, 2026, 11)["volume_factor"] == 1.0


def test_walk_forward_held_out_improvement_enables_bounded_factor(tmp_path):
    root = tmp_path / "reviews" / "2026"
    root.mkdir(parents=True)
    for week in [9, 10, 11]:
        (root / f"week_{week:02}.json").write_text(
            json.dumps(_review(week, 2.0, 2.2)), encoding="utf-8"
        )
    result = choose_calibration(tmp_path, 2026, 12)
    assert result["volume_factor"] == pytest.approx(1.1)
    assert result["method"] == "bounded_walk_forward_volume_calibration"
    row = {"projected_fg_attempts": 2.0, "projected_xp": 2.0, "projected_points": 8.0}
    apply_calibration(row, result)
    assert row["projected_fg_attempts"] == pytest.approx(2.2)
    assert row["projected_points"] == pytest.approx(8.6)
    assert row["raw_projected_points"] == 8.0
