# Fantasy Kicker Tracker

Automatically analyze **all 32 NFL teams and their kickers** for a ten-team fantasy league. Every kicker receives the same opportunity, recent-form, and matchup analysis; no kicker is used as a special benchmark. The report is generated every Wednesday afternoon and displayed directly inside the email when Gmail secrets are configured.

## Scoring and analysis

- Made FG: 0–39 yards **+3**, 40–49 yards **+4**, 50+ yards **+5**
- Made extra point **+1**, missed field goal **−1** (provisional league assumption), missed extra point **0**
- Track attempts/game and last 3/5 games for offense, kicker and opponent defense.
- Track red-zone opportunities, red-zone TD% on both sides, and fourth-down go-for-it attempts within *approximate* realistic field-goal range.
- Track fantasy points by week, median, last 3/5 average, percent below five points, percent ten-plus, peak-game share and an outlier-resistant mean.
- Project field-goal attempts by blending a team's attempt rate with opposing defense's conceded attempt rate. Estimate fantasy points with distance-based accuracy shrinkage and expected extra points.
- Rank all 32 teams by projected fantasy points, with a top-10 summary and full 32-team table. Actual league free-agent availability is not currently known.

**Caution:** Projections are uncalibrated heuristics, not guaranteed values. The repository does not yet ingest injuries, weather, sportsbook lines, confirmed NFL depth charts or your league's actual waiver availability. The fourth-down statistic measures observed fourth-down tries in plausible FG range, not a count of field goals that definitely would have been attempted. It does not claim a validated historical backtest. Always confirm a kicker is active.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
python -m kicker_tracker.cli --season 2026 --as-of 2026-11-04
```

Outputs are `report/latest.html`, `report/latest.json`, and a dated `week_<week>_<season>.html` file. The HTML is an archival browser report; the scheduled email embeds this same formatted report **directly in Gmail**, so recipients do not need to open an HTML attachment. For local viewing, double-click the `.html` file or open it in a web browser. PBP is downloaded from [nflverse-data](https://github.com/nflverse/nflverse-data) and schedules from [nflverse nfldata](https://github.com/nflverse/nfldata). These are community-maintained datasets, not an official NFL feed. To use downloaded files, pass `--pbp /path/to/file.parquet --schedule /path/to/games.csv`.

The report fails closed on stale input (last completed game more than 12 days before report day), missing data, or incomplete 32-team season coverage. On a local rerun, remove cached `data/` files to refresh. GitHub Actions runners use a fresh checkout.

## Wednesday 3 PM Central delivery

`.github/workflows/weekly-kicker-report.yml` contains two Wednesday cron expressions for daylight-saving time and a Central-time guard. Note GitHub Actions schedules may be delayed or occasionally skipped due to platform load.

To email the report from Gmail to **that same Gmail inbox**, add just **two** GitHub Actions repository secrets at [Settings → Secrets and variables → Actions](https://github.com/MisterEgge/fantasy-kicker-tracker/settings/secrets/actions):

| Secret | Value |
| --- | --- |
| `GMAIL_ADDRESS` | Your full Gmail address (both sender and recipient) |
| `GMAIL_APP_PASSWORD` | A dedicated 16-character Google app password; **not** your normal Google password |

Gmail's SMTP server is hardcoded as `smtp.gmail.com` on port `587` using STARTTLS. You do **not** configure SMTP hostname, port, sender or recipient separately. The code uses Python's standard-library `smtplib`, so no email package is required.

To obtain an app password:

1. Turn on [Google 2-Step Verification](https://myaccount.google.com/security) if it isn't already enabled.
2. Visit [Google App Passwords](https://myaccount.google.com/apppasswords), create a password named `Fantasy Kicker Tracker`, and copy the 16-character value.
3. Save it **only** under `GMAIL_APP_PASSWORD` in GitHub Actions secrets. Do not paste it into code, issues, or chat.
4. Save your Gmail address under `GMAIL_ADDRESS`.
5. Choose [Actions → Weekly fantasy kicker report](https://github.com/MisterEgge/fantasy-kicker-tracker/actions) → **Run workflow** to validate data ingestion and email.

If App Passwords is unavailable on your account (for example, certain organization policies or Advanced Protection), this delivery method will not work; an OAuth-based provider or email API would be needed instead. Google generally recommends OAuth where supported, but an app password is a practical option for this personal scheduled script.

The report is uploaded as a workflow artifact before the email step. The email contains a styled HTML body (with a plain-text fallback), not a downloadable HTML attachment. If secrets are missing, the email step fails explicitly; it will not report that an email was sent.

## Next development priorities

1. Validate live 2026 nflverse schemas and kickoff schedules on GitHub Actions.
2. Integrate active kicker and injury verification, weather and venue, and implied team totals.
3. Persist dated forecasts for genuine prediction-versus-actual backtesting and weekly rank changes.
4. Incorporate league-specific waiver availability to rank **available** kickers rather than all players.
5. Improve fourth-down decision attribution with field position, score and wind.

The code is meant to be extended as these feeds become available; do not treat omitted factors as already implemented.
