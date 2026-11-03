# Fantasy Kicker Tracker

Automatically analyze **all 32 NFL teams and their kickers** for a ten-team fantasy league. Every kicker receives the same opportunity, recent-form, and matchup analysis; no kicker is used as a special benchmark. The forecast is generated every Wednesday afternoon and displayed directly inside Gmail. Every Tuesday afternoon, a separate job grades the preceding week's **saved pregame predictions** against actual NFL results and emails an accuracy review.

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

## Automated Tuesday review and Wednesday forecast

Both GitHub Actions workflows are scheduled automatically at **3 PM America/Chicago**:

| Day | Workflow | Email |
| --- | --- | --- |
| Tuesday | `.github/workflows/tuesday-model-review.yml` | Grading of last week's predicted versus actual kicker fantasy points and FG attempts for all playing teams |
| Wednesday | `.github/workflows/weekly-kicker-report.yml` | Top 10 projected kickers plus all-32-team report |

You do not need to run either workflow manually after initial setup. Actions schedules can be delayed by GitHub.

### Permanent prediction history

A separate `forecast-history` Git branch preserves dated records:

- `forecasts/<season>/week_<week>.json`: immutable pregame forecasts (created on Wednesdays).
- `reviews/<season>/week_<week>.json`: Tuesday per-team actual-vs-predicted differences and summary error metrics.
- `reviews/<season>/week_<week>.html`: readable Tuesday review email copy.

The Wednesday job will not replace a forecast that was already saved for that week. On reruns it uses the original snapshot for the email; on a manual preview outside Wednesday, no historical forecast is archived. The Tuesday job does not recalculate old forecasts from updated data. When there is no ungraded forecast, it skips the email.

The Tuesday report tracks fantasy-point mean absolute error, prediction bias, FG attempts forecast error, kicker changes, and the largest over/underpredictions. A completed matchup must have play-by-play before it can be evaluated. Reviews are saved for comparison, not just emailed and discarded.

**Guarded model improvement:** The Wednesday model can introduce an automatically calculated *FG-attempt volume* correction only after three completed Tuesday reviews and at least 60 team-games. The proposed factor is trained on earlier weeks and must improve field-goal-attempt error on a held-out later week; adjustments are capped at ±10%. This is deliberately conservative and does **not** automatically rewrite arbitrary model parameters based on a single anomalous game. The review's calibration details are retained in the next forecast's JSON.

The first valid Tuesday backtest requires an archived Wednesday forecast and its following weekend games; before that, there is no reliable prediction-versus-actual history.

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

1. Validate live 2026 nflverse schemas, grading and kickoff schedules on GitHub Actions.
2. Integrate active kicker and injury verification, weather and venue, and implied team totals.
3. Extend the saved prediction history with multiweek trend charts and strict probability calibration.
4. Incorporate league-specific waiver availability to rank **available** kickers rather than all players.
5. Improve fourth-down decision attribution with field position, score and wind.

The code is meant to be extended as these feeds become available; do not treat omitted factors as already implemented.

## Defense / Special Teams (D/ST) tracking

The `defense_tracker/` package adds an independent 32-team defensive analysis, with **Wednesday forecasts** and **Tuesday grading** using saved pregame predictions. It uses the same nflverse data source, email credentials and `forecast-history` branch, but preserves separate D/ST records in `defense-forecasts/` and `defense-reviews/`.

**Provisional D/ST scoring configuration** is in [`defense_scoring.json`](defense_scoring.json). The initial values match ESPN's documented 2026 standard D/ST event scoring: 1/sack, 2/interception, 2/fumble recovered, 2/safety, 2/blocked kick, 6/defensive or return touchdown, plus points-allowed brackets. **These rules are NOT yet confirmed for your league**; replace the JSON to match your league before relying on fantasy-point projections or backtests. Default points-allowed tiers are: 0 points +5; 1–6 +4; 7–13 +3; 14–17 +1; 18–27 0; 28–34 −1; 35–45 −3; 46+ −5. No yardage-allowed scoring is applied.

The defense analysis evaluates sack rates, opponent sacks conceded, turnover creation, opponent turnovers conceded, points allowed, opposing offenses' recent D/ST fantasy points conceded, robust/median and rolling last-3/5 scores, and matchup context. A single pick-six will not become an automatic expectation of future six-point defensive touchdowns. It reports all 32 units and top ten choices, with byes unprojected. Predictions use an **uncalibrated heuristic** until historical audits warrant a correction.

**Known scoring limitation:** The first version estimates D/ST points allowed using the game's *final scoreboard*, which can include opponent defensive or special-teams touchdowns that many fantasy platforms exclude. The report explicitly labels this approximation. Other potential differences include official stat corrections, punt/field-goal blocks, kickoff return edge cases, and platform-specific rules. Validate against your league's actual D/ST totals before treating the backtest as platform-exact.

Locally, after installing requirements:

```bash
python -m defense_tracker.cli --season 2026 --as-of 2026-11-04 --scoring defense_scoring.json
python -m defense_tracker.review --season 2026 --as-of 2026-11-10 --history-dir history-store
```

Once GitHub Actions is activated, `.github/workflows/wednesday-defense-forecast.yml` runs Wednesday **3:20 PM Central**, and `.github/workflows/tuesday-defense-review.yml` runs Tuesday **3:20 PM Central**. Both use the same `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` secrets and email a separate, formatted D/ST report. Tuesday grades only saved Wednesday forecasts against the completed games, including actual sacks, takeaways and fantasy points. If the previous Wednesday forecast is absent, the review skips rather than inventing historical projections.

The initial D/ST learning mechanism uses an automatic bounded correction only after at least 3 backtested weeks and 60 D/ST game observations, with validation on a later held-out week. Corrections are limited to ±1.5 fantasy points and applied only if they improve mean absolute error. Other weights remain unchanged pending more robust evidence.

Data source documentation: [nflverse nflfastR](https://nflfastr.com/reference/field_descriptions.html). Scoring reference: [ESPN standard D/ST settings](https://support.espn.com/hc/en-us/articles/360003914032-Scoring-Formats).
