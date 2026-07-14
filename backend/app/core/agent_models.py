from __future__ import annotations

from dataclasses import dataclass
from typing import Final


GPT_5_6_MODEL_PREFIX: Final = "gpt-5.6"


@dataclass(frozen=True, slots=True)
class AgentModelPolicy:
    workload: str
    setting_name: str
    default_model: str
    runtime: str = "pi_rpc"
    provider: str = "openai-codex"


AGENT_MODEL_POLICIES: Final = (
    AgentModelPolicy(
        workload="onboarding",
        setting_name="pi_rpc_onboarding_model",
        default_model="gpt-5.6-sol",
    ),
    AgentModelPolicy(
        workload="company_research",
        setting_name="pi_rpc_research_model",
        default_model="gpt-5.6-terra",
    ),
    AgentModelPolicy(
        workload="job_verification",
        setting_name="pi_rpc_job_verification_model",
        default_model="gpt-5.6-terra",
    ),
    AgentModelPolicy(
        workload="application_draft",
        setting_name="pi_rpc_application_draft_model",
        default_model="gpt-5.6-terra",
    ),
)


def validate_agent_model_policies(policies: tuple[AgentModelPolicy, ...] = AGENT_MODEL_POLICIES) -> None:
    workloads = [policy.workload for policy in policies]
    setting_names = [policy.setting_name for policy in policies]
    if len(workloads) != len(set(workloads)):
        raise ValueError("Agent model policy workloads must be unique.")
    if len(setting_names) != len(set(setting_names)):
        raise ValueError("Agent model policy setting names must be unique.")

    non_pi = [policy for policy in policies if policy.runtime != "pi_rpc"]
    if non_pi:
        details = ", ".join(f"{policy.workload}={policy.runtime}" for policy in non_pi)
        raise ValueError(f"Application agent runtimes must use Pi RPC: {details}")

    unsupported_providers = [policy for policy in policies if policy.provider != "openai-codex"]
    if unsupported_providers:
        details = ", ".join(f"{policy.workload}={policy.provider}" for policy in unsupported_providers)
        raise ValueError(f"GPT-5.6 application agents must use the openai-codex provider: {details}")

    invalid = [policy for policy in policies if not policy.default_model.startswith(GPT_5_6_MODEL_PREFIX)]
    if invalid:
        details = ", ".join(f"{policy.workload}={policy.default_model}" for policy in invalid)
        raise ValueError(f"Agent runtime defaults must use the GPT-5.6 model family: {details}")


validate_agent_model_policies()

_MODEL_BY_WORKLOAD: Final = {policy.workload: policy.default_model for policy in AGENT_MODEL_POLICIES}


def agent_model_for(workload: str) -> str:
    try:
        return _MODEL_BY_WORKLOAD[workload]
    except KeyError as exc:
        raise KeyError(f"No agent model policy is defined for workload {workload!r}.") from exc
