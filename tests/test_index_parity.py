"""Parity guard: the plugin adapter duplicates the scanner's where-index.

`inventory_where` (plugin, cached digest) and `cmd_where` (scanner, live) each
carry their own section order and labels. They are intentionally independent
implementations, so this test pins them to each other: any section added to one
without the other fails here instead of silently going invisible to agents.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


scan = _load("parity_scanner", REPO / "scripts" / "system-inventory.py")
plug = _load("parity_plugin", REPO / "scripts" / "hermes_inventory_plugin.py")


def _extract(source: str, name: str) -> list[str]:
    """Pull quoted section keys out of a `name = [ ... ]` or `{ ... }` block."""
    m = re.search(rf"{name}\s*=\s*[\[{{](.*?)[\]}}]", source, re.S)
    assert m, f"{name} not found"
    return re.findall(r'"([a-z_]+)"', m.group(1))


def _src(path: Path) -> str:
    return path.read_text()


def test_section_order_parity():
    a = _extract(_src(REPO / "scripts" / "system-inventory.py"), "section_order")
    b = _extract(_src(REPO / "scripts" / "hermes_inventory_plugin.py"),
                 "section_order")
    assert a == b, f"scanner {a}\nplugin  {b}"


def test_section_labels_parity():
    a = _extract(_src(REPO / "scripts" / "system-inventory.py"), "section_labels")
    b = _extract(_src(REPO / "scripts" / "hermes_inventory_plugin.py"),
                 "section_labels")
    assert set(a) == set(b), f"only scanner: {set(a) - set(b)}\n" \
                             f"only plugin:  {set(b) - set(a)}"


def test_every_section_has_a_label():
    src = _src(REPO / "scripts" / "system-inventory.py")
    order = _extract(src, "section_order")
    labels = _extract(src, "section_labels")
    assert set(order) - set(labels) == set()


def test_order_covers_sections_produced_by_live_probes(tmp_path):
    """Every section the scanner can emit is in the print order.

    Probes that are UNAVAILABLE on this host simply contribute nothing, so the
    check is structural: the four new sub-sections must all be present.
    """
    order = _extract(_src(REPO / "scripts" / "system-inventory.py"),
                     "section_order")
    for sec in ("providers", "provider_models", "provider_aliases",
                "plugins", "cron_jobs", "profiles"):
        assert sec in order, f"{sec} missing from section_order"
