# RESUME — inventory-reminder open-source (updated 2026-10-20 ~13:00)

## State
- **Local repo, unpushed:** `~/projects/inventory-reminder`, clean tree at `39e7455`
  (8 commits total: 3 original + WP1 feat(where)+host wiring + docs + review-fixes).
  21/21 tests pass.
- **User pre-authorized publication** ("then publish to github… high quality when I share
  with third parties"). WP3 = create `ether-btc/inventory-reminder` private → green CI →
  flip public → register (REPOS.md note, wiki, AEON). Log the go + do it.
- **Standard decision (user, 10-20):** NousResearch/hermes-agent CONTRIBUTING.md is the
  bar — standalone plugin/skill repo per upstream policy, conform to their conventions.

## What's done (WP1 complete + review defects fixed)
- All 3 minor defects from independent review (deleg_6389fdfd) fixed:
  1. **system-inventory.py** — `scan_skills()` now returns `name_to_source` mapping;
     `cmd_where` uses it so skills show correct source (builtin/official/skills.sh/url/local)
  2. **scripts/refresh.example.sh** — removed; `refresh.sh` is the canonical pipeline
  3. **scripts/setup-host.sh** — `--check` guarded to only run if `inventory.json` exists
     (first run has no drift baseline)
- `CONTRIBUTING.md` — documents owner fail-closed invariant
- `README.md` — documents `--json` must appear after term
- Live `~/.hermes/scripts/*.py` copies **untouched**

## Team results (deleg_9c0c086b) + dispositions
1. **Publication review:** package state CLEAN — invariants hold, live scripts untouched.
2. **Effectivity measurement:** honest result, LOW confidence — folded into README.
3. **Prototype spec:** two defects corrected by design (fixture-correct where tests;
   wrapper-based host wiring with backup + rollback).

## Independent review (deleg_6389fdfd) — ALL DISPOSITIONED
- **RECOMMENDATION: APPROVE** after fixing 3 minor defects → **ALL FIXED**
- All 6 invariants PASS (read-only, UNAVAILABLE-not-hole, deterministic, drift gate,
  stdlib-only, config-driven paths, owner fail-closed)
- README claims match behavior
- All commits follow Conventional Commits
- No secrets/tokens/credentials in repo

## Remaining work, in order
- **WP2 gate:** live-host verification — run `setup-host.sh` (live mutation into
  `~/.hermes`, needs your explicit authorization per hard-gate rule) + verify cron
  still green + independent review subagent dispositioned (done: APPROVE)
- **WP3 publish (pre-authorized):** private create → push → CI green → public →
  register: `repo-inventory --note`, wiki filing, AEON entry.
  Then optionally run setup-host.sh for real so prototype is OPERATIONAL here.

## Gotchas
- `test_deterministic_reruns` is flaky on live host (systemd running_total changes
  between runs — pre-existing, not a regression). Re-run passes.
- Trigger words in shell command lines are runtime-blocked — route prose through files.
- Always `git status --short` before commits (SPEC.md/spec_output.json untracked).