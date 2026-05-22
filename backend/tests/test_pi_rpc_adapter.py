from __future__ import annotations

import json
from pathlib import Path

from backend.app.agents.pi_rpc import PiRpcOnboardingChatAdapter, PiRpcPromptResult
from backend.app.core.config import Settings


class FakePiRpcClient:
    def __init__(self, replies: list[str] | None = None) -> None:
        self.replies = list(replies or ["First onboarding question?"])
        self.prompts: list[str] = []
        self.closed = False

    def prompt(self, message: str, *, timeout_seconds: float) -> PiRpcPromptResult:
        self.prompts.append(message)
        return PiRpcPromptResult(
            text=self.replies.pop(0) if self.replies else "Next reply.",
            events=[
                {"type": "response", "id": "fake", "command": "prompt", "success": True},
                {"type": "agent_end", "messages": []},
            ],
        )

    def command(self, payload, *, timeout_seconds: float):
        return {"type": "response", "success": True, "data": {}}

    def close(self) -> None:
        self.closed = True


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        RUNS_ROOT=tmp_path,
        SCHEMAS_ROOT=tmp_path / "schemas",
        PI_RPC_BINARY="pi",
        PI_RPC_EXTENSION_PATH=Path("backend/pi_extensions/onboarding_artifacts.ts"),
        PI_RPC_NO_BUILTIN_TOOLS=True,
        PI_RPC_TIMEOUT_SECONDS=12,
    )


def test_pi_rpc_adapter_prepares_workspace_and_builds_restricted_command(tmp_path: Path):
    clients: dict[str, FakePiRpcClient] = {}
    captured = {}

    def factory(command, cwd, env):
        captured["command"] = list(command)
        captured["cwd"] = cwd
        captured["env"] = dict(env)
        client = FakePiRpcClient()
        clients["run-1"] = client
        return client

    adapter = PiRpcOnboardingChatAdapter(settings=_settings(tmp_path), clients={}, client_factory=factory)
    workspace = adapter.prepare_agent_workspace("run-1", "# Onboarding Recruiting Agent\n")

    attachment = adapter.attach_session("run-1", fresh=True)
    status = adapter.start_or_attach("run-1")

    assert status == "started"
    assert attachment["runtime"] == "pi_rpc"
    assert Path(workspace["host_workspace"]).name == "workspace"
    assert (tmp_path / "run-1" / "workspace" / "AGENTS.md").read_text(encoding="utf-8").startswith("# Onboarding")
    assert captured["cwd"] == tmp_path / "run-1" / "workspace"
    assert captured["command"][:3] == ["pi", "--mode", "rpc"]
    assert "ONBOARDING_PYTHON" in captured["env"]
    assert "ONBOARDING_REPO_ROOT" in captured["env"]
    assert "--continue" not in captured["command"]
    assert "--no-builtin-tools" in captured["command"]
    assert "--extension" in captured["command"]
    assert "--session-dir" in captured["command"]


def test_pi_rpc_adapter_resumes_saved_pi_session(tmp_path: Path):
    captured = {}
    session_dir = tmp_path / "run-1" / "logs" / "pi-session"
    session_dir.mkdir(parents=True)
    (session_dir / "previous.jsonl").write_text("{}", encoding="utf-8")

    def factory(command, cwd, env):
        captured["command"] = list(command)
        return FakePiRpcClient()

    adapter = PiRpcOnboardingChatAdapter(settings=_settings(tmp_path), clients={}, client_factory=factory)
    adapter.prepare_agent_workspace("run-1", "# Onboarding Recruiting Agent\n")
    adapter.start_or_attach("run-1")

    assert "--continue" in captured["command"]


def test_pi_rpc_adapter_sends_prompt_persists_transcript_and_event_log(tmp_path: Path):
    fake_client = FakePiRpcClient(["Tell me your target roles."])

    adapter = PiRpcOnboardingChatAdapter(
        settings=_settings(tmp_path),
        clients={},
        client_factory=lambda command, cwd, env: fake_client,
    )
    adapter.prepare_agent_workspace("run-1", "# Instructions")
    adapter.start_or_attach("run-1")

    reply = adapter.send_message("run-1", "I want backend roles in Berlin.")

    assert reply.message == "Tell me your target roles."
    assert fake_client.prompts == ["I want backend roles in Berlin."]
    entries = adapter.transcript_entries("run-1")
    assert [entry["role"] for entry in entries] == ["user", "assistant"]
    assert entries[0]["content"] == "I want backend roles in Berlin."
    assert entries[1]["content"] == "Tell me your target roles."
    event_lines = (tmp_path / "run-1" / "logs" / "pi_rpc_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert any(json.loads(line)["type"] == "agent_end" for line in event_lines)
    assert adapter.session_state("run-1").status == "running"


def test_pi_rpc_adapter_reset_closes_process_and_clears_transcript(tmp_path: Path):
    fake_client = FakePiRpcClient()
    adapter = PiRpcOnboardingChatAdapter(
        settings=_settings(tmp_path),
        clients={},
        client_factory=lambda command, cwd, env: fake_client,
    )
    adapter.prepare_agent_workspace("run-1", "# Instructions")
    adapter.start_or_attach("run-1")
    adapter.send_message("run-1", "hello")
    session_dir = tmp_path / "run-1" / "logs" / "pi-session"
    session_dir.mkdir(parents=True)
    (session_dir / "previous.jsonl").write_text("{}", encoding="utf-8")

    adapter.reset_session("run-1")

    assert fake_client.closed is True
    assert adapter.session_state("run-1").status == "not_started"
    assert [entry["event"] for entry in adapter.transcript_entries("run-1")] == ["reset"]
    assert not session_dir.exists()
