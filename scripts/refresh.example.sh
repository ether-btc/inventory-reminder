#!/usr/bin/env bash
# refresh.example.sh — regenerate the repo inventory, then the system
# inventory, then report drift. Wire this into cron or a service.
#
# Point INVENTORY_CONFIG at your JSON config (see config.example.json);
# without it the scripts use their built-in defaults (~/.hermes layout).
set -uo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LOG=${LOG:-"$SCRIPT_DIR/refresh.log"}
mkdir -p "$(dirname "$LOG")"
TS() { date -Iseconds; }

echo "[$(TS)] starting inventory refresh" >> "$LOG"

# 1. repo inventory first (REPOS.md + repos.json)
python3 "$SCRIPT_DIR/repo-inventory.py" --write >> "$LOG" 2>&1
rc=$?
if [[ $rc -ne 0 ]]; then
  echo "[$(TS)] repo-inventory FAILED (exit $rc)" >> "$LOG"
  exit $rc
fi

# 2. full system inventory
python3 "$SCRIPT_DIR/system-inventory.py" --write >> "$LOG" 2>&1
rc=$?
if [[ $rc -ne 0 ]]; then
  echo "[$(TS)] system-inventory FAILED (exit $rc)" >> "$LOG"
  exit $rc
fi

# 3. drift check (exit 1 on drift — cron-friendly)
python3 "$SCRIPT_DIR/system-inventory.py" --check >> "$LOG" 2>&1
rc=$?

# 4. one-line summary
SUMMARY=$(python3 "$SCRIPT_DIR/system-inventory.py" --summary 2>/dev/null)
echo "[$(TS)] drift_check_exit=$rc" >> "$LOG"
echo "[$(TS)] $SUMMARY" >> "$LOG"

echo "$SUMMARY"
[[ $rc -eq 0 ]] && exit 0 || exit $rc
