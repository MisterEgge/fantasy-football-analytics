from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    owned_team: str = "CIN"
    min_swap_edge: float = 2.0
    outlier_cap: float = 2.5
    recent_weight: float = 0.65
    distance_priors: tuple[float, float, float] = (0.94, 0.82, 0.67)
    missed_fg_penalty: int = -1

TEAMS = {
    "ARI":"Arizona Cardinals", "ATL":"Atlanta Falcons", "BAL":"Baltimore Ravens",
    "BUF":"Buffalo Bills", "CAR":"Carolina Panthers", "CHI":"Chicago Bears",
    "CIN":"Cincinnati Bengals", "CLE":"Cleveland Browns", "DAL":"Dallas Cowboys",
    "DEN":"Denver Broncos", "DET":"Detroit Lions", "GB":"Green Bay Packers",
    "HOU":"Houston Texans", "IND":"Indianapolis Colts", "JAX":"Jacksonville Jaguars",
    "KC":"Kansas City Chiefs", "LA":"Los Angeles Rams", "LAC":"Los Angeles Chargers",
    "LV":"Las Vegas Raiders", "MIA":"Miami Dolphins", "MIN":"Minnesota Vikings",
    "NE":"New England Patriots", "NO":"New Orleans Saints", "NYG":"New York Giants",
    "NYJ":"New York Jets", "PHI":"Philadelphia Eagles", "PIT":"Pittsburgh Steelers",
    "SEA":"Seattle Seahawks", "SF":"San Francisco 49ers", "TB":"Tampa Bay Buccaneers",
    "TEN":"Tennessee Titans", "WAS":"Washington Commanders"
}
ALIASES = {"STL":"LA", "SD":"LAC", "OAK":"LV", "JAC":"JAX", "WSH":"WAS"}
def team_code(code):
    return ALIASES.get(str(code), str(code))
