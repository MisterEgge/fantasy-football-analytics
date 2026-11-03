"""Grade immutable pregame forecasts against completed weekly NFL results.

Tuesday reviews are factual backtests, not reconstructions of what was predicted.
"""
import argparse
import json
from datetime import date
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

from .analysis import _attempts, _xp
from .config import TEAMS, team_code
from .data import load_pbp, load_schedule, select_completed_games


def history_path(root, season, week, kind="forecasts"):
    return Path(root) / kind / str(int(season)) / f"week_{int(week):02d}.json"


def _team_events(events, game_ids, team):
    return events[
        events.game_id.isin(game_ids)
        & events.posteam.map(team_code).eq(team)
    ]


def grade_forecast(snapshot, pbp, schedule, as_of):
    meta = snapshot["metadata"]
    season = int(meta["season"])
    week = int(meta["target_week"])
    forecast_date = pd.Timestamp(meta["as_of"]).normalize()
    cutoff = pd.Timestamp(as_of).normalize()
    if forecast_date >= cutoff:
        raise ValueError("Forecast must predate the evaluation")
    if cutoff.dayofweek != 1:
        raise ValueError("Tuesday review must use a Tuesday as-of date")
    if not snapshot.get("teams"):
        raise ValueError("Missing immutable pregame projections")

    games = schedule[
        schedule.season.eq(season)
        & schedule.week.eq(week)
        & schedule.game_type.eq("REG")
    ].copy()
    if games.empty:
        raise RuntimeError(f"No scheduled games for {season} week {week}")
    if games.gameday.isna().any() or games.gameday.max() >= cutoff:
        raise RuntimeError("Week has not fully completed by Tuesday review cutoff")

    p = pbp[
        pbp.season.eq(season)
        & pbp.week.eq(week)
        & pbp.game_date.lt(cutoff)
    ].copy()
    if p.empty:
        raise RuntimeError("No play-by-play for the forecasted week")
    # Require both teams' play-by-play for every scheduled matchup. This catches
    # delayed nflverse data instead of silently treating missing games as zero.
    for _, g in games.iterrows():
        h, a = team_code(g.home_team), team_code(g.away_team)
        matching = p[
            (p.posteam.map(team_code).eq(h) & p.defteam.map(team_code).eq(a))
            | (p.posteam.map(team_code).eq(a) & p.defteam.map(team_code).eq(h))
        ]
        if matching.empty:
            raise RuntimeError(f"Missing play-by-play matchup: {a} at {h}")
        if matching.game_id.nunique() != 1:
            raise RuntimeError(f"Ambiguous game data: {a} at {h}")

    fg = _attempts(p)
    xp = _xp(p)
    game_map = {}
    for _, g in games.iterrows():
        home, away = team_code(g.home_team), team_code(g.away_team)
        matchup = p[
            (p.posteam.map(team_code).eq(home) & p.defteam.map(team_code).eq(away))
            | (p.posteam.map(team_code).eq(away) & p.defteam.map(team_code).eq(home))
        ]
        gid = matchup.game_id.iloc[0]
        game_map[home] = (gid, away)
        game_map[away] = (gid, home)

    projected = {r["team"]: r for r in snapshot["teams"]}
    rows = []
    for team, (gid, opponent) in game_map.items():
        if team not in projected:
            raise RuntimeError(f"Forecast lacks {team}")
        prediction = projected[team]
        if prediction.get("projected_points") is None or prediction.get("projected_fg_attempts") is None:
            raise RuntimeError(f"Missing pregame projection for {team}")
        actual_fg = _team_events(fg, [gid], team)
        actual_xp = _team_events(xp, [gid], team)
        fg_points = float(actual_fg.points.sum())
        xp_points = int(actual_xp.made.sum())
        actual_points = fg_points + xp_points
        predicted_kicker = (prediction.get("form") or {}).get("kicker")
        actual_kickers = sorted(set(
            str(k) for k in pd.concat([actual_fg.kicker, actual_xp.kicker])
            if pd.notna(k) and str(k) != "Unknown kicker"
        ))
        # A zero-attempt game has no observed kicker, not proof of replacement.
        kicker_changed = bool(actual_kickers and predicted_kicker and predicted_kicker not in actual_kickers)
        actual_attempts = int(len(actual_fg))
        projected_attempts = float(prediction["projected_fg_attempts"])
        projected_points = float(prediction["projected_points"])
        raw_attempts = float(prediction.get("raw_projected_fg_attempts", projected_attempts))
        raw_points = float(prediction.get("raw_projected_points", projected_points))
        rows.append({
            "team": team, "opponent": opponent,
            "predicted_kicker": predicted_kicker,
            "actual_kickers": actual_kickers,
            "kicker_changed": kicker_changed,
            "predicted_points": projected_points,
            "actual_points": actual_points,
            "points_error": round(projected_points - actual_points, 2),
            "predicted_fg_attempts": projected_attempts,
            "actual_fg_attempts": actual_attempts,
            "fg_attempt_error": round(projected_attempts - actual_attempts, 2),
            "raw_projected_fg_attempts": raw_attempts,
            "raw_projected_points": raw_points,
            "actual_fg_points": fg_points,
            "actual_xp_points": xp_points,
            "actual_fg_made": int(actual_fg.made.sum()),
            "actual_xp_made": xp_points,
        })
    rows.sort(key=lambda r: r["team"])
    scores = np.asarray([r["points_error"] for r in rows])
    fga = np.asarray([r["fg_attempt_error"] for r in rows])
    median_mae = float(np.mean(np.abs(
        np.asarray([r["actual_points"] for r in rows]) -
        np.median([r["actual_points"] for r in rows])
    )))
    summary = {
        "graded_teams": len(rows),
        "games": len(games),
        "points_mae": round(float(np.mean(np.abs(scores))), 2),
        "points_bias": round(float(np.mean(scores)), 2),
        "fg_attempt_mae": round(float(np.mean(np.abs(fga))), 2),
        "fg_attempt_bias": round(float(np.mean(fga)), 2),
        "constant_median_benchmark_mae": round(median_mae, 2),
        "kicker_changed_count": sum(r["kicker_changed"] for r in rows),
    }
    if len(rows) != len(games) * 2:
        raise RuntimeError("Incomplete weekly review")
    review = {
        "metadata": {
            "season": season, "week": week, "forecast_as_of": str(meta["as_of"]),
            "review_as_of": str(cutoff.date()),
            "model_calibration": meta.get("model_calibration", {}),
            "scoring": "FG: 3/4/5 by distance, made XP +1, missed FG -1",
        },
        "summary": summary,
        "teams": rows,
    }
    return review


