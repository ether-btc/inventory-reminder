# inventory-reminder

A live, evidence-backed inventory of what is actually on your host — repos,
skills, tools, apps, models, services — regenerated from ground truth and
surfaced so that AI agents (and humans) never have to re-derive "what do I
already have" from memory.

Born from a standing operational frustration:

> "I am tired of having to remind you, a machine, of its own cogs and levers
> over and over again, instead of you, yourself, being conscious about its
> own infrastructure and how to use it."

The system closes that loop with two read-only scanners and one digest:

| Piece | What it answers |
|---|---|
| `repo-inventory.py` | Which of my GitHub repos are LOCAL (cloned here) vs ONLINE-ONLY (on GitHub, intentionally off-disk)? `where <name>` gives a one-shot lookup + ready clone command. |
| `system-inventory.py` | Which skills, MCP servers, CLIs, Python packages, local models and systemd services does this host actually have RIGHT NOW? |
| `refresh.example.sh` | The pipeline: repo scan → system scan → drift check → one-line summary. Wire it to cron. |

## Guarantees

- **Read-only on the system.** The scanners run listings and read metadata;
  the only files they write are their own outputs. `repo-inventory` runs only
  fixed read-only `gh` reads and `git remote get-url` — it never clones,
  commits, pushes, or deletes.
- **UNAVAILABLE is a category, not a hole.** A section whose source is broken
  is reported UNAVAILABLE with the reason — "missing from the file" always
  means "really gone", never "the scan broke".
- **Deterministic.** Two consecutive runs produce byte-identical output
  (the timestamp lives in `generated_at` only).
- **Drift gate.** `--check` compares live state to the last written inventory
  and exits 1 on drift (new/gone skills, models, MCP toggles, CLI changes,
  service changes, repo count/status changes) — cron/monitor friendly.
- **Stdlib only.** No dependencies to install; Python 3.9+.

## Quick start

```bash
# 1. point the scanners at your host (defaults assume a ~/.hermes layout)
cp config.example.json inventory.json   # edit paths, owner, hints

# 2. build the inventory
INVENTORY_CONFIG=inventory.json python3 scripts/repo-inventory.py --write
INVENTORY_CONFIG=inventory.json python3 scripts/system-inventory.py --write

# 3. one-line summary, for your memory layer / cron feed
INVENTORY_CONFIG=inventory.json python3 scripts/system-inventory.py --summary
# INVENTORY 2026-10-20 11:02 | repos 150 (23L/127O) | skills 445 (...) | mcp 4/5 | pkgs 142 | models 4 (2.7G) | services 4/22

# 4. drift gate
INVENTORY_CONFIG=inventory.json python3 scripts/system-inventory.py --check   # exit 1 on drift
```

Without a config file the scripts keep their built-in defaults (`$HOME/.hermes`
output layout, `hermes` venv paths, common model dirs), so on a Hermes host
they work out of the box.

## Surfacing mechanisms

The value is in where the digest gets read. This project ships the scanners;
pick your surfaces:

1. **Session bootstrap** — reference `INVENTORY.md` in your agent's always-loaded
   context file (SOUL.md / AGENTS.md): *"Know your own infrastructure: read
   `INVENTORY.md` at session start."*
2. **Skill/agent rules** — a rule like "before suggesting any external tool
   or library, check the inventory first."
3. **Memory layer** — store the `--summary` line in long-term memory weekly.
4. **Cron** — `refresh.example.sh` on a weekly schedule; `--check` exit code
   feeds alerts.

## Positioning vs. prior art

The "remember what you have" pattern is well-trodden; the difference here is
a *live capability digest of the host itself*, not a transcript store:

| Project | What it does |
|---|---|
| `thedotmack/claude-mem` (~100k★) | Cross-session transcript recall / injection |
| `mksglu/context-mode` (~28k★) | FTS5+BM25 context store for tool output |
| `OthmanAdi/planning-with-files` (~27k★) | Hook-based per-turn plan re-injection |
| Hermes bundled Tool Search / skills index | Defers/loads *its own* tools and skills |

inventory-reminder answers the question those leave open: *what is actually
installed/running on this machine right now, per category, with an honest
UNAVAILABLE marker where a probe broke.*

## Honest limits

- Sections degrade to UNAVAILABLE when their source is absent (no `hermes`
  CLI → no skills section; no venv → no packages). That is by design.
- `repo-inventory` tracks a single GitHub owner (via `REPO_INVENTORY_OWNER`
  or config `owner`); foreign clones are listed, not tracked upstream.
- The MCP parser is a minimal line-scanner for the top-level `mcp_servers:`
  map of a Hermes `config.yaml` — other tooling configs need their own keys
  in the config file.
- Service filtering is a name/description hint list, not "what should be
  running".
- Model discovery is `*.gguf` under the configured dirs.

## Layout

```
scripts/system-inventory.py   the scanner (stdlib only)
scripts/repo-inventory.py    repo LOCAL/ONLINE-ONLY scanner (stdlib only)
scripts/refresh.example.sh    pipeline for cron
config.example.json           every overridable path/list
tests/                        hermetic fixtures + determinism + drift contracts
```

## License

MIT — see [LICENSE](LICENSE).
