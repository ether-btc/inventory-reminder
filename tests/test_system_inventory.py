"""system-inventory.py: config-driven paths, UNAVAILABLE degradation,
determinism, and the drift-check exit contract."""
import json
from pathlib import Path

from conftest import run_script


def _load(hermes: Path) -> dict:
    return json.loads((hermes / "inventory.json").read_text())


def test_write_produces_both_files(cfg, fake_home):
    p = run_script("system-inventory.py", ["--config", str(cfg), "--write"])
    assert p.returncode == 0, p.stderr
    hermes = fake_home / ".hermes"
    assert (hermes / "INVENTORY.md").exists()
    inv = _load(hermes)
    assert inv["repos"]["available"] is True
    assert inv["repos"]["owned_total"] == 2
    assert inv["repos"]["local"] == 1
    assert inv["repos"]["online_only"] == 1


def test_unavailable_sections_degrade_not_silently(cfg, fake_home):
    """No hermes output / no venv python -> UNAVAILABLE, not empty."""
    p = run_script("system-inventory.py", ["--config", str(cfg), "--write"])
    assert p.returncode == 0, p.stderr
    inv = _load(fake_home / ".hermes")
    assert inv["skills"]["available"] is False
    assert "hermes" in inv["skills"]["error"] or "parse" in inv["skills"]["error"]
    assert inv["apps"]["available"] is False
    # md renders the UNAVAILABLE marker instead of omitting the section
    md = (fake_home / ".hermes" / "INVENTORY.md").read_text()
    assert "UNAVAILABLE" in md


def test_mcp_servers_parsed_from_config_yaml(cfg, fake_home):
    inv = _load_run(cfg, fake_home)
    names = {s["name"]: s for s in inv["tools"]["mcp_servers"]}
    assert names["demo_mcp"]["enabled"] is True
    assert names["other_mcp"]["enabled"] is False
    assert inv["tools"]["mcp_enabled"] == ["demo_mcp"]


def test_models_found(cfg, fake_home):
    inv = _load_run(cfg, fake_home)
    assert inv["models"]["count"] == 1
    assert inv["models"]["models"][0]["name"] == "fake-7b"
    assert inv["models"]["models"][0]["size_bytes"] == 1024 * 1024


def _load_run(cfg, fake_home) -> dict:
    p = run_script("system-inventory.py", ["--config", str(cfg), "--write"])
    assert p.returncode == 0, p.stderr
    return _load(fake_home / ".hermes")


def test_deterministic_reruns(cfg, fake_home):
    """Two --write runs: byte-identical except generated_at (JSON) / header line (MD)."""
    hermes = fake_home / ".hermes"
    run_script("system-inventory.py", ["--config", str(cfg), "--write"])
    a = json.loads((hermes / "inventory.json").read_text())
    md_a = "\n".join(l for l in (hermes / "INVENTORY.md").read_text().splitlines()
                     if not l.startswith("Generated "))
    import time
    time.sleep(1.1)  # cross a second boundary so generated_at would differ
    run_script("system-inventory.py", ["--config", str(cfg), "--write"])
    b = json.loads((hermes / "inventory.json").read_text())
    md_b = "\n".join(l for l in (hermes / "INVENTORY.md").read_text().splitlines()
                     if not l.startswith("Generated "))
    a.pop("generated_at")
    b.pop("generated_at")
    assert a == b
    assert md_a == md_b


def test_check_no_drift_exit0_then_drift_exit1(cfg, fake_home):
    hermes = fake_home / ".hermes"
    run_script("system-inventory.py", ["--config", str(cfg), "--write"])
    p = run_script("system-inventory.py", ["--config", str(cfg), "--check"])
    assert p.returncode == 0, p.stdout + p.stderr
    assert "NO DRIFT" in p.stdout

    # simulate drift: a new owned repo appears in repos.json
    repos = json.loads((hermes / "repos.json").read_text())
    repos["our_repos"].append({
        "repo": "fixture-owner/newrepo", "url": "https://github.com/fixture-owner/newrepo",
        "visibility": "PRIVATE", "status": "ONLINE-ONLY", "local_paths": [],
    })
    (hermes / "repos.json").write_text(json.dumps(repos, indent=2) + "\n")
    p2 = run_script("system-inventory.py", ["--config", str(cfg), "--check"])
    assert p2.returncode == 1
    assert "REPO-OWNED_TOTAL" in p2.stdout


def test_summary_one_line(cfg, fake_home):
    run_script("system-inventory.py", ["--config", str(cfg), "--write"])
    p = run_script("system-inventory.py", ["--config", str(cfg), "--summary"])
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip().startswith("INVENTORY ")
    assert len(p.stdout.strip().splitlines()) == 1


def test_missing_config_file_exits_2(fake_home):
    p = run_script("system-inventory.py", ["--config", str(fake_home / "nope.json"), "--write"])
    assert p.returncode == 2


def test_where_hit_repo_owned(cfg, fake_home):
    p = run_script("system-inventory.py", ["--config", str(cfg), "where", "demo"])
    assert p.returncode == 0, p.stderr
    assert "REPOS (owned)" in p.stdout
    assert "fixture-owner/demo" in p.stdout


def test_where_hit_repo_foreign(cfg, fake_home):
    p = run_script("system-inventory.py", ["--config", str(cfg), "where", "upstream"])
    assert p.returncode == 0, p.stderr
    assert "REPOS (foreign)" in p.stdout
    assert "upstream/foo" in p.stdout


def test_where_hit_mcp(cfg, fake_home):
    p = run_script("system-inventory.py", ["--config", str(cfg), "where", "demo_mcp"])
    assert p.returncode == 0, p.stderr
    assert "MCP SERVERS" in p.stdout
    assert "demo_mcp" in p.stdout
    assert "enabled" in p.stdout


def test_where_hit_model(cfg, fake_home):
    p = run_script("system-inventory.py", ["--config", str(cfg), "where", "fake-7b"])
    assert p.returncode == 0, p.stderr
    assert "MODELS" in p.stdout
    assert "fake-7b" in p.stdout


def test_where_miss_exits_1(cfg, fake_home):
    p = run_script("system-inventory.py", ["--config", str(cfg), "where", "definitely-not-there-xyz"])
    assert p.returncode == 1, p.stdout
    assert "MISS" in p.stdout
    assert "not found in any section" in p.stdout


def test_where_json_output(cfg, fake_home):
    p = run_script("system-inventory.py", ["--config", str(cfg), "where", "demo", "--json"])
    assert p.returncode == 0, p.stderr
    import json
    data = json.loads(p.stdout)
    assert data["query"] == "demo"
    assert len(data["hits"]) >= 1
    assert all(k in h for h in data["hits"] for k in ("section", "item", "detail"))
    # should have repos_owned hit
    sections = {h["section"] for h in data["hits"]}
    assert "repos_owned" in sections


def test_where_case_insensitive(cfg, fake_home):
    p = run_script("system-inventory.py", ["--config", str(cfg), "where", "DEMO_MCP"])
    assert p.returncode == 0, p.stderr
    assert "demo_mcp" in p.stdout.lower()


def test_where_skills_unavailable_degrades_gracefully(cfg, fake_home):
    """Skills section is UNAVAILABLE in fixtures; where should not crash, just skip it."""
    p = run_script("system-inventory.py", ["--config", str(cfg), "where", "nonexistent-skill"])
    # Since skills is UNAVAILABLE and term not found elsewhere -> MISS
    assert p.returncode == 1, p.stdout
    assert "MISS" in p.stdout
