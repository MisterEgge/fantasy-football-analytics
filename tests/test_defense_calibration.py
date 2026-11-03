"""Model feedback requires sufficient separate weeks and held-out improvement."""
import json
import pytest

from defense_tracker.calibration import choose, adjust


def review(week,predicted,actual):
    return {
        "metadata":{"season":2026,"week":week},
        "teams":[
            {"team":str(i),"predicted_points":predicted,
             "raw_projected_points":predicted,"actual_points":actual}
            for i in range(28)
        ],
    }


def test_defense_bias_correction_requires_history(tmp_path):
    root=tmp_path/"defense-reviews"/"2026"
    root.mkdir(parents=True)
    for w in (9,10):
        (root/f"week_{w:02d}.json").write_text(json.dumps(review(w,7,8)),encoding="utf-8")
    r=choose(tmp_path,2026,11)
    assert r["point_adjustment"]==0


def test_defense_bias_correction_validated_on_holdout(tmp_path):
    root=tmp_path/"defense-reviews"/"2026"
    root.mkdir(parents=True)
    for w in (9,10,11):
        (root/f"week_{w:02d}.json").write_text(json.dumps(review(w,7,8)),encoding="utf-8")
    r=choose(tmp_path,2026,12)
    assert r["method"]=="walk_forward_validated_bias_correction"
    assert r["point_adjustment"]==pytest.approx(1)
    row={"projected_points":6.5}
    adjust(row,r)
    assert row["raw_projected_points"]==6.5
    assert row["projected_points"]==7.5


def test_calibration_ignores_current_and_future_reviews(tmp_path):
    root=tmp_path/"defense-reviews"/"2026"
    root.mkdir(parents=True)
    for w in (9,10,11):
        (root/f"week_{w:02d}.json").write_text(json.dumps(review(w,7,8)),encoding="utf-8")
    assert choose(tmp_path,2026,11)["point_adjustment"]==0


def test_scoring_config_validation(tmp_path):
    from defense_tracker.scoring import DefenseScoring
    p=tmp_path/"scoring.json"
    p.write_text(json.dumps({"sack":2,"points_allowed_tiers":[[0,10],[999,0]]}))
    s=DefenseScoring.from_json(p)
    assert s.sack==2
    assert s.allowance(0)==10
    with pytest.raises(ValueError):
        s.allowance(-1)
