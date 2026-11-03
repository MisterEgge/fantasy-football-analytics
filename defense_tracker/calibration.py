"""Conservative D/ST forecast correction with true walk-forward validation.

Only historical Tuesday reviews strictly before the forecasted week are eligible.
A held-out later week must improve before a correction is applied.
"""
from pathlib import Path
import json
import numpy as np


def select(history_root, season, week):
    root=Path(history_root)/"defense-reviews"/str(season)
    if not root.exists():
        return []
    records=[]
    for path in root.glob("week_*.json"):
        r=json.loads(path.read_text(encoding="utf-8"))
        m=r["metadata"]
        if int(m["season"])==season and int(m["week"])<week:
            records.append(r)
    return sorted(records,key=lambda r:r["metadata"]["week"])


def _rows(reviews):
    return [item for r in reviews for item in r["teams"]
            if item.get("raw_projected_points", item.get("predicted_points")) is not None
            and item.get("actual_points") is not None]


def choose(history_root, season, target_week):
    reviews=select(history_root,season,target_week)
    n=len(_rows(reviews))
    base={"method":"no_validated_adjustment","point_adjustment":0.,
          "review_weeks":len(reviews),"graded_defenses":n,
          "reason":"Awaiting at least three weekly reviews and sixty defense-games"}
    if len(reviews)<3 or n<60:
        return base
    prior=_rows(reviews[:-1])
    holdout=_rows(reviews[-1:])
    if len(prior)<40 or len(holdout)<16:
        return base
    signed=np.asarray([
        float(r["actual_points"])-float(r.get("raw_projected_points",r["predicted_points"]))
        for r in prior
    ])
    # A simple conservative shift, capped at +/-1.5 points.
    correction=float(np.clip(np.mean(signed),-1.5,1.5))
    predicted=np.asarray([
        float(r.get("raw_projected_points",r["predicted_points"]))
        for r in holdout
    ])
    actual=np.asarray([float(r["actual_points"]) for r in holdout])
    old=float(np.mean(abs(predicted-actual)))
    new=float(np.mean(abs(predicted+correction-actual)))
    base.update({"candidate_adjustment":round(correction,3),
                 "held_out_mae_original":round(old,3),
                 "held_out_mae_candidate":round(new,3),
                 "validation_week":reviews[-1]["metadata"]["week"]})
    if new+0.05>=old:
        base["reason"]="Correction did not improve held-out weekly MAE"
        return base
    base["method"]="walk_forward_validated_bias_correction"
    base["point_adjustment"]=round(correction,3)
    base["reason"]="Older weeks fit correction; later unseen week validates it"
    return base


def adjust(row,calibration):
    if row.get("projected_points") is None:
        return
    original=float(row["projected_points"])
    row["raw_projected_points"]=original
    row["projected_points"]=round(original+float(calibration["point_adjustment"]),2)
