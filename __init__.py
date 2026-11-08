"""Hermes plugin entrypoint for inventory-reminder."""

from __future__ import annotations

try:
    from .scripts.hermes_inventory_plugin import register  # noqa: E402
except ImportError:  # pragma: no cover - fallback for top-level/test imports
    import pathlib
    import sys

    _HERE = str(pathlib.Path(__file__).resolve().parent)
    _SCRIPTS = str(pathlib.Path(_HERE) / "scripts")
    for _p in (_HERE, _SCRIPTS):
        if _p not in sys.path:
            sys.path.insert(0, _p)
    from hermes_inventory_plugin import register  # noqa: E402

__all__ = ["register"]
