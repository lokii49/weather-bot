# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Single-file Python bot (`bot.py`). It builds a consensus forecast for Telangana and Hyderabad zones from several weather models, has Claude write a tweet about it, and posts the tweet to X with Tweepy. There are no tests, linter config, or build step.

## Running

Requires Python 3.10 or newer (`anthropic` 1.x). CI uses 3.12.

```bash
pip install -r requirements.txt
python bot.py --dry-run   # or DRY_RUN=1; prints the tweet, no post, no Gist write
python bot.py             # posts a real tweet and writes to the real Gist
```

Always test with `--dry-run`. Without `ANTHROPIC_API_KEY`, a dry run stops after detection, which is enough to check the forecast logic. Open-Meteo needs no key, so detection works with no secrets at all.

Env vars (from `.env` locally, GitHub secrets in CI):

| Group | Vars |
|---|---|
| X | `API_KEY`, `API_SECRET`, `ACCESS_TOKEN`, `ACCESS_SECRET`, `BEARER_TOKEN` |
| Claude | `ANTHROPIC_API_KEY` |
| State | `GIST_ID`, `GIST_TOKEN` |
| Optional sources | `OPENWEATHER_KEY`, `WEATHERAPI_KEY` (each provider is skipped if its var is unset) |

## Deployment

`.github/workflows/weather.yml` runs every 30 minutes (:05 and :35 UTC, off GitHub's congested top of the hour); `posting_decision` decides which runs actually post. Each run makes about 83 provider requests (1 Open-Meteo, 41 OpenWeatherMap, 41 WeatherAPI), so check free-tier quotas before shortening the interval or adding cities. Manual `workflow_dispatch` runs have a `dry_run` checkbox. CI is the only production runtime: pushing to `main` makes changes live, and any new env var must also be added to the workflow's `env:` block. GitHub disables scheduled workflows after 60 days with no repo activity; re-enable with `gh workflow enable weather.yml`.

## Architecture (flow of `tweet_weather()`)

1. **Locations**: `ZONES` and `HYD_ZONES` map zone → city → hard-coded `(lat, lon)`. The coordinates were verified against Nominatim, so no geocoding happens at runtime. A new city needs verified coordinates.
2. **Sources** (`fetch_all_sources`): each source returns `{city: [point]}` with normalized hourly points (`ts` as an aware IST datetime, `temp`, `pop` 0–100, `precip` mm/h, `rainy`, `thunder`).
   - **Open-Meteo**: one request covers all cities and three models (ECMWF, GFS, ICON). Each model counts as its own source.
   - **OpenWeatherMap**: the free 5-day/3-hour endpoint. Each 3-hour step is spread over three hourly points.
   - **WeatherAPI**: uses `time_epoch`, not the naive `time` strings.
3. **Consensus** (`detect_city_events`): for each hour in the next `LOOKAHEAD_HOURS`, one source counts as wet if precip ≥ `RAIN_MM`, or pop ≥ `RAIN_POP`, or a rain code comes with some precip.
   - An hour is flagged when `_votes_needed(n)` sources agree: at least 2, and a majority once there are many sources.
   - A flagged hour is labeled `thunderstorm`, `heavy_rain` or `rain`.
   - `heat` and `cold` use the median temperature across sources.
   - Thresholds are module constants.
4. **Zones** (`build_zone_alerts`): flagged hours from all cities in a zone are merged into contiguous windows per event. Each window gets a human `when` label (`tonight`, `tomorrow morning`, …), a clock range, a cities-affected count and the source agreement.
5. **Tweet** (`generate_tweet`): Claude (`claude-opus-5-5`, effort `low`) writes the tweet.
   - The header time comes from `header_time()` (run time rounded down to the half hour), so the prompt copies it rather than formatting dates.
   - `SYSTEM_PROMPT` fixes one professional forecast-desk format: a header, one `📍` line per area, and a `⚠️` advisory only for severe events. The user message is the JSON payload alone (alerts with intensity, places, coverage, model agreement, and Hyderabad's current condition).
   - Server-side refusal fallbacks are on (`fallbacks="default"`).
   - `tweet_weight` approximates X's weighted length (emoji count as 2). An over-length draft is regenerated once, then dropped. It is never truncated.
6. **Posting policy** (`posting_decision`), checked before calling Claude so skipped runs cost only the forecast fetch. It returns an `update_type` that the prompt uses to pick the header and framing:
   - **Severe** (`SEVERE_EVENTS`: thunderstorm, heavy rain, heat):
     - Severe changes need two runs in a row to agree, so a single run where the models flip can't trigger an alert/all-clear pair. Each run stores what it saw in `last_run_severe`.
     - Severe weather the last post didn't cover posts as `escalation` once a second consecutive run confirms it.
     - A changed severe forecast posts after `SEVERE_MIN_GAP_HOURS`, and an unchanged one repeats every `SEVERE_REPEAT_HOURS`, both as `severe_update`.
     - When severe weather is absent on two consecutive runs, the bot posts `all_clear`.
   - **Non-severe alerts** (`regular`) post at most every `NORMAL_MIN_GAP_HOURS`. An unchanged forecast isn't repeated within `DEDUP_HOURS`. `alert_signature` hashes the (zone, event, date, time-of-day) tuples.
   - **Calm** (signature `"calm"`) posts once per day during `CALM_POST_HOURS` (IST morning).
   - `severe_update` and `all_clear` pass the previous tweet to Claude so it can say what changed.

### Persistent state (GitHub Gist)

CI has no disk persistence. `last_tweet.json` in the Gist holds `{text, signature, severe, posted_at, last_calm_date, last_run_severe}`. The Gist is read once per run, and written after a successful post or when `last_run_severe` flips. Dry runs never write it.
