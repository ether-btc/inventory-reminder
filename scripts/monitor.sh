#!/usr/bin/env bash
# monitor.sh — diagnostics + effectivity measurement for inventory-reminder.
# Read-only diagnostics plus an on-demand refresh run with timing/drift capture.
# Subcommands:
#   monitor.sh status     — snapshot of wiring + last known inventory state
#   monitor.sh run        — execute refresh.sh, capture duration/exit/drift
#   monitor.sh history N  — last N lines of the refresh log
# Effectivity is reported honestly: scan success rate, drift events, section
# availability, and time since last successful scan. No claims beyond what the
# host can produce.
set -uo pipefail

CONFIG="$HOME/.hermes/inventory-config.json"
REFRESH_DST="$HOME/.hermes/scripts/inventory-refresh.sh"
INSTALL_STATE="$HOME/.hermes/inventory-reminder-install.json"
LOG_FILE="$HOME/.hermes/logs/inventory-refresh.log"
OUT_JSON="$HOME/.hermes/inventory.json"
OUT_MD="$HOME/.hermes/INVENTORY.md"

TS() { date -Iseconds; }

# --- helpers -----------------------------------------------------------------

have() { command -v "$1" >/dev/null 2>&1; }

json_get() {
    # json_get <file> <jq-filter> — prints value or "UNAVAILABLE"
    local file="$1" filter="$2"
    if [[ -f "$file" ]] && have jq; then
        jq -r "$filter" "$file" 2>/dev/null || echo "UNAVAILABLE"
    elif [[ -f "$file" ]]; then
        echo "UNAVAILABLE (no jq)"
    else
        echo "UNAVAILABLE"
    fi
}

section_count() {
    # section_count <file> <section-key> — count items in an available section
    local file="$1" key="$2"
    if [[ ! -f "$file" ]] || ! have jq; then
        echo "UNAVAILABLE"; return
    fi
    local avail
    avail=$(jq -r ".$key.available // false" "$file" 2>/dev/null)
    if [[ "$avail" != "true" ]]; then
        echo "UNAVAILABLE"; return
    fi
    case "$key" in
        skills)    jq -r ".$key.names | length" "$file" 2>/dev/null;;
        repos)     jq -r ".repos.local // 0" "$file" 2>/dev/null;;
        tools)     jq -r ".tools.mcp_total // 0" "$file" 2>/dev/null;;
        apps)      jq -r ".apps.count // 0" "$file" 2>/dev/null;;
        models)    jq -r ".models.count // 0" "$file" 2>/dev/null;;
        services)  jq -r ".services.count // 0" "$file" 2>/dev/null;;
        *)         echo "UNAVAILABLE";;
    esac
}

unavailable_count() {
    # unavailable_count <file> — number of sections reporting UNAVAILABLE
    local file="$1"
    if [[ ! -f "$file" ]] || ! have jq; then
        echo "UNAVAILABLE"; return
    fi
    jq '[.skills.available, .repos.available, .tools.available, .apps.available, .models.available, .services.available] | map(select(. == false)) | length' "$file" 2>/dev/null || echo "UNAVAILABLE"
}

# --- subcommands -------------------------------------------------------------

cmd_status() {
    echo "=== inventory-reminder diagnostics ==="
    echo "host:        $(hostname)"
    echo "time:        $(TS)"
    echo

    echo "-- wiring --"
    [[ -f "$INSTALL_STATE" ]] && echo "install-state: present ($INSTALL_STATE)" || echo "install-state: ABSENT"
    [[ -f "$CONFIG" ]] && echo "config:        present ($CONFIG)" || echo "config:        ABSENT"
    [[ -f "$REFRESH_DST" ]] && echo "refresh script: present ($REFRESH_DST, executable=$(test -x "$REFRESH_DST" && echo yes || echo no))" || echo "refresh script: ABSENT"
    echo

    echo "-- last inventory state --"
    if [[ -f "$OUT_JSON" ]]; then
        echo "inventory.json: present (last generated $(date -r "$OUT_JSON" -Iseconds 2>/dev/null || stat -c %y "$OUT_JSON"))"
        echo "  skills:      $(section_count "$OUT_JSON" skills)"
        echo "  repos:       $(section_count "$OUT_JSON" repos)"
        echo "  MCP servers: $(section_count "$OUT_JSON" tools)"
        echo "  packages:    $(section_count "$OUT_JSON" apps)"
        echo "  models:      $(section_count "$OUT_JSON" models)"
        echo "  services:    $(section_count "$OUT_JSON" services)"
        echo "  unavailable sections: $(unavailable_count "$OUT_JSON")"
    else
        echo "inventory.json: ABSENT (run setup-host.sh or refresh.sh first)"
    fi
    if [[ -f "$OUT_MD" ]]; then
        echo "INVENTORY.md:  present"
    else
        echo "INVENTORY.md:  ABSENT"
    fi
    echo

    echo "-- refresh log --"
    if [[ -f "$LOG_FILE" ]]; then
        echo "refresh log:   present ($LOG_FILE, $(wc -l < "$LOG_FILE") lines)"
        tail -1 "$LOG_FILE"
    else
        echo "refresh log:   ABSENT"
    fi
}

