#!/usr/bin/env python3
"""
contract_monitor.py — RPi5 Federal Contract Intelligence Pipeline
================================================================

WHAT THIS DOES
--------------
Daily pulls active federal opportunities from the official SAM.gov v2
Opportunities Public API, enriches each with prior-award competitive intel
from USAspending.gov, classifies + scores actionability, stores in SQLite,
and emits a prioritized Markdown report (optional CSV + SMS alerts) tuned
for winning bids. Designed to run on a Raspberry Pi 5 under cron.

Only `requests` + `pyyaml` are required. `beautifulsoup4` is optional for
future county / state scrapers.

----------------------------------------------------------------------
SAM.gov PUBLIC API KEY — setup steps
----------------------------------------------------------------------
1. Create an account at https://sam.gov  (Sign In → Create Account).
2. Sign in to https://open.gsa.gov/api/get-started/ and follow
   "Get an API key", which redirects to https://api.data.gov/signup/.
   Fill in first/last/email — the key is emailed instantly.
3. Put the key in config.yaml as `sam_api_key:` OR export it as
   the environment variable `SAM_API_KEY` (env wins over config).
4. Public/non-federal accounts get ~1,000 requests/day. This script
   sleeps between page fetches and USAspending calls to stay polite.

----------------------------------------------------------------------
EMAIL ALERTS (recommended primary channel — stdlib smtplib, no deps)
----------------------------------------------------------------------
Sends a rich HTML daily digest with:
  • per-opportunity cards sorted by Actionability Score, with color-coded
    deadline countdowns, Local Advantage / Strong Incumbent badges
  • prior-award PRICE-POINT BARS + a "bid window" (min / median / max of
    what similar contracts actually went for)
  • one-click 📅 "Add to Google Calendar" links per deadline, PLUS an
    attached deadlines.ics (every deadline as an all-day event with a
    2-day-before reminder — opens in Apple/Google/Outlook calendar)
  • ✉️ pre-filled mailto: drafts to each contracting officer (subject +
    capability-statement intro already written — just hit send)
  • the daily Markdown report and CSV attached
  • urgent runs flagged high-priority so they surface in your inbox

Gmail setup (easiest):
1. Enable 2-Step Verification on your Google account.
2. Create an App Password: https://myaccount.google.com/apppasswords
   (choose "Mail", copy the 16-char password).
3. In config.yaml:
       email:
         enabled: true
         smtp_host: "smtp.gmail.com"
         smtp_port: 465
         smtp_user: "you@gmail.com"
         smtp_password: ""            # or export EMAIL_PASSWORD instead
         from_addr: "you@gmail.com"
         to_addrs: ["you@gmail.com"]
4. Or export EMAIL_PASSWORD=xxxx in the cron env — env wins over config.
Any SMTP provider works (Fastmail, Outlook, self-hosted) — just change
host/port. Port 465 = SSL, 587 = STARTTLS (auto-detected).

Test it any time without a fetch:
    python3 contract_monitor.py --email-test

----------------------------------------------------------------------
TWILIO SMS (optional fallback channel)
----------------------------------------------------------------------
1. Free trial account at https://www.twilio.com/try-twilio
2. Console → grab Account SID and Auth Token from the top card.
3. Console → Phone Numbers → Manage → Buy a number (trial credit works).
4. While on the trial, add your personal number under "Verified Caller
   IDs" — Twilio will only text verified numbers on trial accounts.
5. Fill in config.yaml:
       sms_enabled: true
       sms_provider: "twilio"
       phone_number: "+15551234567"        # E.164, your phone
       twilio_account_sid: "ACxxxxxxxx"
       twilio_auth_token: "xxxxxxxxxxxxx"
       twilio_from_number: "+1xxxxxxxxxx"  # your Twilio number
6. Fallback: Textbelt (https://textbelt.com) — one free SMS/day per
   number. Set `sms_provider: "textbelt"` and leave `textbelt_key:
   "textbelt"` (or your paid key).

----------------------------------------------------------------------
INSTALL
----------------------------------------------------------------------
    sudo apt-get install -y python3-pip sqlite3
    pip3 install --user requests pyyaml
    # Optional (for future county scrapers):
    # pip3 install --user beautifulsoup4

----------------------------------------------------------------------
FIRST RUN
----------------------------------------------------------------------
    cd /home/pi/contract
    python3 contract_monitor.py --update --lookback 30
    # First run auto-creates config.yaml — edit it and re-run.

----------------------------------------------------------------------
CRON EXAMPLE (crontab -e)
----------------------------------------------------------------------
    # Daily at 06:15 local time.
    15 6 * * * cd /home/pi/contract && \\
        SAM_API_KEY=xxxxxxx /usr/bin/python3 contract_monitor.py --update --csv \\
        >> monitor.log 2>&1

    # Or source the key from a file kept 0600:
    15 6 * * * . /home/pi/.sam_env && cd /home/pi/contract && \\
        /usr/bin/python3 contract_monitor.py --update >> monitor.log 2>&1

----------------------------------------------------------------------
ALWAYS-ON DASHBOARD (RPi5 kiosk, browser, or phone on LAN)
----------------------------------------------------------------------
The `--serve` flag starts a zero-dependency HTTP server (stdlib only) that
reads directly from contracts.db every ~30 s and renders a live, filterable
dashboard. Data is always current because the page fetches JSON from the
same SQLite file that cron keeps refreshing.

    python3 contract_monitor.py --serve --host 0.0.0.0 --port 8080
    # then open http://<rpi-ip>:8080 from any device on your LAN.

Run it as a systemd service so it survives reboots. Create
`/etc/systemd/system/contract-dashboard.service`:

    [Unit]
    Description=Contract Monitor Dashboard
    After=network-online.target

    [Service]
    User=pi
    WorkingDirectory=/home/pi/contract
    ExecStart=/usr/bin/python3 /home/pi/contract/contract_monitor.py --serve
    Restart=always
    RestartSec=5

    [Install]
    WantedBy=multi-user.target

Then:
    sudo systemctl daemon-reload
    sudo systemctl enable --now contract-dashboard
    sudo systemctl status contract-dashboard

For a kiosk-style always-on display on the RPi5 itself, set Chromium as an
autostart with `--kiosk http://localhost:8080`.

----------------------------------------------------------------------
DIRECTORY LAYOUT
----------------------------------------------------------------------
    contract_monitor.py
    config.yaml              (auto-created on first run — edit it!)
    contracts.db             (SQLite, upserts on noticeId)
    reports/
        daily_YYYY-MM-DD.md
        daily_YYYY-MM-DD.csv (with --csv)
    monitor.log

----------------------------------------------------------------------
CLI
----------------------------------------------------------------------
    --update           Fetch recent SAM window, enrich, upsert, generate report (default)
    --full             Also re-enrich all active rows + fetch description URLs
    --report-only      Regenerate today's report from DB (no network)
    --dry-run          Fetch + classify but do not write DB/report/SMS
    --csv              Also write CSV alongside the markdown report
    --serve            Start always-on dashboard HTTP server (reads DB live)
    --host HOST        Dashboard bind host (default 0.0.0.0)
    --port PORT        Dashboard port (default 8080)
    --config PATH      Config path (default ./config.yaml)
    --db PATH          Override DB path
    --reports-dir PATH Override reports directory
    --lookback N       Override lookback_days for this run
    --email-test       Send a test email (verifies SMTP creds, no SAM fetch)
    --no-email         Force email digest off for this run
    --no-sms           Force SMS disabled for this run
    --verbose          DEBUG logging
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import requests
import yaml

try:
    from bs4 import BeautifulSoup  # noqa: F401 — optional, county scrapers only
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False


LOG = logging.getLogger("contract_monitor")

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

SAM_BASE = "https://api.sam.gov/opportunities/v2/search"
USASPENDING_BASE = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
USER_AGENT = "contract-monitor/1.0 (RPi5)"
HTTP_TIMEOUT = 30

# NAICS 2-digit → sector name.
# EDIT: adjust labels or add sub-sector granularity for your bid focus.
NAICS_SECTOR_MAP: Dict[str, str] = {
    "11": "Agriculture",
    "21": "Mining/Extraction",
    "22": "Utilities",
    "23": "Construction",
    "31": "Manufacturing",
    "32": "Manufacturing",
    "33": "Manufacturing",
    "42": "Wholesale Trade",
    "44": "Retail Trade",
    "45": "Retail Trade",
    "48": "Transportation",
    "49": "Warehousing/Postal",
    "51": "Information/IT",
    "52": "Finance/Insurance",
    "53": "Real Estate/Leasing",
    "54": "Professional/Technical Services",
    "55": "Management of Companies",
    "56": "Administrative/Support Services",
    "61": "Educational Services",
    "62": "Health Care/Social Services",
    "71": "Arts/Entertainment/Recreation",
    "72": "Accommodation/Food",
    "81": "Other Services (repair, maintenance, personal)",
    "92": "Public Administration",
}

# Local-advantage geofence bonuses (added to match_score).
# EDIT: tune to your service area.
LOCAL_STATE_BOOST = 10   # POP in one of the configured state codes
LOCAL_COUNTY_BOOST = 20  # POP city inside LA/OC (or configured county)

_LA_ORANGE_CITIES = {
    # Los Angeles County
    "los angeles", "long beach", "whittier", "compton", "downey", "norwalk",
    "cerritos", "pico rivera", "santa fe springs", "la mirada", "artesia",
    "bellflower", "lakewood", "torrance", "gardena", "carson", "inglewood",
    "hawthorne", "el monte", "pomona", "pasadena", "burbank", "glendale",
    "santa monica", "culver city", "west covina", "monterey park", "alhambra",
    # Orange County
    "anaheim", "santa ana", "irvine", "orange", "garden grove",
    "huntington beach", "costa mesa", "fullerton", "buena park",
    "westminster", "tustin", "yorba linda", "mission viejo", "lake forest",
    "aliso viejo", "laguna niguel", "san clemente", "cypress", "brea",
    "newport beach", "rancho santa margarita",
}

# Requirements-extraction rule set.
# Each rule = (regex, short label, actionable checklist bullet).
# EDIT: add rules for your typical scope (e.g. "traffic control plan",
#       "MBE/DBE", "environmental compliance", "background checks").
_REQ_RULE_DEFS: List[Tuple[str, str, str]] = [
    (r"\b(performance|payment)\s+bond\b|\bbid bond\b|\bbonding\b",
     "Bonding",
     "Confirm bonding capacity (performance/payment/bid) meets stated limits."),
    (r"\b(commercial|general)\s+liability\b|\bcertificate of insurance\b|\bCOI\b|\binsurance requirements?\b",
     "Insurance/COI",
     "Prepare COI meeting the stated liability limits and additional-insured wording."),
    (r"\b(prior|past)\s+(similar|experience|performance)\b|\bpast performance\b|\bCPARS\b|\bproject references\b",
     "Past Performance",
     "Assemble 3+ past-performance / CPARS references for similar scope."),
    (r"\b(license|licensed|certif(?:ied|ication)|ASE|OSHA|EPA|CDL|C-\d{1,3})\b",
     "Certifications/License",
     "Verify all required trade licenses / certifications are current."),
    (r"\bsite visit\b|\bwalk[- ]?through\b|\bpre[- ]?bid meeting\b",
     "Site Visit",
     "Attend or schedule the mandatory site visit / pre-bid meeting."),
    (r"\bq\s*&\s*a\b|\bquestion(?:s)? due\b|\bquestion deadline\b|\binquiries? due\b",
     "Q&A Deadline",
     "Submit clarification questions before the Q&A deadline."),
    (r"\b(fleet|vehicle|truck|automotive|tow(?:ing)?|roadside|shop rate)\b",
     "Fleet/Vehicle",
     "Confirm shop capacity, ASE-certified techs, and vehicle inventory."),
    (r"\b(SAM(?:\.gov)? registration|active SAM|CAGE code|UEI)\b",
     "SAM/UEI",
     "Verify SAM.gov active status + UEI/CAGE codes current."),
    (r"\b(small business|SBA|8\(a\)|HUBZone|SDVOSB|WOSB|VOSB)\b",
     "Set-Aside Eligibility",
     "Confirm the socioeconomic certification (SBA / 8(a) / HUBZone / SDVOSB / WOSB) is active."),
    (r"\b(background check|fingerprint|clearance|CJIS|LiveScan|drug test)\b",
     "Background/Clearance",
     "Ensure personnel background checks / clearances meet requirements."),
    (r"\bprevailing wage\b|\bDavis[- ]Bacon\b|\bcertified payroll\b",
     "Prevailing Wage",
     "Plan for Davis-Bacon / certified-payroll compliance."),
    (r"\btraffic control plan\b|\bMUTCD\b|\blane closure\b",
     "Traffic Control",
     "Prepare MUTCD-compliant traffic control plan / flaggers."),
]
_REQ_RULES: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(p, re.IGNORECASE), lbl, chk) for p, lbl, chk in _REQ_RULE_DEFS
]

# Regex for pulling out any date-like tail after a keyword — used for the
# "Calendar: site visit on X" reminder in the checklist.
_DATE_TAIL = re.compile(
    r"(site visit|walk[- ]?through|pre[- ]?bid|q\s*&\s*a|questions? due)"
    r"[^.\n]{0,80}?"
    r"((?:\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)"
    r"|(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}(?:,\s*\d{4})?))",
    re.IGNORECASE,
)

# --------------------------------------------------------------------------- #
# Embedded sample config.yaml — written to disk if config missing on 1st run.
# --------------------------------------------------------------------------- #

DEFAULT_CONFIG_YAML = """\
# ------------------------------------------------------------------
# contract_monitor.py — sample config.yaml
# See the docstring at the top of contract_monitor.py for SAM + Twilio
# setup steps.
# ------------------------------------------------------------------

