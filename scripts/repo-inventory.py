#!/usr/bin/env python3
"""repo-inventory.py — never mistake an online-only repo for a vanished one.

Builds the authoritative LOCAL-vs-ONLINE picture of every repository this host
cares about, from live ground truth (the GitHub API + the filesystem), and
writes it to TWO discoverable files:

    ~/.hermes/REPOS.md     human-readable, grouped by status
    ~/.hermes/repos.json   machine-readable (drift checks, other tools)

A repo with no local clone is NOT missing: it is reported as ONLINE-ONLY with
its URL and a ready clone command. That distinction is the whole point — after a
disk-reclamation session makes a repo online-only, the next session must not
read the empty directory as "vanished".

Usage:
    repo-inventory.py --write            regenerate both files (default action)
    repo-inventory.py --check            compare live state to repos.json;
                                         exit 1 on drift (cron/monitor friendly)
    repo-inventory.py where <name>       one-shot lookup, e.g. `repos where aeon`
    repo-inventory.py --note 'o/r=text'  annotate a repo (persists across runs)
    repo-inventory.py --config F         override owner/paths via JSON config
                                         (or INVENTORY_CONFIG); see
                                         config.example.json

Set the owner via REPO_INVENTORY_OWNER or the config `owner` key; without
it the owned-repo scan is skipped (local-clone scanning still works).

Notes live in ~/.hermes/repos-notes.json so a regeneration never loses the
"who moved this online and why" annotation. Stdlib only. Read-only on git and
GitHub: it runs `gh repo list`/`gh api` reads and scans the filesystem; it never
creates, clones, commits, pushes or deletes anything.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path(os.environ.get("HOME") or "/")
OWNER = os.environ.get("REPO_INVENTORY_OWNER", "")
HERMES = HOME / ".hermes"
OUT_MD = HERMES / "REPOS.md"
OUT_JSON = HERMES / "repos.json"
NOTES = HERMES / "repos-notes.json"

PRUNE = {".cache", "node_modules", ".venv", "venv", "__pycache__",
         ".mypy_cache", ".pytest_cache", ".ruff_cache", "site-packages",
         "backups", "cache", "models", "audio_cache", "dist", "build", "target"}
MAX_DEPTH = 5


def apply_config(path: str | None) -> None:
    """Point host-specific paths/owner at the given JSON config.

    Config keys (all optional; missing keys keep the defaults above):
      home, hermes_home, out_dir, out_md, out_json, notes_file,
      owner, scan_root, max_depth

    `owner` falls back to the REPO_INVENTORY_OWNER env var; with neither
    set the scan of owned repos is unavailable (local-clone scan still works).
    Discovered via `--config PATH` and/or the INVENTORY_CONFIG env var.
    """
    global HOME, OWNER, HERMES, OUT_MD, OUT_JSON, NOTES, MAX_DEPTH

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
    OUT_MD = Path(cfg.get("out_md", out_dir / "REPOS.md"))
    OUT_JSON = Path(cfg.get("out_json", out_dir / "repos.json"))
    NOTES = Path(cfg.get("notes_file", out_dir / "repos-notes.json"))
    if cfg.get("owner"):
        OWNER = str(cfg["owner"])
    if cfg.get("scan_root"):
        HOME = Path(cfg["scan_root"])
    if cfg.get("max_depth"):
        MAX_DEPTH = int(cfg["max_depth"])


def gh(args: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=180)
        return p.returncode, p.stdout
    except Exception as e:  # noqa: BLE001
        return 1, json.dumps({"error": str(e)})


def norm_remote(url: str) -> str:
    """git@github.com:o/r.git | https://github.com/o/r -> 'o/r'."""
    if not url:
        return ""
    u = url.strip()
    for pre in ("git@github.com:", "https://github.com/", "http://github.com:", "ssh://git@github.com/"):
        if u.startswith(pre):
            u = u[len(pre):]
    if u.endswith(".git"):
        u = u[:-4]
    u = u.strip("/")
    return u if u.count("/") == 1 else ""


