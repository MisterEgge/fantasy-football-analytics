"""Conservative walk-forward model calibration from past Tuesday reviews.

Never use the target week's actual outcomes to tune a pregame prediction.
"""
import json
from pathlib import Path

import numpy as np


def load_reviews(history_dir, season, before_week):
    root = Path(history_dir) / "reviews" / str(season)
    if not root.exists():
        return []
    result = []
    for file in sorted(root.glob("week_*.json")):
        payload = json.loads(file.read_text(encoding="utf-8"))
        metadata = payload.get("metadata", {})
        if int(metadata.get("season", -1)) == season and int(metadata.get("week", 999)) < before_week:
            result.append(payload)
    return sorted(result, key=lambda item: int(item["metadata"]["week"]))


def _rows(review):
    return [
        r for r in review.get("teams", [])
        if r.get("raw_projected_fg_attempts") is not None
        and r.get("actual_fg_attempts") is not None
    ]


def _fit_factor(reviews):
    entries = [r for rev in reviews for r in _rows(rev)]
    if not entries:
        return 1.0
    pred = np.asarray([float(r["raw_projected_fg_attempts"]) for r in entries])
    actual = np.asarray([float(r["actual_fg_attempts"]) for r in entries])
    denominator = float(np.dot(pred, pred))
    if denominator < 1e-6:
        return 1.0
    # No noisy or exaggerated automated corrections.
    return float(np.clip(float(np.dot(pred, actual)) / denominator, 0.9, 1.1))


def choose_calibration(history_dir, season, target_week):
    reviews = load_reviews(history_dir, season, target_week)
    base = {
        "volume_factor": 1.0,
        "method": "uncalibrated_baseline",
        "review_weeks": len(reviews),
        "graded_team_games": sum(len(_rows(r)) for r in reviews),
        "reason": "Insufficient historical evidence",
    }
    # Minimum three FULLY independent reviews and 60 observations.
    if len(reviews) < 3 or base["graded_team_games"] < 60:
        return base
    training, validation = reviews[:-1], reviews[-1]
    train_rows = [r for v in training for r in _rows(v)]
    if len(training) < 2 or len(train_rows) < 40 or len(_rows(validation)) < 16:
        return base
    candidate = _fit_factor(training)
    test = _rows(validation)
    pred = np.asarray([float(r["raw_projected_fg_attempts"]) for r in test])
    actual = np.asarray([float(r["actual_fg_attempts"]) for r in test])
    baseline_mae = float(np.mean(np.abs(pred - actual)))
    candidate_mae = float(np.mean(np.abs(pred * candidate - actual)))
    base.update({
        "candidate_factor": round(candidate, 4),
        "validation_week": validation["metadata"]["week"],
        "baseline_validation_mae": round(baseline_mae, 4),
        "adjusted_validation_mae": round(candidate_mae, 4),
    })
    # Only accept correction with meaningful out-of-sample improvement.
    if candidate_mae + 0.03 >= baseline_mae:
        base["reason"] = "Held-out week showed insufficient improvement"
        return base
    base["volume_factor"] = round(candidate, 4)
    base["method"] = "bounded_walk_forward_volume_calibration"
    base["reason"] = "Validated on a later week not included in factor fitting"
    return base


def apply_calibration(row, calibration):
    """Scale FG attempts and the FG-derived portion of forecast points only."""
    if row.get("projected_points") is None:
        return
    factor = float(calibration["volume_factor"])
    row["raw_projected_fg_attempts"] = row["projected_fg_attempts"]
    row["raw_projected_points"] = row["projected_points"]
    fg_component = float(row["projected_points"]) - float(row["projected_xp"])
    row["projected_fg_attempts"] = round(float(row["projected_fg_attempts"]) * factor, 2)
    row["projected_points"] = round(fg_component * factor + float(row["projected_xp"]), 2)
    row["source"] = (
        "transparent heuristic + walk-forward FG-volume adjustment"
        if factor != 1.0 else "transparent heuristic (not yet calibrated)"
    )
