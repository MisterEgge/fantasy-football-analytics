# Fantasy Kicker Tracker

Automatically analyze **all 32 NFL teams and their active kickers** for a ten-team fantasy league, comparing potential streamers against **Evan McPherson (Cincinnati)**. The report is generated every Wednesday afternoon and emailed when SMTP secrets are configured.

## Scoring and analysis

- Made FG: 0–39 yards **+3**, 40–49 yards **+4**, 50+ yards **+5**
- Made extra point **+1**, missed field goal **−1** (provisional league assumption), missed extra point **0**
- Track attempts/game and last 3/5 games for offense, kicker and opponent defense.
- Track red-zone opportunities, red-zone TD% on both sides, and fourth-down go-for-it attempts within *approximate* realistic field-goal range.
- Track fantasy points by week, median, last 3/5 average, percent below five points, percent ten-plus, peak-game share and an outlier-resistant mean.
- Project field-goal attempts by blending a team's attempt rate with opposing defense's conceded attempt rate. Estimate fantasy points with distance-based accuracy shrinkage and expected extra points.
- Compare estimated future points to McPherson; a proposed streamer must show roughly a **+2 point projected advantage** to justify moving.

**Caution:** Projections are uncalibrated heuristics, not guaranteed values. The repository does not yet ingest injuries, weather, sportsbook lines, confirmed NFL depth charts or your league's actual waiver availability. The fourth-down statistic measures observed fourth-down tries in plausible FG range, not a count of field goals that definitely would have been attempted. It does not claim a validated historical backtest. Always confirm a kicker is active.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
python -m kicker_tracker.cli --season 2026 --as-of 2026-11-04
```

Outputs are `report/latest.html`, `report/latest.json`, and a dated `week_<week>_<season>.html` file. PBP is downloaded from [nflverse-data](https://github.com/nflverse/nflverse-data) and schedules from [nflverse nfldata](https://github.com/nflverse/nfldata). These are community-maintained datasets, not an official NFL feed. To use downloaded files, pass `--pbp /path/to/file.parquet --schedule /path/to/games.csv`.

The report fails closed on stale input (last completed game more than 12 days before report day), missing data, or incomplete 32-team season coverage. On a local rerun, remove cached `data/` files to refresh. GitHub Actions runners use a fresh checkout.

## Wednesday 3 PM Central delivery

`.github/workflows/weekly-kicker-report.yml` contains two Wednesday cron expressions for daylight-saving time and a Central-time guard. Note GitHub Actions schedules may be delayed or occasionally skipped due to platform load.

In the GitHub repository, add the following **Actions repository secrets** under **Settings → Secrets and variables → Actions**:

| Secret | Value |
| --- | --- |
| `EMAIL_TO` | Recipient email address |
| `EMAIL_FROM` | Approved sender address |
| `SMTP_HOST` | SMTP server hostname |
| `SMTP_PORT` | Usually `587` |
| `SMTP_USERNAME` | SMTP account or app-specific username |
| `SMTP_PASSWORD` | App password / SMTP credential |

Never commit email credentials. After configuring secrets, go to **Actions → Weekly fantasy kicker report → Run workflow** to verify the live nflverse download, report output and SMTP delivery. If no secrets are configured, artifact generation can still run but the email step fails explicitly.

## Next development priorities

1. Validate live 2026 nflverse schemas and kickoff schedules on GitHub Actions.
2. Integrate active kicker and injury verification, weather and venue, and implied team totals.
3. Persist dated forecasts for genuine prediction-versus-actual backtesting and weekly rank changes.
4. Incorporate league-specific waiver availability to rank **available** kickers rather than all players.
5. Improve fourth-down decision attribution with field position, score and wind.

The code is meant to be extended as these feeds become available; do not treat omitted factors as already implemented.
