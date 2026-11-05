# Automation operations — Fantasy Football Analytics

**Single source of truth:** GitHub Actions in [MisterEgge/fantasy-football-analytics](https://github.com/MisterEgge/fantasy-football-analytics/actions). ChatGPT must not independently schedule or email NFL/fantasy reports; this avoids duplicate/split delivery. All times below are **America/Chicago**. GitHub cron expressions run in UTC and jobs can be delayed or dropped.

## Five recurring production workflows

| Day / intended time (Central) | Workflow file | Output / email behavior |
| --- | --- | --- |
| Tuesday 3:00 PM | [Tuesday kicker model review](.github/workflows/tuesday-model-review.yml) | Compare immutable Wednesday kicker projections with actual scoring/field-goal opportunities. Archive in `forecast-history/reviews/`; email **only when a new review is produced**. |
| Tuesday 3:20 PM | [Tuesday defense review](.github/workflows/tuesday-defense-review.yml) | Grade D/ST projections, sacks and takeaways. Archive in `forecast-history/defense-reviews/`; email **only when a new review is produced**. |
| Wednesday 3:00 PM | [Wednesday kicker forecasts](.github/workflows/weekly-kicker-report.yml) | Rank all 32 NFL teams' kickers, include venue, Thursday/early-international matches, weather and injuries. Archive immutable `forecast-history/forecasts/`. Email the full report. |
| Wednesday 3:20 PM | [Wednesday defense forecasts](.github/workflows/wednesday-defense-forecast.yml) | Rank all 32 D/ST units. Include recent opponents' D/ST points allowed, matchup history, weather, injuries and location. Archive immutable `forecast-history/defense-forecasts/`. Email the full report. |
| Thu–Mon, every three UTC hours | [Change-only weather/injury alert](.github/workflows/change-only-alerts.yml) | Compare each upcoming game's current weather, roof and key injuries with Wednesday's snapshot. Sends a **single consolidated email only on significant new changes**, and stops alerts for a game once it begins. Sent IDs live in `forecast-history/alerts/` to avoid repeating unchanged alerts. |

**DST handling:** Each Tuesday/Wednesday workflow has two UTC cron entries for 3:00/3:20 PM Central (CDT/CST). Its internal guard skips the out-of-season UTC entry. Thus GitHub Actions can show **two successful workflow records even though only one generated and emailed a report**. Inspect the *Email* step, not the overall green status. The Thu–Mon change-only check is intentionally UTC-based and compares real game kickoff instants, including Thursday night and 8:30/9:30 AM Eastern international games.

**Shared GitHub secrets:** `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` are repository Actions secrets. They are used by all five workflows. Neither ChatGPT nor an external scheduler sends these messages.

## Quality and maintenance

- [Fantasy Football Analytics tests](.github/workflows/tests.yml) run on pushes and pull requests; this is CI, **not a sixth scheduled fantasy email**.
- `forecast-history` is a separate branch for pregame forecast snapshots, subsequent grades, and the state of sent weather/injury alerts.
- All workflows that may change `forecast-history` share the `fantasy-history-updates` concurrency group, so simultaneous Git pushes do not conflict.
- Wednesday weather and injury flags are monitored, but **do not currently change projected points automatically** without validated historical evidence. D/ST fantasy scoring is **provisional and not guaranteed to match a specific league**. Defensive points-allowed currently use final scoreboard as an approximation.
- The Tuesday reviews require a valid saved Wednesday prediction and completed games. No email when there is nothing valid to grade.
- Job execution is not guaranteed at the exact cron minute. A manually dispatched report is not proof a scheduled run occurred. Check the GitHub event type (`schedule` or `workflow_dispatch`), the relevant email step, and Gmail receipt.
- No standing missed-run watchdog has been implemented. If GitHub skips a schedule entirely, the workflow won't self-recover without an independent watchdog. This is an **identified reliability gap**, not an existing feature.

## Historical ChatGPT task

A separate ChatGPT automation named **Weekly Fantasy Kicker Tracker** used to run Tuesdays at 8:00 AM Central. It was paused to prevent duplicate reporting when GitHub took over. **Do not re-enable it** or create another ChatGPT fantasy automation; instead improve or add GitHub Actions workflows in this repository.

## Troubleshooting

1. Check [GitHub Actions](https://github.com/MisterEgge/fantasy-football-analytics/actions) for the relevant workflow and its `schedule` event. No run means no scheduler trigger, not an SMTP failure.
2. In the selected run, confirm *Test*, *Generate/Grade*, *Archive* and *Email* steps. A green skipped run is not an emailed report.
3. If *Test* fails during collection, ensure tests are scoped to `tests/` and not duplicated under `history-store/`.
4. If archive push fails due to concurrent updates, ensure every history writer uses `fantasy-history-updates`.
5. If *Email* succeeds, GitHub confirms Gmail SMTP acceptance—not final inbox placement. Check inbox filtering, Spam and Promotions.
6. Compare the saved pregame JSON with the next Tuesday grade; never silently recreate an old prediction from new data.
