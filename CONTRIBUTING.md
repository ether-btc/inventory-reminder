# Contributing to inventory-reminder

Thank you for contributing! This project provides a live, evidence-backed inventory of
what's actually on your host — repos, skills, tools, apps, models, services — so that
AI agents (and humans) never have to re-derive "what do I already have" from memory.

This project follows the contribution conventions of **NousResearch/hermes-agent**
(upstream). Where this document and upstream differ, upstream wins for placement
decisions; this document governs project-specific invariants.

---

## Contribution Priorities

We value contributions in this order:

1. **Bug fixes** — crashes, incorrect output, silent failures, data loss. Always top priority.
2. **Cross-platform compatibility** — macOS, Linux distros, WSL2. The `systemctl`
   services section explicitly reports UNAVAILABLE on macOS/WSL; fixes that preserve
   this honest degradation are welcome.
3. **Security hardening** — shell injection, path traversal, credential leakage.
   See [Security](#security-considerations).
4. **Performance and robustness** — faster scans, better error handling, graceful degradation.
5. **New capability queries** — extensions to `where` that search additional sections.
6. **Documentation** — fixes, clarifications, new examples.

---

## Before You Start: Search First

- **Search both open *and* merged PRs and issues** for your topic:
  ```bash
  gh search issues --repo ether-btc/inventory-reminder ""
  gh search prs --repo ether-btc/inventory-reminder --state all ""
  ```
- **Search the source** (`rg`, `search_files`) for the capability before proposing it.
- If an open PR already addresses it, consider reviewing/improving that one instead.
- For larger work, comment on the issue to signal you're working on it.

---

## Invariants (Project-Specific)

Every change must preserve these invariants. CI enforces them; reviewers will block on them.

| Invariant | What it means | Test |
|---|---|---|
| **Read-only on the system** | Scanners only run listings/read metadata; only writes are their own output files (`INVENTORY.md`, `inventory.json`, `REPOS.md`, `repos.json`). | `test_unavailable_sections_degrade_not_silently` |
| **UNAVAILABLE is a category, not a hole** | A broken probe reports UNAVAILABLE with the reason — never silently omitted. | `test_unavailable_sections_degrade_not_silently` |
| **Deterministic reruns** | Two consecutive `--write` runs produce byte-identical output (except `generated_at` in JSON / "Generated" line in MD). | `test_deterministic_reruns` |
| **Drift gate exit contract** | `--check` exits 1 on drift, 0 on no drift. Exit code is a stable interface. | `test_check_no_drift_exit0_then_drift_exit1` |
| **Stdlib only** | No third-party Python imports. CI runs an AST-based stdlib guard. | `.github/workflows/ci.yml` |
| **Config-driven paths** | All host-specific paths come from `--config`/`INVENTORY_CONFIG`; no hardcoded paths. | `test_write_produces_both_files` with custom config |
| **Owner fail-closed** | `repo-inventory.py` hard-exits (2) if `owner` is configured but `gh repo list` fails, rather than degrading silently. This is intentional — a broken GitHub read must not produce a false "no repos owned" result. | `test_no_owner_configured_still_writes_local_clones` |

---

## Development Setup

### Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.9+** | Stdlib only — no `uv`/`pip` dependencies required |
| **Git** | For version control |
| **pytest** | For running tests (`pip install pytest` or use system) |

### Quick start

```bash
git clone https://github.com/ether-btc/inventory-reminder
cd inventory-reminder

# Run tests (hermetic fixtures, no host dependencies)
python -m pytest tests -v

# Test on your host (uses built-in ~/.hermes defaults)
python scripts/system-inventory.py --write
python scripts/system-inventory.py --check
python scripts/system-inventory.py --summary
```

---

## Project Structure

```
inventory-reminder/
├── scripts/
│   ├── system-inventory.py       # Host capability scanner (stdlib)
│   ├── repo-inventory.py         # GitHub repo LOCAL/ONLINE-ONLY scanner (stdlib)
│   ├── refresh.sh                # Cron pipeline (repo scan → system scan → drift → summary)
│   ├── setup-host.sh             # Idempotent host wiring (config + refresh script + install-state)
│   ├── rollback-host.sh          # Reverses setup-host.sh (restores backup, removes config)
│   └── hermes_inventory_plugin.py # Hermes plugin adapter (tools + optional session digest)
├── config.example.json           # Template with placeholder paths/owner
├── config.host.json              # Origin-host config (owner=ether-btc, real paths)
├── tests/
│   ├── conftest.py               # Hermetic fixtures (fake $HOME, stubbed gh)
│   ├── test_system_inventory.py  # system-inventory.py invariants + where tests
│   └── test_repo_inventory.py    # repo-inventory.py tests
├── .github/workflows/ci.yml      # AST stdlib guard + pytest
├── README.md
├── LICENSE
└── CONTRIBUTING.md               # This file
```

---

## Pull Request Process

### Branch naming

```
fix/description     # Bug fixes
feat/description    # New features (e.g., feat/where-search-models)
docs/description    # Documentation
test/description    # Tests
refactor/description # Code restructuring (no behavior change)
chore/description   # Build, CI, dependency updates
```

### Before submitting

1. **Run tests**: `python -m pytest tests -v` (matches CI)
2. **Test manually**: Run the scanners on your host with a config; verify `where` and `--check`.
3. **Check cross-platform impact**: If you touch file I/O, process management, or `systemctl`,
   consider macOS/Linux/WSL2. The services section must degrade to UNAVAILABLE, not crash.
4. **Keep PRs focused**: One logical change per PR.

### PR description

Include:

- **What** changed and **why**
- **How to test** it (reproduction steps for bugs, usage examples for features)
- **What platforms** you tested on
- Reference any related issues

### Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>
```

| Type | Use for |
|------|---------|
| `fix` | Bug fixes |
| `feat` | New features |
| `docs` | Documentation |
| `test` | Tests |
| `refactor` | Code restructuring (no behavior change) |
| `chore` | Build, CI, dependency updates |

Scopes: `system-scan`, `repo-scan`, `where`, `config`, `tests`, `ci`, `docs`, `plugin`, `cron`.

Examples:
```
fix(where): handle UNAVAILABLE skills section without crash
feat(where): add case-insensitive substring match for models
docs(readme): add quickstart for this host
test(system): add where JSON output test
refactor(config): unify config keys across both scanners
```

---

## Security Considerations

- **No secrets in the repo**. `config.example.json` uses `/home/YOURUSER` placeholders.
- **Read-only scanners**: listings, file reads, fixed `gh` API reads only.
- **No network calls** other than authenticated `gh` API reads against the user's own repos.
- **Shell injection**: All `subprocess.run` calls use list args (never `shell=True`).
- **Path traversal**: Paths are resolved from config; user input never directly interpolated into paths.
- **Vulnerability reporting**: Open a private [Security Advisory](https://github.com/ether-btc/inventory-reminder/security/advisories/new) on GitHub.

---

## Reporting Issues

- Use [GitHub Issues](https://github.com/ether-btc/inventory-reminder/issues)
- Include: OS, Python version, full error traceback, steps to reproduce
- Check existing issues before creating duplicates

---

## Community

- **Discord**: [discord.gg/NousResearch](https://discord.gg/NousResearch) — for questions, showcasing projects, and sharing skills/plugins
- **GitHub Discussions**: For design proposals and architecture discussions

---

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).

---

## Cross-Platform Honesty

The services section uses `systemctl list-units`. On macOS and WSL2 where `systemctl`
is absent, the section reports:

```
UNAVAILABLE — `systemctl list-units` exited 127: [Errno 2] No such file or directory: 'systemctl'
```

This is **by design**. "Missing from the file" means "really gone", not "the scan broke".
Fixes that preserve this honest degradation (e.g., adding a launchd probe for macOS as
a *separate* section) are welcome. Fixes that paper over the absence with empty data
will be rejected.

---

## Adding New `where` Search Sections

To add a new searchable section to `system-inventory.py where`:

1. Ensure the section's data is already in `build()` output (add to `build()` if needed).
2. Add a search block in `cmd_where()` following the existing pattern.
3. Add the section to `section_order` and `section_labels`.
4. Add fixture-correct tests in `tests/test_system_inventory.py` that query
   sections **available in the fixtures** (repos, MCP servers, models, CLI tools —
   skills/apps are UNAVAILABLE in fixtures by design).
5. Verify `pytest tests/ -q` passes and CI AST guard is clean.