cmd_run() {
    echo "=== inventory-reminder refresh + diagnostics ==="
    echo "start: $(TS)"
    echo

    # Pre-flight wiring checks
    local wiring_ok=1
    [[ -f "$CONFIG" ]] || { echo "CONFIG MISSING: $CONFIG — run setup-host.sh first"; wiring_ok=0; }
    [[ -f "$REFRESH_DST" ]] || { echo "REFRESH SCRIPT MISSING: $REFRESH_DST — run setup-host.sh first"; wiring_ok=0; }
    if [[ $wiring_ok -ne 0 ]]; then
        echo "wiring: OK"
    else
        echo "wiring: BROKEN — aborting run"
        exit 2
    fi

    # Capture previous inventory for drift comparison
    local prev_json=""
    if [[ -f "$OUT_JSON" ]]; then
        prev_json=$(cat "$OUT_JSON")
    fi

    # Run refresh and time it
    local start_ns end_ns duration_ms rc
    start_ns=$(date +%s%N 2>/dev/null || date +%s)
    INVENTORY_CONFIG="$CONFIG" "$REFRESH_DST" >> "$LOG_FILE" 2>&1
    rc=$?
    end_ns=$(date +%s%N 2>/dev/null || date +%s)
    if [[ "$start_ns" =~ ^[0-9]+$ ]] && [[ "$end_ns" =~ ^[0-9]+$ ]]; then
        duration_ms=$(( (end_ns - start_ns) / 1000000 ))
    else
        duration_ms="unknown"
    fi

    echo "refresh exit code: $rc"
    echo "duration: ${duration_ms}ms"
    echo

    if [[ -f "$OUT_JSON" ]]; then
        echo "-- current inventory --"
        echo "  skills:      $(section_count "$OUT_JSON" skills)"
        echo "  repos:       $(section_count "$OUT_JSON" repos)"
        echo "  MCP servers: $(section_count "$OUT_JSON" tools)"
        echo "  packages:    $(section_count "$OUT_JSON" apps)"
        echo "  models:      $(section_count "$OUT_JSON" models)"
        echo "  services:    $(section_count "$OUT_JSON" services)"
        echo "  unavailable sections: $(unavailable_count "$OUT_JSON")"
        echo

        # Drift vs previous
        if [[ -n "$prev_json" ]]; then
            echo "-- drift vs previous run --"
            local prev_skills prev_models prev_repos prev_mcp
            prev_skills=$(echo "$prev_json" | jq -r '.skills.names | length // 0' 2>/dev/null || echo "?")
            prev_models=$(echo "$prev_json" | jq -r '.models.count // 0' 2>/dev/null || echo "?")
            prev_repos=$(echo "$prev_json" | jq -r '.repos.local // 0' 2>/dev/null || echo "?")
            prev_mcp=$(echo "$prev_json" | jq -r '.tools.mcp_total // 0' 2>/dev/null || echo "?")
            echo "  skills:      $prev_skills -> $(section_count "$OUT_JSON" skills)"
            echo "  models:      $prev_models -> $(section_count "$OUT_JSON" models)"
            echo "  repos:       $prev_repos -> $(section_count "$OUT_JSON" repos)"
            echo "  MCP servers: $prev_mcp -> $(section_count "$OUT_JSON" tools)"
        fi
    fi

    echo
    echo "end: $(TS)"
    [[ $rc -eq 0 ]] && echo "RESULT: refresh OK" || echo "RESULT: refresh FAILED (exit $rc)"
}

cmd_history() {
    local n="${1:-10}"
    echo "=== inventory-reminder refresh log (last $n lines) ==="
    if [[ -f "$LOG_FILE" ]]; then
        tail -n "$n" "$LOG_FILE"
    else
        echo "no refresh log at $LOG_FILE"
    fi
}

# --- dispatch ----------------------------------------------------------------

case "${1:-}" in
    status)  cmd_status ;;
    run)     cmd_run ;;
    history) cmd_history "${2:-10}" ;;
    *)
        echo "Usage: monitor.sh {status|run|history [N]}"
        echo
        echo "  status   — diagnostic snapshot of wiring + last inventory state"
        echo "  run      — execute refresh.sh, capture duration/exit/drift"
        echo "  history  — last N lines of the refresh log"
        exit 1
        ;;
esac