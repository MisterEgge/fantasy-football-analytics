"""Focused weather and injury flags, including indoor/neutral exclusions."""
import pandas as pd

from kicker_tracker.context import (
    game_lookup, weather_for_game, weather_flags, injuries_for_team, load_context, kickoff_local_hour,
)


def game(home="TB", away="ATL", roof="outdoors", neutral=False, kickoff="13:00"):
    return {
        "home": home, "away": away, "date": "2026-11-08",
        "roof": roof, "neutral_site": neutral, "kickoff": kickoff,
        "stadium": "Test stadium",
    }


def sample_hourly(_lat, _lon, _date):
    hours = [f"2026-11-08T{h:02d}:00" for h in range(24)]
    return {
        "time": hours, "wind_speed_10m": [4]*12+[24]*4+[4]*8,
        "wind_gusts_10m": [10]*12+[35]*4+[10]*8,
        "precipitation": [0.0]*12+[0.20]*4+[0.0]*8,
        "snowfall": [0.0]*24,
        "temperature_2m": [55.0]*24,
    }


def test_high_risk_weather_flags_at_kickoff():
    weather=weather_for_game(game(),fetch=sample_hourly)
    assert weather["status"]=="forecast"
    assert "Sustained wind 20+ mph" in weather["flags"]
    assert "Gusts 30+ mph" in weather["flags"]
    assert "Heavy precipitation potential" in weather["flags"]
    assert weather["wind_mph"]==24


def test_no_weather_flag_for_dome_even_when_outside_bad():
    def fail_fetch(*_args):
        raise AssertionError("Dome should never call forecast provider")
    result=weather_for_game(game(roof="dome"),fetch=fail_fetch)
    assert result["status"]=="indoor"
    assert result["flags"]==[]


def test_neutral_and_unknown_roof_do_not_use_wrong_stadium():
    for game_data in (game(neutral=True),game(roof="unknown")):
        out=weather_for_game(game_data,fetch=lambda *_: (_ for _ in ()).throw(AssertionError()))
        assert out["status"] in ("roof_unknown","venue_unknown")


def test_wednesday_injury_status_latest_only_and_only_key_positions():
    report=pd.DataFrame([
        {"team":"TB","week":9,"position":"QB","full_name":"A QB",
         "report_status":"Questionable","date_modified":"2026-11-03T10:00:00Z"},
        {"team":"TB","week":9,"position":"QB","full_name":"A QB",
         "report_status":"Out","date_modified":"2026-11-04T12:00:00Z"},
        {"team":"TB","week":9,"position":"WR","full_name":"A WR",
         "report_status":"Out","date_modified":"2026-11-04T11:00:00Z"},
        {"team":"TB","week":9,"position":"K","full_name":"A K",
         "report_status":"Questionable","date_modified":"2026-11-04T12:00:00Z"},
    ])
    report["date_modified"]=pd.to_datetime(report.date_modified,utc=True)
    result=injuries_for_team(report,"TB",9)
    assert result["status"]=="available"
    assert len(result["flags"])==2
    assert next(x for x in result["flags"] if x["position"]=="QB")["status"]=="out"


def test_game_lookup_uses_schedule_roof_and_time():
    schedule=pd.DataFrame([{
        "season":2026,"week":9,"game_type":"REG","home_team":"TB",
        "away_team":"ATL","gameday":pd.Timestamp("2026-11-08"),
        "roof":"outdoors","stadium":"Raymond James Stadium",
        "gametime":"13:00","location":"Home",
    }])
    d=game_lookup(schedule,2026,9)
    assert d["TB"]["home"]=="TB"
    assert d["ATL"]["roof"]=="outdoors"
    assert d["TB"]["kickoff"]=="13:00"


def test_context_missing_injury_feed_is_explicit(monkeypatch):
    from kicker_tracker import context
    def fail(*_args,**_kwargs):
        raise OSError("Unreachable")
    monkeypatch.setattr(context,"load_injuries",fail)
    schedule=pd.DataFrame([{
        "season":2026,"week":9,"game_type":"REG","home_team":"TB",
        "away_team":"ATL","gameday":pd.Timestamp("2026-11-08"),
        "roof":"closed","stadium":"Test","location":"Home","gametime":"13:00",
    }])
    out=load_context(schedule,2026,9,"2026-11-04")
    assert out["TB"]["team_injuries"]["status"]=="unavailable"
    assert out["ATL"]["weather"]["status"]=="indoor"

def test_eastern_schedule_time_converts_to_stadium_local():
    assert kickoff_local_hour(game(home="SF", kickoff="16:25"))==13
    assert kickoff_local_hour(game(home="ARI", kickoff="16:05"))==14
    assert kickoff_local_hour(game(home="TB", kickoff="13:00"))==13
