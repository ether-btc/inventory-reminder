"""Load-contract tests for the inventory-reminder Hermes plugin wrapper.

The scanners have their own suites (test_repo_inventory.py, test_system_inventory.py). These
tests cover only the plugin surface: the manifest/entrypoint, the two tool registrations, and
the fail-closed handler contract (a missing or malformed inventory is an answer, not a crash).
"""

from __future__ import annotations

import json
import pathlib
import sys
from unittest.mock import MagicMock

import pytest

# The adapter lives in scripts/ (the scanners' home); the plugin root puts it on sys.path.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import hermes_inventory_plugin as adapter  # noqa: E402

FIXTURE = {
    "generated_at": "2026-11-06T10:00:00",
    "repos": {"available": True, "owned_total": 3, "local": 2, "online_only": 1,
              "local_repos": ["ether-btc/inventory-reminder", "ether-btc/ram-first-context"]},
    "skills": {"available": True, "total": 2, "names": ["aider", "reddit-reading"],
               "by_source": {"aider": "bundled", "reddit-reading": "local"}},
    "tools": {"available": True, "mcp_servers": [], "cli_tools": {"ocr": "/home/hermes-pi/.local/bin/ocr"},
              "mcp_total": 0, "mcp_enabled": []},
    "apps": {"available": False},
    "models": {"available": False},
    "services": {"available": False},
}


@pytest.fixture
def inventory_file(tmp_path, monkeypatch):
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(FIXTURE))
    monkeypatch.setenv("INVENTORY_JSON", str(path))
    return path


def test_register_declares_both_tools():
    ctx = MagicMock()
    adapter.register(ctx)
    names = [c.kwargs["name"] for c in ctx.register_tool.call_args_list]
    assert names == ["inventory_where", "inventory_summary"]


def test_missing_inventory_is_a_clean_json_answer(tmp_path, monkeypatch):
    monkeypatch.setenv("INVENTORY_JSON", str(tmp_path / "absent.json"))
    out = adapter.cmd_inventory_where("aider")
    assert isinstance(out, str)
    parsed = json.loads(out)
    assert parsed["hits"] == []
    assert "inventory.json not found" in parsed["error"]


def test_where_finds_a_skill_from_the_cached_inventory(inventory_file):
    parsed = json.loads(adapter.cmd_inventory_where("aider", as_json=True))
    assert parsed["hits"], "the fixture lists a skill named 'aider'"
    assert any(h["section"] == "skills" and h["item"] == "aider" for h in parsed["hits"])


def test_where_default_surface_is_readable_text(inventory_file):
    """`json=False` (the tool default) stays a compact human answer, not a JSON blob."""
    out = adapter.cmd_inventory_where("aider")
    assert isinstance(out, str) and "aider" in out and not out.startswith("{")


def test_summary_is_a_one_line_digest(inventory_file):
    out = adapter.cmd_inventory_summary()
    assert isinstance(out, str)
    assert out.startswith("INVENTORY ")
    assert "\n" not in out


def test_malformed_inventory_does_not_raise(tmp_path, monkeypatch):
    bad = tmp_path / "inventory.json"
    bad.write_text(json.dumps({"skills": {"available": True, "names": "not-a-list"}}))
    monkeypatch.setenv("INVENTORY_JSON", str(bad))
    # 'names' is a string, so iterating it yields characters — the handler must still answer.
    out = adapter.cmd_inventory_where("a", as_json=True)
    assert isinstance(out, str)
    json.loads(out)


def test_handlers_return_strings_the_dispatcher_can_forward(inventory_file):
    ctx = MagicMock()
    adapter.register(ctx)
    for call in ctx.register_tool.call_args_list:
        handler = call.kwargs["handler"]
        out = handler({"term": "aider"}, task_id="t1", session_id="s1")
        assert isinstance(out, str)


def test_register_wraps_schemas_with_parameters():
    ctx = MagicMock()
    adapter.register(ctx)
    by_name = {c.kwargs["name"]: c.kwargs["schema"] for c in ctx.register_tool.call_args_list}
    where = by_name["inventory_where"]
    assert "parameters" in where
    assert where["parameters"]["type"] == "object"
    assert "term" in where["parameters"]["properties"]
    assert where["parameters"].get("required") == ["term"]
    summary = by_name["inventory_summary"]
    assert "parameters" in summary
    assert summary["parameters"].get("properties") == {}


def test_empty_term_is_rejected_via_handler():
    out = adapter.cmd_inventory_where("   ")
    parsed = json.loads(out)
    assert parsed["hits"] == []
    assert "empty" in parsed["error"].lower()


def test_inventory_path_follows_hermes_home(monkeypatch):
    monkeypatch.delenv("INVENTORY_JSON", raising=False)
    adapter._PLUGIN_CONFIG.clear()
    monkeypatch.setenv("HERMES_HOME", "/tmp/hermes-home-smoke")
    assert str(adapter.inventory_json()).startswith("/tmp/hermes-home-smoke")
    assert adapter.inventory_json().name == "inventory.json"


