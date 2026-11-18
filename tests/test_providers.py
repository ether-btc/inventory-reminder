"""Tests for the providers section of system-inventory.py.

Synthetic config.yaml/.env fixtures only — no real host values.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "sysinv", REPO / "scripts" / "system-inventory.py"
)
assert _spec is not None and _spec.loader is not None
sysinv = importlib.util.module_from_spec(_spec)
sys.modules["sysinv"] = sysinv
_spec.loader.exec_module(sysinv)

CFG = """\
model:
  default: test-model-a
  provider: custom
  max_tokens: 4096
  base_url: https://api.testlane.invalid/v1
  aliases:
    sb: openrouter/test/space-bunny
    argon: opencode-go/gemini-4-argon
  api_key: ${TEST_LANE_API_KEY}
fallback_providers:
  - provider: fallback-one
    model: fb-model-1
  - provider: fallback-two
    model: fb-model-2
credential_pool_strategies:
  custom:testlane:
    ai: round_robin
toolsets:
  - hermes-cli
custom_providers:
  - name: alpha
    base_url: https://api.alpha.invalid/v1
    default_model: alpha-main
    key_env: ALPHA_API_KEY
    models:
      alpha-main: {}
      alpha-mini: {}
    models_discovered: true
  - name: beta
    base_url: https://api.beta.invalid/v1
    model: beta-only
    api_key: sk-plaintext-looking-value
    models:
      beta-only: {}
mcp_servers:
  - name: some-mcp
    enabled: true
    command: /bin/true
"""

ENV = """\
TEST_LANE_API_KEY=fake-value-never-checked
ALPHA_API_KEY=another-fake-value
DEBUG_MODE=verbose
PATH=/usr/bin
"""


def _scan(tmp_path: Path) -> dict:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(CFG)
    env = tmp_path / ".env"
    env.write_text(ENV)
    return sysinv.scan_providers(cfg=cfg, env=env)


def test_default_model_block(tmp_path):
    d = _scan(tmp_path)
    assert d["available"] is True
    assert d["default_provider"] == "custom"
    assert d["default_model"] == "test-model-a"
    assert d["base_url"] == "https://api.testlane.invalid/v1"


def test_aliases(tmp_path):
    d = _scan(tmp_path)
    assert d["aliases"] == {
        "sb": "openrouter/test/space-bunny",
        "argon": "opencode-go/gemini-4-argon",
    }


def test_fallback_chain(tmp_path):
    d = _scan(tmp_path)
    assert d["fallback_providers"] == [
        {"provider": "fallback-one", "model": "fb-model-1"},
        {"provider": "fallback-two", "model": "fb-model-2"},
    ]


def test_credential_pools(tmp_path):
    d = _scan(tmp_path)
    assert d["credential_pools"] == ["custom:testlane"]


def test_custom_providers_and_models(tmp_path):
    d = _scan(tmp_path)
    cps = {c["name"]: c for c in d["custom_providers"]}
    assert set(cps) == {"alpha", "beta"}
    assert cps["alpha"]["default_model"] == "alpha-main"
    assert cps["alpha"]["models"] == ["alpha-main", "alpha-mini"]
    assert cps["alpha"]["key_env"] == "ALPHA_API_KEY"
    assert cps["beta"]["model"] == "beta-only"


def test_secrets_never_leak(tmp_path):
    d = _scan(tmp_path)
    s = json.dumps(d)
    assert "fake-value-never-checked" not in s
    assert "another-fake-value" not in s
    assert "sk-plaintext-looking-value" not in s
    assert "REDACTED" in s
    # env-var references stay visible (names, not values)
    assert "${TEST_LANE_API_KEY}" in s
    assert d["api_key_env"] == "${TEST_LANE_API_KEY}"


def test_env_key_names_names_only(tmp_path):
    d = _scan(tmp_path)
    assert d["env_key_names"] == ["TEST_LANE_API_KEY", "ALPHA_API_KEY"]
    assert "DEBUG_MODE" not in d["env_key_names"]
    assert "PATH" not in d["env_key_names"]


def test_where_finds_deepseek_style_term(tmp_path):
    """A provider added via custom_providers is findable by `where <term>`."""
    d = _scan(tmp_path)
    hits = []
    for c in d.get("custom_providers", []):
        if "alph" in c["name"].lower():
            hits.append(c["name"])
        for mid in c.get("models", []):
            if "alpha-main" in mid:
                hits.append(mid)
    assert "alpha" in hits
    assert "alpha-main" in hits


def test_unavailable_on_missing_config(tmp_path):
    d = sysinv.scan_providers(cfg=tmp_path / "nope.yaml")
    assert d["available"] is False
