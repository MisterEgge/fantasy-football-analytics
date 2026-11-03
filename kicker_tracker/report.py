"""Readable email-first weekly report. All NFL kickers receive identical treatment."""
from datetime import datetime, timezone
from html import escape
from pathlib import Path
import json

NAVY = "#14263d"
MUTED = "#53657a"
BLUE = "#eaf2fb"
BORDER = "#dfe6ee"


def fmt(value, digits=1):
    return "—" if value is None else f"{float(value):.{digits}f}"


def pct(value):
    return "—" if value is None else f"{float(value)*100:.0f}%"


def _cell(value, head=False, left=False, highlight=False):
    background = "#e9f2fc" if highlight else "#ffffff"
    if head:
        background = NAVY
    style = (
        "padding:9px 10px;border-bottom:1px solid " + BORDER + ";"
        "font-size:12px;vertical-align:top;"
        "text-align:" + ("left" if left else "right") + ";"
        "color:" + ("#ffffff" if head else NAVY) + ";"
        "background:" + background + ";"
    )
    return f'<{"th" if head else "td"} style="{style}">{value}</{"th" if head else "td"}>'


def _table(headers, rows):
    top = "".join(_cell(escape(str(h)), head=True, left=i < 2) for i, h in enumerate(headers))
    body = ""
    for i, values in enumerate(rows):
        body += "<tr>" + "".join(
            _cell(escape(str(value)), left=j < 2, highlight=i % 2 == 1)
            for j, value in enumerate(values)
        ) + "</tr>"
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'style="width:100%;border-collapse:collapse;background:#ffffff;">'
        f"<thead><tr>{top}</tr></thead><tbody>{body}</tbody></table>"
    )


