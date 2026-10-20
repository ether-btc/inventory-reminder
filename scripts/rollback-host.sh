#!/usr/bin/env bash
# uninstall-host.sh — cleanly remove inventory-reminder wiring from this host.
# Reverses setup-host.sh completely: restores/removes the refresh script,
# removes config, install-state, generated outputs, logs, and pycache.
# Safe to run multiple times (idempotent). Live scripts in ~/.hermes/scripts/
# other than inventory-refresh.sh are never touched.
set -uo pipefail

INSTALL_STATE="$HOME/.hermes/inventory-reminder-install.json"
CONFIG_DST="$HOME/.hermes/inventory-config.json"
REFRESH_DST="$HOME/.hermes/scripts/inventory-refresh.sh"
LOG_FILE="$HOME/.hermes/logs/inventory-refresh.log"
OUT_JSON="$HOME/.hermes/inventory.json"
OUT_MD="$HOME/.hermes/INVENTORY.md"

echo "Uninstalling inventory-reminder from $(hostname)..."

removed=0
restored=0

# 1. Read install-state if present (captures what setup-host.sh installed)
REPO_DIR=""
REFRESH_BAK=""
if [[ -f "$INSTALL_STATE" ]]; then
    REPO_DIR=$(jq -r '.repo_dir // empty' "$INSTALL_STATE" 2>/dev/null || true)
    CONFIG_DST=$(jq -r '.config_dst // empty' "$INSTALL_STATE" 2>/dev/null || true)
    REFRESH_DST=$(jq -r '.refresh_dst // empty' "$INSTALL_STATE" 2>/dev/null || true)
    REFRESH_BAK=$(jq -r '.refresh_bak // empty' "$INSTALL_STATE" 2>/dev/null || true)
fi

# 2. Restore the original live refresh script from backup, if one was made
if [[ -n "$REFRESH_BAK" && -f "$REFRESH_BAK" ]]; then
    cp "$REFRESH_BAK" "$REFRESH_DST"
    chmod +x "$REFRESH_DST"
    rm -f "$REFRESH_BAK"
    echo "  restored $REFRESH_DST from backup ($REFRESH_BAK)"
    restored=1
elif [[ -f "$REFRESH_DST" ]]; then
    # No backup: setup-host.sh installed the repo version over nothing prior.
    # Remove it so any prior original takes over again.
    rm -f "$REFRESH_DST"
    echo "  removed $REFRESH_DST (no prior backup to restore from)"
    removed=1
fi

# 3. Remove generated outputs that setup-host.sh's verification run created
for f in "$OUT_JSON" "$OUT_MD"; do
    if [[ -f "$f" ]]; then
        rm -f "$f"
        echo "  removed $f"
        removed=1
    fi
done

# 4. Remove config file
if [[ -f "$CONFIG_DST" ]]; then
    rm -f "$CONFIG_DST"
    echo "  removed $CONFIG_DST"
    removed=1
fi

# 5. Remove refresh log
if [[ -f "$LOG_FILE" ]]; then
    rm -f "$LOG_FILE"
    echo "  removed $LOG_FILE"
    removed=1
fi

# 6. Remove install state
if [[ -f "$INSTALL_STATE" ]]; then
    rm -f "$INSTALL_STATE"
    echo "  removed $INSTALL_STATE"
    removed=1
fi

# 7. Remove pycache created by running the scanners
REPO_SCRIPTS="${REPO_DIR:-}/scripts"
if [[ -n "$REPO_DIR" && -d "$REPO_SCRIPTS/__pycache__" ]]; then
    rm -rf "$REPO_SCRIPTS/__pycache__"
    echo "  removed $REPO_SCRIPTS/__pycache__"
    removed=1
fi

if [[ $removed -eq 0 && $restored -eq 0 ]]; then
    echo "  nothing installed — host already clean"
fi

# 8. Verify nothing of ours remains
remaining=0
for f in "$CONFIG_DST" "$INSTALL_STATE" "$LOG_FILE"; do
    [[ -f "$f" ]] && { echo "  WARNING: $f still present"; remaining=1; }
done
if [[ -f "$REFRESH_DST" ]]; then
    echo "  NOTE: $REFRESH_DST still present (no backup existed to restore from)"
fi

if [[ $remaining -eq 0 ]]; then
    echo "Uninstall complete — inventory-reminder fully removed from this host."
else
    echo "Uninstall partially complete — some files remain (see WARNING above)."
fi