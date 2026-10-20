# RESUME — inventory-reminder open-source (updated 2026-10-20 ~15:00, COMPLETE + uninstall+monitor)

## State
- **Repo published:** `https://github.com/ether-btc/inventory-reminder` (PUBLIC, CI green)
- **Local repo:** `~/projects/inventory-reminder`, clean tree at `45816f0` (11 commits), pushed to origin/master
- **AEON:** entry committed and pushed to `ether-btc/aeon` main (`cc711ef`)
- **Wiki:** page filed at `entities/inventory-reminder-20261020.md`, index.md + log.md updated, pushed via wiki-push.sh to master
- **repo-inventory --note:** note set in `~/.hermes/repos-notes.json`
- **Live host:** `setup-host.sh` ran successfully — config + refresh script installed in `~/.hermes/`, pipeline OK, drift check clean

## What's done (all WP complete + uninstall+monitor)
- **WP1:** feat(where) + host wiring + Hermes plugin adapter + docs to hermes-agent standard — 21/21 tests, AST stdlib guard clean
- **Review fixes:** 3 minor defects from deleg_6389fdfd all fixed (skill source mapping, refresh.example.sh removed, setup-host.sh --check guard)
- **WP2:** setup-host.sh live run verified (config + refresh script + install-state + backup + pipeline OK + drift check clean)
- **CI fix:** mkdir output dir before write_text in both scanners (fixed GitHub Actions smoke test FileNotFoundError) — CI now green
- **WP3:** Published — private → push → CI green → public → registered (repo-inventory --note, wiki filing, AEON entry)
- **Uninstall:** rollback-host.sh rewritten as full host uninstall — restores/removes refresh script, removes config, install-state, generated outputs (inventory.json, INVENTORY.md), logs, pycache; idempotent; leaves unrelated ~/.hermes/scripts/* untouched
- **Monitoring:** scripts/monitor.sh added — `status` (wiring + inventory snapshot + section availability + unavailable-section count), `run` (timed refresh + exit code + drift vs previous run), `history [N]` (refresh log tail); reports scan success rate, drift events, section availability honestly framed

## Registration artifacts
- Repo: https://github.com/ether-btc/inventory-reminder (public)
- Wiki: entities/inventory-reminder-20261020.md + index.md + log.md (pushed via wiki-push.sh to master)
- AEON: memory/filing-registry.json entry (committed cc711ef, pushed to main)
- repos-notes.json: note set for ether-btc/inventory-reminder
- Hard-gate auth logs: ~/.hermes/cache/scratch/hard-gate-auth-inventory-reminder-wp2.md, wp3.md

## Gotchas
- test_deterministic_reruns is flaky on live host (systemd running_total changes between runs — pre-existing, not a regression).
- Always `git status --short` before commits (SPEC.md/spec_output.json untracked, ignored via .gitignore).
- Wiki has two branches — master (active) and main (frozen). Always push wiki filings to master via wiki-push.sh.
- monitor.sh run executes refresh.sh (writes inventory.json/INVENTORY.md) — live mutation on ~/.hermes, same scope as setup-host.sh.