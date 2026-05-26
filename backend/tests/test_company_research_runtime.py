from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.agents.company_research_runtime import CompanyResearchRuntime, contain_path, safe_research_env
from backend.app.core.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        RUNS_ROOT=tmp_path,
        SCHEMAS_ROOT=tmp_path / "schemas",
        PI_RPC_BINARY="pi",
        PI_RPC_RESEARCH_EXTENSION_PATH=Path("backend/pi_extensions/company_research.ts"),
        PI_RPC_NO_BUILTIN_TOOLS=True,
        PI_RPC_TIMEOUT_SECONDS=12,
        PI_RPC_RESEARCH_TIMEOUT_SECONDS=34,
    )


def test_company_research_runtime_builds_restricted_pi_command(tmp_path: Path):
    runtime = CompanyResearchRuntime(settings=_settings(tmp_path), clients={}, client_factory=lambda command, cwd, env: None)

    command = runtime._command("run-1")

    assert command[:3] == ["pi", "--mode", "rpc"]
    assert "--extension" in command
    assert "company_research.ts" in str(command)
    assert "--no-builtin-tools" in command
    assert "--session-dir" in command
    assert command[command.index("--provider") + 1] == "openai-codex"
    assert command[command.index("--model") + 1] == "gpt-5.5"
    assert command[command.index("--thinking") + 1] == "low"


def test_safe_research_env_filters_secrets_and_sets_runtime_context(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("GMAIL_TOKEN", "secret")
    monkeypatch.setenv("PATH", "safe-path")

    env = safe_research_env()

    assert env["PATH"] == "safe-path"
    assert "OPENAI_API_KEY" not in env
    assert "GMAIL_TOKEN" not in env
    assert "COMPANY_RESEARCH_REPO_ROOT" in env
    assert "COMPANY_RESEARCH_PYTHON" in env


def test_contain_path_allows_children_and_blocks_escapes(tmp_path: Path):
    root = tmp_path / "run" / "workspace"
    root.mkdir(parents=True)
    child = root / "notes.txt"
    child.write_text("ok", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("no", encoding="utf-8")

    assert contain_path(root, child) == child.resolve()
    with pytest.raises(ValueError):
        contain_path(root, outside)
    with pytest.raises(ValueError):
        contain_path(root, root)


def test_company_research_extension_contains_output_caps_and_blocked_write_guards():
    source = Path("backend/pi_extensions/company_research.ts").read_text(encoding="utf-8")

    assert "MAX_COMMAND_OUTPUT_BYTES" in source
    assert "MAX_COMMAND_TIMEOUT_MS" in source
    assert "assertChildPath(outputRoot, outputPath)" in source
    assert "safeEnv()" in source
    assert "company_research_write_contact" in source


def test_company_research_runtime_closes_client_after_prompt_failure(tmp_path: Path):
    class FailingClient:
        def __init__(self) -> None:
            self.closed = False

        def prompt(self, message: str, *, timeout_seconds: float):
            self.timeout_seconds = timeout_seconds
            raise RuntimeError("prompt failed")

        def command(self, payload, *, timeout_seconds: float):
            return {}

        def close(self) -> None:
            self.closed = True

    run_root = tmp_path / "run-1"
    run_root.mkdir(parents=True)
    (run_root / "task.md").write_text("# Task", encoding="utf-8")
    (run_root / "instructions.md").write_text("# Instructions", encoding="utf-8")
    client = FailingClient()
    runtime = CompanyResearchRuntime(settings=_settings(tmp_path), clients={"run-1": client})
    runtime._mark_run = lambda *args, **kwargs: None

    runtime._run_agent("run-1")

    assert client.closed is True
    assert client.timeout_seconds == 34
    assert "run-1" not in runtime.clients
    state = json.loads((run_root / "logs" / "company_research_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "failed"


def test_company_research_runtime_uses_campaign_time_budget_for_prompt_timeout(tmp_path: Path):
    run_root = tmp_path / "run-1"
    input_root = run_root / "input"
    input_root.mkdir(parents=True)
    (input_root / "campaign.json").write_text(json.dumps({"time_budget_minutes": 2}), encoding="utf-8")
    runtime = CompanyResearchRuntime(settings=_settings(tmp_path), clients={})

    assert runtime._prompt_timeout_seconds("run-1") == 34

    runtime = CompanyResearchRuntime(
        settings=Settings(
            RUNS_ROOT=tmp_path,
            SCHEMAS_ROOT=tmp_path / "schemas",
            PI_RPC_RESEARCH_TIMEOUT_SECONDS=1000,
        ),
        clients={},
    )

    assert runtime._prompt_timeout_seconds("run-1") == 180
