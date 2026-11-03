"""Only email material NEW pregame weather/injury developments.

Uses the frozen Wednesday forecast as baseline and a persistent list of previously
notified event IDs to suppress duplicate notifications across GitHub Actions runs.
"""
import argparse
import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from kicker_tracker.context import game_lookup, kickoff_utc, load_context
from kicker_tracker.data import load_schedule


def _weather_levels(weather):
    if weather.get("status") != "forecast":
        return {}
    wind = weather.get("wind_mph") or 0
    gust = weather.get("gust_mph") or 0
    rain = weather.get("precip_in_hour") or 0
    snow = weather.get("snow_cm") or 0
    levels = {}
    if wind >= 25:
        levels["wind"] = ("high", f"Sustained wind up to {wind:.0f} mph")
    elif wind >= 15:
        levels["wind"] = ("medium", f"Wind up to {wind:.0f} mph")
    if gust >= 40:
        levels["gust"] = ("high", f"Gusts up to {gust:.0f} mph")
    elif gust >= 30:
        levels["gust"] = ("medium", f"Gusts up to {gust:.0f} mph")
    if rain >= 0.2:
        levels["rain"] = ("high", f"Heavy precipitation up to {rain:.2f} in/hr")
    elif rain >= 0.12:
        levels["rain"] = ("medium", f"Precipitation up to {rain:.2f} in/hr")
    if snow >= 2:
        levels["snow"] = ("high", f"Snow up to {snow:.1f} cm/hr")
    elif snow >= 0.5:
        levels["snow"] = ("medium", f"Snow up to {snow:.1f} cm/hr")
    return levels


def _injury_map(report):
    if report.get("status") != "available":
        return None
    return {
        (item.get("player"), item.get("position")): str(item.get("status", "")).lower()
        for item in report.get("flags", [])
    }


def _injury_severity(status, position):
    if status in ("out", "ir", "injured reserve"):
        return 3
    if status == "doubtful":
        return 2
    if status == "questionable":
        return 1 if position in ("QB", "K") else 0
    if "did not practice" in status:
        return 1 if position in ("QB", "K") else 0
    return 0


def compare_game(game, baseline, current, already_notified):
    """New significant risks only; never mistake an unavailable feed for a clear sky."""
    new = []
    matchup = f'{game["away"]}@{game["home"]}'
    before_roof = str((baseline or {}).get("roof","unknown")).lower()
    after_roof = str((current or {}).get("roof","unknown")).lower()
    known_roof = {"open", "closed", "dome", "indoor", "outdoors", "outdoor"}
    old_outdoor = before_roof in {"open", "outdoors", "outdoor"}
    new_outdoor = after_roof in {"open", "outdoors", "outdoor"}
    if (before_roof in known_roof and after_roof in known_roof
            and old_outdoor != new_outdoor):
        ident = f"{matchup}|roof|{'outdoor' if new_outdoor else 'indoor'}"
        if ident not in already_notified:
            new.append({"id": ident, "game": matchup, "category": "Roof status changed",
                        "message": ("Game now designated OUTDOORS" if new_outdoor
                                    else "Game now designated INDOORS / CLOSED"),
                        "why": "Outdoor wind and precipitation exposure has changed"})
    old_weather = (baseline or {}).get("weather") or {}
    now_weather = (current or {}).get("weather") or {}
    old_levels = _weather_levels(old_weather)
    new_levels = _weather_levels(now_weather)
    ranks = {"medium": 1, "high": 2}
    if now_weather.get("status") == "forecast":
        for kind, (level, label) in new_levels.items():
            prior_level = old_levels.get(kind, ("none", ""))[0]
            if ranks[level] <= ranks.get(prior_level, 0):
                continue
            identifier = f"{matchup}|weather|{kind}|{level}"
            if identifier not in already_notified:
                new.append({"id": identifier, "game": matchup, "category": "Weather",
                            "message": f'{label} (was {old_weather.get("summary", "unavailable")})',
                            "why": "Could affect kick distance, play calling, or ball security"})
        # A major weather risk materially improves from high to medium or clear.
        # State IDs ensure only one improvement notice per category and game.
        for kind, (prior_level, _) in old_levels.items():
            if (ranks.get(prior_level, 0) < 2 or
                    ranks.get(new_levels.get(kind, ("none",""))[0], 0) >= 2):
                continue
            identifier = f"{matchup}|weather|{kind}|eased"
            if identifier not in already_notified:
                new.append({"id": identifier, "game": matchup,
                            "category": "Weather improved",
                            "message": f"Previously severe {kind} forecast has eased",
                            "why": "A major weather concern is no longer in the highest category"})
    for team in (game["home"], game["away"]):
        ctx_old = baseline.get(team, {}) if isinstance(baseline, dict) and team in baseline else baseline or {}
        ctx_new = current.get(team, {}) if isinstance(current, dict) and team in current else current or {}
        previous = _injury_map(ctx_old.get("team_injuries") or {})
        latest = _injury_map(ctx_new.get("team_injuries") or {})
        if latest is None:
            continue
        previous = previous or {}
        for (player, position), status in latest.items():
            severity = _injury_severity(status, position)
            older = _injury_severity(previous.get((player, position), ""), position)
            if severity <= older or severity == 0:
                continue
            identifier = f"{matchup}|injury|{team}|{position}|{player}|{status}"
            if identifier not in already_notified:
                new.append({"id": identifier, "game": matchup, "category": "Injury",
                            "message": f"{team} {position} {player}: {status} (previous: {previous.get((player, position), 'not reported')})",
                            "why": "Confirmed personnel update that may affect kicking or defensive opportunities"})
    return new


