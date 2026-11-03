"""A quiet alerting system: early kickoffs, change thresholds and dedupe."""
from datetime import datetime, timezone
import json

import pandas as pd

from kicker_tracker.alerts import compare_game, detect_changes, run
from kicker_tracker.context import kickoff_utc, venue_location, weather_for_game


def make_game(home="TB", away="ATL", when="2026-11-05", kickoff="20:15",
              stadium="Raymond James Stadium", neutral=False, roof="outdoors"):
    return {
        "home": home, "away": away, "date": when, "kickoff": kickoff,
        "roof": roof, "stadium": stadium, "neutral_site": neutral,
    }


def ctx(weather=None, injuries=None):
    return {
        "weather": weather or {"status": "forecast", "wind_mph": 6,
                               "gust_mph": 9, "precip_in_hour": 0, "flags": [],
                               "summary": "Light wind"},
        "team_injuries": injuries or {"status": "available", "flags": []},
        "opponent_injuries": {"status": "available", "flags": []},
    }


def test_international_game_gets_correct_local_weather_location_and_early_utc():
    game = make_game(home="JAX", away="NE", when="2026-11-08", kickoff="09:30",
                     stadium="Wembley Stadium", neutral=True)
    lat,lon,zone=venue_location(game)
    assert zone == "Europe/London"
    assert 51 < lat < 52
    assert kickoff_utc(game).isoformat().startswith("2026-11-08T14:30:00")
    def forecast(_lat, _lon, _date):
        assert abs(_lat - lat) < 0.01
        times=[f"2026-11-08T{h:02d}:00" for h in range(24)]
        return {
            "time":times,
            "wind_speed_10m":[4]*14+[24]*4+[4]*6,
            "wind_gusts_10m":[10]*14+[34]*4+[10]*6,
            "precipitation":[0]*24,
            "snowfall":[0]*24,
            "temperature_2m":[50]*24,
        }
    w=weather_for_game(game,fetch=forecast)
    assert w["status"]=="forecast"
    assert w["wind_mph"]==24


def test_unknown_international_venue_fails_safe():
    game=make_game(home="JAX",away="NE",neutral=True,stadium="Unknown Park")
    assert venue_location(game) is None
    assert weather_for_game(game)["status"]=="venue_unknown"


def test_new_wind_threshold_alerts_once():
    game=make_game()
    baseline={"TB":ctx(),"ATL":ctx(), **ctx()}
    now={"TB":ctx({"status":"forecast","wind_mph":23,"gust_mph":34,
                    "precip_in_hour":0,"flags":["Sustained wind 20+ mph"],
                    "summary":"wind 23 mph"}), "ATL":ctx()}
    now.update(now["TB"])
    events=compare_game(game,baseline,now,set())
    assert {e["category"] for e in events}=={"Weather"}
    assert len(events)==2  # wind and gust are independently significant
    assert compare_game(game,baseline,now,{e["id"] for e in events})==[]


def test_small_wind_variation_does_not_email():
    game=make_game()
    baseline={"TB":ctx(),"ATL":ctx(), **ctx()}
    current={"TB":ctx({"status":"forecast","wind_mph":12,"gust_mph":16,
                        "precip_in_hour":0,"flags":[],"summary":"wind 12 mph"}),
             "ATL":ctx()}
    current.update(current["TB"])
    assert compare_game(game,baseline,current,set())==[]


def test_key_injury_out_after_questionable_and_no_duplicate():
    game=make_game()
    old=ctx(injuries={"status":"available","flags":[
        {"player":"QB Example","position":"QB","status":"questionable"}]})
    new=ctx(injuries={"status":"available","flags":[
        {"player":"QB Example","position":"QB","status":"out"}]})
    baseline={"TB":old,"ATL":ctx(), **old}
    current={"TB":new,"ATL":ctx(), **new}
    events=compare_game(game,baseline,current,set())
    assert len(events)==1
    assert "QB Example" in events[0]["message"]
    assert compare_game(game,baseline,current,{events[0]["id"]})==[]


