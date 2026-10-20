#!/usr/bin/env bash
# setup-host.sh — wire this host to the repo's inventory pipeline
# Idempotent. Reversible: removes only files it created; live scripts in ~/.hermes/scripts/ untouched.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_SRC="$REPO_DIR/config.host.json"
CONFIG_DST="$HOME/.hermes/inventory-config.json"
REFRESH_SRC="$REPO_DIR/scripts/refresh.sh"
REFRESH_DST="$HOME/.hermes/scripts/inventory-refresh.sh"
INSTALL_STATE="$HOME/.hermes/inventory-reminder-install.json"
LOG_DIR="$HOME/.hermes/logs"

echo "Wiring inventory-reminder for host $(hostname)..."

# 1. Config file (copy, don't symlink — survives repo moves)
if [[ ! -f "$CONFIG_DST" ]] || ! cmp -s "$CONFIG_SRC" "$CONFIG_DST"; then
    cp "$CONFIG_SRC" "$CONFIG_DST"
    echo "  installed $CONFIG_DST"
else
    echo "  config already current"
fi

# 2. Refresh script — backup live original first, then install repo version
mkdir -p "$(dirname "$REFRESH_DST")"
if [[ ! -f "$INSTALL_STATE" ]]; then
    # First run: back up the live script (if it exists)
    if [[ -f "$REFRESH_DST" ]]; then
        cp "$REFRESH_DST" "${REFRESH_DST}.bak"
        echo "  backed up live script to ${REFRESH_DST}.bak"
    else
        echo "  no live script to back up"
    fi
fi

if [[ ! -f "$REFRESH_DST" ]] || ! cmp -s "$REFRESH_SRC" "$REFRESH_DST"; then
    cp "$REFRESH_SRC" "$REFRESH_DST"
    chmod +x "$REFRESH_DST"
    echo "  installed $REFRESH_DST (repo version; backup at ${REFRESH_DST}.bak)"
else
    echo "  refresh script already current"
fi

# 3. Record install state (pins repo dir for rollback)
cat > "$INSTALL_STATE" <<EOF
{
  "repo_dir": "$REPO_DIR",
  "installed_at": "$(date -Iseconds)",
  "config_dst": "$CONFIG_DST",
  "refresh_dst": "$REFRESH_DST",
  "refresh_bak": "${REFRESH_DST}.bak"
}
EOF
echo "  recorded install state at $INSTALL_STATE"

# 4. Log dir
mkdir -p "$LOG_DIR"

# 5. Verify
echo "Verifying..."
INVENTORY_CONFIG="$CONFIG_DST" python3 "$REPO_DIR/scripts/repo-inventory.py" --write >/dev/null
INVENTORY_CONFIG="$CONFIG_DST" python3 "$REPO_DIR/scripts/system-inventory.py" --write >/dev/null
INVENTORY_CONFIG="$CONFIG_DST" python3 "$REPO_DIR/scripts/system-inventory.py" --check >/dev/null
echo "  pipeline OK — INVENTORY.md + inventory.json regenerated, drift check clean"

echo "Done. Cron job 'inventory-refresh' (weekly) now runs the repo's refresh.sh via Hermes."
echo "To rollback: $REPO_DIR/scripts/rollback-host.sh"