def scan_local_clones() -> dict[str, list[str]]:
    """owner/repo -> [paths] for every clone under HOME."""
    found: dict[str, list[str]] = {}
    for root, dirs, _files in os.walk(HOME):
        depth = len(Path(root).relative_to(HOME).parts)
        dirs[:] = [d for d in dirs if d not in PRUNE and not d.startswith(".Trash")]
        if depth >= MAX_DEPTH:
            dirs[:] = [d for d in dirs if d == ".git"]
        if ".git" in dirs:
            gitdir = Path(root) / ".git"
            if gitdir.is_dir():
                p = subprocess.run(["git", "-C", root, "remote", "get-url", "origin"],
                                   capture_output=True, text=True)
                remote = norm_remote(p.stdout)
                if remote:
                    rel = str(Path(root).relative_to(HOME))
                    found.setdefault(remote, []).append(rel)
            dirs[:] = [d for d in dirs if d != ".git"]
    for k in found:
        found[k].sort(key=lambda p: (p.count("/"), len(p)))
    return found


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return default


def build() -> dict:
    local = scan_local_clones()
    notes = load_json(NOTES, {})
    owner_error = ""
    if not OWNER:
        repos: list[dict] = []
        owner_error = ("no owner configured — set REPO_INVENTORY_OWNER "
                       "or the config 'owner' key to list owned repos")
    else:
        rc, out = gh(["repo", "list", OWNER, "--limit", "300", "--json",
                     "name,nameWithOwner,url,visibility,isFork,isArchived,pushedAt,description"])
        if rc != 0:
            print(f"FATAL: `gh repo list {OWNER}` failed — refusing to write a partial inventory.\n{out}",
                  file=sys.stderr)
            sys.exit(2)
        repos = json.loads(out)
    entries = []
    for r in sorted(repos, key=lambda r: r["nameWithOwner"].lower()):
        full = r["nameWithOwner"]
        paths = local.get(full, [])
        entries.append({
            "repo": full,
            "url": r["url"],
            "visibility": r["visibility"],
            "fork": r["isFork"],
            "archived": r["isArchived"],
            "pushed_at": (r.get("pushedAt") or "")[:10],
            "description": (r.get("description") or "").strip(),
            "status": "LOCAL" if paths else "ONLINE-ONLY",
            "local_paths": paths,
            "note": notes.get(full, ""),
        })
    foreign = sorted(
        ({"repo": k, "local_paths": v} for k, v in local.items() if not k.startswith(OWNER + "/")),
        key=lambda e: e["repo"].lower(),
    )
    return {
        "owner": OWNER,
        "owner_error": owner_error,
        "generated_by": str(Path(__file__).resolve()),
        "our_repos": entries,
        "foreign_clones": foreign,
    }


def write_files(inv: dict) -> None:
    OUT_JSON.write_text(json.dumps(inv, indent=2) + "\n")
    ours, foreign = inv["our_repos"], inv["foreign_clones"]
    online = [e for e in ours if e["status"] == "ONLINE-ONLY"]
    loc = [e for e in ours if e["status"] == "LOCAL"]
    L = []
    L.append("# Repository inventory — LOCAL vs ONLINE-ONLY")
    L.append("")
    L.append(f"Generated from live ground truth by `{inv['generated_by']} --write`.")
    L.append("**A repo with no local clone is NOT gone.** Re-run `repos where <name>` (or read this file)")
    L.append("before concluding anything has vanished, and clone on demand with the printed command.")
    L.append("")
    L.append(f"Totals: {len(ours)} repos owned by `{inv['owner']}` — "
             f"{len(loc)} local, **{len(online)} online-only**; "
             f"{len(foreign)} foreign clones on this host.")
    L.append("")
    L.append("## ONLINE-ONLY — exists on GitHub, intentionally not on this disk")
    L.append("")
    L.append("| repo | vis | last push | clone with | note |")
    L.append("|---|---|---|---|---|")
    for e in online:
        clone = f"`git clone {e['url'].replace('https://', 'git@').replace('github.com/', 'github.com:')}`"
        L.append(f"| [{e['repo'].split('/')[1]}]({e['url']}) | {e['visibility'][:3]} | {e['pushed_at']} "
                 f"| {clone} | {e['note'] or ''} |")
    L.append("")
    L.append("## LOCAL — a clone exists on this host")
    L.append("")
    L.append("| repo | vis | last push | path(s) |")
    L.append("|---|---|---|---|")
    for e in loc:
        L.append(f"| [{e['repo'].split('/')[1]}]({e['url']}) | {e['visibility'][:3]} | {e['pushed_at']} "
                 f"| {', '.join('`~/'+p+'`' for p in e['local_paths'][:3])} |")
    L.append("")
    L.append("## Foreign clones on this host (upstream projects, informational)")
    L.append("")
    for e in foreign:
        L.append(f"- `{e['repo']}` — {', '.join('`~/'+p+'`' for p in e['local_paths'][:2])}")
    L.append("")
    OUT_MD.write_text("\n".join(L) + "\n")


