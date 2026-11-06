"""Hermes plugin entrypoint for inventory-reminder.

The scanners and the adapter live in `scripts/`; the plugin root puts that directory on
sys.path for this one import so the loader can call `register(ctx)` from a normal
directory-plugin layout.
"""

from __future__ import annotations

import pathlib
import sys

_HERE = str(pathlib.Path(__file__).resolve().parent)
_SCRIPTS = str(pathlib.Path(_HERE) / "scripts")
for _p in (_HERE, _SCRIPTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from hermes_inventory_plugin import register  # noqa: E402

__all__ = ["register"]