def test_register_reads_plugin_config(monkeypatch):
    monkeypatch.delenv("INVENTORY_JSON", raising=False)
    adapter._PLUGIN_CONFIG.clear()

    def fake_get_config(key, default=None):
        if key == "inventory_json":
            return "/tmp/cfg-inventory.json"
        return default

    ctx = MagicMock()
    ctx.get_config.side_effect = fake_get_config
    adapter.register(ctx)
    assert adapter._PLUGIN_CONFIG.get("inventory_json") == "/tmp/cfg-inventory.json"
    assert adapter.inventory_json() == pathlib.Path("/tmp/cfg-inventory.json")


# --- where/summary must cover the provider/plugin/cron/profile sections ---

_EXTRA_INV = {
    "generated_at": "2026-11-18T20:29:00+01:00",
    "repos": {"available": True, "owned_total": 161, "local": 30,
              "online_only": 131},
    "skills": {"available": True, "total": 340, "by_source": {"local": 308}},
    "tools": {"available": True, "mcp_total": 5, "mcp_enabled": ["a", "b", "c"]},
    "providers": {
        "available": True,
        "custom_providers": [
            {"name": "deepseek", "default_model": "deepseek-flash",
             "models": ["deepseek-flash"], "base_url": "https://api.deepseek.invalid"},
        ],
        "aliases": {"sb": "openrouter/test/space-bunny"},
    },
    "plugins": {"available": True, "count": 1, "plugins": [
        {"name": "gliformer", "version": "1.0.0", "kind": "backend",
         "tools": ["gliformer_embed_text"]}]},
    "cron": {"available": True, "total": 77, "enabled": 58, "jobs": [
        {"name": "hermes-health-watchdog", "schedule": "0 9,21 * * *",
         "enabled": True, "last_status": "ok"}]},
    "profiles": {"available": True, "count": 18, "total_skills": 1208,
                 "profiles": [{"name": "reviewer", "skills": 279,
                               "cron_total": 0, "cron_enabled": 0}]},
    "apps": {"available": True, "count": 142, "key_packages": {}},
    "models": {"available": True, "count": 6, "total_size": "4.1G", "models": []},
    "services": {"available": True, "count": 0, "running_total": 19, "services": []},
}


@pytest.fixture
def extra_inventory(tmp_path, monkeypatch):
    p = tmp_path / "inventory.json"
    p.write_text(json.dumps(_EXTRA_INV))
    monkeypatch.setenv("INVENTORY_JSON", str(p))
    adapter._PLUGIN_CONFIG.clear()
    yield p
    adapter._PLUGIN_CONFIG.clear()


def _hits(term):
    return json.loads(adapter.cmd_inventory_where(term, as_json=True))["hits"]


def test_where_finds_custom_provider(extra_inventory):
    assert any(h["section"] == "providers" and h["item"] == "deepseek"
               for h in _hits("deepseek"))


def test_where_finds_provider_alias(extra_inventory):
    assert any(h["section"] == "provider_aliases" for h in _hits("sb"))


def test_where_finds_plugin_and_tool(extra_inventory):
    secs = {h["item"] for h in _hits("gliformer")}
    assert {"gliformer", "gliformer_embed_text"} <= secs


def test_where_finds_cron_job(extra_inventory):
    assert any(h["section"] == "cron_jobs" for h in _hits("watchdog"))


def test_where_finds_profile(extra_inventory):
    hits = _hits("reviewer")
    assert any(h["section"] == "profiles" and h["item"] == "reviewer" for h in hits)


def test_summary_includes_new_sections(extra_inventory):
    out = adapter.cmd_inventory_summary()
    for token in ("providers 1", "plugins 1", "cron 58/77", "profiles 18"):
        assert token in out, out


def test_hermes_home_fallback_expands_user_and_env_syntax(monkeypatch):
    """Fallback path expands ~ and $VAR like hermes_constants does."""
    monkeypatch.delenv("INVENTORY_JSON", raising=False)
    adapter._PLUGIN_CONFIG.clear()
    monkeypatch.setitem(sys.modules, "hermes_constants", None)
    monkeypatch.setenv("HOME", "/tmp/fake-home")
    monkeypatch.setenv("HERMES_HOME", "$HOME/.hermes-expanded")
    assert str(adapter.inventory_json()) == "/tmp/fake-home/.hermes-expanded/inventory.json"
    monkeypatch.setenv("HERMES_HOME", "~/sub/.hermes-expanded")
    assert str(adapter.inventory_json()) == str(
        pathlib.Path("/tmp/fake-home") / "sub" / ".hermes-expanded" / "inventory.json"
    )
