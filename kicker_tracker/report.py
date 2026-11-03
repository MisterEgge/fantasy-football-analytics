"""Self-contained mobile-friendly HTML report."""
from html import escape
from datetime import datetime
from pathlib import Path
import json

CSS='''body{font:15px/1.55 system-ui,Arial,sans-serif;max-width:1150px;margin:auto;padding:25px;color:#172033;background:#f6f8fb}h1{font-size:28px}h2{margin-top:34px}p{max-width:900px}.note{background:#fff3cd;padding:12px;border-left:4px solid #d79b00}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;background:white}th,td{padding:8px 10px;border-bottom:1px solid #e4e9f0;text-align:right;white-space:nowrap}th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}thead{background:#eaf0f7}.owned{background:#e6f5ef}.pos{color:#166534;font-weight:700}.neg{color:#991b1b;font-weight:700}small{color:#546173}a{color:#175e9b}'''

def fmt(v, digits=1):
    return 'N/A' if v is None else f'{v:.{digits}f}'

def build_html(rows, metadata):
    season=metadata['season']
    week=metadata['target_week']
    asof=metadata['as_of']
    owned=metadata.get('owned_team','CIN')
    arr=list(rows)
    arr.sort(key=lambda r:(r.get('projected_points') is not None, r.get('projected_points') if r.get('projected_points') is not None else -1),reverse=True)
    base=next((r.get('projected_points') for r in arr if r['team']==owned),None)
    lines=[]
    for idx,r in enumerate(arr,1):
        f=r.get('form') or {}
        diff=r['projected_points']-base if base is not None and r.get('projected_points') is not None else None
        cls='owned' if r['team']==owned else ''
        recent=', '.join(str(int(v['points'])) for v in f.get('weekly',[])[-5:])
        line=(f'<tr class="{cls}"><td>{idx}</td>'
              f'<td>{escape(r["team"])} — {escape(str(f.get("kicker","unknown")))}</td>'
              f'<td>{escape(str(r.get("opponent","BYE")))}</td>'
              f'<td>{fmt(r.get("projected_points"))}</td>'
              f'<td class="{"pos" if diff is not None and diff>=2 else "neg" if diff is not None and diff<=-2 else ""}">'
              f'{"N/A" if diff is None else f"{diff:+.1f}"}</td>'
              f'<td>{fmt(r["fg_attempts_pg"])}</td><td>{fmt(r["fg_last3_pg"])}</td>'
              f'<td>{fmt(r.get("opp_fg_allowed_pg"))}</td>'
              f'<td>{fmt(r["opp_rz_td_allowed_pct"]*100) if r.get("opp_rz_td_allowed_pct") is not None else "N/A"}%</td>'
              f'<td>{fmt(f.get("median_ppg"))}</td><td>{fmt(f.get("last3_ppg"))}</td>'
              f'<td>{escape(recent)}</td></tr>')
        lines.append(line)
    intro=f'Generated {escape(datetime.now().strftime("%Y-%m-%d %H:%M"))}. Completed games only before {escape(asof)}. Next target week: {week}.'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fantasy Kicker Tracker — Week {week}</title><style>{CSS}</style></head><body><h1>Fantasy Kicker Tracker — {season} Week {week}</h1><p>{intro}</p><p class="note"><b>Model status:</b> Heuristic projection, not a validated probability model. Opponent / offensive FG attempt rates are observed; forecast points and swap edges are estimates. Injuries, weather, betting markets and actual league ownership are <b>not included</b>. Confirm the kicker is active before a waiver move.</p><h2>All 32 teams versus your Cincinnati baseline</h2><p>Consider swapping only for a projected edge of at least +2 points. Scoring: 3/4/5 per made FG by distance, +1 made XP, −1 missed FG.</p><div class="table-wrap"><table><thead><tr><th>Rank</th><th>Team / kicker</th><th>Opponent</th><th>Projected pts</th><th>vs CIN</th><th>FG/game</th><th>Last 3 FG/game</th><th>Opp FG allowed/game</th><th>Opp RZ TD%</th><th>Median pts</th><th>Last 3 pts/game</th><th>Last 5 weekly pts</th></tr></thead><tbody>{''.join(lines)}</tbody></table></div><h2>Method</h2><p>Expected field-goal attempts blend season and recent offense attempt rates with the opponent defense's season and recent conceded attempts, with a bounded red-zone adjustment. Field-goal accuracy by distance uses shrinkage priors. Extra-point projection uses season and recent makes. This is an initial heuristic: no valid historical prediction backtest exists yet.</p><p>All teams including bye weeks are present; a bye produces no startable projection. Confirm real injury and depth-chart status before adding a player.</p><p><small>Data: <a href="https://github.com/nflverse/nflverse-data">nflverse play-by-play</a>. See README for limitations.</small></p></body></html>'''

def save_report(rows, metadata, folder='report'):
    out=Path(folder)
    out.mkdir(parents=True,exist_ok=True)
    page=out/f'week_{metadata["target_week"]}_{metadata["season"]}.html'
    page.write_text(build_html(rows,metadata),encoding='utf-8')
    (out/'latest.html').write_text(page.read_text(encoding='utf-8'),encoding='utf-8')
    (out/'latest.json').write_text(json.dumps({'metadata':metadata,'teams':rows},indent=2,default=str),encoding='utf-8')
    return page
