"""Defense and special-teams team-game scoring from nflverse play by play.

Important caveat: scoreboards include opponent D/ST scores and can differ from
platform-defined D/ST 'points allowed'. That approximation is clearly disclosed.
"""
import numpy as np
import pandas as pd
from kicker_tracker.config import TEAMS, team_code
from kicker_tracker.analysis import robust_mean
from .scoring import DefenseScoring


def numeric(frame, key):
    if key not in frame:
        return pd.Series(0, index=frame.index, dtype=float)
    return pd.to_numeric(frame[key], errors="coerce").fillna(0)


def _teams(group):
    home = group["home_team"].dropna()
    away = group["away_team"].dropna()
    if home.empty or away.empty:
        raise ValueError("PBP missing game home_team/away_team")
    return team_code(home.iloc[0]), team_code(away.iloc[0])


def _final_score(group, home, away):
    if {"home_score", "away_score"}.issubset(group.columns):
        h = pd.to_numeric(group["home_score"], errors="coerce").dropna()
        a = pd.to_numeric(group["away_score"], errors="coerce").dropna()
        if not h.empty and not a.empty:
            return int(h.iloc[-1]), int(a.iloc[-1])
    if {"total_home_score", "total_away_score"}.issubset(group.columns):
        h = pd.to_numeric(group["total_home_score"], errors="coerce").dropna()
        a = pd.to_numeric(group["total_away_score"], errors="coerce").dropna()
        if not h.empty and not a.empty:
            return int(h.iloc[-1]), int(a.iloc[-1])
    raise ValueError("Missing final game score; refusing inaccurate D/ST scoring")


def game_stats(pbp, scoring=None):
    scoring = scoring or DefenseScoring()
    required = {"game_id", "week", "season", "posteam", "defteam",
                "home_team", "away_team", "play_type", "sack", "interception",
                "fumble_lost", "safety", "touchdown", "td_team",
                "punt_blocked", "field_goal_result", "extra_point_result"}
    missing = required-set(pbp)
    if missing:
        raise ValueError(f"Missing defensive PBP columns: {sorted(missing)}")
    result=[]
    for game_id, group in pbp.groupby("game_id", sort=False):
        group=group.copy()
        home,away=_teams(group)
        hs,as_=_final_score(group,home,away)
        if home not in TEAMS or away not in TEAMS:
            continue
        for team,opponent,allowed in [(home,away,as_), (away,home,hs)]:
            # Defensive PBP team is the opponent of the offense. For punts and
            # kickoffs, the return team is normally defteam.
            defense = group[group.defteam.map(team_code).eq(team)]
            sacks=int(numeric(defense,"sack").eq(1).sum())
            ints=int(numeric(defense,"interception").eq(1).sum())
            fumbles=int(numeric(defense,"fumble_lost").eq(1).sum())
            safeties=int(numeric(defense,"safety").eq(1).sum())
            blocked=int(
                (defense.get("field_goal_result",pd.Series(index=defense.index,dtype=object)).astype(str).str.lower().eq("blocked")
                 | defense.get("extra_point_result",pd.Series(index=defense.index,dtype=object)).astype(str).str.lower().eq("blocked")
                 | numeric(defense,"punt_blocked").eq(1)
                ).sum()
            )
            td_team = group.get("td_team",pd.Series(index=group.index,dtype=object)).map(team_code)
            scored_td = numeric(group,"touchdown").eq(1) & td_team.eq(team)
            # Count only defensive or return TDs: offense that has posteam=team
            # is excluded. This includes kickoff/punt returns via return_touchdown.
            defensive_tds=int((scored_td & group.posteam.map(team_code).ne(team)).sum())
            # Playing-opponent offense statistics, not raw team defense.
            offense = group[group.posteam.map(team_code).eq(opponent)]
            qb_dropbacks=int((numeric(offense,"pass_attempt").eq(1) |
                              numeric(offense,"sack").eq(1)).sum())
            attempts=int(numeric(offense,"pass_attempt").eq(1).sum())
            interceptions_thrown=int(numeric(offense,"interception").eq(1).sum())
            lost_fumbles=int(numeric(offense,"fumble_lost").eq(1).sum())
            plays=int(offense.play_type.isin(["run","pass"]).sum())
            yards=float(numeric(offense,"yards_gained").where(offense.play_type.isin(["run","pass"]),0).sum())
            points=(sacks*scoring.sack+ints*scoring.interception+
                    fumbles*scoring.fumble_recovery+safeties*scoring.safety+
                    blocked*scoring.blocked_kick+defensive_tds*scoring.return_td+
                    scoring.allowance(allowed))
            result.append({
                "game_id":str(game_id),"season":int(group.season.iloc[0]),
                "week":int(group.week.iloc[0]),"team":team,"opponent":opponent,
                "home_game":bool(team==home),
                "points_allowed_scoreboard":allowed,"sacks":sacks,"interceptions":ints,
                "fumble_recoveries":fumbles,"safeties":safeties,
                "blocked_kicks":blocked,"return_tds":defensive_tds,
                "return_td_points":float(defensive_tds*scoring.return_td),
                "dropbacks_faced":qb_dropbacks,"pass_attempts_faced":attempts,
                "opponent_interceptions":interceptions_thrown,
                "opponent_fumbles_lost":lost_fumbles,"offense_plays_faced":plays,
                "offense_yards_faced":round(yards,1),"fantasy_points":round(points,2),
            })
    return pd.DataFrame(result)


