"""NFLverse PBP ingestion; fail closed on absent or malformed inputs."""
from pathlib import Path
import os
import pandas as pd
import requests

PBP_URL = 'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet'
SCHEDULE_URL = 'https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv'
REQUIRED = {
    'game_id','season','week','season_type','posteam','defteam','play_type',
    'field_goal_attempt','field_goal_result','kick_distance','extra_point_attempt',
    'extra_point_result','yardline_100','down','drive','kicker_player_name','game_date'
}

def download(url: str, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    res = requests.get(url, timeout=120, headers={'User-Agent':'fantasy-kicker-tracker/1.0'})
    res.raise_for_status()
    if len(res.content) < 1000:
        raise ValueError(f'Download unexpectedly small: {url}')
    target.write_bytes(res.content)
    return target

def load_pbp(season:int, path: str | None = None) -> pd.DataFrame:
    p = Path(path) if path else Path('data') / f'play_by_play_{season}.parquet'
    if not p.exists():
        download(PBP_URL.format(season=season), p)
    df = pd.read_parquet(p)
    missing = REQUIRED - set(df)
    if missing:
        raise ValueError(f'PBP schema missing required columns: {sorted(missing)}')
    df = df[(df.season.eq(season)) & (df.season_type.eq('REG'))].copy()
    df['game_date'] = pd.to_datetime(df['game_date'], errors='coerce')
    if df.empty or df['game_date'].isna().all():
        raise ValueError('No dated regular-season play-by-play found')
    return df

def load_schedule(path: str | None = None) -> pd.DataFrame:
    p = Path(path) if path else Path('data/games.csv')
    if not p.exists():
        download(os.getenv('SCHEDULE_URL', SCHEDULE_URL), p)
    df = pd.read_csv(p)
    required = {'season','week','game_type','home_team','away_team','gameday'}
    if required-set(df):
        raise ValueError(f'Schedule schema mismatch: {sorted(required-set(df))}')
    df['gameday'] = pd.to_datetime(df.gameday, errors='coerce')
    return df

def select_completed_games(pbp:pd.DataFrame, as_of:str) -> pd.DataFrame:
    """Date cutoff excludes same-day live games; run Wednesday after completed week."""
    cutoff = pd.Timestamp(as_of).normalize()
    return pbp[pbp.game_date.lt(cutoff)].copy()