sam_api_key: "REPLACE_ME_OR_SET_SAM_API_KEY_ENV"

# EDIT: keyword hit list. Drives match_score (+10 each, cap +50) and tagging.
keywords:
  - maintenance
  - repair
  - fleet
  - vehicle
  - roadside
  - towing
  - printing
  - signage
  - supplies
  - services
  - construction
  - janitorial
  - landscaping
  - 3d printing

# EDIT: 2-digit prefixes or full NAICS codes. Startswith-match.
target_naics:
  - "23"      # Construction
  - "54"      # Prof/Tech Services
  - "56"      # Admin/Support Services
  - "51"      # Information/IT
  - "33"      # Manufacturing
  - "811"     # Repair/Maintenance
  - "561210"  # Facilities Support

# EDIT: preferred set-aside codes or descriptions — substring-match against
# SAM's `typeOfSetAside` + `typeOfSetAsideDescription`.
preferred_set_asides:
  - "SBA"
  - "8A"
  - "HUBZone"
  - "SDVOSBC"
  - "WOSB"
  - "VOSB"

# Threshold for High-Match sections + baseline SMS alert eligibility.
min_match_score: 60

# EDIT: locations that trigger the Local Advantage badge / score bonus.
# Two-letter state codes match against POP state; "X County" strings match
# against POP city (LA/OC city list is hardcoded); free-form city strings
# match against POP city.
locations:
  - "CA"
  - "Los Angeles County"
  - "Orange County"
  - "Whittier"

business_profile:
  focus: "vehicle maintenance, fleet repair, roadside services, light construction, 3D printing/signage, general services"

# How many days back to pull on --update.
lookback_days: 60

paths:
  db: "contracts.db"
  reports_dir: "reports"

usaspending:
  enabled: true
  per_opp_limit: 5

polite:
  sleep_seconds: 0.5     # between SAM pages / USAspending calls
  max_retries: 4

# ------------------------------------------------------------------
# Email alerts (primary channel). Stdlib smtplib — zero extra deps.
# Gmail: use an App Password (see file header). Password can also come
# from the EMAIL_PASSWORD env var (env wins).
# ------------------------------------------------------------------
email:
  enabled: false
  smtp_host: "smtp.gmail.com"
  smtp_port: 465               # 465 = SSL, 587 = STARTTLS (auto-detected)
  smtp_user: "midbonj@gmail.com"
  smtp_password: ""            # leave blank + export EMAIL_PASSWORD instead
  from_addr: "midbonj@gmail.com"
  to_addrs:
    - "midbonj@gmail.com"
  # What goes in the email:
  top_n: 15                    # max opportunity cards in the digest
  only_when_new: false         # true = skip the email on days with 0 new opps
  attach_report: true          # attach daily_YYYY-MM-DD.md
  attach_csv: true             # attach the CSV when --csv is used
  attach_ics: true             # attach deadlines.ics (calendar events + reminders)
  # EDIT: pre-filled intro used for the one-click mailto: drafts to
  # contracting officers. {title} {sol} {company} are substituted.
  officer_intro: >
    Good morning — regarding {title} (Solicitation {sol}): {company} is an
    experienced local contractor and we would welcome the opportunity to be
    considered. Could you confirm the submission requirements and add us to
    the interested-vendors list? A capability statement is available on
    request. Thank you.
  company_name: "Your Company LLC"    # EDIT: used in the officer intro

# ------------------------------------------------------------------
# SMS / Text alerts (optional fallback). Both providers use plain requests.
# ------------------------------------------------------------------
sms_enabled: false
sms_provider: "twilio"          # or "textbelt"
phone_number: "+15551234567"    # E.164 format, your phone

# Twilio (leave blank if using textbelt)
twilio_account_sid: ""
twilio_auth_token: ""
twilio_from_number: ""

# Textbelt — free tier is 1 SMS/day per phone; use "textbelt" as the key.
textbelt_key: "textbelt"

# SMS triggers on new opps where EITHER:
#   match_score >= min_match_score, OR
#   0 <= days_until_deadline <= sms_deadline_days
# Only newly-seen (first_seen == today) opps are considered, unless --full.
sms_deadline_days: 10
sms_max_per_run: 5              # hard cap so a big pull can't spam you

# ------------------------------------------------------------------
# Always-on dashboard (stdlib http.server; --serve)
# ------------------------------------------------------------------
dashboard:
  host: "0.0.0.0"            # 127.0.0.1 for localhost-only
  port: 8080
  refresh_seconds: 30        # browser auto-refresh interval
  top_n: 200                 # max rows sent to the client per refresh
