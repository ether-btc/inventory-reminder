# inventory-reminder

A live, evidence-backed inventory of what is actually on your host — repos,
skills, tools, apps, models, services — regenerated from ground truth and
surfaced so that AI agents (and humans) never have to re-derive "what do I
already have" from memory.

Born from a standing operational frustration:

> "I am tired of having to remind you, a machine, of its own cogs and levers
> over and over again, instead of you, yourself, being conscious about its
> own infrastructure and how to use it."

The system closes that loop with three read-only scanners and one digest:

| Piece | What it answers |
|---|---|
| `repo-inventory.py` | Which of my GitHub repos are LOCAL (cloned here) vs ONLINE-ONLY (on GitHub, intentionally off-disk)? `where <name>` gives a one-shot lookup + ready clone command. |
| `system-inventory.py` | Which skills, MCP servers, CLIs, Python packages, local models and systemd services does this host actually have RIGHT NOW? `where <term>` searches all sections at once. |
| `refresh.sh` | The pipeline: repo scan → system scan → drift check → one-line summary. Wire it to cron via `setup-host.sh`. |

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

## Quickstart (this host)

```bash
cd ~/projects/inventory-reminder
./scripts/setup-host.sh
# Now you can:
system-inventory.py where aider      # do we have aider anywhere?
repo-inventory.py where aeon         # where is aeon repo?
~/.hermes/scripts/inventory-refresh.sh  # manual refresh (cron runs weekly)
```

## Quick start (generic)

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

## Capability query: `where <term>`

Both scanners expose a `where` subcommand for fast lookups:

```bash
# system-inventory.py — searches ALL sections (skills, repos, MCP, CLIs, models, key packages)
system-inventory.py where <term> [--config PATH] [--json]

# repo-inventory.py — searches owned + foreign repos only
repo-inventory.py where <term> [--config PATH]
```

- Case-insensitive substring match across all sections.
- Exit code: `0` on hit (≥1 match), `1` on miss.
- `--json` emits `{"query": "...", "hits": [{"section", "item", "detail"}, ...]}` for scripting.
- `--json` must appear *after* the term argument: `where <term> --json`. (The term is positional.)
- Human output groups hits by section.

## Observed effectivity on the origin host

*Observed on the origin host; sample size too small for statistical claims.*

Across 5 manually reviewed substantial sessions per window (PRE: 2026-09-20..2026-10-13, 1984 total; POST: 2026-10-14..2026-10-20, 441 total), zero clear "re-derive/suggest-already-local" incidents were found in either window — PRE sessions performed manual discovery using live probes (system-inventory.py, repo-inventory.py, SSH to a16, local git), while POST sessions used the Inventory Reminder System (reading INVENTORY.md, invoking system-inventory.py --check, querying Mnemosyne/wiki). The INVENTORY.md --check drift gate has run twice (2026-10-14, 2026-10-18) with zero drift (exit 0). The operator's original frustration ("I am tired of having to remind you, a machine, of its own cogs and levers") motivated the 2026-10-14 implementation; the environment-awareness skill Rule 0f now directs agents to INVENTORY.md first. Sample size (N=5/window) is insufficient for rate estimation; automated scoring produced false positives; the effect is visible in workflow (agents now read INVENTORY.md and use --check) but not quantifiable as a rate reduction from this sample.

## Hermes integration

This project was born inside Hermes and ships an optional plugin adapter for first-class integration:

```bash
# In a Hermes session with the plugin loaded:
hermes inventory where aider          # searches the live digest via the adapter
hermes inventory --summary            # one-line digest for session bootstrap
```

The adapter registers:
- CLI subcommand: `hermes inventory where <term> [--json]`
- Tool: `inventory_where(term: str, json: bool = false)` — callable from agents
- Opt-in session-start digest: `HERMES_INVENTORY_DIGEST=1` in env prints a one-line `--summary` at session start (default OFF; zero per-turn cost, cached).

See `scripts/hermes_inventory_plugin.py` for the adapter source (stdlib only, reads `inventory.json` — no live rescans per turn).

## Surfacing mechanisms

The value is in where the digest gets read. This project ships the scanners;
pick your surfaces:

1. **Session bootstrap** — reference `INVENTORY.md` in your agent's always-loaded
   context file (SOUL.md / AGENTS.md): *"Know your own infrastructure: read
   `INVENTORY.md` at session start."*
2. **Skill/agent rules** — a rule like "before suggesting any external tool
   or library, check the inventory first."
3. **Memory layer** — store the `--summary` line in long-term memory weekly.
4. **Cron** — `refresh.sh` on a weekly schedule; `--check` exit code
   feeds alerts.
5. **Hermes plugin adapter** — `hermes inventory` CLI + `inventory_where` tool
   + optional session-start digest line.

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
- **Cross-platform:** `systemctl` is used for the services section. On macOS/WSL
  where `systemctl` is absent, the section reports UNAVAILABLE with the reason
  — it does not silently succeed with empty data. This is by design (see
  `scan_services()`).

## Layout

```
scripts/system-inventory.py     the scanner (stdlib only)
scripts/repo-inventory.py       repo LOCAL/ONLINE-ONLY scanner (stdlib only)
scripts/refresh.sh              pipeline for cron (uses INVENTORY_CONFIG)
scripts/setup-host.sh           idempotent host wiring (installs config + refresh script + install-state)
scripts/rollback-host.sh        reverses setup-host.sh (restores backup, removes config + state)
config.example.json             template with placeholder paths/owner
config.host.json                origin-host config (owner=ether-btc, real paths)
tests/                          hermetic fixtures + determinism + drift contracts
```

## License

MIT — see [LICENSE](LICENSE).

## Security

- No secrets, tokens, or credentials in the repo. The config template uses
  `/home/YOURUSER` placeholders.
- The scanners are read-only on the system (listings, file reads, `gh` API reads).
- No network calls other than fixed `gh` API reads against the authenticated user.
- Vulnerability reporting: open a private [Security Advisory](https://github.com/ether-btc/inventory-reminder/security/advisories/new) on GitHub.