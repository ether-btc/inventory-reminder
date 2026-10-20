# RESUME — inventory-reminder open-source packaging (paused 2026-10-20)

## State
- **Local repo, unpushed:** `~/projects/inventory-reminder`, 1 commit `286025c`, clean tree.
- **All 13 tests pass** (hermes venv pytest, 2.5s). No-config default mode verified
  against the live host: `--check` correctly reported 14 real drifts (445→458 skills
  since the 10-18 weekly refresh; cron will catch up Sunday).
- Live `~/.hermes/scripts/*.py` copies **untouched**.

## What's done
- `system-inventory.py` + `repo-inventory.py` packaged: `--config`/`INVENTORY_CONFIG`
  JSON override (config.example.json); no hardcoded host paths; owner fail-closed
  when unset; `generated_by`/headers dynamic.
- `tests/` hermetic fixtures (fake HOME, stubbed `gh`); `ci.yml`; MIT LICENSE;
  README (prior-art positioning: claude-mem / context-mode / planning-with-files);
  CONTRIBUTING (stdlib-only, read-only, UNAVAILABLE-never-silent, determinism);
  `refresh.example.sh`.

## Next steps (in order)
1. **Create + publish the GitHub repo** — HARD GATE (external publication): needs
   explicit user go. Suggest `ether-btc/inventory-reminder`, start PRIVATE, flip
   public after the first green CI run. Then add to `REPOS.md` registry
   (`repo-inventory --note`) and file to wiki (evidence-preserving-wiki-filing).
2. Optional post-publish: decide whether `project-catalog` (separate private repo,
   catalog generator for logical projects) gets the same treatment, or is folded
   in as a sibling module later.
3. Optional host migration: point the live cron at the repo version with an
   `INVENTORY_CONFIG` (owner=ether-btc) — NOT required for publication.

## Gotchas
- `repo-inventory.py` no-config on THIS host lists everything as "foreign clones"
  because owner is unset without `REPO_INVENTORY_OWNER`/config — expected, documented.
- Determinism tests strip `generated_at` (JSON) / "Generated …" line (MD); keep it that way.
