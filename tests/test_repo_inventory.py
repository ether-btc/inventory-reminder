"""repo-inventory.py: remote normalization, local/online classification with a
stubbed `gh`, and the drift-check exit contract."""
import importlib.util
import json
import os
import subprocess
from pathlib import Path

from conftest import REPO_ROOT, run_script


def _import_repo_inventory():
    spec = importlib.util.spec_from_file_location(
        "repo_inv", REPO_ROOT / "scripts" / "repo-inventory.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_norm_remote_variants():
    mod = _import_repo_inventory()
    f = mod.norm_remote
    assert f("git@github.com:o/r.git") == "o/r"
    assert f("https://github.com/o/r") == "o/r"
    assert f("http://github.com:o/r.git") == "o/r"
    assert f("ssh://git@github.com/o/r.git") == "o/r"
    assert f("o/r") == "o/r"
    assert f("git@github.com:o/r/sub.git") == ""      # >1 slash: not a repo
    assert f("") == ""
    assert f("not-a-github-url") == ""


def _make_git_repo(root: Path, name: str, origin: str) -> None:
    d = root / "projects" / name
    d.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "remote", "add", "origin", origin], cwd=d, check=True)


def _gh_stub(tmp_path: Path, repos_json: list) -> Path:
    """A fake `gh` that emits the given repos list for `repo list`."""
    out = tmp_path / "ghout.json"
    out.write_text(json.dumps(repos_json))
    stub = tmp_path / "bin" / "gh"
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text(f"#!/bin/sh\ncat {out}\n")
    stub.chmod(0o755)
    return stub


GH_REPO_A = {"name": "demo", "nameWithOwner": "fixture-owner/demo",
             "url": "https://github.com/fixture-owner/demo", "visibility": "PRIVATE",
             "isFork": False, "isArchived": False, "pushedAt": "2026-10-01T00:00:00Z",
             "description": "demo project"}
GH_REPO_B = {"name": "other", "nameWithOwner": "fixture-owner/other",
             "url": "https://github.com/fixture-owner/other", "visibility": "PUBLIC",
             "isFork": False, "isArchived": False, "pushedAt": "2026-09-01T00:00:00Z",
             "description": ""}


def test_local_vs_online_classification(cfg, fake_home, tmp_path):
    home = fake_home
    _make_git_repo(home, "demo", "https://github.com/fixture-owner/demo")
    _make_git_repo(home, "foo", "https://github.com/upstream/foo")  # foreign clone
    stub = _gh_stub(tmp_path, [GH_REPO_A, GH_REPO_B])

    p = run_script("repo-inventory.py", ["--config", str(cfg), "--write"],
                   env_extra={"PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}"})
    assert p.returncode == 0, p.stderr
    inv = json.loads((home / ".hermes" / "repos.json").read_text())
    by = {e["repo"]: e for e in inv["our_repos"]}
    assert by["fixture-owner/demo"]["status"] == "LOCAL"
    assert by["fixture-owner/other"]["status"] == "ONLINE-ONLY"
    assert {"repo": "upstream/foo", "local_paths": ["projects/foo"]} in inv["foreign_clones"]
    assert (home / ".hermes" / "REPOS.md").exists()


def test_no_owner_configured_still_writes_local_clones(cfg, fake_home, tmp_path):
    home = fake_home
    _make_git_repo(home, "foo", "https://github.com/upstream/foo")
    stub = _gh_stub(tmp_path, [])
    cfg_no_owner = tmp_path / "cfg2.json"
    data = json.loads(cfg.read_text())
    data.pop("owner")
    cfg_no_owner.write_text(json.dumps(data))
    env = {"PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
           "REPO_INVENTORY_OWNER": ""}

    p = run_script("repo-inventory.py", ["--config", str(cfg_no_owner), "--write"],
                   env_extra=env)
    assert p.returncode == 0, p.stderr
    inv = json.loads((home / ".hermes" / "repos.json").read_text())
    assert inv["owner_error"]
    assert inv["our_repos"] == []
    assert any(f["repo"] == "upstream/foo" for f in inv["foreign_clones"])


def test_check_drift_exit_contract(cfg, fake_home, tmp_path):
    home = fake_home
    _make_git_repo(home, "demo", "https://github.com/fixture-owner/demo")
    stub_dir = tmp_path / "bin"
    env = {"PATH": f"{stub_dir}:{os.environ['PATH']}"}
    _gh_stub(tmp_path, [GH_REPO_A, GH_REPO_B])

    p1 = run_script("repo-inventory.py", ["--config", str(cfg), "--write"], env_extra=env)
    assert p1.returncode == 0, p1.stderr
    ok = run_script("repo-inventory.py", ["--config", str(cfg), "--check"], env_extra=env)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "NO DRIFT" in ok.stdout

    # upstream removes a repo -> GONE-UPSTREAM drift
    out = tmp_path / "ghout.json"
    out.write_text(json.dumps([GH_REPO_A]))
    p2 = run_script("repo-inventory.py", ["--config", str(cfg), "--check"], env_extra=env)
    assert p2.returncode == 1
    assert "GONE-UPSTREAM" in p2.stdout


def test_where_lookup(cfg, fake_home, tmp_path):
    _make_git_repo(fake_home, "demo", "https://github.com/fixture-owner/demo")
    stub = _gh_stub(tmp_path, [GH_REPO_A, GH_REPO_B])
    env = {"PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}"}
    p = run_script("repo-inventory.py", ["--config", str(cfg), "where", "demo"], env_extra=env)
    assert p.returncode == 0, p.stderr
    assert "fixture-owner/demo: LOCAL" in p.stdout

    p2 = run_script("repo-inventory.py", ["--config", str(cfg), "where", "other"], env_extra=env)
    assert p2.returncode == 0
    assert "ONLINE-ONLY" in p2.stdout