def _metric_table(headers, data):
    head = "".join(
        f'<th style="padding:8px 9px;background:#14263d;color:#fff;text-align:left;font-size:12px;">{escape(str(v))}</th>'
        for v in headers
    )
    tr = []
    for i, row in enumerate(data):
        cells = "".join(
            f'<td style="padding:8px 9px;border-bottom:1px solid #dce6f0;font-size:12px;">{escape(str(x))}</td>'
            for x in row
        )
        tr.append(f'<tr style="background:{"#edf4fc" if i%2 else "#fff"}">{cells}</tr>')
    return '<table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;"><tr>' + head + '</tr>' + "".join(tr) + '</table>'


def build_review_html(review):
    m, s = review["metadata"], review["summary"]
    rows = review["teams"]
    worst = sorted(rows, key=lambda r: abs(r["points_error"]), reverse=True)[:6]
    all_rows = [
        (r["team"], r["opponent"], r["predicted_kicker"] or "Unverified",
         f'{r["predicted_points"]:.1f}', f'{r["actual_points"]:.1f}',
         f'{r["points_error"]:+.1f}', f'{r["predicted_fg_attempts"]:.1f}',
         r["actual_fg_attempts"], "Changed" if r["kicker_changed"] else "")
        for r in rows
    ]
    high_fga = sum(r["fg_attempt_error"] > 1.0 for r in rows)
    low_fga = sum(r["fg_attempt_error"] < -1.0 for r in rows)
    notes = [
        f'{high_fga} teams were projected at least 1 extra field-goal attempt.',
        f'{low_fga} teams attempted at least 1 more FG than projected.',
        f'{s["kicker_changed_count"]} teams had evidence that a different kicker handled attempts.',
    ]
    notes_html = "".join(f"<li>{escape(n)}</li>" for n in notes)
    review_label = f'{m["season"]} Week {m["week"]}'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Prediction Review · {escape(review_label)}</title></head>
