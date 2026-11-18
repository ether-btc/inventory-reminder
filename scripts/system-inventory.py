#!/usr/bin/env python3
"""system-inventory.py — never re-derive "what is on this host" from memory.

One command answers the question every new session asks: what repos, skills,
tools, apps, models and services does this host actually have RIGHT NOW?
It reads live ground truth (the filesystem + the tools' own listings) and
writes it to TWO discoverable files:

    ~/.hermes/INVENTORY.md     human-readable, one section per category
    ~/.hermes/inventory.json   machine-readable (drift checks, other tools)

Categories, each from its own source of truth:

  repos     read from ~/.hermes/repos.json (repo-inventory.py already scanned;
            this script never re-scans GitHub — reference, don't duplicate)
  skills    `hermes skills list` (parsed; COLUMNS is widened so names do not
            come back truncated with "…")
  tools     MCP servers from ~/.hermes/config.yaml + key CLIs via which()
  providers chat model wiring: default provider/model, aliases, fallbacks,
            custom_providers, .env key NAMES (values never read)
  plugins   ~/.hermes/plugins/*/plugin.yaml: name, version, kind, tools
  cron      ~/.hermes/cron/jobs.json: schedule, enabled, last status,
            needs-attention list
  apps      `pip list` inside the hermes venv
  models    *.gguf under the llama-cpp + mnemosyne model dirs
  services  `systemctl list-units --type=service --state=running`, filtered

A section whose source is unavailable is reported as UNAVAILABLE with the
reason — never silently omitted, so "missing from the file" always means
"really gone" rather than "the scan broke".

Usage:
    system-inventory.py                regenerate both files (default action)
    system-inventory.py --write        same, explicit
    system-inventory.py --check        compare live state to inventory.json;
                                       exit 1 on drift (cron/monitor friendly)
    system-inventory.py --summary      one line for Mnemosyne / cron
    system-inventory.py --config F     override host paths via JSON config
                                       (or set INVENTORY_CONFIG); see
                                       config.example.json

Stdlib only. Read-only on the system: it runs listings and scans the
filesystem; the only writes are the two output files above.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HOME = Path(os.environ.get("HOME") or "/")
HERMES = HOME / ".hermes"

OUT_MD = HERMES / "INVENTORY.md"
OUT_JSON = HERMES / "inventory.json"

REPOS_JSON = HERMES / "repos.json"        # written by repo-inventory.py
REPOS_MD = HERMES / "REPOS.md"
CONFIG = HERMES / "config.yaml"
VENV = HERMES / "hermes-agent" / "venv"
HERMES_BIN = VENV / "bin" / "hermes"

MODEL_DIRS = [
    HOME / ".local" / "share" / "llama-cpp" / "models",
    HERMES / "mnemosyne" / "models",
]

# Key CLIs worth a positive/negative answer. Absent != broken, but the
# inventory should state it rather than let a session guess.
CLI_TOOLS = [
    "hermes", "gh", "git", "codex", "gopass", "node", "npm", "npx",
    "podman", "docker", "rg", "jq", "curl", "python3", "systemctl",
    "sqlite3", "ffmpeg", "tailscale", "gpg", "hc", "xf", "claude", "aider",
]

# A running service counts as "hermes-related" if its unit name or its
# description mentions one of these. Deliberately a name filter, not "all
# running services" — this section exists to catch hermes-side units dying.
SERVICE_HINTS = (
    "hermes", "mnem", "prompro", "aeon", "arc-", "llama", "weth",
    "decider", "curator", "claw", "beichtstuhl", "astra",
)

# Packages whose version is worth surfacing in the human view.
KEY_PACKAGES = (
    "hermes-agent", "mnemosyne-memory", "llama-cpp-python", "openai",
    "anthropic", "httpx", "fastapi", "rich", "pydantic", "numpy",
    "transformers", "torch", "sentence-transformers", "onnxruntime",
    "cryptography", "prompt-toolkit", "uvicorn", "requests",
)

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
SKILLS_TOTALS_RE = re.compile(
    r"(\d+)\s+hub-installed,\s+(\d+)\s+builtin,\s+(\d+)\s+local"
    r"\s+—\s+(\d+)\s+enabled,\s+(\d+)\s+disabled"
)


def apply_config(path: str | None) -> None:
    """Point every host-specific path/list at the given JSON config.

    Config keys (all optional; missing keys keep the defaults above):
      home, hermes_home, out_dir, repos_json, repos_md, config_yaml,
      venv, hermes_bin, model_dirs, cli_tools, service_hints, key_packages

    Discovered via `--config PATH` (this process only) and/or the
    INVENTORY_CONFIG env var (also inherited by refresh pipelines).
    No config file -> byte-identical behaviour to the original script.
    """
    global HOME, HERMES, OUT_MD, OUT_JSON, REPOS_JSON, REPOS_MD, CONFIG
    global VENV, HERMES_BIN, MODEL_DIRS, CLI_TOOLS, SERVICE_HINTS, KEY_PACKAGES

    src = path or os.environ.get("INVENTORY_CONFIG", "")
    cfg: dict = {}
    if src:
        try:
            cfg = json.loads(Path(src).read_text())
        except Exception as e:  # noqa: BLE001
            print(f"config error ({src}): {e}", file=sys.stderr)
            raise SystemExit(2)

    home = Path(cfg.get("home", str(HOME)))
    hermes_home = Path(cfg.get("hermes_home", home / ".hermes"))
    out_dir = Path(cfg.get("out_dir", str(hermes_home)))
    HOME = home
    HERMES = hermes_home
    OUT_MD = Path(cfg.get("out_md", out_dir / "INVENTORY.md"))
    OUT_JSON = Path(cfg.get("out_json", out_dir / "inventory.json"))
    REPOS_JSON = Path(cfg.get("repos_json", hermes_home / "repos.json"))
    REPOS_MD = Path(cfg.get("repos_md", hermes_home / "REPOS.md"))
    CONFIG = Path(cfg.get("config_yaml", hermes_home / "config.yaml"))
    VENV = Path(cfg.get("venv", hermes_home / "hermes-agent" / "venv"))
    HERMES_BIN = Path(cfg.get("hermes_bin", VENV / "bin" / "hermes"))
    if cfg.get("model_dirs"):
        MODEL_DIRS = [Path(d) for d in cfg["model_dirs"]]
    if cfg.get("cli_tools"):
        CLI_TOOLS = list(cfg["cli_tools"])
    if cfg.get("service_hints"):
        SERVICE_HINTS = tuple(cfg["service_hints"])
    if cfg.get("key_packages"):
        KEY_PACKAGES = tuple(cfg["key_packages"])


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def run(cmd: list[str], timeout: int = 120, extra_env: dict | None = None) -> tuple[int, str]:
    """Run a read-only command; never raise, always return (rc, stdout+stderr)."""
    env = dict(os.environ)
    env.setdefault("PATH", "")
    env["PATH"] = str(HOME / ".local" / "bin") + os.pathsep + env["PATH"]
    if extra_env:
        env.update(extra_env)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:  # noqa: BLE001
        return 1, f"{type(e).__name__}: {e}"


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def fmt_size(n: int) -> str:
    for unit, div in (("G", 1 << 30), ("M", 1 << 20), ("K", 1 << 10)):
        if n >= div:
            return f"{n / div:.1f}{unit}"
    return f"{n}B"


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return default


def unavailable(reason: str, **extra) -> dict:
    d = {"available": False, "error": reason}
    d.update(extra)
    return d


# --------------------------------------------------------------------------
# repos — reference repo-inventory.py output; do NOT re-scan GitHub
# --------------------------------------------------------------------------
def scan_repos() -> dict:
    data = load_json(REPOS_JSON, None)
    if not data:
        return unavailable(f"no {REPOS_JSON} — run `repo-inventory.py --write` first")
    ours = data.get("our_repos", [])
    foreign = data.get("foreign_clones", [])
    local = [e for e in ours if e.get("status") == "LOCAL"]
    online = [e for e in ours if e.get("status") == "ONLINE-ONLY"]
    md_lines = 0
    if REPOS_MD.exists():
        md_lines = len(REPOS_MD.read_text(errors="replace").splitlines())
    return {
        "available": True,
        "source": str(REPOS_JSON),
        "md": str(REPOS_MD),
        "md_lines": md_lines,
        "owner": data.get("owner", ""),
        "owned_total": len(ours),
        "local": len(local),
        "online_only": len(online),
        "foreign_clones": len(foreign),
        "local_repos": sorted(e.get("repo", "") for e in local),
    }


# --------------------------------------------------------------------------
# skills — parse `hermes skills list`
# --------------------------------------------------------------------------
def scan_skills() -> dict:
    if not HERMES_BIN.exists():
        return unavailable(f"hermes CLI not found at {HERMES_BIN}")
    # Wider COLUMNS stops rich from truncating names/categories with "…".
    rc, out = run([str(HERMES_BIN), "skills", "list"], timeout=300,
                  extra_env={"COLUMNS": "400", "TERM": "dumb"})
    out = strip_ansi(out)
    if rc != 0:
        return unavailable(f"`hermes skills list` exited {rc}")

    rows: list[dict] = []
    totals = {"hub": None, "builtin": None, "local": None,
              "enabled": None, "disabled": None}
    for line in out.splitlines():
        if "│" in line:
            parts = line.split("│")
            if len(parts) >= 7:
                name = parts[1].strip()
                if name and name.lower() != "name":
                    rows.append({
                        "name": name,
                        "category": parts[2].strip() or "(uncategorized)",
                        "source": parts[3].strip(),
                        "trust": parts[4].strip(),
                        "status": parts[5].strip(),
                    })
        m = SKILLS_TOTALS_RE.search(line)
        if m:
            h, b, l, e, d = (int(x) for x in m.groups())
            totals = {"hub": h, "builtin": b, "local": l, "enabled": e, "disabled": d}

    truncated = [r["name"] for r in rows if "…" in r["name"]]
    by_source: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for r in rows:
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        by_category[r["category"]] = by_category.get(r["category"], 0) + 1

    if not rows and totals["enabled"] is None:
        return unavailable("could not parse `hermes skills list` (no table rows, no totals line)")

    return {
        "available": True,
        "source": f"`{HERMES_BIN} skills list`",
        "total": totals["enabled"] if totals["enabled"] is not None else len(rows),
        "enabled": totals["enabled"], "disabled": totals["disabled"],
        "hub": totals["hub"], "builtin": totals["builtin"], "local": totals["local"],
        "parsed_rows": len(rows),
        "truncated_names": truncated,
        "by_source": dict(sorted(by_source.items(), key=lambda kv: -kv[1])),
        "by_category": dict(sorted(by_category.items(), key=lambda kv: -kv[1])),
        "hub_installed": sorted(r["name"] for r in rows if r["source"] not in ("local", "builtin")),
        "builtin": sorted(r["name"] for r in rows if r["source"] == "builtin"),
        "names": sorted(r["name"] for r in rows),
        "name_to_source": {r["name"]: r["source"] for r in rows},
    }


# --------------------------------------------------------------------------
# tools — MCP servers from config.yaml + key CLIs via which()
# --------------------------------------------------------------------------
def parse_mcp_servers(cfg: Path) -> tuple[list[dict], str | None]:
    """Minimal stdlib YAML-subset reader for the top-level `mcp_servers:` map.

    Every MCP entry is `  <name>:` at indent 2 with its keys at indent 4, so a
    line scan is enough and cannot be confused by nesting elsewhere in the file.
    """
    try:
        lines = cfg.read_text(errors="replace").splitlines()
    except Exception as e:  # noqa: BLE001
        return [], f"cannot read {cfg}: {e}"

    start = None
    for i, l in enumerate(lines):
        if re.match(r"^mcp_servers:\s*$", l):
            start = i + 1
            break
    if start is None:
        return [], "no top-level `mcp_servers:` key in config.yaml"

    servers: list[dict] = []
    cur: dict | None = None
    for raw in lines[start:]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0:
            break  # next top-level key
        name_m = re.match(r"^ {2}([^\s:#][^:]*):\s*$", raw)
        if name_m:
            cur = {"name": name_m.group(1).strip(), "enabled": None, "command": ""}
            servers.append(cur)
            continue
        if cur is not None:
            body = raw.strip()
            if body.startswith("enabled:"):
                cur["enabled"] = body.split(":", 1)[1].strip().lower() == "true"
            elif body.startswith("command:"):
                cur["command"] = body.split(":", 1)[1].strip().strip("'\"")
            elif body.startswith("lazy:"):
                cur["lazy"] = body.split(":", 1)[1].strip().lower() == "true"
    return servers, None


def scan_tools() -> dict:
    mcp, err = parse_mcp_servers(CONFIG)
    cli = {}
    for t in CLI_TOOLS:
        path = shutil.which(t, path=str(HOME / ".local" / "bin") + os.pathsep + os.environ.get("PATH", ""))
        cli[t] = path or ""
    present = [k for k, v in cli.items() if v]
    d = {
        "available": True,
        "config": str(CONFIG),
        "mcp_servers": mcp,
        "mcp_enabled": sorted(s["name"] for s in mcp if s.get("enabled")),
        "mcp_total": len(mcp),
        "cli_tools": cli,
        "cli_present": present,
        "cli_missing": [k for k, v in cli.items() if not v],
    }
    if err:
        d["mcp_error"] = err
    return d


# providers — chat model/provider wiring from config.yaml + .env key NAMES
# --------------------------------------------------------------------------
def _top_block(lines: list[str], key: str) -> list[str]:
    """Lines of the top-level `key:` block (until the next top-level key)."""
    start = None
    for i, l in enumerate(lines):
        if re.match(rf"^{key}:\s*(#.*)?$", l):
            start = i + 1
            break
    if start is None:
        return []
    out: list[str] = []
    for raw in lines[start:]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[0].isspace():
            break  # next top-level key
        out.append(raw)
    return out


def _scalar(s: str) -> str:
    return s.strip().strip("'\"")


def parse_model_block(bl: list[str]) -> tuple[dict, dict]:
    """(scalars, aliases) from the top-level `model:` block."""
    d: dict = {}
    aliases: dict = {}
    in_aliases = False
    for raw in bl:
        indent = len(raw) - len(raw.lstrip(" "))
        if indent <= 2:
            in_aliases = False
            k, _, v = raw.strip().partition(":")
            v = _scalar(v)
            if v:
                d[k] = v
            elif k == "aliases":
                in_aliases = True
        elif indent >= 4 and in_aliases:
            k, _, v = raw.strip().partition(":")
            if k.strip():
                aliases[k.strip()] = _scalar(v)
    return d, aliases


def parse_fallbacks(bl: list[str]) -> list[dict]:
    out: list[dict] = []
    cur: dict | None = None
    for raw in bl:
        s = raw.strip()
        if s.startswith("- provider:"):
            cur = {"provider": _scalar(s.split(":", 1)[1])}
            out.append(cur)
        elif cur is not None and s.startswith("model:"):
            cur["model"] = _scalar(s.split(":", 1)[1])
    return out


def parse_pool_names(bl: list[str]) -> list[str]:
    return [_scalar(l.strip()[:-1]) for l in bl
            if (len(l) - len(l.lstrip(" "))) == 2 and l.strip().endswith(":")]


# Values that name an env var (${VAR}) are safe to show; anything else in a
# key slot is treated as a secret and never leaves the process unredacted.
# `key_env` fields name an env var by definition, so they stay visible.
_SECRET_FIELDS = ("api_key", "key", "token")


def _safe_val(k: str, v: str) -> str:
    v = _scalar(v)
    if k in _SECRET_FIELDS and not v.startswith("${"):
        return "REDACTED"
    return v


def parse_custom_providers(bl: list[str]) -> list[dict]:
    out: list[dict] = []
    cur: dict | None = None
    in_models = False
    for raw in bl:
        indent = len(raw) - len(raw.lstrip(" "))
        s = raw.strip()
        if indent <= 2:
            in_models = False
            if s.startswith("- name:"):
                cur = {"name": _scalar(s.split(":", 1)[1])}
                out.append(cur)
            continue
        if cur is None:
            continue
        if indent == 4:
            in_models = False
            if s == "models:":
                in_models = True
            elif ":" in s:
                k, _, v = s.partition(":")
                cur[k.strip()] = _safe_val(k.strip(), v)
        elif indent >= 6 and in_models and s.endswith(": {}"):
            cur.setdefault("models", []).append(s.split(":", 1)[0].strip())
    return out


ENV_KEY_RE = re.compile(r"(?i)^([A-Z_]*(?:API_KEY|_KEY|TOKEN|APIKEY)[A-Z_0-9]*)\s*=")


def env_key_names(env: Path) -> list[str]:
    """Names only (never values) of API-key-style variables set in .env."""
    try:
        lines = env.read_text(errors="replace").splitlines()
    except OSError:
        return []
    out: list[str] = []
    for l in lines:
        m = ENV_KEY_RE.match(l.strip())
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def scan_providers(cfg: Path | None = None, env: Path | None = None) -> dict:
    cfg = cfg or CONFIG
    env = env or (HERMES / ".env")
    try:
        lines = cfg.read_text(errors="replace").splitlines()
    except Exception as e:  # noqa: BLE001
        return unavailable(f"cannot read {cfg}: {e}")
    model, aliases = parse_model_block(_top_block(lines, "model"))
    return {
        "available": True,
        "config": str(cfg),
        "default_model": model.get("default", ""),
        "default_provider": model.get("provider", ""),
        "base_url": model.get("base_url", ""),
        "api_key_env": _safe_val("api_key_env", model.get("api_key", "")),
        "aliases": aliases,
        "fallback_providers": parse_fallbacks(_top_block(lines, "fallback_providers")),
        "credential_pools": parse_pool_names(_top_block(lines, "credential_pool_strategies")),
        "custom_providers": parse_custom_providers(_top_block(lines, "custom_providers")),
        "env_key_names": env_key_names(env),
    }


# --------------------------------------------------------------------------
# plugins — ~/.hermes/plugins/*/plugin.yaml (name/version/kind/tools)
# --------------------------------------------------------------------------
def _yaml_scalar(s: str) -> str:
    return _scalar(s)


def scan_plugins(plugins_dir: Path | None = None) -> dict:
    plugins_dir = plugins_dir or (HERMES / "plugins")
    if not plugins_dir.is_dir():
        return unavailable(f"no plugins dir at {plugins_dir}")
    out: list[dict] = []
    for d in sorted(p for p in plugins_dir.iterdir() if p.is_dir()):
        y = d / "plugin.yaml"
        if not y.is_file():
            continue
        try:
            lines = y.read_text(errors="replace").splitlines()
        except OSError:
            continue
        meta: dict = {}
        tools: list[str] = []
        in_tools = False
        for raw in lines:
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            if indent == 0:
                in_tools = False
                if ":" in s:
                    k, _, v = s.partition(":")
                    k, v = k.strip(), _yaml_scalar(v)
                    if k == "provides_tools" and not v:
                        in_tools = True
                    elif v:
                        meta[k] = v
            elif in_tools and s.startswith("- "):
                tools.append(_yaml_scalar(s[2:]))
        desc = meta.get("description", "")
        if len(desc) > 110:
            desc = desc[:107].rstrip() + "…"
        out.append({
            "dir": d.name,
            "name": meta.get("name", d.name),
            "version": meta.get("version", ""),
            "kind": meta.get("kind", ""),
            "description": desc,
            "tools": tools,
        })
    return {"available": True, "dir": str(plugins_dir),
            "count": len(out), "plugins": out}


# --------------------------------------------------------------------------
# cron — ~/.hermes/cron/jobs.json (name/schedule/enabled/last status)
# --------------------------------------------------------------------------
def scan_cron(cron_dir: Path | None = None) -> dict:
    cron_dir = cron_dir or (HERMES / "cron")
    jf = cron_dir / "jobs.json"
    try:
        data = json.loads(jf.read_text())
    except Exception as e:  # noqa: BLE001
        return unavailable(f"cannot read {jf}: {e}")
    if isinstance(data, dict):
        jobs = data.get("jobs", [])
    else:
        jobs = data if isinstance(data, list) else []
    jobs = [j for j in jobs if isinstance(j, dict)]
    rows: list[dict] = []
    for j in jobs:
        sch = j.get("schedule") or {}
        rows.append({
            "name": j.get("name", j.get("id", "?")),
            "id": j.get("id", ""),
            "schedule": sch.get("display") or sch.get("expr") or "",
            "kind": sch.get("kind", ""),
            "enabled": bool(j.get("enabled")),
            "last_status": j.get("last_status"),
            "failure_streak": j.get("failure_streak", 0) or 0,
            "last_run_at": j.get("last_run_at"),
            "next_run_at": j.get("next_run_at"),
            "deliver": j.get("deliver", ""),
        })
    by_status: dict[str, int] = {}
    for r in rows:
        k = r["last_status"] or "never"
        by_status[k] = by_status.get(k, 0) + 1
    attention = [r["name"] for r in rows
                 if r["enabled"] and r["last_status"] not in (None, "ok")]
    return {
        "available": True,
        "jobs_file": str(jf),
        "total": len(rows),
        "enabled": sum(1 for r in rows if r["enabled"]),
        "by_status": by_status,
        "needs_attention": attention,
        "jobs": rows,
    }


# --------------------------------------------------------------------------
# apps — pip list inside the hermes venv
# --------------------------------------------------------------------------
def scan_apps() -> dict:
    py = VENV / "bin" / "python"
    if not py.exists():
        return unavailable(f"venv python not found at {py}")
    rc, out = run([str(py), "-m", "pip", "list", "--format=freeze"], timeout=300)
    if rc != 0:
        return unavailable(f"`pip list` exited {rc}: {out.strip()[:200]}")
    pkgs: dict[str, str] = {}
    for line in strip_ansi(out).splitlines():
        if "==" in line:
            n, v = line.split("==", 1)
            pkgs[n.strip()] = v.strip()
    _, pyv = run([str(py), "-V"], timeout=30)
    key = {k: pkgs[k] for k in KEY_PACKAGES if k in pkgs}
    return {
        "available": True,
        "venv": str(VENV),
        "python": pyv.strip().replace("Python ", "") or "?",
        "count": len(pkgs),
        "key_packages": dict(sorted(key.items())),
        "packages": dict(sorted(pkgs.items())),
    }


# --------------------------------------------------------------------------
# models — *.gguf on disk
# --------------------------------------------------------------------------
def scan_models() -> dict:
    found: list[dict] = []
    searched: list[str] = []
    for d in MODEL_DIRS:
        searched.append(str(d))
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*.gguf")):
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            rel = str(p).replace(str(HOME) + "/", "~/")
            found.append({
                "name": p.stem,
                "file": p.name,
                "path": rel,
                "size_bytes": size,
                "size": fmt_size(size),
            })
    found.sort(key=lambda m: (-m["size_bytes"], m["name"]))
    return {
        "available": True,
        "dirs": searched,
        "count": len(found),
        "total_bytes": sum(m["size_bytes"] for m in found),
        "total_size": fmt_size(sum(m["size_bytes"] for m in found)),
        "models": found,
    }


# --------------------------------------------------------------------------
# services — running systemd services, hermes-related only
# --------------------------------------------------------------------------
def scan_services() -> dict:
    rc, out = run(["systemctl", "list-units", "--type=service", "--state=running",
                   "--no-legend", "--plain"], timeout=60)
    if rc != 0:
        return unavailable(f"`systemctl list-units` exited {rc}: {out.strip()[:200]}")
    all_units: list[dict] = []
    for line in strip_ansi(out).splitlines():
        f = line.split(None, 4)
        if len(f) < 5:
            continue
        all_units.append({"name": f[0], "load": f[1], "active": f[2],
                          "sub": f[3], "description": f[4].strip()})
    hers = [u for u in all_units
            if any(h in u["name"].lower() or h in u["description"].lower()
                   for h in SERVICE_HINTS)]
    return {
        "available": True,
        "running_total": len(all_units),
        "count": len(hers),
        "services": hers,
    }


# --------------------------------------------------------------------------
# build / write
# --------------------------------------------------------------------------
def build() -> dict:
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generated_by": str(Path(__file__).resolve()),
        "host": os.uname().nodename,
        "repos": scan_repos(),
        "skills": scan_skills(),
        "tools": scan_tools(),
        "providers": scan_providers(),
        "plugins": scan_plugins(),
        "cron": scan_cron(),
        "apps": scan_apps(),
        "models": scan_models(),
        "services": scan_services(),
    }


def _sec(title: str, note: str = "") -> list[str]:
    L = ["", f"## {title}", ""]
    if note:
        L += [note, ""]
    return L


def write_files(inv: dict) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(inv, indent=2, sort_keys=False) + "\n")

    L: list[str] = []
    L.append("# System inventory — what is actually on this host")
    L.append("")
    L.append(f"Generated {inv['generated_at']} on `{inv['host']}` by "
             f"`{inv['generated_by']} --write`.")
    L.append(f"Machine-readable twin: `{OUT_JSON}`. "
             "Drift check: `system-inventory.py --check` (exit 1 on drift).")
    L.append("")
    L.append("**A category listed as UNAVAILABLE means its probe broke — it does "
             "NOT mean the host is empty.** Re-run the probe before concluding "
             "anything vanished.")
    L.append("")

    # ---- one-line totals
    r, s, t, p, a, m, sv = (inv["repos"], inv["skills"], inv["tools"],
                            inv["providers"], inv["apps"], inv["models"],
                            inv["services"])
    pl, cr = inv["plugins"], inv["cron"]
    bits = []
    if r.get("available"):
        bits.append(f"{r['owned_total']} repos ({r['local']} local / {r['online_only']} online-only)")
    if s.get("available"):
        bits.append(f"{s['total']} skills")
    if t.get("available"):
        bits.append(f"{t['mcp_total']} MCP servers")
    if p.get("available"):
        bits.append(f"{len(p['custom_providers'])} custom providers")
    if pl.get("available"):
        bits.append(f"{pl['count']} plugins")
    if cr.get("available"):
        bits.append(f"cron {cr['enabled']}/{cr['total']} on"
                    + (f", {len(cr['needs_attention'])} need attention"
                       if cr["needs_attention"] else ""))
    if a.get("available"):
        bits.append(f"{a['count']} python packages")
    if m.get("available"):
        bits.append(f"{m['count']} local models ({m['total_size']})")
    if sv.get("available"):
        bits.append(f"{sv['count']} hermes-related services running")
    L.append("**Totals:** " + " · ".join(bits))
    L.append("")

    # ---- repos
    L += _sec("Repositories", f"Source: `{REPOS_JSON}` (written by "
                              "`repo-inventory.py`; not re-scanned here).")
    if not r.get("available"):
        L.append(f"UNAVAILABLE — {r['error']}")
    else:
        L.append(f"- Owned by `{r['owner']}`: **{r['owned_total']}** — "
                 f"{r['local']} local, **{r['online_only']} online-only**")
        L.append(f"- Foreign clones on this host: {r['foreign_clones']}")
        L.append(f"- Human view: `{r['md']}` ({r['md_lines']} lines)")
        L.append("")
        L.append("Online-only repos still exist on GitHub — clone on demand with "
                 "`repos where <name>`; do not read an empty directory as "
                 "\"vanished\".")

    # ---- skills
    L += _sec("Skills", "Source: `hermes skills list` (parsed; COLUMNS widened "
                        "to defeat rich's `…` truncation).")
    if not s.get("available"):
        L.append(f"UNAVAILABLE — {s['error']}")
    else:
        L.append(f"**{s['total']} enabled, {s['disabled']} disabled** — "
                 f"by source: " + ", ".join(f"{v} {k}" for k, v in s["by_source"].items()))
        if s.get("truncated_names"):
            L.append("")
            L.append(f"⚠ {len(s['truncated_names'])} names came back truncated "
                     f"(e.g. `{s['truncated_names'][0]}`) — counts by source are "
                     "still trustworthy, by-name lists are not.")
        L.append("")
        L.append("### By category")
        L.append("")
        L.append("| category | skills |")
        L.append("|---|---|")
        for k, v in s["by_category"].items():
            L.append(f"| {k} | {v} |")
        L.append("")
        if s.get("hub_installed"):
            L.append(f"### Hub-installed ({len(s['hub_installed'])}) — curated from the hub")
            L.append("")
            for n in s["hub_installed"]:
                L.append(f"- `{n}`")
            L.append("")
        if s.get("builtin"):
            L.append(f"### Builtin ({len(s['builtin'])}) — shipped with Hermes")
            L.append("")
            for n in s["builtin"]:
                L.append(f"- `{n}`")
            L.append("")
        L.append(f"Full by-name list: `inventory.json` → `skills.names` "
                 f"({len(s['names'])} entries).")

    # ---- tools
    L += _sec("Tools", f"MCP servers from `{CONFIG}`; CLIs via `which`.")
    if not t.get("available"):
        L.append(f"UNAVAILABLE — {t['error']}")
    else:
        L.append("### MCP servers")
        L.append("")
        L.append("| server | enabled | command |")
        L.append("|---|---|---|")
        for srv in t["mcp_servers"]:
            en = "yes" if srv.get("enabled") else "**no**"
            cmd = srv.get("command") or "—"
            L.append(f"| `{srv['name']}` | {en} | `{cmd}` |")
        if t.get("mcp_error"):
            L.append("")
            L.append(f"⚠ {t['mcp_error']}")
        L.append("")
        L.append("### Key CLI tools")
        L.append("")
        L.append("| tool | path |")
        L.append("|---|---|")
        for name, path in t["cli_tools"].items():
            L.append(f"| `{name}` | {('`' + path + '`') if path else '**absent**'} |")

    # ---- providers
    L += _sec("Providers", "Source: `~/.hermes/config.yaml`; key NAMES only "
                           "from `~/.hermes/.env` (values never leave the "
                           "process).")
    if not p.get("available"):
        L.append(f"UNAVAILABLE — {p['error']}")
    else:
        L.append(f"- Default: **{p['default_provider']}** · model "
                 f"`{p['default_model']}` · `{p['base_url']}` "
                 f"(key ref: `{p['api_key_env']}`)")
        if p["aliases"]:
            L.append("- Aliases: " + ", ".join(
                f"`{k}→{v}`" for k, v in sorted(p["aliases"].items())))
        if p["fallback_providers"]:
            L.append("- Fallback chain: " + " → ".join(
                f"{f['provider']}/{f.get('model', '?')}"
                for f in p["fallback_providers"]))
        if p["credential_pools"]:
            L.append("- Credential pools: " + ", ".join(
                f"`{k}`" for k in p["credential_pools"]))
        if p["custom_providers"]:
            L.append("")
            L.append("| custom provider | base_url | default model | key |")
            L.append("|---|---|---|---|")
            for c in p["custom_providers"]:
                key = c.get("key_env") or c.get("api_key") or "REDACTED"
                L.append(f"| `{c['name']}` | {c.get('base_url', '—')} | "
                         f"{c.get('default_model') or c.get('model') or '—'} | "
                         f"`{key}` |")
        L.append("")
        L.append("API-key env names set: " + (", ".join(
            f"`{k}`" for k in p["env_key_names"]) or "none"))

    # ---- plugins
    L += _sec("Plugins", f"`{HERMES}/plugins/*/plugin.yaml` — local user-space "
                         "extensions (bundled plugins excluded).")
    if not pl.get("available"):
        L.append(f"UNAVAILABLE — {pl['error']}")
    else:
        L.append(f"**{pl['count']} local plugins.**")
        L.append("")
        L.append("| plugin | version | kind | tools | description |")
        L.append("|---|---|---|---|---|")
        for pg in pl["plugins"]:
            ntools = len(pg["tools"]) or "—"
            L.append(f"| `{pg['name']}` | {pg['version'] or '—'} | "
                     f"{pg['kind'] or '—'} | {ntools} | {pg['description'] or '—'} |")

    # ---- cron
    L += _sec("Automation (cron)", f"`{HERMES}/cron/jobs.json` — the full job "
                                   "fleet with schedule, enable state and last "
                                   "run status.")
    if not cr.get("available"):
        L.append(f"UNAVAILABLE — {cr['error']}")
    else:
        st = ", ".join(f"{k} {v}" for k, v in sorted(cr["by_status"].items()))
        L.append(f"**{cr['total']} jobs · {cr['enabled']} enabled** — last "
                 f"status: {st}.")
        if cr["needs_attention"]:
            L.append("")
            L.append("Needs attention (enabled but last run not ok): "
                     + ", ".join(f"`{n}`" for n in cr["needs_attention"]))
        L.append("")
        L.append("| job | schedule | on | last status | last run |")
        L.append("|---|---|---|---|---|")
        ordered = ([j for j in cr["jobs"]
                    if j["enabled"] and j["last_status"] not in (None, "ok")]
                   + [j for j in cr["jobs"]
                      if not (j["enabled"] and j["last_status"] not in (None, "ok"))])
        for j in ordered:
            L.append(f"| `{j['name']}` | `{j['schedule'] or '—'}` | "
                     f"{'on' if j['enabled'] else 'off'} | "
                     f"{j['last_status'] or 'never'} | "
                     f"{(j['last_run_at'] or '—')[:16]} |")

    # ---- apps
    L += _sec("Apps", f"`pip list` inside `{VENV}`.")
    if not a.get("available"):
        L.append(f"UNAVAILABLE — {a['error']}")
    else:
        L.append(f"**{a['count']} packages** — Python {a['python']} in `{a['venv']}`.")
        L.append("")
        L.append("Key packages:")
        L.append("")
        L.append("| package | version |")
        L.append("|---|---|")
        for k, v in a["key_packages"].items():
            L.append(f"| {k} | {v} |")
        L.append("")
        L.append(f"Full list ({a['count']}): `inventory.json` → `apps.packages`.")

    # ---- models
    L += _sec("Local models", "`*.gguf` under: "
                              + ", ".join(f"`{d}`" for d in MODEL_DIRS))
    if not m.get("available"):
        L.append(f"UNAVAILABLE — {m['error']}")
    else:
        L.append(f"**{m['count']} models, {m['total_size']} on disk.**")
        L.append("")
        L.append("| model | size | path |")
        L.append("|---|---|---|")
        for mo in m["models"]:
            L.append(f"| `{mo['name']}` | {mo['size']} | `{mo['path']}` |")

    # ---- services
    L += _sec("Services", "Running systemd units filtered to hermes-related names "
                          f"({', '.join(SERVICE_HINTS[:6])}, …).")
    if not sv.get("available"):
        L.append(f"UNAVAILABLE — {sv['error']}")
    else:
        L.append(f"**{sv['count']} of {sv['running_total']} running services** match.")
        L.append("")
        L.append("| unit | active | description |")
        L.append("|---|---|---|")
        for u in sv["services"]:
            L.append(f"| `{u['name']}` | {u['active']}/{u['sub']} | {u['description']} |")
        if not sv["services"]:
            L.append("")
            L.append("_No hermes-related units are running — check whether that is expected._")

    L.append("")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(L) + "\n")


# --------------------------------------------------------------------------
# --check  /  --summary
# --------------------------------------------------------------------------
def cmd_check(inv: dict) -> int:
    old = load_json(OUT_JSON, None)
    if not old:
        print("CHECK: no previous inventory.json — run --write first")
        return 1
    drift: list[str] = []

    def diff_sets(label: str, a, b) -> None:
        """a=old, b=new; report additions and removals."""
        old_s, new_s = set(a), set(b)
        for x in sorted(new_s - old_s):
            drift.append(f"NEW-{label}: {x}")
        for x in sorted(old_s - new_s):
            drift.append(f"GONE-{label}: {x}")

    # skills
    o, n = old.get("skills", {}), inv["skills"]
    if o.get("available") and n.get("available"):
        diff_sets("SKILL", o.get("names", []), n.get("names", []))
        if o.get("total") != n.get("total"):
            drift.append(f"SKILL-COUNT: {o.get('total')} -> {n.get('total')}")

    # models
    o, n = old.get("models", {}), inv["models"]
    if o.get("available") and n.get("available"):
        diff_sets("MODEL", [m["name"] for m in o.get("models", [])],
                  [m["name"] for m in n.get("models", [])])

    # mcp servers
    o, n = old.get("tools", {}), inv["tools"]
    if o.get("mcp_servers") is not None and n.get("mcp_servers") is not None:
        om = {s["name"]: bool(s.get("enabled")) for s in o["mcp_servers"]}
        nm = {s["name"]: bool(s.get("enabled")) for s in n["mcp_servers"]}
        diff_sets("MCP-SERVER", list(om), list(nm))
        for k in sorted(set(om) & set(nm)):
            if om[k] != nm[k]:
                drift.append(f"MCP-TOGGLED: {k} enabled {om[k]} -> {nm[k]}")

    # cli tools present/absent
    if o.get("cli_tools") is not None and n.get("cli_tools") is not None:
        op = {k for k, v in o["cli_tools"].items() if v}
        np_ = {k for k, v in n["cli_tools"].items() if v}
        for x in sorted(np_ - op):
            drift.append(f"NEW-CLI: {x} now on PATH")
        for x in sorted(op - np_):
            drift.append(f"GONE-CLI: {x} no longer on PATH")

    # plugins — membership + version changes
    o, n = old.get("plugins", {}), inv["plugins"]
    if o.get("available") and n.get("available"):
        opg = {pg["name"]: pg.get("version") for pg in o.get("plugins", [])}
        npg = {pg["name"]: pg.get("version") for pg in n.get("plugins", [])}
        diff_sets("PLUGIN", list(opg), list(npg))
        for k in sorted(set(opg) & set(npg)):
            if opg[k] != npg[k]:
                drift.append(f"PLUGIN-VERSION: {k} {opg[k]} -> {npg[k]}")

    # cron — membership + enabled toggles (status churn is not drift)
    o, n = old.get("cron", {}), inv["cron"]
    if o.get("available") and n.get("available"):
        oj = {j["name"]: j["enabled"] for j in o.get("jobs", [])}
        nj = {j["name"]: j["enabled"] for j in n.get("jobs", [])}
        diff_sets("CRON-JOB", list(oj), list(nj))
        for k in sorted(set(oj) & set(nj)):
            if oj[k] != nj[k]:
                drift.append(f"CRON-TOGGLED: {k} enabled {oj[k]} -> {nj[k]}")

    # services
    o, n = old.get("services", {}), inv["services"]
    if o.get("available") and n.get("available"):
        diff_sets("SERVICE", [u["name"] for u in o.get("services", [])],
                  [u["name"] for u in n.get("services", [])])

    # apps — count + key package versions
    o, n = old.get("apps", {}), inv["apps"]
    if o.get("available") and n.get("available"):
        if o.get("count") != n.get("count"):
            drift.append(f"APP-COUNT: {o.get('count')} -> {n.get('count')} packages")
        opk, npk = o.get("key_packages", {}), n.get("key_packages", {})
        for k in sorted(set(opk) | set(npk)):
            if opk.get(k) != npk.get(k):
                drift.append(f"APP-VERSION: {k} {opk.get(k, '(absent)')} -> {npk.get(k, '(absent)')}")

    # repos — counts only (membership lives in repos.json's own drift check)
    o, n = old.get("repos", {}), inv["repos"]
    if o.get("available") and n.get("available"):
        for k in ("owned_total", "local", "online_only", "foreign_clones"):
            if o.get(k) != n.get(k):
                drift.append(f"REPO-{k.upper()}: {o.get(k)} -> {n.get(k)}")

    if drift:
        print(f"DRIFT DETECTED ({len(drift)}):")
        for d in drift:
            print("  " + d)
        return 1

    tot = inv.get("skills", {}).get("total", "?")
    print(f"NO DRIFT: {tot} skills, {inv['models'].get('count', '?')} models, "
          f"{inv['tools'].get('mcp_total', '?')} MCP servers, "
          f"{inv['services'].get('count', '?')} hermes services, "
          f"{inv['apps'].get('count', '?')} packages")
    return 0


def cmd_summary(inv: dict) -> int:
    r, s, t, p, a, m, sv = (inv["repos"], inv["skills"], inv["tools"],
                            inv["providers"], inv["apps"], inv["models"],
                            inv["services"])
    pl, cr = inv["plugins"], inv["cron"]
    parts = []
    if r.get("available"):
        parts.append(f"repos {r['owned_total']} ({r['local']}L/{r['online_only']}O)")
    else:
        parts.append("repos N/A")
    if s.get("available"):
        src = "/".join(f"{v}{k[:1]}" for k, v in s["by_source"].items())
        parts.append(f"skills {s['total']} ({src})")
    else:
        parts.append("skills N/A")
    if t.get("available"):
        parts.append(f"mcp {t['mcp_enabled'].__len__()}/{t['mcp_total']}")
    else:
        parts.append("mcp N/A")
    if p.get("available"):
        parts.append(f"providers {len(p['custom_providers'])}")
    if pl.get("available"):
        parts.append(f"plugins {pl['count']}")
    if cr.get("available"):
        parts.append(f"cron {cr['enabled']}/{cr['total']}"
                     + (f" ({len(cr['needs_attention'])}!)"
                        if cr["needs_attention"] else ""))
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
    print(f"INVENTORY {stamp} | " + " | ".join(parts))
    return 0


def cmd_where(term: str, as_json: bool = False) -> int:
    """Search all inventory sections for a case-insensitive substring match."""
    inv = build()
    term_l = term.lower()
    hits = []

    # skills
    s = inv.get("skills", {})
    if s.get("available"):
        for name in s.get("names", []):
            if term_l in name.lower():
                source = s.get("name_to_source", {}).get(name, "local")
                hits.append({
                    "section": "skills",
                    "item": name,
                    "detail": source
                })

    # repos owned
    r = inv.get("repos", {})
    if r.get("available"):
        for repo in r.get("local_repos", []):
            if term_l in repo.lower():
                hits.append({
                    "section": "repos_owned",
                    "item": repo,
                    "detail": f"LOCAL — {HOME}/projects/{repo.split('/')[-1]}"
                })
        # foreign clones
        data = load_json(REPOS_JSON, {})
        for fc in data.get("foreign_clones", []):
            repo = fc.get("repo", "")
            if term_l in repo.lower():
                path = fc.get("local_paths", ["?"])[0]
                hits.append({
                    "section": "repos_foreign",
                    "item": repo,
                    "detail": f"LOCAL — {HOME}/{path}"
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

    # providers — custom provider names, aliases, model ids
    pr = inv.get("providers", {})
    if pr.get("available"):
        for c in pr.get("custom_providers", []):
            if term_l in c.get("name", "").lower():
                hits.append({
                    "section": "providers",
                    "item": c["name"],
                    "detail": f"{c.get('base_url', '—')} → "
                              f"{c.get('default_model') or c.get('model') or '—'}"
                })
            for mid in c.get("models", []):
                if term_l in mid.lower():
                    hits.append({
                        "section": "provider_models",
                        "item": mid,
                        "detail": f"custom provider `{c['name']}`"
                    })
        for ak, av in pr.get("aliases", {}).items():
            if term_l in ak.lower() or term_l in av.lower():
                hits.append({
                    "section": "provider_aliases",
                    "item": ak,
                    "detail": av
                })

    # plugins — names, tool names
    plg = inv.get("plugins", {})
    if plg.get("available"):
        for pg in plg.get("plugins", []):
            if term_l in pg.get("name", "").lower():
                hits.append({
                    "section": "plugins",
                    "item": pg["name"],
                    "detail": f"{pg.get('version', '?')} "
                              f"({pg.get('kind', '?')}) — "
                              f"{pg.get('description', '')}"
                })
            for tool in pg.get("tools", []):
                if term_l in tool.lower():
                    hits.append({
                        "section": "plugins",
                        "item": tool,
                        "detail": f"tool of plugin `{pg['name']}`"
                    })

    # cron jobs — names, schedules
    crn = inv.get("cron", {})
    if crn.get("available"):
        for j in crn.get("jobs", []):
            if term_l in j.get("name", "").lower() or \
                    term_l in (j.get("schedule") or "").lower():
                hits.append({
                    "section": "cron_jobs",
                    "item": j["name"],
                    "detail": f"`{j.get('schedule', '—')}` "
                              f"{'on' if j.get('enabled') else 'off'}, "
                              f"last {j.get('last_status') or 'never'}"
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
        if as_json:
            print(json.dumps({"query": term, "hits": []}, indent=2))
        else:
            print(f"MISS: {term} — not found in any section")
        return 1

    if as_json:
        print(json.dumps({"query": term, "hits": hits}, indent=2))
        return 0

    # human table, grouped by section
    by_section: dict[str, list[dict]] = {}
    for h in hits:
        by_section.setdefault(h["section"], []).append(h)

    section_order = [
        "skills", "repos_owned", "repos_foreign",
        "mcp_servers", "cli_tools", "providers", "provider_models",
        "provider_aliases", "plugins", "cron_jobs", "models", "key_packages"
    ]
    section_labels = {
        "skills": "SKILLS",
        "repos_owned": "REPOS (owned)",
        "repos_foreign": "REPOS (foreign)",
        "mcp_servers": "MCP SERVERS",
        "cli_tools": "CLI TOOLS",
        "providers": "PROVIDERS",
        "provider_models": "PROVIDER MODELS",
        "provider_aliases": "PROVIDER ALIASES",
        "plugins": "PLUGINS",
        "cron_jobs": "CRON JOBS",
        "models": "MODELS",
        "key_packages": "KEY PACKAGES",
    }

    for sec in section_order:
        if sec not in by_section:
            continue
        print(section_labels[sec])
        print()
        for h in by_section[sec]:
            print(f"  {h['item']}         ({h['detail']})")
        print()
    return 0


def main() -> int:
    args = sys.argv[1:]
    config_path = None
    i = 0
    while i < len(args):
        if args[i] == "--config":
            if i + 1 >= len(args):
                print("usage: --config PATH", file=sys.stderr)
                return 2
            config_path = args[i + 1]
            del args[i:i + 2]
            continue
        i += 1
    apply_config(config_path)
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args and args[0] == "--check":
        return cmd_check(build())
    if args and args[0] == "--summary":
        return cmd_summary(build())
    if args and args[0] == "where":
        if len(args) < 2:
            print("usage: system-inventory.py where <term> [--json]", file=sys.stderr)
            return 2
        term = args[1]
        as_json = "--json" in args[2:]
        return cmd_where(term, as_json)
    inv = build()
    write_files(inv)
    print(f"wrote {OUT_MD} and {OUT_JSON}")
    return cmd_summary(inv)


if __name__ == "__main__":
    sys.exit(main())
