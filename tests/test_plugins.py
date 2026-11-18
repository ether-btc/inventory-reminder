"""Tests for the plugins section of system-inventory.py.

Synthetic plugin.yaml fixtures only.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "sysinv_plugins", REPO / "scripts" / "system-inventory.py"
)
assert _spec is not None and _spec.loader is not None
sysinv = importlib.util.module_from_spec(_spec)
sys.modules["sysinv_plugins"] = sysinv
_spec.loader.exec_module(sysinv)

PLUGIN_YAML = """\
name: demo-plugin
version: 2.1.0
description: "A demo plugin that exposes two tools for testing purposes. This \
description is intentionally long enough to exercise the ~110 char clamp."
author: Test
kind: backend
provides_tools:
  - demo_alpha
  - demo_beta
"""

TOOLLESS_YAML = """\
name: bare-plugin
version: 0.1.0
description: No tools at all.
kind: hook
"""


def _make(tmp_path: Path) -> Path:
    pdir = tmp_path / "plugins"
    (pdir / "demo").mkdir(parents=True)
    (pdir / "demo" / "plugin.yaml").write_text(PLUGIN_YAML)
    (pdir / "bare").mkdir()
    (pdir / "bare" / "plugin.yaml").write_text(TOOLLESS_YAML)
    (pdir / "not-a-plugin").mkdir()  # no plugin.yaml → ignored
    return pdir


def test_lists_plugins_with_metadata(tmp_path):
    d = sysinv.scan_plugins(plugins_dir=_make(tmp_path))
    assert d["available"] is True
    assert d["count"] == 2
    names = {p["name"]: p for p in d["plugins"]}
    assert set(names) == {"demo-plugin", "bare-plugin"}
    assert names["demo-plugin"]["version"] == "2.1.0"
    assert names["demo-plugin"]["kind"] == "backend"


def test_provides_tools_list(tmp_path):
    d = sysinv.scan_plugins(plugins_dir=_make(tmp_path))
    demo = next(p for p in d["plugins"] if p["name"] == "demo-plugin")
    assert demo["tools"] == ["demo_alpha", "demo_beta"]
    bare = next(p for p in d["plugins"] if p["name"] == "bare-plugin")
    assert bare["tools"] == []


def test_description_clamped(tmp_path):
    d = sysinv.scan_plugins(plugins_dir=_make(tmp_path))
    demo = next(p for p in d["plugins"] if p["name"] == "demo-plugin")
    assert len(demo["description"]) <= 110
    assert demo["description"].endswith("…")


def test_missing_plugins_dir_unavailable(tmp_path):
    d = sysinv.scan_plugins(plugins_dir=tmp_path / "nope")
    assert d["available"] is False
    assert "no plugins dir" in d["error"]
