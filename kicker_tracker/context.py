"""Pregame weather and official NFL injury-report context.

Weather and injuries are observational flags, NOT automatic point modifiers.
Store the forecast alongside predictions for honest Tuesday validation.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import pandas as pd
import requests

from kicker_tracker.config import team_code

# Approximate stadium-area coordinates; never substitute for neutral-site games.
# Shared-stadium teams intentionally use identical coordinates.
STADIUMS = {
    "ARI": (33.5276, -112.2626), "ATL": (33.7554, -84.4008),
    "BAL": (39.2780, -76.6227), "BUF": (42.7738, -78.7868),
    "CAR": (35.2258, -80.8530), "CHI": (41.8623, -87.6167),
    "CIN": (39.0954, -84.5160), "CLE": (41.5061, -81.6995),
    "DAL": (32.7480, -97.0929), "DEN": (39.7439, -105.0201),
    "DET": (42.3400, -83.0456), "GB": (44.5013, -88.0622),
    "HOU": (29.6847, -95.4107), "IND": (39.7601, -86.1639),
    "JAX": (30.3239, -81.6373), "KC": (39.0489, -94.4839),
    "LA": (33.9534, -118.3390), "LAC": (33.9534, -118.3390),
    "LV": (36.0909, -115.1833), "MIA": (25.9580, -80.2389),
    "MIN": (44.9738, -93.2581), "NE": (42.0909, -71.2643),
    "NO": (29.9509, -90.0812), "NYG": (40.8135, -74.0745),
    "NYJ": (40.8135, -74.0745), "PHI": (39.9008, -75.1675),
    "PIT": (40.4468, -80.0158), "SEA": (47.5952, -122.3316),
    "SF": (37.4030, -121.9700), "TB": (27.9759, -82.5033),
    "TEN": (36.1665, -86.7713), "WAS": (38.9077, -76.8645),
}
# Do not treat a roof with an unknown opening state as outdoor.
# nflverse schedule gametime is ALWAYS Eastern. Convert to stadium local.
WEST = {"SEA", "SF", "LA", "LAC", "LV"}
MOUNTAIN = {"DEN"}
CENTRAL = {"CHI", "DAL", "GB", "HOU", "KC", "MIN", "NO", "TEN"}
ARIZONA = {"ARI"}

NEUTRAL_VENUES = {
    "wembley": (51.5560, -0.2796, "Europe/London"),
    "tottenham hotspur stadium": (51.6043, -0.0664, "Europe/London"),
    "allianz arena": (48.2188, 11.6247, "Europe/Berlin"),
    "deutsche bank park": (50.0686, 8.6455, "Europe/Berlin"),
    "santiago bernab": (40.4531, -3.6883, "Europe/Madrid"),
    "croke park": (53.3607, -6.2513, "Europe/Dublin"),
    "neo quimica arena": (-23.5457, -46.4732, "America/Sao_Paulo"),
    "arena corinthians": (-23.5457, -46.4732, "America/Sao_Paulo"),
}

def venue_location(game):
    if game["neutral_site"]:
        label = str(game.get("stadium", "")).lower()
        for phrase, details in NEUTRAL_VENUES.items():
            if phrase in label:
                return details
        return None
    home = game["home"]
    coords = STADIUMS.get(home)
    if not coords:
        return None
    local_zone = ("America/Los_Angeles" if home in WEST else
                  "America/Denver" if home in MOUNTAIN else
                  "America/Phoenix" if home in ARIZONA else
                  "America/Chicago" if home in CENTRAL else "America/New_York")
    return (coords[0], coords[1], local_zone)

def kickoff_utc(game):
    parts = str(game.get("kickoff", "")).split(":")
    if len(parts)<2 or not game.get("date"):
        raise ValueError("Unknown game kickoff")
    hour, minute = int(parts[0]), int(parts[1])
    if not 0<=hour<=23 or not 0<=minute<=59:
        raise ValueError("Invalid kickoff clock")
    return datetime.fromisoformat(game["date"] + f"T{hour:02d}:{minute:02d}").replace(
        tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)

def kickoff_local_hour(game):
    location = venue_location(game)
    if not location:
        raise ValueError("Game venue unverified")
    return kickoff_utc(game).astimezone(ZoneInfo(location[2])).hour

ROOF_INDOOR = {"dome", "closed", "indoor"}
ROOF_OUTDOOR = {"outdoors", "outdoor", "open"}
INJURY_URL = "https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{season}.parquet"
KEY_POSITIONS = {"K", "QB", "C", "G", "T", "OT", "OG", "LT", "RT", "LG", "RG", "OL",
                 "DE", "DT", "DL", "EDGE", "LB", "ILB", "OLB", "CB", "S", "FS", "SS"}
IMPORTANT_STATUSES = {"out", "doubtful", "questionable", "injured reserve", "ir"}


def _safe_date(value):
    if value is None or pd.isna(value):
        return None
    return str(value)[:10]


def game_lookup(schedule, season, week):
    games = schedule[
        schedule.season.eq(season) & schedule.week.eq(week) & schedule.game_type.eq("REG")
    ]
    result = {}
    for _, game in games.iterrows():
        home, away = team_code(game.home_team), team_code(game.away_team)
        info = {
            "home": home, "away": away,
            "date": _safe_date(game.get("gameday")),
            "roof": str(game.get("roof", "unknown")).lower().strip(),
            "stadium": str(game.get("stadium", "unknown")),
            "neutral_site": str(game.get("location", "Home")).lower() not in ("home", "nan", "none", ""),
            "kickoff": str(game.get("gametime", "unknown")),
        }
        result[home] = info
        result[away] = info
    return result


def weather_flags(wind, gust, rain, snow):
    flags = []
    if wind is not None and wind >= 20:
        flags.append("Sustained wind 20+ mph")
    elif wind is not None and wind >= 15:
        flags.append("Wind 15+ mph")
    if gust is not None and gust >= 30:
        flags.append("Gusts 30+ mph")
    if rain is not None and rain >= 0.12:
        flags.append("Heavy precipitation potential")
    if snow is not None and snow >= 0.5:
        flags.append("Snow potential")
    return flags


def _forecast_hourly(latitude, longitude, game_date, timeout=12):
    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude, "longitude": longitude,
            "start_date": game_date, "end_date": game_date,
            "hourly": "temperature_2m,wind_speed_10m,wind_gusts_10m,precipitation,snowfall",
            "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
            "precipitation_unit": "inch", "timezone": "auto",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["hourly"]


def weather_for_game(game, fetch=_forecast_hourly):
    roof = game["roof"]
    if roof in ROOF_INDOOR:
        return {"status": "indoor", "summary": "Indoor / roof closed", "flags": []}
    if roof not in ROOF_OUTDOOR:
        return {"status": "roof_unknown", "summary": "Roof state not verified", "flags": []}
    location = venue_location(game)
    if not location:
        return {"status": "venue_unknown", "summary": "Venue coordinates unverified", "flags": []}
    if not game["date"]:
        return {"status": "unavailable", "summary": "Missing scheduled game date", "flags": []}
    lat, lon, _zone = location
    try:
        hourly = fetch(lat, lon, game["date"])
        timestamps = pd.to_datetime(hourly["time"], errors="coerce")
        if len(timestamps)==0:
            raise ValueError("No hourly weather available")
        # nflverse kickoff is Eastern; converted to stadium-local timezone above.
        try:
            start_hour = kickoff_local_hour(game)
        except (ValueError, KeyError, TypeError):
            return {"status": "kickoff_unknown", "summary": "Kickoff time unverified", "flags": []}
        hours = [i for i, ts in enumerate(timestamps)
                 if pd.notna(ts) and start_hour <= ts.hour < min(start_hour + 4, 24)]
        if not hours:
            hours = list(range(len(timestamps)))
        def values(key):
            v = hourly.get(key, [])
            return [float(v[i]) for i in hours if i < len(v) and v[i] is not None]
        winds, gusts = values("wind_speed_10m"), values("wind_gusts_10m")
        precip, snow = values("precipitation"), values("snowfall")
        temps = values("temperature_2m")
        wind = max(winds) if winds else None
        gust = max(gusts) if gusts else None
        rain = max(precip) if precip else None
        snowfall = max(snow) if snow else None
        flags = weather_flags(wind, gust, rain, snowfall)
        desc = []
        if wind is not None:
            desc.append(f"wind up to {wind:.0f} mph")
        if gust is not None:
            desc.append(f"gusts {gust:.0f} mph")
        if rain is not None:
            desc.append(f"precip up to {rain:.2f} in/hr")
        if temps:
            desc.append(f"{sum(temps)/len(temps):.0f}°F")
        return {
            "status": "forecast", "summary": ", ".join(desc) or "Weather forecast available",
            "flags": flags, "wind_mph": wind, "gust_mph": gust,
            "precip_in_hour": rain, "snow_cm": snowfall,
            "source": f"Open-Meteo hourly forecast, local {start_hour}:00–{min(start_hour+4,24)}:00",
        }
    except (ValueError, KeyError, IndexError, requests.RequestException) as error:
        return {"status": "unavailable", "summary": f"Weather unavailable ({type(error).__name__})", "flags": []}


def load_injuries(season, cutoff, path=None):
    """Return only reports published by the Wednesday cutoff. Fail openly, not silently."""
    if path:
        injuries = pd.read_parquet(path)
    else:
        response = requests.get(INJURY_URL.format(season=season), timeout=35)
        response.raise_for_status()
        from io import BytesIO
        injuries = pd.read_parquet(BytesIO(response.content))
    needed = {"team", "week", "position", "full_name", "report_status", "date_modified"}
    if needed-set(injuries):
        raise ValueError(f"Injury report schema missing: {sorted(needed-set(injuries))}")
    injuries = injuries.copy()
    # timezone-aware dates are compared as UTC and truncated to the report day.
    injuries["date_modified"] = pd.to_datetime(injuries.date_modified, utc=True, errors="coerce")
    if injuries.date_modified.isna().all():
        raise ValueError("Injury-report timestamps unavailable")
    as_of = pd.Timestamp(cutoff).tz_localize("UTC") + pd.Timedelta(days=1)
    injuries = injuries[injuries.date_modified.lt(as_of)]
    injuries["team"] = injuries.team.map(team_code)
    injuries["position"] = injuries.position.fillna("").astype(str).str.upper()
    injuries["report_status"] = injuries.report_status.fillna("").astype(str).str.lower()
    return injuries


def injuries_for_team(injuries, team, week):
    if injuries is None:
        return {"status": "unavailable", "flags": [], "summary": "Injury feed unavailable"}
    subset = injuries[
        injuries.team.eq(team) & pd.to_numeric(injuries.week, errors="coerce").eq(week)
        & injuries.position.isin(KEY_POSITIONS)
    ]
    if subset.empty:
        return {"status": "no_report", "flags": [], "summary": "No qualifying official injury entries"}
    subset = subset.sort_values("date_modified").drop_duplicates("full_name", keep="last")
    entries = []
    for row in subset.itertuples():
        status = str(row.report_status)
        practice = str(getattr(row, "practice_status", "")).lower()
        if status in IMPORTANT_STATUSES:
            label = status
        elif practice in ("did not participate", "dnp", "did not practice"):
            label = "did not practice (not confirmed out)"
        elif practice in ("limited participation", "limited"):
            label = "limited practice"
        else:
            continue
        entries.append({
            "player": str(row.full_name), "position": row.position,
            "status": label,
        })
    return {
        "status": "available", "flags": entries,
        "summary": "; ".join(f'{e["position"]} {e["player"]}: {e["status"]}' for e in entries)
                   if entries else "No key-position game designations",
    }


def load_context(schedule, season, week, cutoff, injury_file=None, fetch=_forecast_hourly):
    games = game_lookup(schedule, season, week)
    seen = {}
    injury_error = None
    try:
        injuries = load_injuries(season, cutoff, path=injury_file)
    except (OSError, ValueError, KeyError, requests.RequestException, ImportError) as error:
        injuries = None
        injury_error = type(error).__name__
    output = {}
    for team, game in games.items():
        key = (game["home"], game["away"])
        if key not in seen:
            seen[key] = weather_for_game(game, fetch)
        offense = injuries_for_team(injuries, team, week)
        opponent = game["away"] if team==game["home"] else game["home"]
        opponent_injuries = injuries_for_team(injuries, opponent, week)
        output[team] = {
            "weather": seen[key],
            "team_injuries": offense,
            "opponent_injuries": opponent_injuries,
            "injury_data_error": injury_error,
            "venue": game["stadium"],
            "roof": game["roof"],
            "game_date": game["date"],
            "weekday": (pd.Timestamp(game["date"]).day_name() if game["date"] else "Unknown"),
            "kickoff_eastern": game["kickoff"],
            "neutral_site": game["neutral_site"],
        }
    return output
