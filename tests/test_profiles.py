"""Tests for the profiles section of system-inventory.py.

Synthetic profiles tree fixtures only.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "sysinv_profiles", REPO / "scripts" / "system-inventory.py"
)
assert _spec is not None and _spec.loader is not None
sysinv = importlib.util.module_from_spec(_spec)
sys.modules["sysinv_profiles"] = sysinv
_spec.loader.exec_module(sysinv)


def _skill(root: Path, name: str, category: str | None = None) -> None:
    d = root / category / name if category else root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: x\n---\n")


def _make(tmp_path: Path) -> Path:
    pdir = tmp_path / "profiles"

    a = pdir / "alpha"
    _skill(a / "skills", "flat-skill")
    _skill(a / "skills", "nested-skill", category="devops")
    (a / "SOUL.md").write_text("soul")
    (a / "memories").mkdir(parents=True)
    (a / "memories" / "MEMORY.md").write_text("memory")
    (a / "cron").mkdir()
    (a / "cron" / "jobs.json").write_text(json.dumps({"jobs": [
        {"name": "j1", "enabled": True},
        {"name": "j2", "enabled": False},
    ]}))

    b = pdir / "beta"
    b.mkdir(parents=True)  # bare profile, nothing configured
    (b / "plugins" / "plug").mkdir(parents=True)
    (b / "plugins" / "plug" / "plugin.yaml").write_text("name: plug\n")
    (b / "plugins" / "empty").mkdir()

    return pdir


def test_counts_per_profile(tmp_path):
    d = sysinv.scan_profiles(profiles_dir=_make(tmp_path))
    assert d["available"] is True
    assert d["count"] == 2
    by = {p["name"]: p for p in d["profiles"]}
    assert by["alpha"]["skills"] == 2          # flat + category-nested
    assert by["alpha"]["cron_total"] == 2
    assert by["alpha"]["cron_enabled"] == 1
    assert by["alpha"]["has_soul"] is True
    assert by["alpha"]["has_memory"] is True
    assert by["beta"]["skills"] == 0
    assert by["beta"]["cron_total"] == 0
    assert by["beta"]["plugins"] == 1          # only dirs with plugin.yaml
    assert by["beta"]["has_soul"] is False


def test_total_skills_sums_profiles(tmp_path):
    d = sysinv.scan_profiles(profiles_dir=_make(tmp_path))
    assert d["total_skills"] == 2


def test_broken_jobs_json_degrades_to_zero(tmp_path):
    pdir = tmp_path / "profiles"
    g = pdir / "gamma"
    g.mkdir(parents=True)
    (g / "cron").mkdir()
    (g / "cron" / "jobs.json").write_text("{broken")
    d = sysinv.scan_profiles(profiles_dir=pdir)
    row = next(p for p in d["profiles"] if p["name"] == "gamma")
    assert row["cron_total"] == 0


def test_missing_profiles_dir_unavailable(tmp_path):
    d = sysinv.scan_profiles(profiles_dir=tmp_path / "nope")
    assert d["available"] is False
