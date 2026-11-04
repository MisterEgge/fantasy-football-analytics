"""Produce 32-team D/ST projections using strictly prior completed games."""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import pandas as pd

from kicker_tracker.data import load_pbp, load_schedule, select_completed_games
from kicker_tracker.config import TEAMS, team_code
from kicker_tracker.context import load_context
from .model import game_stats, team_profiles, predict
from .scoring import DefenseScoring
from .report import save
from .calibration import choose, adjust


def upcoming(schedule, season, as_of):
    future=schedule[
        schedule.season.eq(season) &
        schedule.game_type.eq("REG") &
        schedule.gameday.ge(pd.Timestamp(as_of))
    ]
    if future.empty:
        raise RuntimeError("No future regular-season games found")
    target_week=int(future.week.min())
    opponents={}
    for _,g in future[future.week.eq(target_week)].iterrows():
        home,away=team_code(g.home_team),team_code(g.away_team)
        opponents[home]=away
        opponents[away]=home
    return target_week,opponents


def build_forecast(season, as_of, pbp, schedule, scoring=None, history_dir=None, context_enabled=True):
    scoring=scoring or DefenseScoring()
    clipped=select_completed_games(pbp,as_of)
    if clipped.empty:
        raise RuntimeError("No prior completed games")
    cutoff=pd.Timestamp(as_of)
    if clipped.game_date.max() < cutoff-pd.Timedelta(days=12):
        raise RuntimeError("nflverse dataset is stale; abort instead of emailing misleading rankings")
    target_week,opponents=upcoming(schedule,season,as_of)
    stats=game_stats(clipped,scoring)
    profiles=team_profiles(stats)
    if len(profiles)!=32:
        raise RuntimeError(f"Expected 32 teams; found {len(profiles)}")
    calibration=(choose(history_dir,season,target_week) if history_dir else
                 {"method":"no_history","point_adjustment":0.,"review_weeks":0,
                  "graded_defenses":0,"reason":"Historical review data unavailable"})
    context = load_context(schedule, season, target_week, as_of) if context_enabled else {}
    teams=[]
    for team in TEAMS:
        row=dict(profiles[team])
        opponent=opponents.get(team)
        row["opponent"]=opponent or "BYE"
        row["game_context"]=context.get(team, {})
        # The upcoming opponent's recent defenses, with explicit team, week,
        # home/away and scoring. Retain the data in the immutable Wednesday
        # snapshot so the Tuesday audit can examine matchup assumptions.
        opponent_profile=profiles.get(opponent,{}) if opponent else {}
        row["opponent_recent_dst_results"]=opponent_profile.get("recent_opposing_defenses",[])[-5:]
        row["opponent_dst_allowed_last3"]=opponent_profile.get("dst_points_allowed_last3")
        row["opponent_dst_allowed_last3_without_return_tds"]=opponent_profile.get(
            "dst_points_allowed_last3_without_return_tds")
        row["upcoming_home_game"]=bool(
            team==next((g.home_team for _,g in schedule[
                schedule.season.eq(season) &
                schedule.week.eq(target_week) &
                schedule.game_type.eq("REG")
            ].iterrows() if team_code(g.home_team)==team or team_code(g.away_team)==team),"")
        ) if opponent else None
        row.update(predict(row,profiles[opponent]) if opponent else
                   {"projected_points":None,"projected_sacks":None,"projected_takeaways":None})
        adjust(row,calibration)
        # Raw game data are not needed in the archived snapshot; grades use nflverse.
        row.pop("raw_game_records",None)
        teams.append(row)
    return {
        "metadata":{
            "season":season,"target_week":target_week,"as_of":as_of,
            "model_version":"defense-v1", "calibration":calibration,
            "scoring":{
                "sack":scoring.sack,"interception":scoring.interception,
                "fumble_recovery":scoring.fumble_recovery,
                "safety":scoring.safety,"blocked_kick":scoring.blocked_kick,
                "return_td":scoring.return_td,
                "points_allowed_tiers":scoring.points_allowed_tiers,
            },
            "scoring_status":"PROVISIONAL; user league settings not confirmed",
            "points_allowed_method":"final scoreboard proxy, not platform-exact",
        },
        "teams":teams,
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--season",type=int,default=date.today().year)
    ap.add_argument("--as-of",default=date.today().isoformat())
    ap.add_argument("--scoring",default="defense_scoring.json")
    ap.add_argument("--pbp")
    ap.add_argument("--schedule")
    ap.add_argument("--output",default="defense-report")
    ap.add_argument("--history-dir",default=None)
    args=ap.parse_args()
    scoring=DefenseScoring.from_json(args.scoring)
    payload=build_forecast(args.season,args.as_of,load_pbp(args.season,args.pbp),
                           load_schedule(args.schedule),scoring,args.history_dir)
    file=save(payload,args.output,"forecast")
    print(f'Created {file} with {len(payload["teams"])} D/ST units')


if __name__=="__main__":
    main()
