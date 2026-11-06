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
