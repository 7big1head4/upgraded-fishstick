#!/usr/bin/env bash
#
# install.sh — one-shot setup for contract_monitor.py on a Raspberry Pi.
#
# Installs Python deps, wires up the daily cron job (with self-update), and
# optionally installs the always-on dashboard as a systemd service.
#
# Usage:
#   ./install.sh                     # interactive, sensible defaults
#   ./install.sh --time 06:15        # daily run time (24h local), default 06:15
#   ./install.sh --no-self-update    # cron runs without pulling latest code
#   ./install.sh --dashboard         # also install + start the dashboard service
#   ./install.sh --port 8080         # dashboard port (with --dashboard)
#   ./install.sh --uninstall         # remove the cron line (and service)
#   ./install.sh --help
#
set -euo pipefail

# ---- defaults ---------------------------------------------------------------
RUN_TIME="06:15"
SELF_UPDATE=1
WITH_DASHBOARD=0
DASH_PORT=8080
UNINSTALL=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3 || true)"
CRON_TAG="# contract_monitor (managed by install.sh)"

# ---- args -------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --time) RUN_TIME="$2"; shift 2 ;;
    --no-self-update) SELF_UPDATE=0; shift ;;
    --dashboard) WITH_DASHBOARD=1; shift ;;
    --port) DASH_PORT="$2"; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help)
      sed -n '3,20p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$PY" ]]; then
  echo "ERROR: python3 not found. Run: sudo apt-get install -y python3 python3-pip" >&2
  exit 1
fi

# ---- uninstall path ---------------------------------------------------------
# Print the current crontab minus any line we manage. Never fails (grep
# finding nothing must not abort the script under `set -e`).
current_crontab_without_ours() {
  crontab -l 2>/dev/null | grep -v -F "$CRON_TAG" | grep -v "contract_monitor.py" || true
}

if [[ "$UNINSTALL" == "1" ]]; then
  echo "Removing contract_monitor cron line..."
  current_crontab_without_ours | crontab -
  if systemctl list-unit-files 2>/dev/null | grep -q contract-dashboard; then
    sudo systemctl disable --now contract-dashboard 2>/dev/null || true
    sudo rm -f /etc/systemd/system/contract-dashboard.service
    sudo systemctl daemon-reload
    echo "Removed dashboard service."
  fi
  echo "Done."
  exit 0
fi

# ---- parse HH:MM into cron fields ------------------------------------------
if [[ ! "$RUN_TIME" =~ ^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$ ]]; then
  echo "ERROR: --time must be HH:MM (24h), e.g. 06:15" >&2
  exit 2
fi
CRON_HOUR="${RUN_TIME%%:*}"; CRON_HOUR="${CRON_HOUR#0}"; CRON_HOUR="${CRON_HOUR:-0}"
CRON_MIN="${RUN_TIME##*:}";  CRON_MIN="${CRON_MIN#0}";   CRON_MIN="${CRON_MIN:-0}"

echo "==> contract_monitor installer"
echo "    dir:         $SCRIPT_DIR"
echo "    daily run:   $RUN_TIME  (cron: $CRON_MIN $CRON_HOUR * * *)"
echo "    self-update: $([[ $SELF_UPDATE == 1 ]] && echo on || echo off)"
echo

# ---- 1. dependencies --------------------------------------------------------
echo "==> Installing Python dependencies (requests, pyyaml)..."
if [[ -f "$SCRIPT_DIR/requirements.txt" ]]; then
  pip3 install --user -r "$SCRIPT_DIR/requirements.txt"
else
  pip3 install --user requests pyyaml
fi

# ---- 2. first-run config bootstrap -----------------------------------------
if [[ ! -f "$SCRIPT_DIR/config.yaml" ]]; then
  echo "==> Creating starter config.yaml..."
  ( cd "$SCRIPT_DIR" && "$PY" contract_monitor.py --report-only >/dev/null 2>&1 || true )
  echo "    Edit $SCRIPT_DIR/config.yaml — set keywords, NAICS, locations, email."
fi

# ---- 3. SAM API key env file -----------------------------------------------
SAM_ENV="$HOME/.sam_env"
if [[ ! -f "$SAM_ENV" ]]; then
  cat > "$SAM_ENV" <<EOF
# contract_monitor secrets — sourced by cron. Keep this file private (0600).
export SAM_API_KEY="REPLACE_WITH_YOUR_SAM_KEY"
# Optional: Gmail App Password for email alerts (or set in config.yaml)
# export EMAIL_PASSWORD="your_16_char_app_password"
EOF
  chmod 600 "$SAM_ENV"
  echo "==> Wrote $SAM_ENV (0600) — put your SAM.gov key in it."
else
  echo "==> Using existing $SAM_ENV"
fi

# ---- 4. cron job ------------------------------------------------------------
SELF_FLAG=""
[[ "$SELF_UPDATE" == "1" ]] && SELF_FLAG="--self-update "
CRON_LINE="$CRON_MIN $CRON_HOUR * * * . \$HOME/.sam_env && cd $SCRIPT_DIR && $PY contract_monitor.py ${SELF_FLAG}--update --csv >> $SCRIPT_DIR/monitor.log 2>&1 $CRON_TAG"

echo "==> Installing daily cron job..."
# Remove any prior managed line, then append the fresh one (idempotent).
{ current_crontab_without_ours; echo "$CRON_LINE"; } | crontab -
echo "    $CRON_LINE"

# ---- 5. optional dashboard service -----------------------------------------
if [[ "$WITH_DASHBOARD" == "1" ]]; then
  echo "==> Installing dashboard systemd service on port $DASH_PORT..."
  UNIT=/etc/systemd/system/contract-dashboard.service
  sudo tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=Contract Monitor Dashboard
After=network-online.target

[Service]
User=$USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$PY $SCRIPT_DIR/contract_monitor.py --serve --port $DASH_PORT
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable --now contract-dashboard
  IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  echo "    Dashboard: http://${IP:-<pi-ip>}:$DASH_PORT"
fi

echo
echo "==> Done. Next steps:"
echo "    1. Put your SAM.gov key in  $SAM_ENV"
echo "    2. Edit  $SCRIPT_DIR/config.yaml  (keywords / NAICS / locations / email)"
echo "    3. Test: . \$HOME/.sam_env && cd $SCRIPT_DIR && $PY contract_monitor.py --dry-run --lookback 5"
echo "    4. Email test (after email config): $PY contract_monitor.py --email-test"
echo "    Cron will run daily at $RUN_TIME — watch  $SCRIPT_DIR/monitor.log"