<body style="font-family:Arial,Helvetica,sans-serif;background:#f5f7fb;color:#14263d;margin:0;">
<div style="max-width:1100px;margin:auto;padding:16px;">
<div style="padding:20px;background:#14263d;color:white;">
<p style="font-size:12px;margin:0;">TUESDAY MODEL REVIEW</p>
<h1 style="font-size:23px;margin:9px 0;">{escape(review_label)} · Predicted vs. Actual</h1>
<p style="font-size:13px;">Immutable pregame forecast saved {escape(m["forecast_as_of"])} · Reviewed {escape(m["review_as_of"])}</p></div>
<div style="background:white;padding:20px;">
<h2 style="font-size:18px;">Weekly accuracy</h2>
<p><b>{s["graded_teams"]} teams</b> across {s["games"]} games evaluated.</p>
<p><b>Fantasy points mean absolute error:</b> {s["points_mae"]:.2f} points/team<br>
<b>Fantasy points prediction bias:</b> {s["points_bias"]:+.2f} (positive means overprediction)<br>
<b>Field-goal attempt MAE:</b> {s["fg_attempt_mae"]:.2f} attempts/team<br>
<b>Field-goal attempt bias:</b> {s["fg_attempt_bias"]:+.2f}</p>
<h2 style="font-size:18px;">Largest surprises</h2>
{_metric_table(("Team", "Opponent", "Projected", "Actual", "Error", "FG predicted", "FG actual"), [
(r["team"],r["opponent"],f'{r["predicted_points"]:.1f}',f'{r["actual_points"]:.1f}',
f'{r["points_error"]:+.1f}', f'{r["predicted_fg_attempts"]:.1f}', r["actual_fg_attempts"]) for r in worst])}
<h2 style="font-size:18px;">What the data suggests</h2>
<ul style="font-size:13px;line-height:1.6;">{notes_html}</ul>
<p style="font-size:13px;">One week alone cannot establish a new coaching trend or justify formula changes.
The Wednesday forecast can apply a bounded correction only after three reviewed weeks,
at least 60 graded team-games, and an improved held-out error.</p>
<h2 style="font-size:18px;">Full game-by-game audit (every team)</h2>
{_metric_table(("Team", "Opponent", "Projected kicker", "Proj points", "Actual", "Error", "Proj FGA", "Actual FGA", "Kicker status"), all_rows)}
<p style="font-size:12px;color:#53657a;margin-top:20px;">
Fantasy scoring: made FG 0–39 = 3, 40–49 = 4, 50+ = 5; made XP = 1; missed FG = −1.
Kicker changes are flagged when a different player is recorded; actual team kicking totals
may include replacement kickers. The original forecast is preserved for auditing.</p>
</div></div></body></html>"""


def save_review(review, output_dir="review"):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    season = review["metadata"]["season"]
    week = review["metadata"]["week"]
    page = out / f"week_{week:02d}_{season}.html"
    page.write_text(build_review_html(review), encoding="utf-8")
    (out / "latest.html").write_text(page.read_text(encoding="utf-8"), encoding="utf-8")
    (out / "latest.json").write_text(json.dumps(review, indent=2), encoding="utf-8")
    return page


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history-dir", default="history-store")
    ap.add_argument("--as-of", default=date.today().isoformat())
    ap.add_argument("--season", type=int, default=date.today().year)
    ap.add_argument("--pbp")
    ap.add_argument("--schedule")
    ap.add_argument("--output", default="review")
    args = ap.parse_args()
    root = Path(args.history_dir)
    candidates = sorted((root / "forecasts" / str(args.season)).glob("week_*.json"))
    if not candidates:
        raise RuntimeError("No archived Wednesday forecasts: cannot backtest without pregame predictions")
    forecasts = [json.loads(p.read_text(encoding="utf-8")) for p in candidates]
    # Grade the latest saved week that has not already been evaluated.
    ungraded = [f for f in forecasts if not history_path(
        root, args.season, f["metadata"]["target_week"], "reviews"
    ).exists()]
    if not ungraded:
        print("All archived weekly forecasts have already been graded; no repeat email.")
        return
    forecast = ungraded[0]
    df = select_completed_games(load_pbp(args.season, args.pbp), args.as_of)
    schedule = load_schedule(args.schedule)
    review = grade_forecast(forecast, df, schedule, args.as_of)
    file = save_review(review, args.output)
    print(f"Reviewed week {review['metadata']['week']}: {review['summary']}; wrote {file}")


if __name__ == "__main__":
    main()
