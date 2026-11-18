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


def test_env_key_presence_flags(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "VALUED_API_KEY=super-secret\n"
        "EMPTY_API_KEY=\n"
        "DEBUG_MODE=verbose\n"
    )
    presence = sysinv.env_key_presence(env)
    assert presence["VALUED_API_KEY"] is True
    assert presence["EMPTY_API_KEY"] is False
    assert "DEBUG_MODE" not in presence
    s = repr(presence)
    assert "super-secret" not in s
    # the section must WIRE the flags through, not just the helper itself
    cfg = tmp_path / "config.yaml"
    cfg.write_text("model:\n  default: m\n  provider: p\n")
    d = sysinv.scan_providers(cfg=cfg, env=env)
    assert d["env_key_presence"] == presence


def test_env_missing_is_distinguishable_from_empty(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(CFG)
    missing_env = tmp_path / "nope.env"
    d_missing = sysinv.scan_providers(cfg=cfg, env=missing_env)
    assert d_missing["available"] is True
    assert d_missing["env_available"] is False
    assert d_missing["env_error"] is not None
    assert "nope.env" in d_missing["env_error"]

    empty_env = tmp_path / ".env"
    empty_env.write_text("")
    d_empty = sysinv.scan_providers(cfg=cfg, env=empty_env)
    assert d_empty["available"] is True
    assert d_empty["env_available"] is True
    assert d_empty["env_error"] is None


def test_fallback_entry_key_order_is_irrelevant(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "model:\n"
        "  default: m\n"
        "fallback_providers:\n"
        "  - model: m-first\n"
        "    provider: p-later\n"
    )
    d = sysinv.scan_providers(cfg=cfg, env=tmp_path / ".env")
    assert d["fallback_providers"] == [{"provider": "p-later", "model": "m-first"}]


def test_credential_pool_inline_value_is_reported(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "model:\n"
        "  default: m\n"
        "credential_pool_strategies:\n"
        "  pool-inline: round_robin\n"
    )
    d = sysinv.scan_providers(cfg=cfg, env=tmp_path / ".env")
    assert "pool-inline" in d["credential_pools"]


def test_credential_pool_nested_key_reported_whole(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "model:\n"
        "  default: m\n"
        "credential_pool_strategies:\n"
        "  custom:experientiallabs:\n"
        "    ai: round_robin\n"
    )
    d = sysinv.scan_providers(cfg=cfg, env=tmp_path / ".env")
    assert d["credential_pools"] == ["custom:experientiallabs"]


def test_providers_section_written_to_inventory(cfg, fake_home):
    from conftest import run_script

    hermes = fake_home / ".hermes"
    (hermes / "config.yaml").write_text(
        "model:\n"
        "  default: e2e-model\n"
        "  provider: custom\n"
        "  base_url: https://api.test.invalid/v1\n"
        "  api_key: ${E2E_API_KEY}\n"
        "mcp_servers:\n"
        "  demo_mcp:\n"
        "    command: npx\n"
        "    enabled: true\n"
    )
    secret_value = "e2e-secret-value-DO-NOT-LEAK"
    (hermes / ".env").write_text(
        f"ALPHA_API_KEY={secret_value}\n"
        "BETA_API_KEY=\n"
    )

    p = run_script("system-inventory.py", ["--config", str(cfg), "--write"])
    assert p.returncode == 0, p.stderr + p.stdout

    inv = json.loads((hermes / "inventory.json").read_text())
    assert "providers" in inv
    assert inv["providers"]["available"] is True

    md = (hermes / "INVENTORY.md").read_text()
    assert "## Providers" in [l.strip() for l in md.splitlines()]
    # the presence marker is derived from the VALUE (set vs empty), not the name
    assert "`ALPHA_API_KEY`=SET" in md
    assert "`BETA_API_KEY`=UNSET" in md
    assert secret_value not in md
    assert secret_value not in json.dumps(inv)