"""

# --------------------------------------------------------------------------- #
# Opportunity data type
# --------------------------------------------------------------------------- #

@dataclass
class Opportunity:
    notice_id: str
    title: str = ""
    sol_number: str = ""
    posted_date: str = ""            # ISO YYYY-MM-DD ("" if unknown)
    response_deadline: str = ""
    naics_code: str = ""
    set_aside_code: str = ""
    set_aside: str = ""
    agency: str = ""
    sub_agency: str = ""
    office: str = ""
    pop_state: str = ""
    pop_city: str = ""
    pop_country: str = ""
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    description: str = ""
    description_url: str = ""
    url: str = ""
    # classification / enrichment
    sector: str = ""
    tags: List[str] = field(default_factory=list)
    urgency: int = 0                 # 0..5
    value_bucket: str = ""           # S / M / L / XL / ?
    match_score: int = 0             # 0..100
    local_advantage: bool = False
    strong_incumbent: str = ""       # recipient name, or ""
    requirements: List[str] = field(default_factory=list)     # short labels
    checklist: List[str] = field(default_factory=list)        # actionable bullets
    actionability_score: int = 0     # 0..100 — PRIMARY SORT KEY
    prior_summary: List[Dict[str, Any]] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        LOG.warning("Config not found at %s — writing sample. EDIT it and re-run.", path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")
    with path.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    env_key = os.environ.get("SAM_API_KEY")
    if env_key:
        cfg["sam_api_key"] = env_key
    # sane defaults so downstream code doesn't KeyError
    cfg.setdefault("keywords", [])
    cfg.setdefault("target_naics", [])
    cfg.setdefault("preferred_set_asides", [])
    cfg.setdefault("min_match_score", 60)
    cfg.setdefault("locations", [])
    cfg.setdefault("lookback_days", 60)
    paths = cfg.setdefault("paths", {})
    paths.setdefault("db", "contracts.db")
    paths.setdefault("reports_dir", "reports")
    us = cfg.setdefault("usaspending", {})
    us.setdefault("enabled", True)
    us.setdefault("per_opp_limit", 5)
    polite = cfg.setdefault("polite", {})
    polite.setdefault("sleep_seconds", 0.5)
    polite.setdefault("max_retries", 4)
    cfg.setdefault("sms_enabled", False)
    cfg.setdefault("sms_provider", "twilio")
    cfg.setdefault("sms_deadline_days", 10)
    cfg.setdefault("sms_max_per_run", 5)
    em = cfg.setdefault("email", {})
    em.setdefault("enabled", False)
    em.setdefault("smtp_host", "smtp.gmail.com")
    em.setdefault("smtp_port", 465)
    em.setdefault("smtp_user", "")
    em.setdefault("smtp_password", "")
    em.setdefault("from_addr", em.get("smtp_user", ""))
    em.setdefault("to_addrs", [])
    em.setdefault("top_n", 15)
    em.setdefault("only_when_new", False)
    em.setdefault("attach_report", True)
    em.setdefault("attach_csv", True)
    em.setdefault("attach_ics", True)
    em.setdefault("company_name", "Your Company LLC")
    em.setdefault(
        "officer_intro",
        "Good morning — regarding {title} (Solicitation {sol}): {company} is an "
        "experienced local contractor and we would welcome the opportunity to be "
        "considered. Could you confirm the submission requirements and add us to "
        "the interested-vendors list? Thank you.",
    )
    env_pw = os.environ.get("EMAIL_PASSWORD")
    if env_pw:
        em["smtp_password"] = env_pw
    dash = cfg.setdefault("dashboard", {})
    dash.setdefault("host", "0.0.0.0")
    dash.setdefault("port", 8080)
    dash.setdefault("refresh_seconds", 30)
    dash.setdefault("top_n", 200)
    return cfg


# --------------------------------------------------------------------------- #
# HTTP with polite backoff
# --------------------------------------------------------------------------- #

def _sleep_backoff(attempt: int, retry_after: Optional[str]) -> None:
    if retry_after:
        try:
            time.sleep(min(60, max(1, int(retry_after))))
            return
        except ValueError:
            pass
    time.sleep(min(30, 2 ** attempt))


def http_get_json(url: str, params: Dict[str, Any], max_retries: int = 4) -> Optional[Dict[str, Any]]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504):
                LOG.warning("GET %s → %s (retry %d/%d)", url, r.status_code, attempt + 1, max_retries)
                _sleep_backoff(attempt, r.headers.get("Retry-After"))
                continue
            LOG.error("GET %s → %s: %s", url, r.status_code, r.text[:300])
            return None
        except requests.RequestException as exc:
            LOG.warning("GET %s network error: %s (retry %d/%d)", url, exc, attempt + 1, max_retries)
            _sleep_backoff(attempt, None)
    return None


def http_post_json(url: str, body: Dict[str, Any], max_retries: int = 4) -> Optional[Dict[str, Any]]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    for attempt in range(max_retries):
        try:
            r = requests.post(url, json=body, headers=headers, timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504):
                LOG.warning("POST %s → %s (retry %d/%d)", url, r.status_code, attempt + 1, max_retries)
                _sleep_backoff(attempt, r.headers.get("Retry-After"))
                continue
            LOG.error("POST %s → %s: %s", url, r.status_code, r.text[:300])
            return None
        except requests.RequestException as exc:
            LOG.warning("POST %s network error: %s (retry %d/%d)", url, exc, attempt + 1, max_retries)
            _sleep_backoff(attempt, None)
    return None


# --------------------------------------------------------------------------- #
# Date helpers — SAM mixes ISO 8601 and MM/dd/yyyy.
# --------------------------------------------------------------------------- #

def parse_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(s[:10] if len(s) >= 10 else s, fmt).date()
        except ValueError:
            continue
    return None


def iso(d: Optional[date]) -> str:
    return d.isoformat() if d else ""


def mmddyyyy(d: date) -> str:
    return d.strftime("%m/%d/%Y")


def _safe_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------------- #
# SAM.gov client
# --------------------------------------------------------------------------- #

def _extract_pop(pop: Any) -> Tuple[str, str, str]:
    if not isinstance(pop, dict):
        return "", "", ""
    def _from(node: Any, *keys: str) -> str:
        if isinstance(node, dict):
            for k in keys:
                v = node.get(k)
                if v:
                    return str(v)
            return ""
        return str(node) if node else ""
    city = _from(pop.get("city"), "name", "code")
    state = _from(pop.get("state"), "code", "name")
    country = _from(pop.get("country"), "code", "name")
    return city, state, country


def _extract_contact(contacts: Any) -> Tuple[str, str, str]:
    if not isinstance(contacts, list) or not contacts:
        return "", "", ""
    c = contacts[0] if isinstance(contacts[0], dict) else {}
    return (
        str(c.get("fullName") or c.get("name") or ""),
        str(c.get("email") or ""),
        str(c.get("phone") or ""),
    )


def _extract_naics(item: Dict[str, Any]) -> str:
    code = item.get("naicsCode")
    if code:
        return str(code)
    naics = item.get("naicsCodes")
    if isinstance(naics, list) and naics:
        first = naics[0]
        if isinstance(first, dict):
            return str(first.get("code") or "")
        return str(first)
    return ""


def _extract_office(item: Dict[str, Any]) -> str:
    val = item.get("office")
    if isinstance(val, str) and val:
        return val
    addr = item.get("officeAddress")
    if isinstance(addr, dict):
        return str(addr.get("name") or "")
    return ""


def _normalize_sam_item(item: Dict[str, Any]) -> Optional[Opportunity]:
    notice_id = str(item.get("noticeId") or item.get("noticeID") or "").strip()
    if not notice_id:
        return None
    posted = parse_date(item.get("postedDate"))
    deadline = parse_date(item.get("responseDeadLine") or item.get("responseDeadline"))
    pop_city, pop_state, pop_country = _extract_pop(item.get("placeOfPerformance"))
    contact_name, contact_email, contact_phone = _extract_contact(item.get("pointOfContact"))

    description = ""
    description_url = ""
    desc_field = item.get("description")
    if isinstance(desc_field, str):
        if desc_field.startswith(("http://", "https://")):
            description_url = desc_field
        else:
            description = desc_field
    elif isinstance(desc_field, dict):
        # SAM sometimes returns {"url": "...", "value": "..."}
        if desc_field.get("value"):
            description = str(desc_field["value"])
        if desc_field.get("url"):
            description_url = str(desc_field["url"])

    ui_url = str(item.get("uiLink") or "").strip()
    if not ui_url:
        ui_url = f"https://sam.gov/opp/{notice_id}/view"

    return Opportunity(
        notice_id=notice_id,
        title=str(item.get("title") or "").strip(),
        sol_number=str(item.get("solicitationNumber") or "").strip(),
        posted_date=iso(posted),
        response_deadline=iso(deadline),
        naics_code=_extract_naics(item),
        set_aside_code=str(item.get("typeOfSetAside") or item.get("setAsideCode") or ""),
        set_aside=str(item.get("typeOfSetAsideDescription") or ""),
        agency=str(item.get("fullParentPathName") or item.get("department") or "").strip(),
        sub_agency=str(item.get("subTier") or "").strip(),
        office=_extract_office(item),
        pop_state=pop_state,
        pop_city=pop_city,
        pop_country=pop_country,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
        description=description[:8000],
        description_url=description_url,
        url=ui_url,
    )


def fetch_sam_opportunities(cfg: Dict[str, Any], days_back: int) -> Iterator[Opportunity]:
    api_key = cfg.get("sam_api_key") or ""
    if not api_key or api_key.startswith("REPLACE_ME"):
        LOG.error("sam_api_key not set — put it in config.yaml or export SAM_API_KEY.")
        return
    today = date.today()
    start = today - timedelta(days=max(1, int(days_back)))
    sleep_s = float(cfg.get("polite", {}).get("sleep_seconds", 0.5))
    retries = int(cfg.get("polite", {}).get("max_retries", 4))
    limit = 1000
    offset = 0
    fetched = 0
    while True:
        params = {
            "api_key": api_key,
            "postedFrom": mmddyyyy(start),
            "postedTo": mmddyyyy(today),
            "limit": limit,
            "offset": offset,
            "active": "Yes",
        }
        LOG.info("SAM fetch page offset=%d limit=%d", offset, limit)
        data = http_get_json(SAM_BASE, params, max_retries=retries)
        if not data:
            LOG.error("SAM returned nothing at offset=%d — stopping paging.", offset)
            break
        opps = data.get("opportunitiesData") or data.get("opportunities") or []
        total = int(data.get("totalRecords") or 0)
        LOG.info("SAM page: %d items (running total reported=%d)", len(opps), total)
        if not opps:
            break
        for it in opps:
            try:
                opp = _normalize_sam_item(it)
                if opp:
                    yield opp
                    fetched += 1
            except Exception as exc:
                LOG.warning("Skipping malformed SAM item: %s", exc)
        offset += len(opps)
        if offset >= total or len(opps) < limit:
            break
        time.sleep(sleep_s)
    LOG.info("SAM total normalized: %d", fetched)


def fetch_description_text(url: str, max_bytes: int = 4096) -> str:
    """Optional --full helper: pull a description URL, strip HTML, truncate."""
    if not url:
        return ""
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT},
                         timeout=HTTP_TIMEOUT, stream=True)
        if r.status_code != 200:
            return ""
        raw = r.raw.read(max_bytes * 4, decode_content=True) or b""
        text = raw.decode("utf-8", errors="replace")
        if "<" in text and ">" in text:
            text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()[:max_bytes]
    except requests.RequestException:
        return ""


# --------------------------------------------------------------------------- #
# USAspending.gov prior-award enrichment
# --------------------------------------------------------------------------- #

class UsaSpendingCache:
    """Per-run cache. Key: (naics_prefix, agency_lower). Cuts duplicate calls."""

    def __init__(self, cfg: Dict[str, Any]) -> None:
        self._cache: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        us = cfg.get("usaspending", {}) or {}
        self._enabled = bool(us.get("enabled", True))
        self._limit = int(us.get("per_opp_limit", 5))
        polite = cfg.get("polite", {}) or {}
        self._sleep = float(polite.get("sleep_seconds", 0.5))
        self._retries = int(polite.get("max_retries", 4))

    def fetch(self, naics: str, agency_name: str) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []
        naics_key = (naics or "")[:6]
        # collapse SAM's `A.B.C` hierarchy to top segment for cache key + agency filter
        top_agency = (re.split(r"\.", agency_name or "")[0]).strip()
        key = (naics_key, top_agency.lower())
        if key in self._cache:
            return self._cache[key]
        result = self._raw(naics_key, top_agency)
        # If nothing found with agency filter, retry NAICS-only — USAspending
        # requires exact-name matches on agencies, and SAM's naming often differs.
        if not result and top_agency:
            result = self._raw(naics_key, "")
        self._cache[key] = result
        time.sleep(self._sleep)
        return result

    def _raw(self, naics: str, agency_name: str) -> List[Dict[str, Any]]:
        if not naics and not agency_name:
            return []
        filters: Dict[str, Any] = {
            # Contracts: A, B, C, D. Skip grants/IDVs to keep results comparable.
            "award_type_codes": ["A", "B", "C", "D"],
            "time_period": [{
                "start_date": (date.today() - timedelta(days=730)).isoformat(),
                "end_date": date.today().isoformat(),
            }],
        }
        if naics:
            filters["naics_codes"] = [naics]
        if agency_name:
            filters["agencies"] = [{
                "type": "awarding",
                "tier": "toptier",
                "name": agency_name,
            }]
        # NOTE: contract-award result mappings use "Start Date" (not
        # "Action Date") — sorting by anything else returns HTTP 400.
        body = {
            "filters": filters,
            "fields": [
                "Award ID", "Recipient Name", "Award Amount",
                "Start Date", "Description", "Awarding Agency",
            ],
            "page": 1,
            "limit": max(1, self._limit),
            "sort": "Start Date",
            "order": "desc",
            "subawards": False,
        }
        try:
            data = http_post_json(USASPENDING_BASE, body, max_retries=self._retries)
        except Exception as exc:
            LOG.debug("USAspending exception: %s", exc)
            return []
        if not data:
            return []
        out: List[Dict[str, Any]] = []
        for r in (data.get("results") or [])[: self._limit]:
            out.append({
                "recipient": r.get("Recipient Name") or "",
                "amount": _safe_float(r.get("Award Amount")),
                "action_date": (r.get("Start Date") or "")[:10],
                "contract_number": r.get("Award ID") or "",
                "description": (r.get("Description") or "")[:400],
                "agency": r.get("Awarding Agency") or "",
            })
        return out


# --------------------------------------------------------------------------- #
# Classification / scoring
# --------------------------------------------------------------------------- #

def sector_from_naics(code: str) -> str:
    if not code:
        return ""
    return NAICS_SECTOR_MAP.get(str(code)[:2], "Other")


def urgency_from_deadline(deadline_iso: str) -> int:
    d = parse_date(deadline_iso)
    if not d:
        return 0
    days = (d - date.today()).days
    if days < 0:
        return 0
    if days <= 3:
        return 5
    if days <= 7:
        return 4
    if days <= 14:
        return 3
    if days <= 30:
        return 2
    return 1


def value_bucket(prior: List[Dict[str, Any]]) -> str:
    if not prior:
        return "?"
    amounts = sorted(_safe_float(a.get("amount")) for a in prior)
    amounts = [a for a in amounts if a > 0]
    if not amounts:
        return "?"
    mid = amounts[len(amounts) // 2]
    if mid < 50_000:
        return "S"
    if mid < 250_000:
        return "M"
    if mid < 1_000_000:
        return "L"
    return "XL"


def _hay(opp: Opportunity) -> str:
    return " ".join([opp.title or "", opp.description or ""]).lower()


def tag_keywords(opp: Opportunity, keywords: List[str]) -> List[str]:
    hay = _hay(opp)
    return sorted({kw for kw in keywords if kw and kw.lower() in hay})


def extract_requirements(opp: Opportunity) -> Tuple[List[str], List[str]]:
    hay = " ".join([opp.title or "", opp.description or ""])
    labels: List[str] = []
    checklist: List[str] = []
    seen = set()
    for pat, label, bullet in _REQ_RULES:
        if pat.search(hay) and label not in seen:
            labels.append(label)
            checklist.append(bullet)
            seen.add(label)
    m = _DATE_TAIL.search(hay)
    if m:
        checklist.append(f"Calendar: {m.group(1).title().strip()} on {m.group(2).strip()}.")
    return labels, checklist


def _naics_match(naics: str, targets: List[str]) -> bool:
    if not naics or not targets:
        return False
    for t in targets:
        if t and naics.startswith(str(t)):
            return True
    return False


def _set_aside_match(opp: Opportunity, prefs: List[str]) -> Optional[str]:
    combined = ((opp.set_aside or "") + " " + (opp.set_aside_code or "")).lower()
    for p in prefs:
        if p and p.lower() in combined:
            return p
    return None


def _local_check(opp: Opportunity, locations: List[str]) -> Tuple[bool, int, str]:
    """Return (is_local, bonus_pts, reason)."""
    st = (opp.pop_state or "").strip().upper()
    city = (opp.pop_city or "").strip().lower()
    bonus = 0
    reasons: List[str] = []
    for loc in locations or []:
        loc_s = str(loc).strip()
        if not loc_s:
            continue
        loc_l = loc_s.lower()
        # State-code match
        if len(loc_s) == 2 and st == loc_s.upper():
            bonus = max(bonus, LOCAL_STATE_BOOST)
            reasons.append(f"POP={st}")
            continue
        # "X County" — use LA/OC city set for the big two, else substring match
        if loc_l.endswith("county"):
            county_l = loc_l.replace("county", "").strip()
            if county_l in ("los angeles", "orange") and city in _LA_ORANGE_CITIES:
                bonus = max(bonus, LOCAL_COUNTY_BOOST)
                reasons.append(loc_s)
            elif county_l and county_l in city:
                bonus = max(bonus, LOCAL_COUNTY_BOOST)
                reasons.append(loc_s)
            continue
        # Otherwise treat as a city / free-form location
        if loc_l == city or loc_l in city:
            bonus = max(bonus, LOCAL_COUNTY_BOOST)
            reasons.append(loc_s)
    # Extra safety net: any LA/OC city automatically counts.
    if bonus < LOCAL_COUNTY_BOOST and st == "CA" and city in _LA_ORANGE_CITIES:
        bonus = LOCAL_COUNTY_BOOST
        reasons.append("LA/OC city")
    return (bonus > 0), bonus, ", ".join(sorted(set(reasons)))


def compute_match_score(opp: Opportunity, cfg: Dict[str, Any]) -> Tuple[int, bool, int]:
    """Return (match_score 0..100, local_advantage flag, local_bonus applied)."""
    score = 0
    hay = _hay(opp)
    kw_hits = sum(1 for kw in cfg.get("keywords", []) if kw and kw.lower() in hay)
    score += min(50, kw_hits * 10)
    if _naics_match(opp.naics_code, cfg.get("target_naics", [])):
        score += 15
    if _set_aside_match(opp, cfg.get("preferred_set_asides", [])):
        score += 20
    is_local, local_bonus, _ = _local_check(opp, cfg.get("locations", []))
    if is_local:
        score += local_bonus
    if opp.urgency >= 4:
        score += 5
    return max(0, min(100, score)), is_local, local_bonus


def compute_actionability(opp: Opportunity, cfg: Dict[str, Any], local_bonus: int) -> int:
    """
    Weighted 0..100 — PRIMARY sort key for the daily report.
        match_score      × 0.50           (up to +50)
        urgency (0..5)   × 6              (up to +30)
        local_bonus      × 0.5, cap 10    (up to +10)
        set-aside pref   flat +10
        strong incumbent flat -15         (harder to unseat)
    """
    score = int(opp.match_score * 0.50)
    score += min(30, opp.urgency * 6)
    score += min(10, int(local_bonus * 0.5))
    if _set_aside_match(opp, cfg.get("preferred_set_asides", [])):
        score += 10
    if opp.strong_incumbent:
        score -= 15
    return max(0, min(100, score))


def detect_strong_incumbent(prior: List[Dict[str, Any]]) -> str:
    """Return the recipient name if any single recipient won 2+ of the priors."""
    counts: Dict[str, int] = {}
    for a in prior or []:
        name = (a.get("recipient") or "").strip()
        if name:
            counts[name] = counts.get(name, 0) + 1
    for name, n in counts.items():
        if n >= 2:
            return name
    return ""


# --------------------------------------------------------------------------- #
# SQLite storage
# --------------------------------------------------------------------------- #

SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    notice_id           TEXT PRIMARY KEY,
    title               TEXT,
    sol_number          TEXT,
    posted_date         TEXT,
    response_deadline   TEXT,
    naics_code          TEXT,
    set_aside_code      TEXT,
    set_aside           TEXT,
    agency              TEXT,
    sub_agency          TEXT,
    office              TEXT,
    pop_state           TEXT,
    pop_city            TEXT,
    pop_country         TEXT,
    contact_name        TEXT,
    contact_email       TEXT,
    contact_phone       TEXT,
    description         TEXT,
    description_url     TEXT,
    url                 TEXT,
    sector              TEXT,
    tags_json           TEXT,
    urgency             INTEGER,
    value_bucket        TEXT,
    match_score         INTEGER,
    local_advantage     INTEGER,
    strong_incumbent    TEXT,
    requirements_json   TEXT,
    checklist_json      TEXT,
    actionability_score INTEGER,
    prior_summary_json  TEXT,
    first_seen          TEXT,
    last_seen           TEXT,
    is_active           INTEGER
);
CREATE INDEX IF NOT EXISTS idx_opps_score
    ON opportunities(actionability_score DESC, response_deadline ASC);
CREATE INDEX IF NOT EXISTS idx_opps_active
    ON opportunities(is_active);
"""