def detect_changes(baseline, fresh, schedule, now, notified):
    """Only games NOT kicked off, within four days of the current check."""
    meta = baseline["metadata"]
    games = game_lookup(schedule, int(meta["season"]), int(meta["target_week"]))
    # Distinct games are keyed by home/away; each includes both teams.
    unique = {f'{g["away"]}@{g["home"]}': g for g in games.values()}
    old_rows = {r["team"]: r.get("game_context") or {} for r in baseline["teams"]}
    events = []
    for matchup, game in unique.items():
        try:
            kickoff = kickoff_utc(game)
        except (ValueError, KeyError, TypeError):
            continue
        hours = (kickoff - now).total_seconds() / 3600
        if not (0 < hours <= 96):
            continue
        # A complete game context must be available for BOTH teams.
        home, away = game["home"], game["away"]
        if home not in old_rows or away not in old_rows:
            continue
        current_home = fresh.get(home, {})
        if not current_home:
            continue
        old = dict(old_rows[home])
        old[home] = old_rows[home]
        old[away] = old_rows[away]
        current = dict(current_home)
        current[home] = fresh.get(home, {})
        current[away] = fresh.get(away, {})
        changes = compare_game(game, old, current, notified)
        for event in changes:
            event["kickoff_utc"] = kickoff.isoformat()
            event["hours_until_kickoff"] = round(hours, 1)
        events.extend(changes)
    return events


def render(events, now):
    lines = []
    for e in events:
        lines.append(
            '<tr><td style="padding:9px;border-bottom:1px solid #dfe6ee;">'
            + escape(e["game"]) + '</td><td style="padding:9px;border-bottom:1px solid #dfe6ee;">'
            + escape(e["category"]) + '</td><td style="padding:9px;border-bottom:1px solid #dfe6ee;">'
            + escape(e["message"]) + '</td></tr>'
        )
    return f"""<!doctype html><html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,Helvetica,sans-serif;color:#172638;background:#f5f7fb;padding:15px;">
<div style="max-width:750px;margin:auto;background:white;padding:20px;">
<div style="background:#14263d;color:white;padding:18px;"><h1 style="margin:0;font-size:22px;">
New NFL Weather / Injury Developments</h1></div>
<p>Only significant changes since the Wednesday forecast are shown.
No unchanged games or repeated alerts are included.</p>
<table style="width:100%;border-collapse:collapse;"><tr style="background:#dfeaf6;">
<th style="text-align:left;padding:9px;">Game</th><th style="text-align:left;padding:9px;">Type</th>
<th style="text-align:left;padding:9px;">What's changed</th></tr>{''.join(lines)}</table>
<p style="color:#58677a;font-size:12px;">Checked {escape(now.isoformat())}.
Forecast conditions and injury designations can change again. This email does not revise
the archived Wednesday point projections. Confirm the official game status and final weather
near kickoff.</p></div></body></html>"""


def run(root, season, now=None, schedule=None, context_loader=load_context):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    now = now.astimezone(timezone.utc)
    root = Path(root)
    forecasts = sorted((root / "forecasts" / str(season)).glob("week_*.json"))
    if not forecasts:
        print("No frozen Wednesday kicker forecast available; alerts skipped.")
        return None
    # The latest archived forecast, not a recalculated prediction, is our reference.
    snapshot = json.loads(forecasts[-1].read_text(encoding="utf-8"))
    meta = snapshot["metadata"]
    week = int(meta["target_week"])
    schedule = schedule if schedule is not None else load_schedule()
    baseline_date = datetime.fromisoformat(str(meta["as_of"])).date()
    if now.date() < baseline_date or (now.date() - baseline_date).days > 7:
        print("Most recent baseline is not from the current game week.")
        return None
    state_file = root / "alerts" / str(season) / f"week_{week:02d}.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {
        "season": season, "week": week, "notified": []
    }
    context = context_loader(schedule, season, week, now.date().isoformat())
    events = detect_changes(snapshot, context, schedule, now, set(state.get("notified", [])))
    if not events:
        print("No material NEW conditions: email suppressed.")
        return None
    output = Path("alerts")
    output.mkdir(exist_ok=True)
    (output / "latest.html").write_text(render(events, now), encoding="utf-8")
    (output / "latest.json").write_text(json.dumps({"events": events, "time": now.isoformat()}, indent=2))
    pending = {"season": season, "week": week, "notified": sorted(
        set(state.get("notified", [])) | {e["id"] for e in events}
    )}
    (output / "next_state.json").write_text(json.dumps(pending, indent=2))
    (output / "state_path.txt").write_text(str(state_file.relative_to(root)))
    print(f"{len(events)} new developments; alert email required.")
    return events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--history-dir", default="history-store")
    parser.add_argument("--season", type=int, default=datetime.now(timezone.utc).year)
    args = parser.parse_args()
    run(args.history_dir, args.season)


if __name__ == "__main__":
    main()
