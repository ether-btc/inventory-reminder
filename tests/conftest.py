"""Shared fixtures: a fake $HOME tree that lets the scanners run hermetically."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"


@pytest.fixture()
def fake_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    hermes = home / ".hermes"
    hermes.mkdir(parents=True)

    # repos.json fixture (what repo-inventory.py would have written)
    repos = {
        "owner": "fixture-owner",
        "our_repos": [
            {"repo": "fixture-owner/demo", "url": "https://github.com/fixture-owner/demo",
             "visibility": "PRIVATE", "status": "LOCAL", "local_paths": ["projects/demo"]},
            {"repo": "fixture-owner/online-only", "url": "https://github.com/fixture-owner/online-only",
             "visibility": "PUBLIC", "status": "ONLINE-ONLY", "local_paths": []},
        ],
        "foreign_clones": [
            {"repo": "upstream/foo", "local_paths": ["projects/foo"]},
        ],
    }
    (hermes / "repos.json").write_text(json.dumps(repos, indent=2) + "\n")
    (hermes / "REPOS.md").write_text("# fixture\n")

    # config.yaml with a minimal mcp_servers block (the script's line-scanner shape)
    (hermes / "config.yaml").write_text(
        "mcp_servers:\n"
        "  demo_mcp:\n"
        "    command: npx\n"
        "    enabled: true\n"
        "  other_mcp:\n"
        "    command: /usr/bin/other\n"
        "    enabled: false\n"
    )

    # a fake gguf model dir
    models = home / "models"
    models.mkdir()
    (models / "fake-7b.gguf").write_bytes(b"\x00" * (1024 * 1024))  # 1 MiB

    # hermes venv bin exists but no python -> apps section degrades UNAVAILABLE
    venv_bin = hermes / "hermes-agent" / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "hermes").write_text("#!/bin/sh\nexit 0\n")
    (venv_bin / "hermes").chmod(0o755)
    return home


@pytest.fixture()
def cfg(fake_home: Path, tmp_path: Path) -> Path:
    home = fake_home
    hermes = home / ".hermes"
    data = {
        "home": str(home),
        "hermes_home": str(hermes),
        "out_dir": str(hermes),
        "repos_json": str(hermes / "repos.json"),
        "repos_md": str(hermes / "REPOS.md"),
        "config_yaml": str(hermes / "config.yaml"),
        "venv": str(hermes / "hermes-agent" / "venv"),
        "hermes_bin": str(hermes / "hermes-agent" / "venv" / "bin" / "hermes"),
        "model_dirs": [str(home / "models")],
        "owner": "fixture-owner",
        "scan_root": str(home),
        "service_hints": ["zzz-no-such-unit-9x"],
        "max_depth": 5,
    }
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(data, indent=2))
    return p


def run_script(script: str, args: list[str], env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True, timeout=300, env=env,
    )