def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def upsert_opportunity(conn: sqlite3.Connection, opp: Opportunity, today_iso: str) -> bool:
    """Upsert on notice_id. Return True if the row is newly seen today."""
    cur = conn.execute(
        "SELECT first_seen FROM opportunities WHERE notice_id = ?", (opp.notice_id,)
    )
    row = cur.fetchone()
    is_new = row is None
    first_seen = today_iso if is_new else row[0]
    conn.execute(
        """
        INSERT INTO opportunities (
            notice_id, title, sol_number, posted_date, response_deadline,
            naics_code, set_aside_code, set_aside, agency, sub_agency, office,
            pop_state, pop_city, pop_country,
            contact_name, contact_email, contact_phone,
            description, description_url, url,
            sector, tags_json, urgency, value_bucket, match_score,
            local_advantage, strong_incumbent,
            requirements_json, checklist_json, actionability_score,
            prior_summary_json, first_seen, last_seen, is_active
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(notice_id) DO UPDATE SET
            title=excluded.title,
            sol_number=excluded.sol_number,
            posted_date=excluded.posted_date,
            response_deadline=excluded.response_deadline,
            naics_code=excluded.naics_code,
            set_aside_code=excluded.set_aside_code,
            set_aside=excluded.set_aside,
            agency=excluded.agency,
            sub_agency=excluded.sub_agency,
            office=excluded.office,
            pop_state=excluded.pop_state,
            pop_city=excluded.pop_city,
            pop_country=excluded.pop_country,
            contact_name=excluded.contact_name,
            contact_email=excluded.contact_email,
            contact_phone=excluded.contact_phone,
            description=excluded.description,
            description_url=excluded.description_url,
            url=excluded.url,
            sector=excluded.sector,
            tags_json=excluded.tags_json,
            urgency=excluded.urgency,
            value_bucket=excluded.value_bucket,
            match_score=excluded.match_score,
            local_advantage=excluded.local_advantage,
            strong_incumbent=excluded.strong_incumbent,
            requirements_json=excluded.requirements_json,
            checklist_json=excluded.checklist_json,
            actionability_score=excluded.actionability_score,
            prior_summary_json=excluded.prior_summary_json,
            last_seen=excluded.last_seen,
            is_active=1
        """,
        (
            opp.notice_id, opp.title, opp.sol_number, opp.posted_date, opp.response_deadline,
            opp.naics_code, opp.set_aside_code, opp.set_aside, opp.agency, opp.sub_agency, opp.office,
            opp.pop_state, opp.pop_city, opp.pop_country,
            opp.contact_name, opp.contact_email, opp.contact_phone,
            opp.description, opp.description_url, opp.url,
            opp.sector, json.dumps(opp.tags), opp.urgency, opp.value_bucket, opp.match_score,
            int(opp.local_advantage), opp.strong_incumbent,
            json.dumps(opp.requirements), json.dumps(opp.checklist), opp.actionability_score,
            json.dumps(opp.prior_summary), first_seen, today_iso, 1,
        ),
    )
    return is_new


def mark_stale_inactive(conn: sqlite3.Connection, days_stale: int = 7) -> int:
    """Mark rows we haven't refreshed in `days_stale` days as inactive."""
    threshold = (date.today() - timedelta(days=days_stale)).isoformat()
    cur = conn.execute(
        "UPDATE opportunities SET is_active = 0 "
        "WHERE last_seen < ? AND is_active = 1",
        (threshold,),
    )
    return cur.rowcount


# --------------------------------------------------------------------------- #
# County / State scraper skeleton — extend later.
# --------------------------------------------------------------------------- #

def scrape_county_site_stub(source_cfg: Dict[str, Any]) -> List[Opportunity]:
    """
    Skeleton for a per-county bid scraper.

    # TODO: implement per-source scrapers here.
    # NOTE: OpenGov Procurement, PlanetBids, and Cal eProcure are typically
    #       JavaScript-rendered or login-walled; they cannot be scraped
    #       with `requests` + `bs4` alone. Playwright would be required.
    # EDIT: for scrapable RSS/HTML feeds, parse and return a list of
    #       Opportunity objects using the same notice_id namespace prefix
    #       (e.g. "county-la-<internal_id>") so upserts stay unique.
    """
    if not _HAS_BS4:
        LOG.debug("bs4 not installed; county scraper stub returning empty.")
    return []


# --------------------------------------------------------------------------- #
# SMS notifications
# --------------------------------------------------------------------------- #

def send_sms(cfg: Dict[str, Any], message: str) -> bool:
    provider = str(cfg.get("sms_provider") or "twilio").lower()
    to = cfg.get("phone_number") or ""
    if not to:
        LOG.warning("SMS: no phone_number configured; skipping.")
        return False

    if provider == "twilio":
        sid = cfg.get("twilio_account_sid") or ""
        token = cfg.get("twilio_auth_token") or ""
        from_num = cfg.get("twilio_from_number") or ""
        if not (sid and token and from_num):
            LOG.warning("SMS: Twilio creds incomplete; skipping.")
            return False
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        try:
            r = requests.post(
                url,
                data={"To": to, "From": from_num, "Body": message[:1500]},
                auth=(sid, token),
                headers={"User-Agent": USER_AGENT},
                timeout=HTTP_TIMEOUT,
            )
            if 200 <= r.status_code < 300:
                LOG.info("SMS via Twilio → %s (%d chars)", to, len(message))
                return True
            LOG.error("Twilio SMS %s: %s", r.status_code, r.text[:300])
            return False
        except requests.RequestException as exc:
            LOG.error("Twilio SMS network error: %s", exc)
            return False

    if provider == "textbelt":
        key = cfg.get("textbelt_key") or "textbelt"
        try:
            r = requests.post(
                "https://textbelt.com/text",
                data={"phone": to, "message": message[:800], "key": key},
                headers={"User-Agent": USER_AGENT},
                timeout=HTTP_TIMEOUT,
            )
            try:
                data = r.json()
            except ValueError:
                data = {}
            if data.get("success"):
                LOG.info("SMS via Textbelt → %s (quota left=%s)",
                         to, data.get("quotaRemaining"))
                return True
            LOG.error("Textbelt SMS failed: %s", data or r.text[:300])
            return False
        except requests.RequestException as exc:
            LOG.error("Textbelt SMS network error: %s", exc)
            return False

    LOG.warning("SMS: unknown provider %r", provider)
    return False


