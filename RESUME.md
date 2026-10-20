# RESUME — inventory-reminder open-source (updated 2026-10-20 ~11:45, pre-model-switch)

## State
- **Local repo, unpushed:** `~/projects/inventory-reminder`, clean tree at `55bb0a7`
  (3 commits: `286025c` package / `57a0775` RESUME checkpoint / `55bb0a7` CI
  stdlib-guard fixed grep→AST). 13/13 tests pass (re-verified 11:33).
- **User pre-authorized publication** ("then publish to github… this has to be
  high quality when I share it with third parties"). WP3 = create
  `ether-btc/inventory-reminder` private → green CI → flip public → register
  (REPOS.md note, wiki, AEON). Record the go + execute.
- **Standard decision (user, 10-20):** the work affects Hermes Agent, so
  **NousResearch/hermes-agent CONTRIBUTING.md is the bar** for our repo.
  Their policy places this class of extension as a *standalone plugin/skill
  repo*, not core — so we publish standalone and conform to their
  contribution conventions.

## What's done
- `system-inventory.py` + `repo-inventory.py` packaged: `--config`/`INVENTORY_CONFIG`
  JSON override (config.example.json); no hardcoded host paths; owner fail-closed
  when unset; `generated_by`/headers dynamic; stdlib-only AST guard in CI.
- `tests/` hermetic fixtures (fake HOME, stubbed `gh`); `ci.yml`; MIT LICENSE;
  README (prior-art: claude-mem / context-mode / planning-with-files);
  CONTRIBUTING (invariants); `refresh.example.sh`.
- No-config default mode verified against the live host: `--check` correctly
  reported 14 real drifts (445→458 skills since the 10-18 refresh). Live
  `~/.hermes/scripts/*.py` copies **untouched**.

## Team results (deleg_9c0c086b) + dispositions
1. **Publication review:** current package state CLEAN — 13/13, invariants hold,
   live scripts untouched; its "blockers"/"minors" are just WP1 build items.
   Truncated at iteration cap but its summary covered the package state.
2. **Effectivity measurement:** honest result, LOW confidence — N=5
   sessions/window, zero clear "re-derive/suggest-already-local" incidents in PRE
   (09-20..10-13) and POST (10-14..10-20) alike; POST sessions demonstrably
   consume INVENTORY.md / `--check` / skill rule 0f; drift gate NO DRIFT on the
   10-14 + 10-18 cron runs. DISPOSITION: fold its `citable_paragraph` into README
   as "Observed on the origin host" WITH the stated N/limits — never as a rate
   claim. Raw: /home/hermes-pi/.hermes/cache/delegation/live/deleg_9c0c086b/task-1.log
3. **Prototype spec:** complete spec on disk as untracked `SPEC.md`
   (+ `spec_output.json` raw). TWO DEFECTS caught by my trace-through:
   (a) its `where` tests query the skills section, which is UNAVAILABLE in the
   fixtures → write fixture-correct tests (query repos/MCP/models that ARE in the
   fixtures); (b) its "copy refresh.sh next to live scripts" wiring would make
   cron run the LIVE scripts (dirname resolution), not the repo pipeline →
   replace with: thin wrapper `~/.hermes/scripts/inventory-refresh.sh` +
   install-state file `~/.hermes/inventory-reminder-install.json` (pins repo dir)
   + backup-then-swap; rollback = restore backup + rm wrapper + rm config.

## Untracked working files (do NOT commit — add to .gitignore)
- `SPEC.md` (design spec), `spec_output.json` (raw subagent output).

## Remaining work, in order
- **WP1 build (next):** implement SPEC.md with the two corrections above:
  1. `system-inventory.py where <term> [--json]` (7 sections, ci-substring,
     exit 0 hit / 1 miss) + fixture-correct tests
  2. `scripts/refresh.sh` (rename of refresh.example.sh, executable, config-aware)
  3. `scripts/setup-host.sh` (wrapper + install-state + backup; idempotent; rollback)
  4. `config.host.json` (origin-host values: owner=ether-btc etc.)
  5. Hermes **plugin adapter**: `hermes inventory` CLI + `inventory_where` tool +
     opt-in default-OFF session-start digest line (cached --summary, no per-turn
     rescan) — load skill `hermes-plugin-tool-registration` first
  6. Docs to the hermes-agent standard: README (quickstart + effectivity block +
     Hermes-integration + Security sections); CONTRIBUTING rewritten to
     hermes-agent's structure (contribution priorities, search-first dupes,
     Conventional Commits + scopes, branch naming, PR-template fields,
     cross-platform honesty — systemctl→UNAVAILABLE on macOS/WSL, MIT);
     squash local history to Conventional Commits (repo unpushed — safe)
- **WP2 gate:** live-host verification (`where` against the real digest;
  setup-host.sh idempotent run + rollback proof; cron still green) + fresh
  independent review subagent over the final diff; disposition every finding.
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
