# Federal Contract Monitor (RPi5)

Single-file, cron-friendly pipeline that pulls active federal contract
opportunities from the official **SAM.gov v2 Opportunities API**, enriches each
with prior-award competitive intel from **USAspending.gov**, scores and
classifies them, and produces a prioritized daily Markdown report, optional CSV,
optional SMS alerts, and a live auto-refreshing dashboard — all tuned for a
Raspberry Pi 5.

Everything lives in one file: [`contract_monitor.py`](contract_monitor.py).
Only `requests` + `pyyaml` are required.

## Quick start (Raspberry Pi 5)

```bash
sudo apt-get install -y python3-pip sqlite3
pip3 install --user -r requirements.txt

# Get a free SAM.gov public API key (emailed instantly):
#   https://api.data.gov/signup/
export SAM_API_KEY=your_key_here

# First run auto-creates config.yaml — edit keywords/NAICS/locations, then:
python3 contract_monitor.py --update --lookback 30 --csv
```

Outputs:

```
contracts.db                    # SQLite, idempotent upserts on noticeId
reports/daily_YYYY-MM-DD.md     # prioritized daily brief
reports/daily_YYYY-MM-DD.csv    # optional, sorted by actionability
```

## Daily cron

```cron
15 6 * * * . /home/pi/.sam_env && cd /home/pi/contract && /usr/bin/python3 contract_monitor.py --update --csv >> monitor.log 2>&1
```

## Live dashboard

```bash
python3 contract_monitor.py --serve          # http://<pi-ip>:8080
```

Auto-refreshes from the SQLite DB every 30 s; filter by action score, sector,
urgency, local-only, set-aside-only, and free-text search. A systemd unit
example (survives reboots) and a Chromium `--kiosk` note for an always-on
display are in the docstring at the top of `contract_monitor.py`.

## SMS alerts (optional)

Twilio (plain `requests` POST, no SDK) with a Textbelt fallback. Alerts fire
only on newly-seen opportunities that beat `min_match_score` or are due within
`sms_deadline_days`, capped by `sms_max_per_run`. Setup steps are in the file
header; enable with `sms_enabled: true` in `config.yaml`.

## What the scoring means

| Field | Meaning |
|---|---|
| `match_score` (0–100) | keyword hits + target NAICS + preferred set-aside + Local Advantage + urgency bump |
| `actionability_score` (0–100) | primary sort key: `0.5·match + 6·urgency + local + set-aside − incumbent penalty` |
| 🏠 Local Advantage | place of performance in CA / LA County / Orange County (configurable) |
| ⚠️ Strong Incumbent | same recipient won 2+ recent similar awards on USAspending |
| Bid-prep checklist | bonding, insurance/COI, licenses, past performance, site-visit & Q&A dates extracted from the description |

## CLI

```
--update           Fetch + enrich + report (default)
--full             Re-enrich all active rows + fetch description URLs
--report-only      Regenerate today's report from DB (no network)
--dry-run          Fetch + classify, no DB/report/SMS writes
--csv              Also write sorted CSV
--serve            Start the always-on dashboard (--host/--port)
--config/--db/--reports-dir/--lookback/--no-sms/--verbose
```

## Customizing

Search `contract_monitor.py` for `# EDIT:` (tuning points: keywords, NAICS
map, local geofence, requirement-extraction rules, report layout, dashboard
styling) and `# TODO:` (county/state scraper skeletons — note OpenGov /
PlanetBids / Cal eProcure are JS-heavy or login-walled and would need
Playwright).