def build_sms_body(opp: Opportunity) -> str:
    deadline = opp.response_deadline or "TBD"
    badges: List[str] = []
    if opp.local_advantage:
        badges.append("Local Advantage")
    if opp.set_aside:
        badges.append(opp.set_aside[:20])
    if opp.strong_incumbent:
        badges.append(f"Incumbent:{opp.strong_incumbent[:20]}")
    tag_str = f" [{' | '.join(badges)}]" if badges else ""
    title = (opp.title or "Untitled")[:80]
    # Format matches user spec: "New high-match contract (Score 87): ... - Due ... - ... - Link: ..."
    return (
        f"New match (Act={opp.actionability_score} Score={opp.match_score}): "
        f"{title} - Due {deadline}{tag_str} - {opp.url}"
    )


def maybe_send_alerts(cfg: Dict[str, Any], new_alerts: List[Opportunity]) -> None:
    if not new_alerts:
        LOG.info("SMS: no new opps this run.")
        return
    min_score = int(cfg.get("min_match_score", 60))
    dl_days = int(cfg.get("sms_deadline_days", 10))
    cap = int(cfg.get("sms_max_per_run", 5))
    ranked = sorted(new_alerts, key=lambda o: -o.actionability_score)
    sent = 0
    considered = 0
    for opp in ranked:
        if sent >= cap:
            break
        left = _days_left(opp.response_deadline)
        soon = left is not None and 0 <= left <= dl_days
        if opp.match_score < min_score and not soon:
            continue
        considered += 1
        if send_sms(cfg, build_sms_body(opp)):
            sent += 1
    LOG.info("SMS: sent %d of %d eligible new alerts (cap=%d).", sent, considered, cap)


# --------------------------------------------------------------------------- #
# Email alerts — stdlib smtplib. Rich HTML digest + calendar + officer drafts.
# --------------------------------------------------------------------------- #

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import escape as _h
from urllib.parse import quote as _q


def _gcal_link(opp: Opportunity) -> str:
    """One-click 'Add to Google Calendar' URL for the response deadline."""
    d = parse_date(opp.response_deadline)
    if not d:
        return ""
    start = d.strftime("%Y%m%d")
    end = (d + timedelta(days=1)).strftime("%Y%m%d")
    title = f"BID DUE: {opp.title[:80]}"
    details = f"Sol# {opp.sol_number or 'n/a'}\n{opp.url}"
    return (
        "https://calendar.google.com/calendar/render?action=TEMPLATE"
        f"&text={_q(title)}&dates={start}/{end}&details={_q(details)}"
    )


def _officer_mailto(opp: Opportunity, cfg: Dict[str, Any]) -> str:
    """Pre-filled mailto: draft to the contracting officer — just hit send."""
    if not opp.contact_email:
        return ""
    em = cfg.get("email", {}) or {}
    subject = f"Interested Vendor — {opp.sol_number or opp.title[:60]}"
    body = str(em.get("officer_intro", "")).format(
        title=opp.title, sol=opp.sol_number or "n/a",
        company=em.get("company_name", "Your Company LLC"),
    )
    return f"mailto:{opp.contact_email}?subject={_q(subject)}&body={_q(body)}"


