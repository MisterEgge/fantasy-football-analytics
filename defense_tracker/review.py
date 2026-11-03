"""Tuesday defense forecast audit against immutable Wednesday snapshot."""
import argparse
import json
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd
from kicker_tracker.data import load_pbp, load_schedule, select_completed_games
from kicker_tracker.config import team_code
from .scoring import DefenseScoring
from .model import game_stats
from .report import save


def evaluate(snapshot,pbp,schedule,as_of):
    metadata=snapshot["metadata"]
    season=int(metadata["season"])
    week=int(metadata["target_week"])
    timestamp=pd.Timestamp(as_of).normalize()
    pregame=pd.Timestamp(metadata["as_of"]).normalize()
    if pregame>=timestamp:
        raise ValueError("The forecast must have been saved before grading")
    if timestamp.dayofweek!=1:
        raise ValueError("Defense review is restricted to Tuesdays")
    games=schedule[
        schedule.season.eq(season)&schedule.week.eq(week)&schedule.game_type.eq("REG")
    ]
    if games.empty or games.gameday.isna().any() or games.gameday.max()>=timestamp:
        raise RuntimeError("Requested week is not completely scheduled before Tuesday")
    scoring=DefenseScoring(**{
        **metadata["scoring"],
        "points_allowed_tiers": tuple(tuple(p) for p in metadata["scoring"]["points_allowed_tiers"]),
    })
    actual=game_stats(select_completed_games(pbp,as_of),scoring)
    actual=actual[(actual.season.eq(season)) & actual.week.eq(week)]
    mapping={(r.team,r.opponent):r for r in actual.itertuples()}
    expected={}
    for _,g in games.iterrows():
        h,a=team_code(g.home_team),team_code(g.away_team)
        expected[(h,a)]=None
        expected[(a,h)]=None
    if set(mapping)!=set(expected):
        missing=set(expected)-set(mapping)
        raise RuntimeError(f"Missing or unexpected completed D/ST games; missing {sorted(missing)}")
    pred={t["team"]:t for t in snapshot["teams"]}
    grades=[]
    for (team,opponent),g in sorted(mapping.items()):
        if team not in pred or pred[team].get("projected_points") is None:
            raise ValueError(f"No archived pregame projection for {team}")
        p=pred[team]
        error=round(float(p["projected_points"])-float(g.fantasy_points),2)
        sack_error=round(float(p["projected_sacks"])-g.sacks,2)
        turnover_error=round(float(p["projected_takeaways"])-(g.interceptions+g.fumble_recoveries),2)
        if g.return_tds:
            diagnostic="High-variance defensive/return touchdown"
        elif abs(sack_error)>=2:
            diagnostic="Sack-volume prediction"
        elif abs(turnover_error)>=2:
            diagnostic="Takeaway-volume prediction"
        elif abs(error)>=5:
            diagnostic="Scoring environment, blocks or special teams"
        else:
            diagnostic="Normal weekly variance"
        grades.append({
            "team":team,"opponent":opponent,
            "predicted_points":float(p["projected_points"]),
            "raw_projected_points":float(p.get("raw_projected_points",p["projected_points"])),
            "actual_points":float(g.fantasy_points),
            "error":error,
            "projected_sacks":float(p["projected_sacks"]),
            "actual_sacks":int(g.sacks),
            "projected_takeaways":float(p["projected_takeaways"]),
            "actual_takeaways":int(g.interceptions+g.fumble_recoveries),
            "actual_defensive_tds":int(g.return_tds),
            "actual_points_allowed_scoreboard":int(g.points_allowed_scoreboard),
            "diagnostic":diagnostic,
        })
    errors=np.asarray([r["error"] for r in grades])
    sacks=np.asarray([r["projected_sacks"]-r["actual_sacks"] for r in grades])
    takeaways=np.asarray([r["projected_takeaways"]-r["actual_takeaways"] for r in grades])
    return {
        "metadata":{
            "season":season,"week":week,"forecast_as_of":metadata["as_of"],
            "review_as_of":str(timestamp.date()),"scoring":metadata["scoring"],
            "model_version":metadata["model_version"],
            "calibration":metadata.get("calibration",{}),
            "points_allowed_method":metadata["points_allowed_method"],
        },
        "summary":{
            "teams":len(grades),"games":len(games),
            "mae":round(float(np.mean(abs(errors))),2),
            "bias":round(float(np.mean(errors)),2),
            "sack_mae":round(float(np.mean(abs(sacks))),2),
            "takeaway_mae":round(float(np.mean(abs(takeaways))),2),
        },
        "teams":grades,
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--history-dir",default="history-store")
    ap.add_argument("--season",type=int,default=date.today().year)
    ap.add_argument("--as-of",default=date.today().isoformat())
    ap.add_argument("--pbp")
    ap.add_argument("--schedule")
    ap.add_argument("--output",default="defense-review")
    args=ap.parse_args()
    root=Path(args.history_dir)
    forecasts=sorted((root/"defense-forecasts"/str(args.season)).glob("week_*.json"))
    if not forecasts:
        print("No archived defense forecasts; first review occurs after Wednesday baseline.")
        return
    for forecast in forecasts:
        snapshot=json.loads(forecast.read_text(encoding="utf-8"))
        week=int(snapshot["metadata"]["target_week"])
        review_file=root/"defense-reviews"/str(args.season)/f"week_{week:02d}.json"
        if review_file.exists():
            continue
        result=evaluate(snapshot,load_pbp(args.season,args.pbp),
                        load_schedule(args.schedule),args.as_of)
        print(f"Graded {result['summary']['teams']} team defenses. {result['summary']}")
        save(result,args.output,"review")
        return
    print("All available defense forecasts have already been reviewed; no new email.")


if __name__=="__main__":
    main()
