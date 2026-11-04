"""The opponent's recent defensive opponents must be visible, not just an average."""
import pandas as pd
import pytest

from defense_tracker.model import team_profiles, predict
from defense_tracker.report import forecast_html


def make_game(week, home, away, home_dst, away_dst, away_return_tds=0):
    fields = dict(season=2026,week=week,points_allowed_scoreboard=17,
                  sacks=2,interceptions=1,fumble_recoveries=0,
                  return_tds=0,return_td_points=0,blocked_kicks=0,
                  safeties=0,dropbacks_faced=25,pass_attempts_faced=24,
                  opponent_interceptions=1,opponent_fumbles_lost=0,
                  offense_plays_faced=62,offense_yards_faced=300)
    g=f"2026_{week:02d}_{away}_{home}"
    home_row={**fields,"game_id":g,"team":home,"opponent":away,
              "fantasy_points":home_dst,"home_game":True}
    away_row={**fields,"game_id":g,"team":away,"opponent":home,
              "fantasy_points":away_dst,"home_game":False,
              "return_tds":away_return_tds,"return_td_points":away_return_tds*6}
    return [home_row,away_row]


def test_chicago_recent_opponents_and_tampa_outlier_visible():
    games=pd.DataFrame(
        make_game(6,"CHI","NE",6,8)
        + make_game(7,"GB","CHI",5,6)
        + make_game(8,"SEA","CHI",3,9)
        + make_game(8,"TB","ATL",2,18,away_return_tds=0)
    )
    profiles=team_profiles(games)
    recent=profiles["CHI"]["recent_opposing_defenses"]
    assert [(x["defense"],x["dst_points"]) for x in recent]==[
        ("NE",8.0),("GB",5.0),("SEA",3.0)
    ]
    assert recent[-1]["offense_at_home"] is False  # Chicago traveled to Seattle
    assert profiles["CHI"]["dst_points_allowed_last3"]==pytest.approx(16/3,abs=.01)
    assert profiles["TB"]["recent_weekly_points"][-1]==2.0


def test_return_td_bonus_excluded_from_explanatory_metric_not_from_actual():
    games=pd.DataFrame(make_game(8,"TB","ATL",2,18,away_return_tds=1))
    p=team_profiles(games)
    assert p["TB"]["recent_opposing_defenses"][0]["dst_points"]==18
    assert p["TB"]["recent_opposing_defenses"][0]["dst_points_without_return_tds"]==12
    assert p["TB"]["dst_points_allowed_last3_without_return_tds"]==12


def test_report_displays_specific_recent_defense_results_and_location():
    team={
        "team":"TB","opponent":"CHI","projected_points":8.5,
        "last3_ppg":9,"median_ppg":8,"sacks_last3":3,
        "takeaways_last3":1.3,"dst_points_allowed_last3":4,
        "recent_weekly_points":[3,9,14],
        "game_context":{},
        "previous_defense_game":{
            "fantasy_points":18.0,"opponent":"ATL","home_game":True,
            "return_tds":1,
        },
        "upcoming_home_game":False,
        "opponent_dst_allowed_last3":5,
        "opponent_dst_allowed_last3_without_return_tds":5,
        "opponent_recent_dst_results":[
            {"week":6,"defense":"NE","dst_points":7.0,
             "offense_at_home":True,"return_tds":0},
            {"week":7,"defense":"GB","dst_points":5.0,
             "offense_at_home":False,"return_tds":0},
            {"week":8,"defense":"SEA","dst_points":3.0,
             "offense_at_home":False,"return_tds":0},
        ],
    }
    output=forecast_html({
        "metadata":{"season":2026,"target_week":9,"as_of":"2026-11-04"},
        "teams":[team],
    })
    assert "W8 SEA 3 pts" in output
    assert "18 pts vs ATL" in output
    assert "D/ST TD" in output
    assert "TB (away)" in output
    assert "Last 3 avg excl. return TDs" in output


def test_opponent_allowed_factor_still_applies_and_no_arbitrary_venue_bonus():
    defense=dict(season_ppg=9,last3_ppg=9,sacks_last3=3,takeaways_last3=2)
    tough=dict(dst_points_allowed_pg=3,dst_points_allowed_last3=3,
              sacks_conceded_last3=2,turnovers_conceded_last3=1)
    easy={**tough,"dst_points_allowed_pg":13,"dst_points_allowed_last3":13}
    assert predict(defense,tough)["projected_points"] < predict(defense,easy)["projected_points"]