def build_html(rows, metadata):
    season = metadata["season"]
    week = metadata["target_week"]
    cutoff = metadata["as_of"]
    ranked = sorted(
        rows,
        key=lambda r: (
            r.get("projected_points") is not None,
            r.get("projected_points") if r.get("projected_points") is not None else -1,
        ),
        reverse=True,
    )

    def name(row):
        form = row.get("form") or {}
        return form.get("kicker") or "Unverified kicker"

    active = [r for r in ranked if r.get("projected_points") is not None]
    top_rows = [
        (i, name(r), r["team"], "vs " + r["opponent"],
         fmt(r["projected_points"]), fmt((r.get("form") or {}).get("last3_ppg")))
        for i, r in enumerate(active[:10], 1)
    ]

    weather_rows = []
    for r in ranked:
        ctx = r.get("game_context") or {}
        w = ctx.get("weather") or {}
        injuries = ctx.get("team_injuries") or {}
        opp = ctx.get("opponent_injuries") or {}
        all_flags = (w.get("flags") or [])
        injury_flags = (injuries.get("flags") or [])
        opp_flags = (opp.get("flags") or [])
        if all_flags or injury_flags or opp_flags:
            our_msg = ", ".join(
                f'{x.get("position", "?")} {x.get("player", "?")}: {x.get("status", "?")}'
                for x in injury_flags
            ) or "—"
            opp_msg = ", ".join(
                f'{x.get("position", "?")} {x.get("player", "?")}: {x.get("status", "?")}'
                for x in opp_flags
            ) or "—"
            weather_rows.append((
                r["team"], r.get("opponent", "BYE"),
                w.get("summary", "Not available"),
                our_msg,
                opp_msg,
            ))
    all_rows = []
    for i, r in enumerate(ranked, 1):
        form = r.get("form") or {}
        recent = " / ".join(fmt(v["points"], 0) for v in form.get("weekly", [])[-5:]) or "—"
        all_rows.append((
            i, f'{r["team"]} · {name(r)}', r.get("opponent", "BYE"),
            fmt(r.get("projected_points")),
            fmt(r.get("fg_attempts_pg")),
            fmt(r.get("fg_last3_pg")),
            fmt(r.get("opp_fg_allowed_pg")),
            pct(r.get("opp_rz_td_allowed_pct")),
            fmt(form.get("median_ppg")),
            recent,
        ))

    top = _table(("Rank", "Kicker", "Team", "Matchup", "Proj.", "Last 3 PPG"), top_rows)
    context_table = _table(
        ("Team", "Opponent", "Weather", "Team injuries", "Opponent injuries"),
        weather_rows
    ) if weather_rows else "<p>No high-priority weather or reported injuries detected in available data.</p>"
    missing_weather = sum(
        (r.get("game_context") or {}).get("weather", {}).get("status") in
        ("unavailable", "roof_unknown", "venue_unknown")
        for r in ranked if r.get("opponent") != "BYE"
    )
    missing_injuries = sum(
        (r.get("game_context") or {}).get("team_injuries", {}).get("status") == "unavailable"
        for r in ranked if r.get("opponent") != "BYE"
    )
    all_table = _table((
        "#", "Team / kicker", "Opponent", "Proj. pts", "FG/G",
        "Last 3 FG/G", "Opp FG/G allowed", "Opp RZ TD%", "Median PPG", "Last 5 scores"
    ), all_rows)

    # Inline styles are important: Gmail strips or modifies document-level CSS.
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fantasy Kicker Tracker — Week {week}</title></head>
<body style="margin:0;padding:0;background:#f5f7fb;color:{NAVY};font-family:Arial,Helvetica,sans-serif;">
<div style="max-width:1100px;margin:0 auto;padding:18px;">
  <div style="padding:22px;background:{NAVY};color:#fff;border-radius:8px 8px 0 0;">
    <div style="font-size:12px;letter-spacing:1px;">WEEKLY FANTASY REPORT</div>
    <h1 style="margin:8px 0 3px;font-size:24px;color:#fff;">Week {week} · {season} Kicker Rankings</h1>
    <div style="font-size:13px;color:#d0dce9;">All 32 teams · Data cutoff: {escape(str(cutoff))}</div>
  </div>
  <div style="background:#ffffff;padding:22px;">
    <p style="margin-top:0;font-size:14px;line-height:1.6;">
      Every kicker is evaluated equally on recent scoring, field-goal opportunity,
      accuracy and opponent defensive trends. Bye-week kickers have no projected points.
    </p>
    <h2 style="font-size:18px;margin:22px 0 10px;">Top 10 projected this week</h2>
    {top}
    <p style="color:{MUTED};font-size:12px;margin-top:8px;">
      Projections are preliminary statistical estimates, not verified betting-market or injury-adjusted forecasts.
    </p>
    <h2 style="font-size:18px;margin:24px 0 10px;">Weather and injury watchlist</h2>
    <p style="font-size:12px;color:{MUTED};">Conditions are forecasts, not guaranteed game-day weather.
    Injury designations are the latest available at the report cutoff; questionable does not mean out.
    Context is informational and currently does not change the projected points.</p>
    {context_table}
    <p style="font-size:12px;color:{MUTED};">
      Weather unavailable or roof unverified for {missing_weather} teams;
      official injury status unavailable for {missing_injuries} teams.
      An empty watchlist does not establish that every starter is healthy.</p>
    <h2 style="font-size:18px;margin:24px 0 10px;">All 32 teams</h2>
    <p style="font-size:12px;color:{MUTED};line-height:1.5;">
      FG/G = offensive field-goal attempts per game; Opp FG/G allowed = field goals attempted
      by opposing offenses per game. Last 5 scores are chronological (oldest to newest).
    </p>
    <div style="overflow-x:auto;max-width:100%;">{all_table}</div>
    <div style="border-top:1px solid {BORDER};margin-top:24px;padding-top:12px;">
      <p style="font-size:12px;color:{MUTED};line-height:1.5;">
        Fantasy scoring: FG 0–39 yards = 3; 40–49 = 4; 50+ = 5; made XP = 1;
        missed FG = −1. Model uses nflverse play-by-play, with recent FG rates and opposing
        FG attempts allowed. Weather, injuries, verified active kicker status and waiver availability
        are not yet ingested. Rankings are not historically calibrated.
      </p>
      <p style="font-size:12px;color:{MUTED};">
        <a href="https://github.com/MisterEgge/fantasy-kicker-tracker">Project source</a>
        · Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
      </p>
    </div>
  </div>
</div>
</body></html>"""


def save_report(rows, metadata, folder="report"):
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    html = build_html(rows, metadata)
    page = out / f'week_{metadata["target_week"]}_{metadata["season"]}.html'
    page.write_text(html, encoding="utf-8")
    (out / "latest.html").write_text(html, encoding="utf-8")
    (out / "latest.json").write_text(
        json.dumps({"metadata": metadata, "teams": rows}, indent=2, default=str),
        encoding="utf-8",
    )
    return page