def test_missing_weather_and_injury_feed_do_not_trigger_false_all_clear():
    game=make_game()
    old=ctx({"status":"forecast","wind_mph":28,"gust_mph":45,
             "precip_in_hour":0,"flags":["wind"],"summary":"Very windy"},
             {"status":"available","flags":[]})
    new=ctx({"status":"unavailable","flags":[],"summary":"Provider outage"},
             {"status":"unavailable","flags":[]})
    before={"TB":old,"ATL":old,**old}
    after={"TB":new,"ATL":new,**new}
    assert compare_game(game,before,after,set())==[]


def test_only_not_started_games_are_eligible():
    g=make_game()
    schedule=pd.DataFrame([{
        "season":2026,"week":9,"game_type":"REG",
        "home_team":"TB","away_team":"ATL",
        "gameday":pd.Timestamp("2026-11-05"),
        "roof":"outdoors","stadium":"Raymond James Stadium",
        "location":"Home","gametime":"20:15",
    }])
    snap={"metadata":{"season":2026,"target_week":9,"as_of":"2026-11-04"},
          "teams":[{"team":"TB","game_context":ctx()},
                   {"team":"ATL","game_context":ctx()}]}
    windy=ctx({"status":"forecast","wind_mph":25,"gust_mph":40,
               "precip_in_hour":0,"flags":["wind"],"summary":"High wind"})
    fresh={"TB":windy,"ATL":ctx()}
    pre=datetime(2026,11,5,20,0,tzinfo=timezone.utc)
    after=datetime(2026,11,6,2,0,tzinfo=timezone.utc)
    assert detect_changes(snap,fresh,schedule,pre,set())
    assert detect_changes(snap,fresh,schedule,after,set())==[]


def test_no_archived_forecast_means_no_email(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert run(tmp_path,2026,datetime(2026,11,5,tzinfo=timezone.utc)) is None
    assert not (tmp_path/"alerts"/"latest.html").exists()


def test_outdoor_thursday_roof_change_is_a_single_alert():
    game=make_game(roof="open")
    baseline={"TB":ctx(),"ATL":ctx(), **ctx(), "roof":"closed"}
    current={"TB":ctx(),"ATL":ctx(), **ctx(), "roof":"open"}
    events=compare_game(game,baseline,current,set())
    assert len(events)==1
    assert events[0]["category"]=="Roof status changed"
    assert compare_game(game,baseline,current,{events[0]["id"]})==[]


def test_830_am_eastern_international_start_is_respected():
    g=make_game(home="JAX",away="NE",when="2026-11-08",
                kickoff="08:30",stadium="Tottenham Hotspur Stadium",neutral=True)
    assert kickoff_utc(g).isoformat().startswith("2026-11-08T13:30:00")


def test_sent_change_is_not_emailed_again_on_next_scheduled_check(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    history=tmp_path/"history-store"
    folder=history/"forecasts"/"2026"
    folder.mkdir(parents=True)
    snap={"metadata":{"season":2026,"target_week":9,"as_of":"2026-11-04"},
          "teams":[{"team":"TB","game_context":ctx()},
                   {"team":"ATL","game_context":ctx()}]}
    (folder/"week_09.json").write_text(json.dumps(snap),encoding="utf-8")
    schedule=pd.DataFrame([{
        "season":2026,"week":9,"game_type":"REG",
        "home_team":"TB","away_team":"ATL","gameday":pd.Timestamp("2026-11-05"),
        "roof":"outdoors","stadium":"Raymond James Stadium","location":"Home",
        "gametime":"20:15",
    }])
    wind={"status":"forecast","wind_mph":26,"gust_mph":11,
          "precip_in_hour":0,"flags":["wind"],"summary":"Strong wind"}
    changes=lambda *_args: {"TB":ctx(weather=wind),"ATL":ctx(weather=wind)}
    when=datetime(2026,11,5,18,0,tzinfo=timezone.utc)
    events=run(history,2026,now=when,schedule=schedule,context_loader=changes)
    assert events and len(events)==1
    state=history/"alerts"/"2026"/"week_09.json"
    state.parent.mkdir(parents=True)
    state.write_text((tmp_path/"alerts"/"next_state.json").read_text())
    assert run(history,2026,now=when,schedule=schedule,context_loader=changes) is None
