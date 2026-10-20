#!/usr/bin/env bash
# refresh.sh — repo-driven inventory refresh (reads config from INVENTORY_CONFIG)
set -uo pipefail
export PATH="/usr/local/go/bin:/usr/local/bin:$HOME/.local/bin:$PATH"

CONFIG="${INVENTORY_CONFIG:-$HOME/.hermes/inventory-config.json}"
LOG="$HOME/.hermes/logs/inventory-refresh.log"
mkdir -p "$(dirname "$LOG")"
TS() { date -Iseconds; }

echo "[$(TS)] starting inventory refresh (config: $CONFIG)" >> "$LOG"

# 1. repo inventory
python3 "$(dirname "$0")/repo-inventory.py" --config "$CONFIG" --write >> "$LOG" 2>&1
rc=$?
[[ $rc -ne 0 ]] && { echo "[$(TS)] repo-inventory FAILED (exit $rc)" >> "$LOG"; exit $rc; }

# 2. system inventory
python3 "$(dirname "$0")/system-inventory.py" --config "$CONFIG" --write >> "$LOG" 2>&1
rc=$?
[[ $rc -ne 0 ]] && { echo "[$(TS)] system-inventory FAILED (exit $rc)" >> "$LOG"; exit $rc; }

# 3. drift check
python3 "$(dirname "$0")/system-inventory.py" --config "$CONFIG" --check >> "$LOG" 2>&1
rc=$?

# 4. summary
SUMMARY=$(python3 "$(dirname "$0")/system-inventory.py" --config "$CONFIG" --summary 2>/dev/null)
echo "[$(TS)] drift_check_exit=$rc" >> "$LOG"
echo "[$(TS)] $SUMMARY" >> "$LOG"

echo "$SUMMARY"
[[ $rc -eq 0 ]] && exit 0 || exit $rc