def cmd_check(inv: dict) -> int:
    old = load_json(OUT_JSON, None)
    if not old:
        print("CHECK: no previous repos.json — run --write first")
        return 1
    drift = []
    o_old = {e["repo"]: e["status"] for e in old.get("our_repos", [])}
    o_new = {e["repo"]: e["status"] for e in inv["our_repos"]}
    for r in sorted(set(o_old) | set(o_new)):
        if r not in o_new:
            drift.append(f"GONE-UPSTREAM: {r} (was {o_old[r]}; deleted or renamed on GitHub?)")
        elif r not in o_old:
            drift.append(f"NEW-REPO: {r} ({o_new[r]})")
        elif o_old[r] != o_new[r]:
            drift.append(f"STATUS-CHANGE: {r} {o_old[r]} -> {o_new[r]}")
    if drift:
        print("DRIFT DETECTED:")
        for d in drift:
            print("  " + d)
        return 1
    print(f"NO DRIFT: {len(o_new)} repos, "
          f"{sum(1 for v in o_new.values() if v == 'ONLINE-ONLY')} online-only")
    return 0


def cmd_where(name: str, inv: dict) -> int:
    hits = [e for e in inv["our_repos"]
            if e["repo"].split("/")[1].lower() == name.lower() or name.lower() in e["repo"].lower()]
    if not hits:
        hits = [e for e in inv["foreign_clones"] if name.lower() in e["repo"].lower()]
        for e in hits:
            print(f"{e['repo']}: LOCAL (foreign clone) — "
                  + ", ".join("~/" + p for p in e["local_paths"]))
        return 0 if hits else 1
    for e in hits:
        if e["status"] == "LOCAL":
            print(f"{e['repo']}: LOCAL — " + ", ".join("~/" + p for p in e["local_paths"]))
        else:
            print(f"{e['repo']}: ONLINE-ONLY (exists on GitHub, not on this disk)")
            print(f"    url   : {e['url']}")
            print(f"    vis   : {e['visibility']}   last push: {e['pushed_at']}")
            print(f"    clone : git clone {e['url']} {HOME}/{e['repo'].split('/')[1]}")
        if e["note"]:
            print(f"    note  : {e['note']}")
    return 0


def cmd_list(inv: dict) -> int:
    ours, foreign = inv["our_repos"], inv["foreign_clones"]
    online = [e for e in ours if e["status"] == "ONLINE-ONLY"]
    loc = [e for e in ours if e["status"] == "LOCAL"]
    print(f"{inv['owner']}: {len(loc)} LOCAL, {len(online)} ONLINE-ONLY "
          f"(+{len(foreign)} foreign clones). Full list: {OUT_MD}")
    print("\nONLINE-ONLY (exists on GitHub; NOT on this disk — not 'gone'):")
    for e in online:
        flag = "archived " if e["archived"] else ""
        print(f"  {e['repo']:<46} {e['visibility'][:3]} {flag}{e['pushed_at']}  {e['url']}")
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
    if not args or args[0] == "--list":
        cached = load_json(OUT_JSON, None)
        if not cached:
            cached = build()
            write_files(cached)
        return cmd_list(cached)
    if args and args[0] == "--note":
        if len(args) < 2 or "=" not in args[1]:
            print("usage: --note 'owner/repo=text'", file=sys.stderr)
            return 2
        k, v = args[1].split("=", 1)
        notes = load_json(NOTES, {})
        notes[k.strip()] = v.strip()
        NOTES.write_text(json.dumps(notes, indent=2, sort_keys=True) + "\n")
        print(f"note set for {k.strip()}")
        inv = build()
        write_files(inv)
        return 0
    if args and args[0] == "where":
        if len(args) < 2:
            print("usage: where <name>", file=sys.stderr)
            return 2
        return cmd_where(args[1], build())
    if args and args[0] == "--check":
        return cmd_check(build())
    inv = build()
    write_files(inv)
    n_online = sum(1 for e in inv["our_repos"] if e["status"] == "ONLINE-ONLY")
    print(f"wrote {OUT_MD} and {OUT_JSON}")
    print(f"{len(inv['our_repos'])} repos owned by {inv['owner']}: "
          f"{len(inv['our_repos']) - n_online} LOCAL, {n_online} ONLINE-ONLY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
