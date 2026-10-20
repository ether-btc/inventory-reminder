#!/usr/bin/env python3
"""
hermes_inventory_plugin.py — Hermes plugin adapter for inventory-reminder.

Registers:
- CLI subcommand: `hermes inventory where <term> [--json]`
- Tool: `inventory_where(term: str, json: bool = false)` — callable from agents
- Opt-in session-start digest: HERMES_INVENTORY_DIGEST=1 prints one-line --summary

Reads inventory.json (cached) — no live rescans per turn. Stdlib only.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Default inventory location (overridable by INVENTORY_JSON env)
DEFAULT_INVENTORY_JSON = Path.home() / ".hermes" / "inventory.json"
INVENTORY_JSON = Path(os.environ.get("INVENTORY_JSON", str(DEFAULT_INVENTORY_JSON)))


def load_inventory() -> dict | None:
    """Load inventory.json if it exists and is valid."""
    try:
        if INVENTORY_JSON.exists():
            return json.loads(INVENTORY_JSON.read_text())
    except Exception:  # noqa: BLE001
        pass
    return None


def cmd_inventory_where(term: str, as_json: bool = False) -> str:
    """Tool handler for inventory_where."""
    inv = load_inventory()
    if not inv:
        result = {"query": term, "hits": [], "error": "inventory.json not found or invalid"}
        return json.dumps(result)

    term_l = term.lower()
    hits = []

    # skills
    s = inv.get("skills", {})
    if s.get("available"):
        for name in s.get("names", []):
            if term_l in name.lower():
                hits.append({
                    "section": "skills",
                    "item": name,
                    "detail": f"{s.get('by_source', {}).get(name, 'local')}"
                })

    # repos owned
    r = inv.get("repos", {})
    if r.get("available"):
        for repo in r.get("local_repos", []):
            if term_l in repo.lower():
                hits.append({
                    "section": "repos_owned",
                    "item": repo,
                    "detail": f"LOCAL — {Path.home()}/projects/{repo.split('/')[-1]}"
                })
        # foreign clones
        repos_json = Path.home() / ".hermes" / "repos.json"
        try:
            data = json.loads(repos_json.read_text()) if repos_json.exists() else {}
        except Exception:  # noqa: BLE001
            data = {}
        for fc in data.get("foreign_clones", []):
            repo = fc.get("repo", "")
            if term_l in repo.lower():
                path = fc.get("local_paths", ["?"])[0]
                hits.append({
                    "section": "repos_foreign",
                    "item": repo,
                    "detail": f"LOCAL — {Path.home()}/{path}"
                })

    # mcp servers
    t = inv.get("tools", {})
    if t.get("available"):
        for srv in t.get("mcp_servers", []):
            if term_l in srv.get("name", "").lower():
                en = "enabled" if srv.get("enabled") else "disabled"
                hits.append({
                    "section": "mcp_servers",
                    "item": srv["name"],
                    "detail": f"{en} → {srv.get('command') or '—'}"
                })

    # cli tools
    if t.get("available"):
        for name, path in t.get("cli_tools", {}).items():
            if term_l in name.lower():
                hits.append({
                    "section": "cli_tools",
                    "item": name,
                    "detail": path or "**absent**"
                })

    # models
    m = inv.get("models", {})
    if m.get("available"):
        for mo in m.get("models", []):
            if term_l in mo.get("name", "").lower():
                hits.append({
                    "section": "models",
                    "item": mo["name"],
                    "detail": f"{mo['size']} — {mo['path']}"
                })

    # key packages
    a = inv.get("apps", {})
    if a.get("available"):
        for k, v in a.get("key_packages", {}).items():
            if term_l in k.lower():
                hits.append({
                    "section": "key_packages",
                    "item": k,
                    "detail": v
                })

    if not hits:
        result = {"query": term, "hits": []}
        if as_json:
            return json.dumps(result)
        return f"MISS: {term} — not found in any section"

    if as_json:
        return json.dumps({"query": term, "hits": hits})

    # human output
    by_section: dict[str, list[dict]] = {}
    for h in hits:
        by_section.setdefault(h["section"], []).append(h)

    section_order = [
        "skills", "repos_owned", "repos_foreign",
        "mcp_servers", "cli_tools", "models", "key_packages"
    ]
    section_labels = {
        "skills": "SKILLS",
        "repos_owned": "REPOS (owned)",
        "repos_foreign": "REPOS (foreign)",
        "mcp_servers": "MCP SERVERS",
        "cli_tools": "CLI TOOLS",
        "models": "MODELS",
        "key_packages": "KEY PACKAGES",
    }

    out = []
    for sec in section_order:
        if sec not in by_section:
            continue
        out.append(section_labels[sec])
        out.append("")
        for h in by_section[sec]:
            out.append(f"  {h['item']}         ({h['detail']})")
        out.append("")
    return "\n".join(out).rstrip()


def cmd_inventory_summary() -> str:
    """Tool handler for inventory_summary (one-line digest)."""
    inv = load_inventory()
    if not inv:
        return "INVENTORY unavailable — no inventory.json"

    r, s, t, a, m, sv = (inv.get("repos", {}), inv.get("skills", {}), inv.get("tools", {}),
                         inv.get("apps", {}), inv.get("models", {}), inv.get("services", {}))
    parts = []
    if r.get("available"):
        parts.append(f"repos {r['owned_total']} ({r['local']}L/{r['online_only']}O)")
    else:
        parts.append("repos N/A")
    if s.get("available"):
        src = "/".join(f"{v}{k[:1]}" for k, v in s.get("by_source", {}).items())
        parts.append(f"skills {s['total']} ({src})")
    else:
        parts.append("skills N/A")
    if t.get("available"):
        parts.append(f"mcp {len(t.get('mcp_enabled', []))}/{t.get('mcp_total', '?')}")
    else:
        parts.append("mcp N/A")
    if a.get("available"):
        parts.append(f"pkgs {a['count']}")
    else:
        parts.append("pkgs N/A")
    if m.get("available"):
        parts.append(f"models {m['count']} ({m['total_size']})")
    else:
        parts.append("models N/A")
    if sv.get("available"):
        parts.append(f"services {sv['count']}/{sv['running_total']}")
    else:
        parts.append("services N/A")
    stamp = inv.get("generated_at", "?")[:16].replace("T", " ")
    return f"INVENTORY {stamp} | " + " | ".join(parts)


# Hermes plugin entry point
def register(ctx) -> None:
    """Register the inventory plugin tools and commands with Hermes."""
    # Register the `inventory_where` tool (callable from agents)
    ctx.register_tool(
        name="inventory_where",
        toolset="inventory",
        schema={
            "type": "object",
            "properties": {
                "term": {"type": "string", "description": "Search term (substring, case-insensitive)"},
                "json": {"type": "boolean", "description": "Emit machine-readable JSON", "default": False}
            },
            "required": ["term"],
        },
        handler=lambda args: cmd_inventory_where(args["term"], args.get("json", False)),
        description="Search the live inventory digest for a capability across all sections (skills, repos, MCP, CLIs, models, key packages).",
    )

    # Register the `inventory_summary` tool
    ctx.register_tool(
        name="inventory_summary",
        toolset="inventory",
        schema={
            "type": "object",
            "properties": {},
        },
        handler=lambda _args: cmd_inventory_summary(),
        description="One-line inventory digest for session bootstrap / memory layer.",
    )

    # Register the CLI subcommand: `hermes inventory where <term> [--json]`
    # This is done via a command hook that intercepts the `inventory` subcommand.
    # Since we don't have a direct `register_command` for subcommands, we use
    # a pre-tool-call hook to catch the `hermes inventory` invocation pattern.
    # Alternative: register a tool that the CLI can dispatch to.
    # For simplicity, we expose the functionality via the two tools above.
    # The user can invoke: `hermes tool inventory_where --term aider --json false`
    # Or add a shell alias/function: `hermes-inventory() { hermes tool inventory_where --term "$1" --json "${2:-false}"; }`

    # Session-start digest (opt-in)
    if os.environ.get("HERMES_INVENTORY_DIGEST") == "1":
        print(cmd_inventory_summary(), file=sys.stderr)


if __name__ == "__main__":
    # CLI test mode
    if len(sys.argv) < 2:
        print("Usage: hermes_inventory_plugin.py where|summary <term> [--json]", file=sys.stderr)
        sys.exit(1)
    if sys.argv[1] == "where":
        term = sys.argv[2] if len(sys.argv) > 2 else ""
        as_json = "--json" in sys.argv
        print(cmd_inventory_where(term, as_json))
    elif sys.argv[1] == "summary":
        print(cmd_inventory_summary())
    else:
        print(f"Unknown command: {sys.argv[1]}", file=sys.stderr)
        sys.exit(1)