import argparse
import pandas as pd
from datetime import datetime, timedelta
from .config import Settings, team_code
from .data import load_pbp, load_schedule, select_completed_games
from .analysis import build_team_rows, project
from .calibration import choose_calibration, apply_calibration
from .report import save_report

def run(season, as_of, pbp_file=None, schedule_file=None, output='report', history_dir=None):
    asof=datetime.fromisoformat(as_of).date()
    pbp=select_completed_games(load_pbp(season,pbp_file),as_of)
    if pbp.empty:
        raise ValueError('No completed games before cutoff')
    if pbp.game_date.max().date() < asof-timedelta(days=12):
        raise RuntimeError('NFLverse play-by-play is stale (>12 days): refusing to send ranking')
    schedule=load_schedule(schedule_file)
    future=schedule[(schedule.season.eq(season)) & schedule.game_type.eq('REG') & schedule.gameday.ge(pd.Timestamp(asof))]
    if future.empty:
        raise RuntimeError('No upcoming regular-season games found; do not send stale rankings')
    target_week=int(future.week.min())
    opponent={}
    for _,m in future[future.week.eq(target_week)].iterrows():
        h,a=team_code(m.home_team),team_code(m.away_team)
        opponent[h]=a
        opponent[a]=h
    base=build_team_rows(pbp)
    index={r['team']:r for r in base}
    if len(index)!=32:
        raise RuntimeError(f'Expected all 32 teams, received {len(index)}; refusing incomplete report')
    settings=Settings()
    calibration=(choose_calibration(history_dir, season, target_week) if history_dir else
                 {"volume_factor": 1.0, "method": "no_history_available",
                  "review_weeks": 0, "graded_team_games": 0,
                  "reason": "Historical weekly reviews not supplied"})
    for r in base:
        opp=opponent.get(r['team'])
        r['opponent']=opp or 'BYE'
        result=project(r,index[opp],settings) if opp in index else None
        r.update(result or {'projected_fg_attempts':None,'projected_xp':None,'projected_points':None})
        apply_calibration(r, calibration)
        r['opp_fg_allowed_pg']=index[opp]['fg_allowed_pg'] if opp in index else None
        r['opp_rz_td_allowed_pct']=index[opp]['rz_td_allowed_pct'] if opp in index else None
    metadata={'season':season,'target_week':target_week,'as_of':as_of,'model_calibration':calibration,'data_max_game_date':str(pbp.game_date.max().date()),'data_origin':'nflverse play by play'}
    p=save_report(base,metadata,output)
    print(f'Wrote {p} (week {target_week}, {len(base)} teams)')
    return p

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--season',type=int,default=datetime.now().year)
    parser.add_argument('--as-of',default=datetime.now().strftime('%Y-%m-%d'))
    parser.add_argument('--pbp',default=None)
    parser.add_argument('--schedule',default=None)
    parser.add_argument('--output',default='report')
    parser.add_argument('--history-dir',default=None)
    args=parser.parse_args()
    run(args.season,args.as_of,args.pbp,args.schedule,args.output,args.history_dir)

if __name__=='__main__':
    main()
