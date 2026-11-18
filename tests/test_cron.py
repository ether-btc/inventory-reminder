"""Tests for the cron section of system-inventory.py.

Synthetic jobs.json fixtures only.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "sysinv_cron", REPO / "scripts" / "system-inventory.py"
)
assert _spec is not None and _spec.loader is not None
sysinv = importlib.util.module_from_spec(_spec)
sys.modules["sysinv_cron"] = sysinv
_spec.loader.exec_module(sysinv)

JOBS = {
    "jobs": [
        {
            "id": "aaa111",
            "name": "good-job",
            "enabled": True,
            "schedule": {"display": "0 4 * * *", "expr": "0 4 * * *",
                         "kind": "cron"},
            "last_status": "ok",
            "failure_streak": 0,
            "last_run_at": "2026-11-18T04:00:05+01:00",
            "next_run_at": "2026-11-19T04:00:00+01:00",
            "deliver": "local",
        },
        {
            "id": "bbb222",
            "name": "broken-job",
            "enabled": True,
            "schedule": {"display": "*/5 * * * *", "expr": "*/5 * * * *",
                         "kind": "cron"},
            "last_status": "error",
            "failure_streak": 3,
            "last_run_at": "2026-11-18T20:00:00+01:00",
            "next_run_at": None,
            "deliver": "telegram:1",
        },
        {
            "id": "ccc333",
            "name": "parked-job",
            "enabled": False,
            "schedule": {"display": "0 9 * * 1", "expr": "0 9 * * 1",
                         "kind": "cron"},
            "last_status": None,
            "last_run_at": None,
            "deliver": "local",
        },
    ]
}


def _make(tmp_path: Path) -> Path:
    cdir = tmp_path / "cron"
    cdir.mkdir()
    (cdir / "jobs.json").write_text(json.dumps(JOBS))
    return cdir


def test_totals_and_status_counts(tmp_path):
    d = sysinv.scan_cron(cron_dir=_make(tmp_path))
    assert d["available"] is True
    assert d["total"] == 3
    assert d["enabled"] == 2
    assert d["by_status"] == {"ok": 1, "error": 1, "never": 1}


def test_needs_attention_only_enabled_failures(tmp_path):
    d = sysinv.scan_cron(cron_dir=_make(tmp_path))
    # parked-job is disabled and never ran → not a failure to act on
    assert d["needs_attention"] == ["broken-job"]


def test_row_shape(tmp_path):
    d = sysinv.scan_cron(cron_dir=_make(tmp_path))
    rows = {r["name"]: r for r in d["jobs"]}
    assert rows["good-job"]["schedule"] == "0 4 * * *"
    assert rows["good-job"]["kind"] == "cron"
    assert rows["good-job"]["enabled"] is True
    assert rows["broken-job"]["failure_streak"] == 3
    assert rows["parked-job"]["last_status"] is None


def test_missing_or_broken_file_unavailable(tmp_path):
    assert sysinv.scan_cron(cron_dir=tmp_path / "nope")["available"] is False
    cdir = tmp_path / "cron2"
    cdir.mkdir()
    (cdir / "jobs.json").write_text("{not json")
    d = sysinv.scan_cron(cron_dir=cdir)
    assert d["available"] is False
    assert "cannot read" in d["error"]


def test_plain_list_jobs_file_also_accepted(tmp_path):
    cdir = tmp_path / "cron3"
    cdir.mkdir()
    (cdir / "jobs.json").write_text(json.dumps(JOBS["jobs"]))
    d = sysinv.scan_cron(cron_dir=cdir)
    assert d["available"] is True
    assert d["total"] == 3
