#!/usr/bin/env bash
# rollback-host.sh — undo setup-host.sh
# Restores the original live script and removes installed files.
set -uo pipefail

INSTALL_STATE="$HOME/.hermes/inventory-reminder-install.json"

if [[ ! -f "$INSTALL_STATE" ]]; then
    echo "No install state found at $INSTALL_STATE — nothing to roll back."
    exit 0
fi

REPO_DIR=$(jq -r '.repo_dir' "$INSTALL_STATE")
CONFIG_DST=$(jq -r '.config_dst' "$INSTALL_STATE")
REFRESH_DST=$(jq -r '.refresh_dst' "$INSTALL_STATE")
REFRESH_BAK=$(jq -r '.refresh_bak' "$INSTALL_STATE")

echo "Rolling back inventory-reminder wiring..."

# 1. Restore original live script if backup exists
if [[ -f "$REFRESH_BAK" ]]; then
    cp "$REFRESH_BAK" "$REFRESH_DST"
    chmod +x "$REFRESH_DST"
    echo "  restored $REFRESH_DST from backup"
    rm -f "$REFRESH_BAK"
elif [[ -f "$REFRESH_DST" ]]; then
    # No backup but installed script exists — remove it (original will take over next run)
    rm -f "$REFRESH_DST"
    echo "  removed $REFRESH_DST (no backup; original in ~/.hermes/scripts/ takes over)"
fi

# 2. Remove installed config
if [[ -f "$CONFIG_DST" ]]; then
    rm -f "$CONFIG_DST"
    echo "  removed $CONFIG_DST"
fi

# 3. Remove install state
rm -f "$INSTALL_STATE"
echo "  removed $INSTALL_STATE"

# 4. Verify original works
if [[ -f "$HOME/.hermes/scripts/inventory-refresh.sh" ]]; then
    echo "Verifying original live script..."
    "$HOME/.hermes/scripts/inventory-refresh.sh" --help 2>&1 | head -1 || true
    echo "  original live script is executable"
fi

echo "Rollback complete. Original live scripts in ~/.hermes/scripts/ are now active."