"""Regression tests for D/ST scoring, team forecasts and immutable grading."""
import pandas as pd
import pytest

from defense_tracker.model import game_stats, team_profiles, predict
from defense_tracker.scoring import DefenseScoring
from defense_tracker.review import evaluate


def sample_pbp():
    common=dict(
        game_id="2026_09_BAL_CIN", season=2026, week=9,
        game_date=pd.Timestamp("2026-11-08"), home_team="CIN", away_team="BAL",
        home_score=17, away_score=10, touchdown=0, td_team=None, return_touchdown=0,
        sack=0, interception=0, fumble_lost=0, safety=0, blocked_punt=0,
        field_goal_result=None, extra_point_result=None, pass_attempt=0,
        yards_gained=0, play_type="pass", field_goal_attempt=0,
    )
    rows=[]
    def add(off, defense, **changes):
        item=dict(common,posteam=off,defteam=defense)
        item.update(changes)
        rows.append(item)
    add("BAL","CIN",sack=1, pass_attempt=1, yards_gained=-7)
    add("BAL","CIN",interception=1, pass_attempt=1)
    add("BAL","CIN",fumble_lost=1)
    add("CIN","BAL",pass_attempt=1)
    add("BAL","CIN",touchdown=1,td_team="CIN",return_touchdown=1)
    return pd.DataFrame(rows)


def sample_schedule():
    return pd.DataFrame([{
        "season":2026,"week":9,"game_type":"REG",
        "home_team":"CIN","away_team":"BAL",
        "gameday":pd.Timestamp("2026-11-08"),
    }])


def test_espn_like_points_allowed_brackets():
    score=DefenseScoring()
    assert [score.allowance(v) for v in (0,6,7,13,14,17,18,27,28,34,35,45,46)] == [
        5,4,3,3,1,1,0,0,-1,-1,-3,-3,-5
    ]


def test_dst_scoring_all_components():
    scored=game_stats(sample_pbp())
    cin=scored[scored.team.eq("CIN")].iloc[0]
    bal=scored[scored.team.eq("BAL")].iloc[0]
    assert cin.sacks==1
    assert cin.interceptions==1
    assert cin.fumble_recoveries==1
    assert cin.return_tds==1
    # 1 sack + 2 INT + 2 fumble + 6 return TD + 3 allowed 10 pts
    assert cin.fantasy_points==14
    assert bal.points_allowed_scoreboard==17
    assert bal.fantasy_points==1


def test_configurable_scoring():
    scoring=DefenseScoring(sack=2,points_allowed_tiers=((0,10),(999,0)))
    c=game_stats(sample_pbp(),scoring)
    assert c[c.team.eq("CIN")].iloc[0].fantasy_points==12


def test_opponent_adjustment_both_sides():
    d=dict(season_ppg=10,last3_ppg=10,sacks_last3=3,takeaways_last3=2)
    offense=dict(dst_points_allowed_pg=2,dst_points_allowed_last3=2,
                 sacks_conceded_last3=4,turnovers_conceded_last3=3)
    result=predict(d,offense)
    assert result["projected_points"]==pytest.approx(6.64)
    assert result["projected_sacks"]==3.5
    assert result["projected_takeaways"]==2.5


def test_tuesday_audit_uses_saved_projection():
    df=sample_pbp()
    row=lambda team,opp:dict(team=team,opponent=opp,projected_points=8.0,
                              projected_sacks=1.0,projected_takeaways=1.0)
    meta=dict(season=2026,target_week=9,as_of="2026-11-04",model_version="defense-v1",
              points_allowed_method="scoreboard proxy",
              scoring=dict(sack=1,interception=2,fumble_recovery=2,safety=2,
                           blocked_kick=2,return_td=6,
                           points_allowed_tiers=[[0,5],[6,4],[13,3],[17,1],[27,0],
                                                 [34,-1],[45,-3],[999,-5]]))
    review=evaluate(dict(metadata=meta,teams=[row("CIN","BAL"),row("BAL","CIN")]),
                    df,sample_schedule(),"2026-11-10")
    assert review["summary"]["teams"]==2
    assert next(r for r in review["teams"] if r["team"]=="CIN")["actual_points"]==14
    assert review["summary"]["mae"]==pytest.approx(6.5)
    with pytest.raises(ValueError):
        evaluate(dict(metadata=meta,teams=[row("CIN","BAL"),row("BAL","CIN")]),
                 df,sample_schedule(),"2026-11-09")
