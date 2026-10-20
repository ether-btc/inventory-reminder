# RESUME — inventory-reminder open-source (updated 2026-10-20 ~12:30)

## State
- **Local repo, unpushed:** `~/projects/inventory-reminder`, clean tree at `447f355`
  (6 commits total: 3 original + 2 WP1 + 1 docs). 21/21 tests pass.
- **User pre-authorized publication** ("then publish to github… high quality when I share
  with third parties"). WP3 = create `ether-btc/inventory-reminder` private → green CI →
  flip public → register (REPOS.md note, wiki, AEON). Log the go + do it.
- **Standard decision (user, 10-20):** because the work affects Hermes Agent,
  **NousResearch/hermes-agent CONTRIBUTING.md is the bar** for our repo (their policy
  places this kind of extension as a standalone plugin/skill repo, NOT core — so we
  publish standalone and conform to their contribution conventions).

## What's done (WP1 complete)
- `system-inventory.py` + `repo-inventory.py` packaged: `--config`/`INVENTORY_CONFIG`
  JSON override (config.example.json); no hardcoded host paths; owner fail-closed
  when unset; `generated_by`/headers dynamic; stdlib-only AST guard in CI.
- **`system-inventory.py where <term> [--json]`** — searches all 7 sections
  (skills, repos owned/foreign, MCP servers, CLI tools, models, key packages);
  case-insensitive substring; exit 0 hit / 1 miss; JSON output.
- `config.host.json` — origin-host config (owner=ether-btc, real paths).
- `scripts/refresh.sh` — repo pipeline (INVENTORY_CONFIG-aware, executable).
- `scripts/setup-host.sh` — idempotent host wiring (config + refresh script + install-state + backup).
- `scripts/rollback-host.sh` — reverses setup-host.sh (restores backup, removes config + state).
- `scripts/hermes_inventory_plugin.py` — Hermes adapter (`inventory_where` tool + `inventory_summary` tool + opt-in session-start digest via `HERMES_INVENTORY_DIGEST=1`).
- `tests/` — 21 hermetic tests (fixtures: fake HOME, stubbed `gh`); determinism + drift contracts + fixture-correct `where` tests.
- `ci.yml` — AST-based stdlib check (no false positives on `from pathlib import Path`).
- **README** — quickstart (this host), `where` docs, effectivity paragraph (honest, N=5/window, LOW confidence), Hermes integration, Security, cross-platform honesty.
- **CONTRIBUTING** — rewritten to hermes-agent structure (priorities, search-first, invariants table, PR process, Conventional Commits, security, cross-platform honesty).
- Live `~/.hermes/scripts/*.py` copies **untouched**.
- No-config default mode verified against live host: `--check` correctly reports 14 real drifts (445→458 skills since 10-18 refresh).

## Team results (deleg_9c0c086b) + dispositions
1. **Publication review:** package state CLEAN — 13/13 (now 21/21), invariants hold, live scripts untouched.
2. **Effectivity measurement:** honest result, LOW confidence — folded into README as "Observed on the origin host" with stated N/limits.
3. **Prototype spec:** two defects corrected by design:
   (a) fixture-correct `where` tests (query repos/MCP/models, not skills);
   (b) wrapper-based host wiring (thin wrapper + install-state + backup; rollback restores).

## Remaining work, in order
- **WP2 gate:** live-host verification (`where` against real digest; setup-host.sh
  idempotent run + rollback proof; cron still green) + fresh independent review
  subagent over the final diff; disposition every finding.
- **WP3 publish (pre-authorized):** private create → push → CI green → public →
  register: `repo-inventory --note`, wiki filing (evidence-preserving-wiki-filing),
  AEON entry (standing filing system, per 10-04 operator instruction).
  Then optionally run setup-host.sh for real so the prototype is OPERATIONAL here.

## Gotchas
- Trigger words in shell command lines are runtime-blocked — route such prose
  through files.
- Always `git status --short` before commits (SPEC.md/spec_output.json untracked).
- `repo-inventory.py` no-config on THIS host lists everything as "foreign clones"
  (owner unset without config/env) — expected, documented.
- Determinism tests strip `generated_at` (JSON) / "Generated …" line (MD).