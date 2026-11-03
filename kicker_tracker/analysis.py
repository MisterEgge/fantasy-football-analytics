"""Team-wide field-goal opportunity and empirically shrunk fantasy projections."""
import numpy as np
import pandas as pd
from .config import TEAMS, Settings, team_code

def to_num(s):
    return pd.to_numeric(s, errors='coerce')

def points_for_attempt(distance, made, penalty=-1):
    if not made:
        return penalty
    return 5 if distance >= 50 else 4 if distance >= 40 else 3

def robust_mean(values, cap=2.5):
    a = np.asarray(list(values), dtype=float)
    a = a[np.isfinite(a)]
    if not len(a):
        return 0.0
    if len(a) < 4:
        return float(a.mean())
    median = np.median(a)
    mad = np.median(np.abs(a-median))
    scale = max(1.4826 * mad, 2.0)
    return float(np.clip(a, median-cap*scale, median+cap*scale).mean())

def _attempts(pbp):
    fg = pbp[to_num(pbp.field_goal_attempt).eq(1)].copy()
    fg['distance'] = to_num(fg.kick_distance)
    fg['made'] = fg.field_goal_result.astype(str).str.lower().eq('made')
    fg['tier'] = np.select([fg.distance.ge(50),fg.distance.ge(40)], ['50+','40-49'], default='0-39')
    fg['points'] = [points_for_attempt(d if pd.notna(d) else 0, made) for d,made in zip(fg.distance,fg.made)]
    fg['kicker'] = fg.kicker_player_name.fillna('Unknown kicker')
    return fg

def _xp(pbp):
    x = pbp[to_num(pbp.extra_point_attempt).eq(1)].copy()
    x['made'] = x.extra_point_result.astype(str).str.lower().eq('good')
    x['made'] |= x.extra_point_result.astype(str).str.lower().eq('made')
    x['kicker'] = x.kicker_player_name.fillna('Unknown kicker')
    return x

def team_week_games(pbp):
    games = pbp[['game_id','week','posteam','defteam']].dropna(subset=['game_id','week'])
    g1 = games[['game_id','week','posteam']].rename(columns={'posteam':'team'})
    g2 = games[['game_id','week','defteam']].rename(columns={'defteam':'team'})
    g = pd.concat([g1,g2]).dropna(subset=['team']).drop_duplicates()
    g['team'] = g.team.map(team_code)
    return g[g.team.isin(TEAMS)]

def _rz_drives(pbp):
    """Each offensive drive crossing opponent's 20 counted once."""
    p=pbp[pbp.posteam.notna() & pbp.drive.notna()].copy()
    p['yardline'] = to_num(p.yardline_100)
    p=p[p.posteam.map(team_code).isin(TEAMS)]
    p['posteam']=p.posteam.map(team_code)
    p['defteam']=p.defteam.map(team_code)
    p['rz']=p.yardline.le(20)
    td=to_num(p['touchdown']) if 'touchdown' in p else pd.Series(0,index=p.index)
    turnover=to_num(p['interception']) if 'interception' in p else pd.Series(0,index=p.index)
    lost=to_num(p['fumble_lost']) if 'fumble_lost' in p else pd.Series(0,index=p.index)
    p['off_td']=td.eq(1) & turnover.ne(1) & lost.ne(1) & p.play_type.isin(['pass','run'])
    drive=p.groupby(['game_id','drive','posteam','defteam','week'],dropna=False).agg(
        rz=('rz','max'), td=('off_td','max')).reset_index()
    return drive[drive.rz]

def _go_for_it(pbp):
    """Fourth-down run/pass attempts in plausible field-goal range (not assumed foregone kicks)."""
    p=pbp[to_num(pbp.down).eq(4) & to_num(pbp.yardline_100).between(8,38)].copy()
    p=p[p.play_type.isin(['pass','run'])]
    if 'qb_kneel' in p:
        p=p[to_num(p.qb_kneel).ne(1)]
    return p.groupby('posteam').size().to_dict()

def _averages_by_team(games, events, col='posteam'):
    game_counts=games.groupby('team').game_id.nunique()
    by=events.copy()
    by['team']=by[col].map(team_code)
    n=by.groupby('team').size()
    return {t:float(n.get(t,0)/max(game_counts.get(t,1),1)) for t in TEAMS}

def _last_n_rate(games, events, team, n=3, col='posteam'):
    weeks=games[games.team.eq(team)].sort_values('week').tail(n)
    if weeks.empty:
        return 0.0
    e=events[events[col].map(team_code).eq(team)]
    return float(e.game_id.isin(weeks.game_id).sum()/len(weeks))

