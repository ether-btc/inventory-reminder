"""Tests for the providers section of system-inventory.py.

Synthetic config.yaml/.env fixtures only — no real host values. The
credential file is never read by the scanner; it only appears here as a
fixture that must NOT influence the result.
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
    base_url: https://api.alpha.invalid/v1?api_key=sk-query-secret
    default_model: alpha-main
    key_env: ALPHA_API_KEY
    secret_field: hunter2
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
    return sysinv.scan_providers(cfg=cfg)


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
    assert "sk-query-secret" not in s
    assert "hunter2" not in s
    assert "REDACTED" in s
    assert "api_key=REDACTED" in s
    # env-var references stay visible (names, not values)
    assert "${TEST_LANE_API_KEY}" in s
    assert d["api_key_env"] == "${TEST_LANE_API_KEY}"


def test_key_refs_are_config_references_only(tmp_path):
    d = _scan(tmp_path)
    assert d["key_refs"] == ["ALPHA_API_KEY", "TEST_LANE_API_KEY"]
    assert "DEBUG_MODE" not in d["key_refs"]
    assert "PATH" not in d["key_refs"]


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


def test_literal_model_api_key_is_never_emitted(tmp_path):
    """A literal on model.api_key is not a reference: REDACTED, value never shown."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(CFG.replace(
        "  api_key: ${TEST_LANE_API_KEY}",
        "  api_key: sk-literal-never-show"))
    d = sysinv.scan_providers(cfg=cfg)
    s = json.dumps(d)
    assert d["api_key_env"] == "REDACTED"
    assert "sk-literal-never-show" not in s
    assert "${TEST_LANE_API_KEY}" not in s  # the reference is gone with the config


def test_custom_provider_env_fields_must_be_names(tmp_path):
    """A literal on custom_providers key_env/api_key_env is not a name: REDACTED."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(CFG.replace(
        "    key_env: ALPHA_API_KEY",
        "    key_env: sk-literal-cp-key\n    api_key_env: sk-literal-cp-akey"))
    d = sysinv.scan_providers(cfg=cfg)
    s = json.dumps(d)
    cps = {c["name"]: c for c in d["custom_providers"]}
    assert cps["alpha"]["key_env"] == "REDACTED"
    assert cps["alpha"]["api_key_env"] == "REDACTED"
    assert "sk-literal-cp-key" not in s
    assert "sk-literal-cp-akey" not in s


def test_model_base_url_is_scrubbed(tmp_path):
    """A key riding in the model base_url (userinfo/query) is scrubbed."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(CFG.replace(
        "  base_url: https://api.testlane.invalid/v1",
        "  base_url: https://user:sk-leak-u@host.invalid/v1?api_key=sk-leak-q"))
    d = sysinv.scan_providers(cfg=cfg)
    s = json.dumps(d)
    assert d["base_url"] == "https://REDACTED@host.invalid/v1?api_key=REDACTED"
    assert "sk-leak-u" not in s
    assert "sk-leak-q" not in s


def test_credential_file_is_never_reported(tmp_path):
    """The credential file is never opened: its names and values never show up."""
    hermes = tmp_path / ".hermes"
    hermes.mkdir(parents=True, exist_ok=True)
    (hermes / ".env").write_text("UNREFERENCED_API_KEY=secret-only-in-env\n")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(CFG)
    d = sysinv.scan_providers(cfg=cfg)
    s = json.dumps(d)
    assert "UNREFERENCED_API_KEY" not in s
    assert "secret-only-in-env" not in s
    assert d["key_refs"] == ["ALPHA_API_KEY", "TEST_LANE_API_KEY"]


def test_fallback_entry_key_order_is_irrelevant(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "model:\n"
        "  default: m\n"
        "fallback_providers:\n"
        "  - model: m-first\n"
        "    provider: p-later\n"
    )
    d = sysinv.scan_providers(cfg=cfg)
    assert d["fallback_providers"] == [{"provider": "p-later", "model": "m-first"}]


def test_credential_pool_inline_value_is_reported(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "model:\n"
        "  default: m\n"
        "credential_pool_strategies:\n"
        "  pool-inline: round_robin\n"
    )
    d = sysinv.scan_providers(cfg=cfg)
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
    d = sysinv.scan_providers(cfg=cfg)
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
    assert "Credential key references" in md
    assert "`E2E_API_KEY`" in md
    assert "BETA_API_KEY" not in md
    assert secret_value not in md
    assert secret_value not in json.dumps(inv)