def team_profiles(games):
    profiles={}
    for team in TEAMS:
        own=games[games.team.eq(team)].sort_values("week")
        faced=games[games.opponent.eq(team)].sort_values("week")
        if own.empty:
            continue
        def avg(df,key):
            return float(df[key].mean()) if len(df) else 0.
        pts=own.fantasy_points.to_list()
        opponent_dst=faced.fantasy_points.to_list()
        # These are the D/STs the offense ACTUALLY faced, not its own defense.
        # Keep opponent identity and location; expose both raw and TD-excluded
        # fantasy scores so a single pick-six does not masquerade as a trend.
        recent_opposing_defenses = []
        for rec in faced.tail(5).itertuples():
            td_points = float(rec.return_td_points)
            recent_opposing_defenses.append({
                "week": int(rec.week),
                "defense": str(rec.team),
                "dst_points": round(float(rec.fantasy_points), 2),
                "dst_points_without_return_tds": round(float(rec.fantasy_points)-td_points,2),
                "sacks": int(rec.sacks),
                "takeaways": int(rec.interceptions+rec.fumble_recoveries),
                "return_tds": int(rec.return_tds),
                "offense_at_home": not bool(rec.home_game),
            })
        def smoothed_recent(values):
            if not values:
                return 0.0
            median=float(np.median(values))
            return round(float(np.mean(np.clip(values[-3:],median-6,median+6))),2)
        profiles[team]={
            "team":team, "team_name":TEAMS[team], "games":len(own),
            "recent_weekly_points": [round(float(x),1) for x in pts[-5:]],
            "season_ppg":round(avg(own,"fantasy_points"),2),
            "last3_ppg":round(avg(own.tail(3),"fantasy_points"),2),
            "last3_robust_ppg":smoothed_recent(pts),
            "last5_ppg":round(avg(own.tail(5),"fantasy_points"),2),
            "median_ppg":round(float(np.median(pts)),2),
            "robust_ppg":round(robust_mean(pts),2),
            "pct_under_5":round(float(np.mean(np.asarray(pts)<5)),2),
            "sacks_pg":round(avg(own,"sacks"),2),
            "sacks_last3":round(avg(own.tail(3),"sacks"),2),
            "takeaways_pg":round(avg(own,"interceptions")+avg(own,"fumble_recoveries"),2),
            "takeaways_last3":round(avg(own.tail(3),"interceptions")+avg(own.tail(3),"fumble_recoveries"),2),
            "points_allowed_pg":round(avg(own,"points_allowed_scoreboard"),2),
            "points_allowed_last3":round(avg(own.tail(3),"points_allowed_scoreboard"),2),
            "recent_opposing_defenses":recent_opposing_defenses,
            "dst_points_allowed_last3_without_return_tds":round(
                float((faced.tail(3).fantasy_points - faced.tail(3).return_td_points).mean()),2
            ) if len(faced) else 0.0,
            "dst_points_allowed_pg":round(avg(faced,"fantasy_points"),2),
            "dst_points_allowed_last3":round(avg(faced.tail(3),"fantasy_points"),2),
            "dst_points_allowed_robust":round(robust_mean(opponent_dst),2),
            "dst_points_allowed_last3_robust":smoothed_recent(opponent_dst),
            "sacks_conceded_pg":round(avg(faced,"sacks"),2),
            "sacks_conceded_last3":round(avg(faced.tail(3),"sacks"),2),
            "turnovers_conceded_pg":round(avg(faced,"interceptions")+avg(faced,"fumble_recoveries"),2),
            "turnovers_conceded_last3":round(avg(faced.tail(3),"interceptions")+avg(faced.tail(3),"fumble_recoveries"),2),
            "offense_points_pg":round(avg(faced,"points_allowed_scoreboard"),2),
            "offense_points_last3":round(avg(faced.tail(3),"points_allowed_scoreboard"),2),
            "raw_game_records":own.to_dict(orient="records"),
        }
    return profiles


def predict(defense, opposing_offense):
    """Transparent, conservative heuristic. Tunable once holdout backtests exist."""
    d=.45*defense.get("robust_ppg",defense["season_ppg"])+.55*defense.get("last3_robust_ppg",defense["last3_ppg"])
    o=.45*opposing_offense.get("dst_points_allowed_robust",opposing_offense["dst_points_allowed_pg"])+.55*opposing_offense.get("dst_points_allowed_last3_robust",opposing_offense["dst_points_allowed_last3"])
    # Opponent-friendly tendency is high when that offense gives up D/ST fantasy points.
    forecast=.58*d+.42*o
    sacks=.5*defense["sacks_last3"]+.5*opposing_offense["sacks_conceded_last3"]
    turnovers=.5*defense["takeaways_last3"]+.5*opposing_offense["turnovers_conceded_last3"]
    return {"projected_points":round(float(forecast),2),
            "projected_sacks":round(float(sacks),2),
            "projected_takeaways":round(float(turnovers),2),
            "model":"unvalidated regularized D/ST and opponent fantasy-point rates"}
