from __future__ import annotations

import pytest

from backend.app.core.agent_models import (
    AGENT_MODEL_POLICIES,
    AgentModelPolicy,
    agent_model_for,
    validate_agent_model_policies,
)
from backend.app.core.config import Settings


def test_agent_model_policy_centralizes_gpt_5_6_defaults_by_workload(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PI_RPC_ONBOARDING_MODEL", raising=False)
    monkeypatch.delenv("PI_RPC_RESEARCH_MODEL", raising=False)
    monkeypatch.delenv("PI_RPC_JOB_VERIFICATION_MODEL", raising=False)
    monkeypatch.delenv("PI_RPC_APPLICATION_DRAFT_MODEL", raising=False)
    settings = Settings(_env_file=None)

    assert agent_model_for("onboarding") == "gpt-5.6-sol"
    assert agent_model_for("company_research") == "gpt-5.6-terra"
    assert agent_model_for("job_verification") == "gpt-5.6-terra"
    assert agent_model_for("application_draft") == "gpt-5.6-terra"
    assert {
        policy.setting_name: getattr(settings, policy.setting_name)
        for policy in AGENT_MODEL_POLICIES
    } == {policy.setting_name: policy.default_model for policy in AGENT_MODEL_POLICIES}


def test_every_default_agent_model_setting_is_declared_in_the_central_policy():
    declared_settings = {policy.setting_name for policy in AGENT_MODEL_POLICIES}
    configured_model_defaults = {
        name
        for name, field in Settings.model_fields.items()
        if name.endswith("_model") and field.default is not None
    }

    assert configured_model_defaults == declared_settings


def test_agent_model_policy_rejects_non_gpt_5_6_defaults():
    invalid_policy = (
        AgentModelPolicy(
            workload="future_agent",
            setting_name="future_agent_model",
            default_model="gpt-5.4",
        ),
    )

    with pytest.raises(ValueError, match="GPT-5.6"):
        validate_agent_model_policies(invalid_policy)


def test_agent_model_policy_rejects_non_pi_application_runtime():
    invalid_policy = (
        AgentModelPolicy(
            workload="future_agent",
            setting_name="future_agent_model",
            default_model="gpt-5.6-luna",
            runtime="codex_exec",
        ),
    )

    with pytest.raises(ValueError, match="Pi RPC"):
        validate_agent_model_policies(invalid_policy)