def _kicker_form(fg,xp,games,team,settings):
    """Select most recently active kicker; injury status must be independently verified."""
    f=fg[fg.posteam.map(team_code).eq(team)]
    x=xp[xp.posteam.map(team_code).eq(team)]
    if f.empty and x.empty:
        return None
    all_ev=pd.concat([f[['game_id','week','kicker']],x[['game_id','week','kicker']]])
    kicker=all_ev.sort_values('week').iloc[-1].kicker
    f=f[f.kicker.eq(kicker)]
    x=x[x.kicker.eq(kicker)]
    w=games[games.team.eq(team)].sort_values('week').drop_duplicates('game_id')
    rows=[]
    for _,g in w.iterrows():
        ff=f[f.game_id.eq(g.game_id)]
        xx=x[x.game_id.eq(g.game_id)]
        rows.append({'week':int(g.week),'points':float(ff.points.sum()+xx.made.sum()),
                     'attempts':int(len(ff)),'fg_made':int(ff.made.sum()),
                     'xp_made':int(xx.made.sum())})
    if not rows:
        return None
    points=[r['points'] for r in rows]
    made=f[f.made]
    buckets={b:int((made.tier==b).sum()) for b in ('0-39','40-49','50+')}
    attempts={b:int((f.tier==b).sum()) for b in buckets}
    recent=points[-3:]
    last5=points[-5:]
    return {'kicker':kicker,'weekly':rows,'season_points':sum(points),
      'season_ppg':float(np.mean(points)), 'last3_ppg':float(np.mean(recent)),
      'last5_ppg':float(np.mean(last5)), 'median_ppg':float(np.median(points)),
      'robust_ppg':robust_mean(points,settings.outlier_cap),
      'low_rate':float(np.mean(np.asarray(points)<5)),
      'high_rate':float(np.mean(np.asarray(points)>=10)),
      'peak_share':max(points)/sum(points) if sum(points)>0 else 0,
      'fg_made':int(f.made.sum()), 'fg_attempts':int(len(f)),
      'xp_made':int(x.made.sum()),'fg_buckets_made':buckets,'fg_buckets_attempts':attempts}

def build_team_rows(pbp, settings=Settings()):
    games=team_week_games(pbp)
    fg=_attempts(pbp)
    xp=_xp(pbp)
    rz=_rz_drives(pbp)
    go=_go_for_it(pbp)
    off_fg=_averages_by_team(games,fg)
    def_fg=_averages_by_team(games,fg,'defteam')
    off_rz=_averages_by_team(games,rz)
    def_rz=_averages_by_team(games,rz,'defteam')
    rows=[]
    for team in TEAMS:
        team_games=games[games.team.eq(team)]
        if team_games.empty:
            continue
        rz_o=rz[rz.posteam.eq(team)]
        rz_d=rz[rz.defteam.eq(team)]
        form=_kicker_form(fg,xp,games,team,settings)
        rows.append({'team':team,'team_name':TEAMS[team], 'games':len(team_games),
           'fg_attempts_pg':off_fg[team], 'fg_last3_pg':_last_n_rate(games,fg,team,3),
           'fg_last5_pg':_last_n_rate(games,fg,team,5),
           'fg_allowed_pg':def_fg[team],
           'fg_allowed_last3_pg':_last_n_rate(games,fg,team,3,'defteam'),
           'rz_trips_pg':off_rz[team], 'rz_td_pct':float(rz_o.td.mean()) if len(rz_o) else None,
           'rz_allowed_pg':def_rz[team], 'rz_td_allowed_pct':float(rz_d.td.mean()) if len(rz_d) else None,
           'go_fg_range_pg':go.get(team,0)/len(team_games),
           'form':form})
    return rows

def project(team_row, opponent, settings=Settings()):
    """Transparent baseline; not yet calibrated by historical backtesting."""
    f=team_row['form']
    if not f:
        return None
    own=.35*team_row['fg_attempts_pg']+.65*team_row['fg_last3_pg']
    opp=.4*opponent['fg_allowed_pg']+.6*opponent['fg_allowed_last3_pg']
    fga=max(.1,.6*own+.4*opp)
    rz_denied=1-(opponent['rz_td_allowed_pct'] if opponent['rz_td_allowed_pct'] is not None else .55)
    rz_factor=1+.12*max(-.25,min(.25,rz_denied-.45))
    fga*=rz_factor
    counts=f['fg_buckets_attempts']
    total=sum(counts.values())
    priors=(.50,.30,.20)
    weights=[(counts[b]+8*prior)/(total+8) for b,prior in zip(('0-39','40-49','50+'),priors)]
    made=f['fg_buckets_made']
    probs=[(made[b]+20*prior)/(counts[b]+20) for b,prior in zip(('0-39','40-49','50+'),settings.distance_priors)]
    exp_fg=fga*sum(w*(p*v+(1-p)*settings.missed_fg_penalty) for w,p,v in zip(weights,probs,(3,4,5)))
    xp_pg=.45*f['xp_made']/max(team_row['games'],1)+.55*sum(r['xp_made'] for r in f['weekly'][-3:])/max(len(f['weekly'][-3:]),1)
    expected=exp_fg+xp_pg
    return {'projected_fg_attempts':round(fga,2),'projected_xp':round(xp_pg,2),
            'projected_points':round(expected,2),'source':'transparent heuristic (uncalibrated)'}
