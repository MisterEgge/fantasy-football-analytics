"""HTML email presentation shared by Wednesday forecasts and Tuesday audits."""
from html import escape
from pathlib import Path
import json

STYLE='font-family:Arial,Helvetica,sans-serif;color:#172638;font-size:13px;line-height:1.5'
TH='padding:8px;background:#14263d;color:#fff;text-align:left;font-size:12px'
TD='padding:8px;border-bottom:1px solid #e0e7ef;text-align:left;font-size:12px'

def table(headers, rows):
    header=''.join(f'<th style="{TH}">{escape(str(v))}</th>' for v in headers)
    body=''.join('<tr>'+''.join(f'<td style="{TD}">{escape(str(x))}</td>' for x in row)+'</tr>' for row in rows)
    return f'<table cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse"><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>'

def wrapper(title, body, note):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{escape(title)}</title></head>
<body style="background:#f5f7fb;margin:0;padding:14px"><div style="max-width:1000px;margin:auto;background:white;padding:20px;{STYLE}">
<header style="padding:18px;background:#14263d;color:#fff"><div style="font-size:11px;color:#bdcee0">FANTASY DEFENSE ANALYSIS</div>
<h1 style="font-size:22px;color:#fff;margin:5px 0">{escape(title)}</h1></header>
{body}<p style="font-size:12px;color:#54657a;border-top:1px solid #dfe6ee;padding-top:10px">{escape(note)}</p></div></body></html>'''

def forecast_html(payload):
    meta=payload["metadata"]
    rows=sorted(payload["teams"],key=lambda r:(
        r.get("projected_points") is not None, r.get("projected_points") or -999),reverse=True)
    top=[(i+1,r["team"],r["opponent"],r["projected_points"],r["last3_ppg"],
          r["sacks_last3"],r["takeaways_last3"]) for i,r in enumerate(
              [v for v in rows if v.get("projected_points") is not None][:10])]
    all_rows=[(i+1,r["team"],r["opponent"],(r.get("game_context") or {}).get("weather",{}).get("summary","Unknown"),r.get("projected_points","BYE"),
               r["last3_ppg"],r["median_ppg"],r["sacks_last3"],
               r["takeaways_last3"],r["dst_points_allowed_last3"],
               " / ".join(str(v) for v in r["recent_weekly_points"])) for i,r in enumerate(rows)]
    watch=[]
    for r in rows:
        context=r.get("game_context") or {}
        weather=context.get("weather") or {}
        opponent=context.get("opponent_injuries") or {}
        own=context.get("team_injuries") or {}
        if not (weather.get("flags") or opponent.get("flags") or own.get("flags")):
            continue
        injury_text=lambda flags: "; ".join(
            str(p.get("position","?"))+" "+str(p.get("player","?"))+": "+str(p.get("status","?"))
            for p in flags
        ) or "—"
        watch.append((
            r["team"],r["opponent"],weather.get("summary","—"),
            injury_text(opponent.get("flags",[])),injury_text(own.get("flags",[]))
        ))
    context_html=table(("D/ST","Opponent","Weather","Opponent key injuries","Team key injuries"),watch) if watch else "<p>No major weather or qualifying injury designations found in current data.</p>"
    body=('<h2 style="font-size:17px">Top 10 predicted D/ST units</h2>'+
          table(("Rank","Defense","Opponent","Projected","Last 3 PPG","Sacks/G","Takeaways/G"),top)+
          '<h2 style="font-size:17px;margin-top:25px">Weather and injuries to monitor</h2>'+
          '<p>Pregame forecasts and official injury flags are displayed but do not automatically change predicted fantasy points. Check again near kickoff.</p>'+
          context_html+
          '<h2 style="font-size:17px;margin-top:25px">All 32 NFL defenses</h2>'+
          table(("#","D/ST","Opponent","Weather","Projected","Last 3 PPG","Median PPG","Sacks last 3",
                 "Takeaways last 3","Opponent D/ST pts conceded last 3","Last 5 weekly scores"),all_rows)+
          '<p>Outlier-resistant recent form and opposing offense D/ST points conceded are evaluated together. '
          'Bye teams have no projection.</p>')
    return wrapper(f'{meta["season"]} Week {meta["target_week"]} — Defense Rankings',body,
                   f'Cutoff {meta["as_of"]}. Provisional ESPN-like D/ST scoring. '
                   'Points-allowed values use final game scoreboard as an approximation; this can differ from '
                   'fantasy platform definitions. Weather and injuries shown as watchlist context, not yet numerical adjustments.')

def review_html(payload):
    m=payload["metadata"]
    s=payload["summary"]
    rows=payload["teams"]
    errors=sorted(rows,key=lambda r:abs(r["error"]),reverse=True)
    body=(f'<h2 style="font-size:17px">Prediction accuracy</h2><p>'
          f'{s["teams"]} defenses graded; fantasy points MAE: <b>{s["mae"]:.2f}</b>; '
          f'prediction bias: <b>{s["bias"]:+.2f}</b>. '
          f'Sack MAE: {s["sack_mae"]:.2f}; takeaway MAE: {s["takeaway_mae"]:.2f}.</p>'+
          '<h2 style="font-size:17px">Largest misses</h2>'+
          table(("Defense","Opponent","Forecast","Actual","Error","Pred sacks","Actual sacks","Pred TO","Actual TO"),[
              (r["team"],r["opponent"],r["predicted_points"],r["actual_points"],r["error"],
               r["projected_sacks"],r["actual_sacks"],r["projected_takeaways"],r["actual_takeaways"])
               for r in errors[:8]])+
          '<h2 style="font-size:17px">Full week audit</h2>'+
          table(("Team","Opponent","Forecast","Actual","Error","Error category"),[
              (r["team"],r["opponent"],r["predicted_points"],r["actual_points"],
               r["error"],r["diagnostic"]) for r in rows])+
          '<p>Review any consistent sack, turnover, or scoring-environment bias across multiple weeks. '
          'Do not change a formula based on one anomalous defensive TD.</p>')
    return wrapper(f'{m["season"]} Week {m["week"]} — Defense Forecast Review',body,
                   'Audit against Wednesday immutable pregame predictions; actual scoring uses provisional rules and scoreboard points allowed.')

def save(payload, output, kind):
    out=Path(output)
    out.mkdir(parents=True,exist_ok=True)
    m=payload["metadata"]
    week=int(m.get("target_week",m.get("week")))
    html=forecast_html(payload) if kind=="forecast" else review_html(payload)
    filename=f'week_{week:02d}_{int(m["season"])}.html'
    (out/filename).write_text(html,encoding="utf-8")
    (out/"latest.html").write_text(html,encoding="utf-8")
    (out/"latest.json").write_text(json.dumps(payload,indent=2,default=str),encoding="utf-8")
    return out/"latest.html"
