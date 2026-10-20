# Contributing

The invariants that make this tool trustworthy — please preserve them:

1. **Stdlib only.** No third-party Python dependencies. If a feature needs one,
   split it into an optional extension module, never the core scanners.
2. **Read-only on the system.** Scanners may run listings and fixed
   read-only subcommands. They must never clone, commit, push, delete, or
   execute project code. The only writes are the scanners' own output files.
3. **UNAVAILABLE, never silent.** A broken probe must surface with a reason.
   Adding a section? It must have an unavailable path too.
4. **Determinism.** Reruns must be byte-identical. Timestamps belong only in
   `generated_at` (JSON) and the "Generated …" header line (MD). The
   `test_deterministic_reruns` test guards this — keep it passing.
5. **Config-first for host specifics.** Paths, owners, hints and tool lists
   belong in `config.example.json` keys, not in code. Host defaults may exist
   but must stay overridable.
6. **Drift contracts.** `--check` exit codes are an interface (cron,
   monitors). Changing them is a breaking change — document in the PR.

## Running tests

```bash
python3 -m pytest tests -q
```

Tests are hermetic: they build a fake `$HOME` under a temp dir, stub `gh`
with a shell script, and never touch your real system.

## PR checklist

- [ ] `python3 -m pytest tests -q` green
- [ ] no new imports beyond the standard library
- [ ] new host-specific constant → config key + `config.example.json` entry
- [ ] README "Honest limits" updated if behavior changed
- [ ] determinism test still passes (or was extended, not weakened)