def build_ics(opps: List[Opportunity]) -> str:
    """
    deadlines.ics — every deadline as an all-day VEVENT with a reminder
    2 days before. Opens directly in Apple / Google / Outlook calendars.
    """
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//contract-monitor//bid-deadlines//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")
    for o in opps:
        d = parse_date(o.response_deadline)
        if not d:
            continue
        lines += [
            "BEGIN:VEVENT",
            f"UID:{o.notice_id}@contract-monitor",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(d + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{_esc('BID DUE: ' + (o.title or o.notice_id)[:100])}",
            "DESCRIPTION:" + _esc(
                f"Sol# {o.sol_number or 'n/a'} | Action {o.actionability_score} | {o.url}"
            ),
            f"URL:{o.url}",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_esc('Bid due in 2 days: ' + (o.title or '')[:80])}",
            "TRIGGER:-P2D",
            "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def _bid_window(prior: List[Dict[str, Any]]) -> str:
    """'Bid window: $9.6k – $89.6k – $207.7k (min/median/max)' from priors."""
    amounts = sorted(a for a in (_safe_float(p.get("amount")) for p in prior) if a > 0)
    if not amounts:
        return ""
    med = amounts[len(amounts) // 2]
    return f"{_fmt_money(amounts[0])} – {_fmt_money(med)} – {_fmt_money(amounts[-1])}"


def _email_opp_card(opp: Opportunity, cfg: Dict[str, Any], is_new: bool) -> str:
    """One opportunity card. Inline styles only — survives Gmail/Outlook."""
    dleft = _days_left(opp.response_deadline)
    if dleft is None:
        dl_txt, dl_color = "TBD", "#888"
    elif dleft < 0:
        dl_txt, dl_color = f"{opp.response_deadline} (overdue)", "#b91c1c"
    elif dleft <= 3:
        dl_txt, dl_color = f"{opp.response_deadline} — {dleft}d left", "#dc2626"
    elif dleft <= 7:
        dl_txt, dl_color = f"{opp.response_deadline} — {dleft}d left", "#d97706"
    else:
        dl_txt, dl_color = f"{opp.response_deadline} — {dleft}d left", "#16a34a"

    sc = opp.actionability_score
    sc_color = "#16a34a" if sc >= 70 else "#d97706" if sc >= 40 else "#6b7280"

    badges = []
    if is_new:
        badges.append('<span style="background:#7c3aed;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold">NEW TODAY</span>')
    if opp.local_advantage:
        badges.append('<span style="background:#16a34a;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold">🏠 LOCAL ADVANTAGE</span>')
    if opp.set_aside:
        badges.append(f'<span style="background:#2563eb;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold">🛡 {_h(opp.set_aside[:40])}</span>')
    if opp.strong_incumbent:
        badges.append(f'<span style="background:#d97706;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold">⚠️ INCUMBENT: {_h(opp.strong_incumbent[:30])}</span>')

    # Prior-award price-point bars (table-based; email-client-safe).
    prior_html = ""
    priced = [p for p in opp.prior_summary[:5] if _safe_float(p.get("amount")) > 0]
    if priced:
        mx = max(_safe_float(p["amount"]) for p in priced)
        rows = []
        for p in priced:
            amt = _safe_float(p["amount"])
            pct = max(4, int(amt / mx * 100))
            rows.append(
                '<tr>'
                f'<td style="font-size:11px;color:#555;padding:1px 8px 1px 0;white-space:nowrap">{_h((p.get("recipient") or "?")[:34])}</td>'
                f'<td style="width:220px;padding:1px 0"><div style="background:#3b82f6;height:10px;width:{pct}%;border-radius:3px"></div></td>'
                f'<td style="font-size:11px;color:#111;padding:1px 0 1px 8px;white-space:nowrap"><b>{_fmt_money(amt)}</b> <span style="color:#888">{_h((p.get("action_date") or "")[:10])}</span></td>'
                '</tr>'
            )
        window = _bid_window(opp.prior_summary)
        prior_html = (
            f'<div style="margin-top:8px;font-size:12px;color:#333"><b>What similar work went for</b>'
            + (f' &nbsp;·&nbsp; bid window: <b>{_h(window)}</b>' if window else "")
            + f'</div><table cellpadding="0" cellspacing="0" style="margin-top:4px">{"".join(rows)}</table>'
        )

    checklist_html = ""
    if opp.checklist:
        items = "".join(f'<li style="margin:2px 0">{_h(c)}</li>' for c in opp.checklist[:6])
        checklist_html = (
            f'<div style="margin-top:8px;font-size:12px"><b>Bid-prep checklist</b>'
            f'<ul style="margin:4px 0 0 18px;padding:0;color:#333">{items}</ul></div>'
        )

    actions = [f'<a href="{_h(opp.url)}" style="color:#2563eb;font-weight:bold;text-decoration:none">View on SAM.gov →</a>']
    gcal = _gcal_link(opp)
    if gcal:
        actions.append(f'<a href="{_h(gcal)}" style="color:#2563eb;text-decoration:none">📅 Add deadline to Google Calendar</a>')
    mailto = _officer_mailto(opp, cfg)
    if mailto:
        actions.append(f'<a href="{_h(mailto)}" style="color:#2563eb;text-decoration:none">✉️ Email {_h(opp.contact_name or "contracting officer")} (pre-filled)</a>')

    pop = ", ".join(x for x in [opp.pop_city, opp.pop_state] if x) or "n/a"
    return f"""
<div style="border:1px solid #e5e7eb;border-radius:8px;padding:14px 16px;margin:0 0 12px;background:#ffffff">
  <div style="display:block">
    <span style="background:{sc_color};color:#fff;padding:3px 10px;border-radius:5px;font-weight:bold;font-size:14px">{sc}</span>
    <a href="{_h(opp.url)}" style="font-size:15px;font-weight:bold;color:#111;text-decoration:none">&nbsp;{_h(opp.title or '(untitled)')}</a>
  </div>
  <div style="margin-top:6px">{' '.join(badges)}</div>
  <div style="margin-top:8px;font-size:12px;color:#555">
    {_h(opp.agency or '?')} &nbsp;·&nbsp; NAICS {_h(opp.naics_code)} ({_h(opp.sector)}) &nbsp;·&nbsp; 📍 {_h(pop)} &nbsp;·&nbsp; Sol# {_h(opp.sol_number or '—')}
  </div>
  <div style="margin-top:6px;font-size:13px">Deadline: <b style="color:{dl_color}">{_h(dl_txt)}</b>
    &nbsp;·&nbsp; Match {opp.match_score} &nbsp;·&nbsp; Value {_h(opp.value_bucket)}</div>
  {prior_html}
  {checklist_html}
  <div style="margin-top:10px;font-size:12px">{' &nbsp;|&nbsp; '.join(actions)}</div>
</div>"""


def build_email_html(top: List[Opportunity], new_ids: set, cfg: Dict[str, Any],
                     total_active: int) -> str:
    today = date.today().strftime("%A, %B %d, %Y")
    n_new = sum(1 for o in top if o.notice_id in new_ids)
    n_urgent = sum(1 for o in top if o.urgency >= 4)
    cards = "".join(_email_opp_card(o, cfg, o.notice_id in new_ids) for o in top)
    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<div style="max-width:680px;margin:0 auto;padding:16px">
  <div style="background:#111827;border-radius:8px;padding:16px 20px;color:#fff">
    <div style="font-size:18px;font-weight:bold">📋 Daily Contract Brief</div>
    <div style="font-size:12px;color:#9ca3af;margin-top:2px">{_h(today)}</div>
    <div style="margin-top:10px;font-size:13px">
      <b style="color:#a78bfa">{n_new} new today</b> &nbsp;·&nbsp;
      <b style="color:#f87171">{n_urgent} urgent</b> &nbsp;·&nbsp;
      {total_active} active tracked &nbsp;·&nbsp; showing top {len(top)} by actionability
    </div>
  </div>
  <div style="height:12px"></div>
  {cards if cards else '<div style="background:#fff;border-radius:8px;padding:24px;text-align:center;color:#888">No active opportunities matched today.</div>'}
  <div style="font-size:11px;color:#9ca3af;text-align:center;padding:8px 0 16px">
    contract_monitor.py · deadlines.ics attached — open it to load every deadline
    into your calendar with 2-day reminders · full report attached
  </div>
</div>
</body></html>"""


def send_email(cfg: Dict[str, Any], subject: str, html_body: str, text_body: str,
               attachments: Optional[List[Tuple[str, bytes, str, str]]] = None,
               high_priority: bool = False) -> bool:
    """attachments: list of (filename, data, maintype, subtype)."""
    em = cfg.get("email", {}) or {}
    host = em.get("smtp_host") or ""
    port = int(em.get("smtp_port") or 465)
    user = em.get("smtp_user") or ""
    password = em.get("smtp_password") or ""
    from_addr = em.get("from_addr") or user
    to_addrs = [a for a in (em.get("to_addrs") or []) if a]
    if not (host and user and password and to_addrs):
        LOG.warning("Email: smtp_host/smtp_user/smtp_password/to_addrs incomplete; skipping.")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="contract-monitor.local")
    if high_priority:
        msg["X-Priority"] = "1"
        msg["Importance"] = "high"
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    for fname, data, maintype, subtype in attachments or []:
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=fname)

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(),
                                  timeout=HTTP_TIMEOUT) as s:
                s.login(user, password)
                s.send_message(msg)
        else:  # 587 / 25 → STARTTLS
            with smtplib.SMTP(host, port, timeout=HTTP_TIMEOUT) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(user, password)
                s.send_message(msg)
        LOG.info("Email sent → %s (%s)", ", ".join(to_addrs), subject)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        LOG.error("Email send failed: %s", exc)
        return False


def maybe_send_email_digest(cfg: Dict[str, Any], conn: sqlite3.Connection,
                            new_alerts: List[Opportunity],
                            report_path: Optional[Path],
                            csv_path: Optional[Path]) -> None:
    em = cfg.get("email", {}) or {}
    if not em.get("enabled"):
        LOG.info("Email disabled in config.")
        return
    if em.get("only_when_new") and not new_alerts:
        LOG.info("Email: only_when_new set and nothing new — skipping digest.")
        return

    opps = _fetch_active(conn)
    top = opps[: int(em.get("top_n", 15))]
    new_ids = {o.notice_id for o in new_alerts}
    n_new = sum(1 for o in top if o.notice_id in new_ids)
    urgent_top = [o for o in top if o.urgency >= 4]

    # Subject that reads like a briefing, not a cron job.
    best = top[0] if top else None
    bits = []
    if n_new:
        bits.append(f"{n_new} new")
    if urgent_top:
        nearest = min((_days_left(o.response_deadline) or 99) for o in urgent_top)
        bits.append(f"closest due in {nearest}d")
    if best:
        bits.append(f"top: {best.title[:45]}")
    subject = "🔥 Contract Brief — " + " · ".join(bits) if bits else \
              f"📋 Contract Brief — {len(opps)} active tracked"

    text_lines = [f"Daily Contract Brief — {date.today().isoformat()}", ""]
    for o in top:
        text_lines.append(
            f"[{o.actionability_score}] {o.title} | due {o.response_deadline or 'TBD'} | {o.url}"
        )
    html = build_email_html(top, new_ids, cfg, total_active=len(opps))

    attachments: List[Tuple[str, bytes, str, str]] = []
    if em.get("attach_ics", True) and top:
        attachments.append(("deadlines.ics", build_ics(top).encode("utf-8"), "text", "calendar"))
    if em.get("attach_report", True) and report_path and report_path.exists():
        attachments.append((report_path.name, report_path.read_bytes(), "text", "markdown"))
    if em.get("attach_csv", True) and csv_path and csv_path.exists():
        attachments.append((csv_path.name, csv_path.read_bytes(), "text", "csv"))

    send_email(cfg, subject, html, "\n".join(text_lines), attachments,
               high_priority=bool(urgent_top))


def send_test_email(cfg: Dict[str, Any]) -> bool:
    """--email-test: verify SMTP creds without touching SAM/DB."""
    fake = Opportunity(
        notice_id="test-000", title="TEST — Fleet Vehicle Maintenance Services",
        sol_number="TEST-26-R-0001", posted_date=date.today().isoformat(),
        response_deadline=(date.today() + timedelta(days=6)).isoformat(),
        naics_code="811111", set_aside="Total Small Business Set-Aside",
        agency="TEST AGENCY", pop_city="Whittier", pop_state="CA",
        contact_name="Test Officer", contact_email="officer@example.com",
        url="https://sam.gov", sector="Other Services (repair, maintenance, personal)",
        urgency=4, value_bucket="M", match_score=85, local_advantage=True,
        actionability_score=91,
        checklist=["Confirm bonding capacity meets stated limits."],
        prior_summary=[
            {"recipient": "EXAMPLE CO", "amount": 120000, "action_date": "2026-01-15", "contract_number": "TEST123"},
            {"recipient": "SAMPLE LLC", "amount": 45000, "action_date": "2025-11-02", "contract_number": "TEST456"},
        ],
    )
    html = build_email_html([fake], {"test-000"}, cfg, total_active=1)
    ok = send_email(cfg, "✅ contract_monitor test email — you're wired up",
                    html, "contract_monitor test email — config works.",
                    [("deadlines.ics", build_ics([fake]).encode("utf-8"), "text", "calendar")])
    print("Test email sent." if ok else "Test email FAILED — check log above.")
    return ok


# --------------------------------------------------------------------------- #
# Report generation
# --------------------------------------------------------------------------- #

def _days_left(iso_date: str) -> Optional[int]:
    d = parse_date(iso_date)
    if not d:
        return None
    return (d - date.today()).days


def _row_to_opp(r: sqlite3.Row) -> Opportunity:
    return Opportunity(
        notice_id=r["notice_id"],
        title=r["title"] or "",
        sol_number=r["sol_number"] or "",
        posted_date=r["posted_date"] or "",
        response_deadline=r["response_deadline"] or "",
        naics_code=r["naics_code"] or "",
        set_aside_code=r["set_aside_code"] or "",
        set_aside=r["set_aside"] or "",
        agency=r["agency"] or "",
        sub_agency=r["sub_agency"] or "",
        office=r["office"] or "",
        pop_state=r["pop_state"] or "",
        pop_city=r["pop_city"] or "",
        pop_country=r["pop_country"] or "",
        contact_name=r["contact_name"] or "",
        contact_email=r["contact_email"] or "",
        contact_phone=r["contact_phone"] or "",
        description=r["description"] or "",
        description_url=r["description_url"] or "",
        url=r["url"] or "",
        sector=r["sector"] or "",
        tags=json.loads(r["tags_json"] or "[]"),
        urgency=r["urgency"] or 0,
        value_bucket=r["value_bucket"] or "",
        match_score=r["match_score"] or 0,
        local_advantage=bool(r["local_advantage"]),
        strong_incumbent=r["strong_incumbent"] or "",
        requirements=json.loads(r["requirements_json"] or "[]"),
        checklist=json.loads(r["checklist_json"] or "[]"),
        actionability_score=r["actionability_score"] or 0,
        prior_summary=json.loads(r["prior_summary_json"] or "[]"),
    )


def _fetch_active(conn: sqlite3.Connection) -> List[Opportunity]:
    prev = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT * FROM opportunities "
            "WHERE is_active = 1 "
            "ORDER BY actionability_score DESC, response_deadline ASC"
        )
        rows = cur.fetchall()
    finally:
        conn.row_factory = prev
    return [_row_to_opp(r) for r in rows]


def _fmt_money(n: float) -> str:
    if not n:
        return "$?"
    if n >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"${n/1_000:.1f}k"
    return f"${n:.0f}"


def _render_opp_block(opp: Opportunity) -> str:
    dleft = _days_left(opp.response_deadline)
    dl = opp.response_deadline or "TBD"
    if dleft is not None:
        dl += f" ({-dleft}d overdue)" if dleft < 0 else f" ({dleft}d left)"

    badges: List[str] = []
    if opp.local_advantage:
        badges.append("🏠 **Local Advantage**")
    if opp.set_aside:
        badges.append(f"🛡 {opp.set_aside}")
    if opp.strong_incumbent:
        badges.append(f"⚠️ **Strong Incumbent:** {opp.strong_incumbent}")
    if opp.urgency >= 4:
        badges.append("⏰ **Urgent**")

    lines: List[str] = [
        f"### [{opp.title or '(untitled)'}]({opp.url})",
        (
            f"- **Action Score:** {opp.actionability_score}   "
            f"**Match:** {opp.match_score}   "
            f"**Urgency:** {opp.urgency}/5   "
            f"**Value bucket:** {opp.value_bucket}"
        ),
    ]
    if badges:
        lines.append(f"- {'  '.join(badges)}")
    agency_line = opp.agency or "?"
    if opp.sub_agency:
        agency_line += f" › {opp.sub_agency}"
    if opp.office:
        agency_line += f" › {opp.office}"
    lines.append(f"- **Agency:** {agency_line}")
    lines.append(
        f"- **NAICS:** {opp.naics_code or '?'} — {opp.sector or '?'}   "
        f"**Sol #:** {opp.sol_number or '—'}"
    )
    pop = ", ".join(x for x in [opp.pop_city, opp.pop_state, opp.pop_country] if x)
    lines.append(f"- **Place of Performance:** {pop or 'Not specified'}")
    lines.append(f"- **Posted:** {opp.posted_date or '?'}   **Deadline:** {dl}")
    contact_bits = [x for x in [opp.contact_name, opp.contact_email, opp.contact_phone] if x]
    if contact_bits:
        lines.append(f"- **Contact:** {' | '.join(contact_bits)}")
    if opp.tags:
        lines.append(f"- **Tags:** {', '.join(opp.tags)}")

    if opp.requirements:
        lines.append(f"- **Requirements:** {', '.join(opp.requirements)}")
    if opp.checklist:
        lines.append("- **Bid-Prep Checklist:**")
        for bullet in opp.checklist:
            lines.append(f"  - [ ] {bullet}")

    if opp.prior_summary:
        lines.append("- **Prior Similar Awards (USAspending, last 24mo):**")
        for a in opp.prior_summary[:5]:
            recipient = a.get("recipient") or "?"
            amt = _fmt_money(_safe_float(a.get("amount")))
            dt = (a.get("action_date") or "")[:10]
            cn = a.get("contract_number") or ""
            lines.append(f"  - {recipient} — {amt} — {dt} — `{cn}`")
    else:
        lines.append("- **Prior Similar Awards:** none found via USAspending.")

    if opp.description:
        snip = re.sub(r"\s+", " ", opp.description).strip()[:400]
        lines.append(f"- **Description:** {snip}{'…' if len(opp.description) > 400 else ''}")
    elif opp.description_url:
        lines.append(f"- **Description URL:** <{opp.description_url}>")

    lines.append("")
    return "\n".join(lines)


def render_markdown(conn: sqlite3.Connection, out_path: Path, cfg: Dict[str, Any]) -> Path:
    opps = _fetch_active(conn)
    min_score = int(cfg.get("min_match_score", 60))
    today = date.today()

    high_urgent = [o for o in opps if o.match_score >= min_score and o.urgency >= 4]
    high = [o for o in opps if o.match_score >= min_score and o.urgency < 4]
    high_ids = {o.notice_id for o in high_urgent} | {o.notice_id for o in high}
    watchlist = [
        o for o in opps
        if o.notice_id not in high_ids
        and (o.tags or _set_aside_match(o, cfg.get("preferred_set_asides", [])))
    ]
    watch_ids = {o.notice_id for o in watchlist}

    by_sector: Dict[str, List[Opportunity]] = {}
    for o in opps:
        if o.notice_id in high_ids or o.notice_id in watch_ids:
            continue
        by_sector.setdefault(o.sector or "Other", []).append(o)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    parts: List[str] = []
    parts.append(f"# 📋 Federal Contract Brief — {today.isoformat()}\n")
    parts.append(
        f"_{len(opps)} active opportunities | "
        f"{len(high_urgent)} urgent high-match | "
        f"{len(high)} high-match | "
        f"{len(watchlist)} watchlist | "
        f"min_score={min_score}_\n"
    )
    focus = (cfg.get("business_profile") or {}).get("focus", "")
    if focus:
        parts.append(f"**Business focus:** {focus}\n")
    parts.append("---\n")

    parts.append("## 🔥 High-Match & Urgent\n")
    if not high_urgent:
        parts.append("_None today._\n")
    else:
        for o in sorted(high_urgent, key=lambda x: (-x.actionability_score, x.response_deadline or "9999")):
            parts.append(_render_opp_block(o))

    parts.append("## ⭐ High-Match\n")
    if not high:
        parts.append("_None today._\n")
    else:
        for o in sorted(high, key=lambda x: (-x.actionability_score, x.response_deadline or "9999")):
            parts.append(_render_opp_block(o))

    parts.append("## 🗂 By Sector\n")
    if not by_sector:
        parts.append("_Nothing outside the high-match / watchlist sections._\n")
    for sector in sorted(by_sector.keys()):
        group = sorted(by_sector[sector], key=lambda x: (x.response_deadline or "9999", -x.actionability_score))
        parts.append(f"### {sector} ({len(group)})\n")
        for o in group[:20]:  # cap per-sector so the report stays scannable
            b_bits = []
            if o.local_advantage:
                b_bits.append("🏠")
            if o.strong_incumbent:
                b_bits.append("⚠️")
            badge = " ".join(b_bits)
            parts.append(
                f"- **{o.actionability_score:>3}** {badge} "
                f"[{o.title or '(untitled)'}]({o.url}) — "
                f"{o.agency or '?'} — due {o.response_deadline or 'TBD'}"
            )
        parts.append("")

    parts.append("## 👀 Watchlist (below min but tagged / preferred set-aside)\n")
    if not watchlist:
        parts.append("_None today._\n")
    else:
        wl = sorted(watchlist, key=lambda x: (-x.actionability_score, x.response_deadline or "9999"))
        for o in wl[:25]:
            parts.append(
                f"- **{o.actionability_score:>3}** "
                f"[{o.title or '(untitled)'}]({o.url}) — "
                f"{o.set_aside or '—'} — due {o.response_deadline or 'TBD'}"
            )
        parts.append("")

    parts.append("---\n")
    parts.append("_Generated by contract_monitor.py — daily federal bid intel._\n")

    # EDIT: to post to Slack / email / Discord, call your webhook function here
    # with the assembled `body` string, or read the file after write().
    body = "\n".join(parts)
    out_path.write_text(body, encoding="utf-8")
    LOG.info("Wrote report → %s (%d bytes)", out_path, len(body))
    return out_path


def export_csv(conn: sqlite3.Connection, out_path: Path) -> Path:
    opps = _fetch_active(conn)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "actionability_score", "match_score", "urgency", "value_bucket",
        "notice_id", "title", "sol_number", "posted_date", "response_deadline",
        "naics_code", "sector", "set_aside", "agency", "sub_agency", "office",
        "pop_city", "pop_state", "local_advantage", "strong_incumbent",
        "tags", "requirements", "url",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(fields)
        for o in opps:
            w.writerow([
                o.actionability_score, o.match_score, o.urgency, o.value_bucket,
                o.notice_id, o.title, o.sol_number, o.posted_date, o.response_deadline,
                o.naics_code, o.sector, o.set_aside, o.agency, o.sub_agency, o.office,
                o.pop_city, o.pop_state, int(o.local_advantage), o.strong_incumbent,
                "|".join(o.tags), "|".join(o.requirements), o.url,
            ])
    LOG.info("Wrote CSV → %s (%d rows)", out_path, len(opps))
    return out_path


# --------------------------------------------------------------------------- #
# Enrich + orchestration
# --------------------------------------------------------------------------- #

def enrich(opp: Opportunity, cfg: Dict[str, Any], cache: UsaSpendingCache,
           fetch_desc: bool = False) -> None:
    if fetch_desc and opp.description_url and not opp.description:
        try:
            opp.description = fetch_description_text(opp.description_url)
        except Exception as exc:
            LOG.debug("desc fetch failed for %s: %s", opp.notice_id, exc)

    opp.sector = sector_from_naics(opp.naics_code)
    opp.urgency = urgency_from_deadline(opp.response_deadline)

    reqs, chk = extract_requirements(opp)
    opp.requirements = reqs
    opp.checklist = chk

    try:
        opp.prior_summary = cache.fetch(opp.naics_code, opp.agency)
    except Exception as exc:
        LOG.debug("prior fetch failed for %s: %s", opp.notice_id, exc)
        opp.prior_summary = []

    opp.value_bucket = value_bucket(opp.prior_summary)
    opp.strong_incumbent = detect_strong_incumbent(opp.prior_summary)

    score, is_local, local_bonus = compute_match_score(opp, cfg)
    opp.match_score = score
    opp.local_advantage = is_local
    opp.actionability_score = compute_actionability(opp, cfg, local_bonus)

    kw_tags = tag_keywords(opp, cfg.get("keywords", []))
    extras: List[str] = []
    if opp.urgency >= 4:
        extras.append("urgent")
    if opp.value_bucket and opp.value_bucket != "?":
        extras.append(f"value:{opp.value_bucket}")
    if opp.local_advantage:
        extras.append("local")
    if opp.strong_incumbent:
        extras.append("incumbent")
    for r in opp.requirements:
        slug = r.lower().replace(" ", "_").replace("/", "_")
        extras.append(f"req:{slug}")
    opp.tags = sorted(set(kw_tags + extras))


def run_update(cfg: Dict[str, Any], args: argparse.Namespace) -> None:
    lookback = int(args.lookback or cfg.get("lookback_days", 60))
    if args.dry_run:
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA)
    else:
        conn = init_db(Path(args.db or cfg["paths"]["db"]))

    cache = UsaSpendingCache(cfg)
    today_iso = date.today().isoformat()
    new_alerts: List[Opportunity] = []
    total = 0
    new_count = 0

    LOG.info("Starting SAM pull: lookback=%d days", lookback)
    for opp in fetch_sam_opportunities(cfg, lookback):
        total += 1
        try:
            enrich(opp, cfg, cache, fetch_desc=args.full)
        except Exception as exc:
            LOG.warning("Enrich failed for %s: %s", opp.notice_id, exc)
        try:
            is_new = upsert_opportunity(conn, opp, today_iso)
        except Exception as exc:
            LOG.warning("Upsert failed for %s: %s", opp.notice_id, exc)
            continue
        if is_new:
            new_count += 1
            new_alerts.append(opp)
        if total % 200 == 0:
            conn.commit()
    conn.commit()

    if args.full:
        LOG.info("--full: re-enriching all active rows + fetching description URLs")
        for existing in _fetch_active(conn):
            try:
                enrich(existing, cfg, cache, fetch_desc=True)
                upsert_opportunity(conn, existing, today_iso)
            except Exception as exc:
                LOG.warning("Re-enrich failed for %s: %s", existing.notice_id, exc)
        conn.commit()

    stale = mark_stale_inactive(conn)
    conn.commit()
    LOG.info("Pipeline done: %d fetched, %d new, %d marked stale-inactive.",
             total, new_count, stale)

    dist: Dict[str, int] = {}
    for o in _fetch_active(conn):
        dist[o.sector or "Other"] = dist.get(o.sector or "Other", 0) + 1
    LOG.info("Active by sector: %s", dict(sorted(dist.items())))

    if args.dry_run:
        LOG.info("--dry-run: skipping report + SMS.")
        return

    reports_dir = Path(args.reports_dir or cfg["paths"]["reports_dir"])
    report_path = render_markdown(conn, reports_dir / f"daily_{today_iso}.md", cfg)
    csv_path: Optional[Path] = None
    if args.csv:
        csv_path = export_csv(conn, reports_dir / f"daily_{today_iso}.csv")

    if not args.no_email:
        maybe_send_email_digest(cfg, conn, new_alerts, report_path, csv_path)
    else:
        LOG.info("Email disabled (--no-email).")

    if cfg.get("sms_enabled") and not args.no_sms:
        maybe_send_alerts(cfg, new_alerts)
    else:
        LOG.info("SMS disabled (config or --no-sms).")


def run_report_only(cfg: Dict[str, Any], args: argparse.Namespace) -> None:
    db_path = Path(args.db or cfg["paths"]["db"])
    if not db_path.exists():
        LOG.error("DB not found at %s; run --update first.", db_path)
        sys.exit(2)
    conn = sqlite3.connect(str(db_path))
    reports_dir = Path(args.reports_dir or cfg["paths"]["reports_dir"])
    today_iso = date.today().isoformat()
    render_markdown(conn, reports_dir / f"daily_{today_iso}.md", cfg)
    if args.csv:
        export_csv(conn, reports_dir / f"daily_{today_iso}.csv")


# --------------------------------------------------------------------------- #
# Always-on dashboard — stdlib only (http.server + threading).
# --------------------------------------------------------------------------- #

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# EDIT: tweak layout / colors / branding here. Kept as one string for
# single-file constraint. Uses vanilla JS + fetch + setInterval so any
# modern browser (including Chromium kiosk on the RPi5) works.
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<title>📋 Federal Contract Dashboard</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root {
  --bg:#0f1419; --fg:#e6e6e6; --muted:#8b95a1; --card:#1a2028;
  --border:#2a3441; --accent:#3b82f6; --urgent:#ef4444; --local:#22c55e;
  --warn:#f59e0b; --dim:#111820;
}
@media (prefers-color-scheme: light) {
  :root { --bg:#f7f8fa; --fg:#111; --muted:#556; --card:#fff;
          --border:#dde2e8; --dim:#eef1f5; }
}
* { box-sizing: border-box; }
body { margin:0; font: 14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
       background: var(--bg); color: var(--fg); }
header { padding: 10px 16px; border-bottom: 1px solid var(--border);
         display: flex; gap: 16px; align-items: center; flex-wrap: wrap;
         background: var(--dim); position: sticky; top: 0; z-index: 10; }
header h1 { margin: 0; font-size: 16px; font-weight: 700; }
header .meta { color: var(--muted); font-size: 12px; }
.pulse { display:inline-block; width:8px; height:8px; border-radius:50%;
         background: var(--local); margin-right:6px; animation: pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
.filters { padding: 10px 16px; display: flex; gap: 10px; flex-wrap: wrap;
           border-bottom: 1px solid var(--border); background: var(--dim); }
.filters label { display: flex; gap: 6px; align-items: center;
                 font-size: 12px; color: var(--muted); }
.filters input, .filters select {
  background: var(--card); color: var(--fg); border: 1px solid var(--border);
  border-radius: 4px; padding: 4px 8px; font-size: 13px;
}
.stat { padding: 4px 10px; background: var(--card); border-radius: 4px;
        font-size: 12px; border: 1px solid var(--border); }
main { padding: 16px; max-width: 1400px; margin: 0 auto; }
.card { background: var(--card); border: 1px solid var(--border);
        border-radius: 8px; padding: 12px 16px; margin-bottom: 10px; }
.card h3 { margin: 0 0 6px; font-size: 15px; display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.card h3 a { color: var(--accent); text-decoration: none; }
.card h3 a:hover { text-decoration: underline; }
.card .row { display: flex; flex-wrap: wrap; gap: 12px;
             font-size: 12px; color: var(--muted); margin: 3px 0; }
.badges { display: flex; gap: 6px; flex-wrap: wrap; margin: 6px 0 0; }
.badge { padding: 2px 8px; border-radius: 4px; font-size: 11px;
         font-weight: 600; background: var(--border); color: var(--fg); }
.badge.urgent { background: var(--urgent); color: #fff; }
.badge.local { background: var(--local); color: #fff; }
.badge.incumbent { background: var(--warn); color: #fff; }
.badge.setaside { background: var(--accent); color: #fff; }
.score { display: inline-block; padding: 2px 10px; background: var(--accent);
         color: #fff; border-radius: 4px; font-weight: 700; font-size: 13px; }
.score.low { background: var(--muted); }
.score.mid { background: var(--warn); }
.score.hi  { background: var(--local); }
.deadline { color: var(--warn); font-weight: 600; }
.deadline.past { color: var(--urgent); }
.checklist { color: var(--muted); font-size: 11px; margin-top: 4px;
             padding: 6px 10px; background: var(--dim); border-radius: 4px; }
.empty { padding: 40px; text-align: center; color: var(--muted); }
</style></head>
<body>
<header>
  <h1><span class="pulse"></span>Federal Contract Dashboard</h1>
  <div class="meta" id="meta">loading…</div>
  <div class="meta">refresh <span id="refresh_s">__REFRESH_S__</span>s</div>
</header>
<div class="filters">
  <label>Min action <input type="number" id="f_score" value="0" min="0" max="100" style="width:60px"></label>
  <label>Sector <select id="f_sector"><option value="">Any</option></select></label>
  <label>Urgency ≥ <select id="f_urg">
    <option value="0">Any</option><option value="2">2</option>
    <option value="3">3</option><option value="4">4</option><option value="5">5</option>
  </select></label>
  <label><input type="checkbox" id="f_local"> Local only</label>
  <label><input type="checkbox" id="f_setaside"> Set-aside only</label>
  <label>Search <input type="text" id="f_search" placeholder="title / agency / NAICS" style="width:200px"></label>
  <div class="stat" id="stat_count">–</div>
</div>
<main id="list"><div class="empty">Loading opportunities…</div></main>

<script>
const REFRESH_MS = __REFRESH_MS__;
let _opps = [];

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function daysLeft(iso) {
  if (!iso) return null;
  const d = new Date(iso + "T00:00:00");
  return Math.round((d - new Date()) / 86400000);
}
function scoreClass(s) { return s >= 70 ? 'hi' : s >= 40 ? 'mid' : 'low'; }

async function load() {
  try {
    const r = await fetch('/api/opportunities?ts=' + Date.now());
    if (!r.ok) throw new Error(r.status);
    const data = await r.json();
    _opps = data.opportunities || [];
    document.getElementById('meta').textContent =
      `${data.count} active · db ${data.db_mtime || '?'} · loaded ${new Date().toLocaleTimeString()}`;
    const sectors = [...new Set(_opps.map(o => o.sector).filter(Boolean))].sort();
    const sel = document.getElementById('f_sector');
    const cur = sel.value;
    sel.innerHTML = '<option value="">Any</option>' +
      sectors.map(s => `<option${s===cur?' selected':''}>${esc(s)}</option>`).join('');
    render();
  } catch (e) {
    document.getElementById('meta').textContent = 'load error: ' + e.message;
  }
}
function render() {
  const minScore = +document.getElementById('f_score').value || 0;
  const sector = document.getElementById('f_sector').value;
  const minUrg = +document.getElementById('f_urg').value || 0;
  const localOnly = document.getElementById('f_local').checked;
  const saOnly = document.getElementById('f_setaside').checked;
  const q = document.getElementById('f_search').value.trim().toLowerCase();
  const filtered = _opps.filter(o => {
    if (o.actionability_score < minScore) return false;
    if (sector && o.sector !== sector) return false;
    if (o.urgency < minUrg) return false;
    if (localOnly && !o.local_advantage) return false;
    if (saOnly && !o.set_aside) return false;
    if (q) {
      const hay = ((o.title||'') + ' ' + (o.agency||'') + ' ' + (o.naics_code||'')).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  document.getElementById('stat_count').textContent =
    `${filtered.length} / ${_opps.length} opps`;
  const list = document.getElementById('list');
  if (!filtered.length) {
    list.innerHTML = '<div class="empty">No opportunities match the current filters.</div>';
    return;
  }
  list.innerHTML = filtered.slice(0, 300).map(o => {
    const dl = daysLeft(o.response_deadline);
    let dlStr = o.response_deadline ? o.response_deadline : 'TBD';
    let dlCls = 'deadline';
    if (dl !== null) {
      if (dl < 0) { dlStr += ` (${-dl}d overdue)`; dlCls += ' past'; }
      else dlStr += ` (${dl}d left)`;
    }
    const badges = [];
    if (o.local_advantage) badges.push('<span class="badge local">🏠 Local Advantage</span>');
    if (o.set_aside) badges.push(`<span class="badge setaside">🛡 ${esc(o.set_aside)}</span>`);
    if (o.strong_incumbent) badges.push(`<span class="badge incumbent">⚠️ Incumbent: ${esc(o.strong_incumbent)}</span>`);
    if (o.urgency >= 4) badges.push('<span class="badge urgent">⏰ Urgent</span>');
    const pop = [o.pop_city, o.pop_state, o.pop_country].filter(Boolean).map(esc).join(', ') || 'n/a';
    const checklist = (o.checklist || []).slice(0, 3).map(esc).join(' · ');
    return `<div class="card">
      <h3>
        <span class="score ${scoreClass(o.actionability_score)}">${o.actionability_score}</span>
        <a href="${esc(o.url)}" target="_blank" rel="noopener">${esc(o.title || '(untitled)')}</a>
      </h3>
      <div class="row">
        <span>Match <b>${o.match_score}</b></span>
        <span>Urgency <b>${o.urgency}/5</b></span>
        <span>Value <b>${esc(o.value_bucket)}</b></span>
        <span class="${dlCls}">Due ${esc(dlStr)}</span>
      </div>
      <div class="row">
        <span>${esc(o.agency || '?')}${o.sub_agency ? ' › ' + esc(o.sub_agency) : ''}</span>
        <span>NAICS ${esc(o.naics_code)} — ${esc(o.sector)}</span>
        <span>📍 ${pop}</span>
        <span>Sol# ${esc(o.sol_number) || '—'}</span>
      </div>
      ${badges.length ? `<div class="badges">${badges.join('')}</div>` : ''}
      ${checklist ? `<div class="checklist">✅ ${checklist}</div>` : ''}
    </div>`;
  }).join('');
}
document.querySelectorAll('.filters input, .filters select')
  .forEach(el => el.addEventListener('input', render));
load();
setInterval(load, REFRESH_MS);
</script>
</body></html>
"""


def _opp_to_dict(o: Opportunity) -> Dict[str, Any]:
    return {
        "notice_id": o.notice_id,
        "title": o.title,
        "sol_number": o.sol_number,
        "posted_date": o.posted_date,
        "response_deadline": o.response_deadline,
        "naics_code": o.naics_code,
        "sector": o.sector,
        "set_aside": o.set_aside,
        "set_aside_code": o.set_aside_code,
        "agency": o.agency,
        "sub_agency": o.sub_agency,
        "office": o.office,
        "pop_city": o.pop_city,
        "pop_state": o.pop_state,
        "pop_country": o.pop_country,
        "url": o.url,
        "tags": o.tags,
        "urgency": o.urgency,
        "value_bucket": o.value_bucket,
        "match_score": o.match_score,
        "local_advantage": o.local_advantage,
        "strong_incumbent": o.strong_incumbent,
        "requirements": o.requirements,
        "checklist": o.checklist,
        "actionability_score": o.actionability_score,
    }


def _make_dashboard_handler(cfg: Dict[str, Any], db_path: Path):
    dash_cfg = cfg.get("dashboard", {}) or {}
    refresh_s = int(dash_cfg.get("refresh_seconds", 30))
    top_n = int(dash_cfg.get("top_n", 200))
    html_page = (
        DASHBOARD_HTML
        .replace("__REFRESH_MS__", str(max(5, refresh_s) * 1000))
        .replace("__REFRESH_S__", str(max(5, refresh_s)))
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:  # quieter
            LOG.debug("dashboard: " + fmt, *args)

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(200, html_page.encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/api/opportunities":
                self._serve_api()
                return
            if path == "/api/health":
                self._send(200, b'{"ok":true}', "application/json")
                return
            self._send(404, b"not found", "text/plain")

        def _serve_api(self) -> None:
            if not db_path.exists():
                payload = {"count": 0, "opportunities": [], "error": "db not found"}
                self._send(200, json.dumps(payload).encode("utf-8"), "application/json")
                return
            try:
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                try:
                    opps = _fetch_active(conn)
                finally:
                    conn.close()
                items = [_opp_to_dict(o) for o in opps[:top_n]]
                mtime = datetime.fromtimestamp(db_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                payload = {
                    "count": len(opps),
                    "returned": len(items),
                    "db_mtime": mtime,
                    "opportunities": items,
                }
                self._send(200, json.dumps(payload).encode("utf-8"), "application/json")
            except Exception as exc:
                LOG.warning("dashboard api error: %s", exc)
                self._send(
                    500,
                    json.dumps({"error": str(exc)}).encode("utf-8"),
                    "application/json",
                )

    return Handler


def run_dashboard(cfg: Dict[str, Any], args: argparse.Namespace) -> None:
    dash_cfg = cfg.get("dashboard", {}) or {}
    host = args.host or dash_cfg.get("host", "0.0.0.0")
    port = int(args.port or dash_cfg.get("port", 8080))
    db_path = Path(args.db or cfg["paths"]["db"])
    handler = _make_dashboard_handler(cfg, db_path)
    server = ThreadingHTTPServer((host, port), handler)
    LOG.info("Dashboard listening on http://%s:%d/  (DB: %s)", host, port, db_path)
    LOG.info("Open on RPi5: http://localhost:%d  |  On LAN: http://<pi-ip>:%d", port, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOG.info("Dashboard interrupted.")
    finally:
        server.server_close()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="contract_monitor",
        description="RPi-friendly SAM.gov federal contract intel pipeline.",
    )
    p.add_argument("--update", action="store_true",
                   help="Fetch + enrich + report (default action).")
    p.add_argument("--full", action="store_true",
                   help="Also re-enrich all active rows + fetch description URLs.")
    p.add_argument("--report-only", action="store_true",
                   help="Regenerate today's report from DB (no network).")
    p.add_argument("--dry-run", action="store_true",
                   help="Fetch + classify but skip DB writes, report, and SMS.")
    p.add_argument("--csv", action="store_true",
                   help="Also emit a sorted CSV alongside the markdown report.")
    p.add_argument("--serve", action="store_true",
                   help="Start the always-on dashboard HTTP server.")
    p.add_argument("--host", default=None,
                   help="Dashboard bind host (default from config, then 0.0.0.0).")
    p.add_argument("--port", type=int, default=None,
                   help="Dashboard port (default from config, then 8080).")
    p.add_argument("--config", default="config.yaml",
                   help="Path to config.yaml (default: ./config.yaml).")
    p.add_argument("--db", default=None, help="Override SQLite DB path.")
    p.add_argument("--reports-dir", default=None, help="Override reports output directory.")
    p.add_argument("--lookback", type=int, default=None, help="Override lookback_days.")
    p.add_argument("--no-email", action="store_true", help="Force email digest off for this run.")
    p.add_argument("--email-test", action="store_true",
                   help="Send a test email (verifies SMTP creds; no SAM fetch).")
    p.add_argument("--no-sms", action="store_true", help="Force SMS disabled for this run.")
    p.add_argument("--verbose", action="store_true", help="DEBUG-level logging.")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    cfg = load_config(Path(args.config))
    try:
        if args.email_test:
            return 0 if send_test_email(cfg) else 1
        if args.serve:
            run_dashboard(cfg, args)
        elif args.report_only:
            run_report_only(cfg, args)
        else:
            run_update(cfg, args)
    except KeyboardInterrupt:
        LOG.warning("Interrupted.")
        return 130
    except Exception:
        LOG.exception("Fatal error during pipeline run.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
