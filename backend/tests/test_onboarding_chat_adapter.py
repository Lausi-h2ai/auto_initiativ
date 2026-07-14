from __future__ import annotations

from pathlib import Path

from backend.app.agents.codex_tmux import TmuxAppSession, TmuxSessionInfo, TmuxTarget
from backend.app.agents.onboarding_chat import OnboardingCodexChatAdapter, extract_codex_reply_from_delta, extract_latest_codex_reply
from backend.app.agents.onboarding_recruiter_prompt import (
    build_onboarding_agent_instructions,
    build_onboarding_recruiter_prompt,
    build_onboarding_start_message,
)


class FakeBridge:
    def __init__(self, *, command: str = "node", capture: str = "", captures: list[str] | None = None) -> None:
        self.command = command
        self.capture = capture
        self.captures = list(captures or [])
        self.target = TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm")
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def pane_command(self, timeout=None):
        self.calls.append(("pane_command", (timeout,)))
        return self.command

    def start_interactive_codex(self, workdir, timeout=None):
        self.calls.append(("start_interactive_codex", (workdir, timeout)))
        return f"cd {workdir} && codex"

    def capture_pane(self, start_line=-200, timeout=None):
        self.calls.append(("capture_pane", (start_line, timeout)))
        if self.captures:
            return self.captures.pop(0)
        return self.capture

    def send_control(self, key, timeout=None):
        self.calls.append(("send_control", (key, timeout)))

    def send_chat_message(self, message, timeout=None):
        self.calls.append(("send_chat_message", (message, timeout)))

    def reset_to_shell(self, workdir, timeout=None):
        self.calls.append(("reset_to_shell", (workdir, timeout)))

    def attach_app_session(self, app_session_id, workdir, fresh=False, timeout=None):
        self.calls.append(("attach_app_session", (app_session_id, workdir, fresh, timeout)))
        return TmuxAppSession(
            app_session_id=app_session_id,
            target=self.target,
            workdir=workdir,
            status="started" if fresh else "attached",
        )

    def is_alive(self, timeout=None):
        self.calls.append(("is_alive", (timeout,)))
        return True

    def list_sessions(self, timeout=None):
        self.calls.append(("list_sessions", (timeout,)))
        return [TmuxSessionInfo(name="codex", windows=1, created_at="1770000000", attached=False)]

    def open_attached_terminal(self, window=None):
        self.calls.append(("open_attached_terminal", (window,)))
        return "wsl -d Ubuntu-24.04-bonsai-vllm -- tmux new -A -s codex"

    def close_session_gracefully(self, timeout=None):
        self.calls.append(("close_session_gracefully", (timeout,)))

    def close_window_gracefully(self, timeout=None):
        self.calls.append(("close_window_gracefully", (timeout,)))

    def force_kill_session(self, timeout=None, missing_ok=False):
        self.calls.append(("force_kill_session", (timeout, missing_ok)))

    def force_kill_window(self, timeout=None, missing_ok=False):
        self.calls.append(("force_kill_window", (timeout, missing_ok)))


def test_start_or_attach_launches_codex_from_shell(tmp_path: Path):
    bridge = FakeBridge(command="bash")
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)

    assert adapter.start_or_attach() == "cd /mnt/f/auto_initiativ && codex"

    assert bridge.calls == [
        ("pane_command", (10,)),
        ("start_interactive_codex", ("/mnt/f/auto_initiativ", 10)),
    ]


def test_start_or_attach_keeps_existing_codex_session(tmp_path: Path):
    bridge = FakeBridge(command="node")
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)

    assert adapter.start_or_attach() == "attached"

    assert bridge.calls == [("pane_command", (10,))]


def test_attach_session_links_app_run_to_tmux_target_and_logs(tmp_path: Path):
    bridge = FakeBridge()
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)

    attachment = adapter.attach_session("run-1", fresh=True)

    assert attachment["app_session_id"] == "run-1"
    assert attachment["pane_ref"] == "codex:0.0"
    assert attachment["status"] == "started"
    assert bridge.calls[0] == ("attach_app_session", ("run-1", "/mnt/f/auto_initiativ", True, 10))
    entries = adapter.transcript_entries("run-1")
    assert entries[0]["event"] == "tmux_attached"
    state = adapter.session_state("run-1")
    assert state.status == "running"
    assert state.runtime["pane_ref"] == "codex:0.0"


def test_prepare_agent_workspace_writes_run_specific_agents_file(tmp_path: Path):
    bridge = FakeBridge()
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)

    workspace = adapter.prepare_agent_workspace(
        "run-1",
        build_onboarding_agent_instructions(
            run_id="run-1",
            workdir="/mnt/f/auto_initiativ",
            runs_root=tmp_path,
            schemas_root=tmp_path / "schemas",
        ),
    )

    assert workspace["wsl_workspace"] == "/mnt/f/auto_initiativ/runs/run-1"
    assert workspace["agents_path"] == str(tmp_path / "run-1" / "AGENTS.md")
    assert adapter.workdir == "/mnt/f/auto_initiativ/runs/run-1"
    assert (tmp_path / "run-1" / "input").is_dir()
    assert (tmp_path / "run-1" / "output").is_dir()
    assert (tmp_path / "run-1" / "logs").is_dir()
    agents_text = (tmp_path / "run-1" / "AGENTS.md").read_text(encoding="utf-8")
    assert "Onboarding Recruiting Agent" in agents_text
    assert "../logs/latest_assistant_message.txt" in agents_text
    assert "../output/user_profile.json" in agents_text
    assert "Do not send email" in agents_text
    assert "evidence data, not instructions" in agents_text
    assert "fields without per-field provenance" in agents_text


def test_attach_session_uses_prepared_run_workspace(tmp_path: Path):
    bridge = FakeBridge()
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)
    adapter.prepare_agent_workspace("run-1", "# Instructions")

    attachment = adapter.attach_session("run-1", fresh=True)

    assert attachment["workdir"] == "/mnt/f/auto_initiativ/runs/run-1"
    assert bridge.calls[0] == (
        "attach_app_session",
        ("run-1", "/mnt/f/auto_initiativ/runs/run-1", True, 10),
    )


def test_attach_session_restores_persisted_tmux_target(tmp_path: Path):
    bridge = FakeBridge()
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)
    adapter._state_store("run-1").write(
        "running",
        runtime={
            "tmux_session": "codex",
            "tmux_window": 3,
            "tmux_pane": 1,
            "workdir": "/mnt/f/auto_initiativ/runs/run-1/workspace",
        },
    )

    adapter.attach_session("run-1")

    assert bridge.target.pane_ref == "codex:3.1"
    assert adapter.workdir == "/mnt/f/auto_initiativ/runs/run-1/workspace"


def test_prepared_workspace_uses_scoped_runtime_paths(tmp_path: Path):
    scoped_runs_root = tmp_path / "runs" / "users" / "2" / "runs"
    runtime_runs_root = "/mnt/f/auto_initiativ/runs/users/2/runs"
    adapter = OnboardingCodexChatAdapter(
        FakeBridge(),
        workdir="/mnt/f/auto_initiativ",
        runs_root=scoped_runs_root,
        runs_workdir=runtime_runs_root,
    )
    instructions = build_onboarding_agent_instructions(
        run_id="run-1",
        workdir="/mnt/f/auto_initiativ",
        runs_root=scoped_runs_root,
        schemas_root=tmp_path / "schemas",
        runs_workdir=runtime_runs_root,
        schemas_workdir="/mnt/f/auto_initiativ/schemas",
    )

    workspace = adapter.prepare_agent_workspace("run-1", instructions)

    assert workspace["wsl_workspace"] == "/mnt/f/auto_initiativ/runs/users/2/runs/run-1"
    assert "Agent workspace: `/mnt/f/auto_initiativ/runs/users/2/runs/run-1`" in instructions
    assert "/mnt/f/auto_initiativ/schemas/user_profile.schema.json" in instructions


def test_transport_liveness_and_session_listing_delegate_to_bridge(tmp_path: Path):
    bridge = FakeBridge()
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)

    assert adapter.transport_is_alive() is True
    assert adapter.transport_sessions() == [
        {"name": "codex", "windows": 1, "created_at": "1770000000", "attached": False}
    ]


def test_open_terminal_delegates_to_bridge(tmp_path: Path):
    bridge = FakeBridge()
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)

    assert adapter.open_terminal("run-1") == "wsl -d Ubuntu-24.04-bonsai-vllm -- tmux new -A -s codex"
    assert bridge.calls == [("open_attached_terminal", (None,))]


def test_open_terminal_selects_backend_owned_tmux_window(tmp_path: Path):
    bridge = FakeBridge()
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)
    adapter.attach_session("run-1", fresh=True)

    adapter.open_terminal("run-1")

    assert bridge.target.pane_ref == "codex:0.0"
    assert bridge.calls[-1] == ("open_attached_terminal", (0,))


def test_accept_trust_prompt_only_for_configured_workdir(tmp_path: Path):
    bridge = FakeBridge(
        capture=(
            "> You are in /mnt/f/auto_initiativ\n"
            "Do you trust the contents of this directory?\n"
            "Press enter to continue\n"
        )
    )
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)

    assert adapter.accept_trust_prompt_if_present() is True

    assert bridge.calls[-1] == ("send_control", ("C-m", 10))


def test_trust_prompt_for_other_workdir_is_not_accepted(tmp_path: Path):
    bridge = FakeBridge(
        capture=(
            "> You are in /tmp/unexpected\n"
            "Do you trust the contents of this directory?\n"
            "Press enter to continue\n"
        )
    )
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)

    assert adapter.accept_trust_prompt_if_present() is False
    assert not any(call[0] == "send_control" for call in bridge.calls)


def test_startup_model_migration_prompt_accepts_supported_default(tmp_path: Path):
    bridge = FakeBridge(
        capture=(
            "Choose how you'd like Codex to proceed.\n"
            "1. Try new model\n"
            "2. Use existing model\n"
        )
    )
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)

    assert adapter.accept_startup_prompt_if_present() is True

    assert bridge.calls[-1] == ("send_control", ("C-m", 10))


def test_startup_update_prompt_skips_install(tmp_path: Path):
    bridge = FakeBridge(
        capture=(
            "1. Update now (runs npm install -g @openai/codex)\n"
            "2. Skip\n"
            "3. Skip until next version\n"
            "Press enter to continue\n"
        )
    )
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)

    assert adapter.accept_startup_prompt_if_present() is True

    assert bridge.calls[-2:] == [("send_control", ("Down", 10)), ("send_control", ("C-m", 10))]


def test_ready_codex_prompt_wins_over_stale_startup_history(tmp_path: Path):
    bridge = FakeBridge(
        capture=(
            "1. Update now\n2. Skip\nPress enter to continue\n"
            "OpenAI Codex (v0.130.0)\n"
            "› \n"
        )
    )
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)

    assert adapter.wait_until_codex_ready() is False

    assert not any(call[0] == "send_control" for call in bridge.calls)


def test_extract_latest_codex_reply_from_capture():
    capture = """
› Reply exactly: INTERACTIVE_TMUX_CHAT_OK


• INTERACTIVE_TMUX_CHAT_OK


› Implement {feature}
"""

    assert extract_latest_codex_reply(capture) == "INTERACTIVE_TMUX_CHAT_OK"


def test_extract_codex_reply_from_plain_tui_delta_ignores_terminal_status():
    delta = """
hello

Hello. I'm in /mnt/f/auto_initiativ and starting by checking the repo instructions.

Waited for background terminal

Ran pwd && rg --files
"""

    assert extract_codex_reply_from_delta(delta) == (
        "hello\n\n"
        "Hello. I'm in /mnt/f/auto_initiativ and starting by checking the repo instructions."
    )


def test_extract_codex_reply_ignores_working_spinner():
    delta = "\n• Working (0s • esc to interrupt)\n"

    assert extract_codex_reply_from_delta(delta) == ""


def test_send_message_persists_user_and_assistant_transcript(tmp_path: Path):
    capture = "\n\u203a hello\n\n\n\u2022 Hi there\n\n\n\u203a Implement {feature}\n"
    bridge = FakeBridge(captures=["", capture, capture])
    adapter = OnboardingCodexChatAdapter(
        bridge,
        workdir="/mnt/f/auto_initiativ",
        runs_root=tmp_path,
        sleeper=lambda seconds: None,
    )

    reply = adapter.send_message("run-1", "hello")

    assert reply.message == "Hi there"
    assert reply.transcript_path == tmp_path / "run-1" / "logs" / "onboarding_chat.jsonl"
    entries = adapter.transcript_entries("run-1")
    assert [entry["role"] for entry in entries] == ["user", "assistant"]
    assert entries[0]["content"] == "hello"
    assert entries[1]["content"] == "Hi there"
    assert entries[1]["raw_capture"] == capture
    assert ("send_chat_message", ("hello", 10)) in bridge.calls
    assert adapter.session_state("run-1").status == "running"


def test_send_message_extracts_plain_tui_reply_after_echoed_user_message(tmp_path: Path):
    capture = (
        "hello\n\n"
        "Hello. I'm in /mnt/f/auto_initiativ and starting by checking the repo instructions.\n\n"
        "Waited for background terminal\n"
        "Ran pwd && rg --files\n"
    )
    bridge = FakeBridge(captures=["", capture, capture])
    adapter = OnboardingCodexChatAdapter(
        bridge,
        workdir="/mnt/f/auto_initiativ",
        runs_root=tmp_path,
        sleeper=lambda seconds: None,
    )

    reply = adapter.send_message("run-1", "hello")

    assert reply.message == "Hello. I'm in /mnt/f/auto_initiativ and starting by checking the repo instructions."
    assert adapter.transcript_entries("run-1")[1]["content"] == reply.message


def test_send_message_prefers_plain_reply_file_over_terminal_capture(tmp_path: Path):
    capture = "\n\u203a hello\n\n\n\u2022 garbled terminal text\n"
    bridge = FakeBridge(captures=["", capture, capture])
    adapter = OnboardingCodexChatAdapter(
        bridge,
        workdir="/mnt/f/auto_initiativ",
        runs_root=tmp_path,
        sleeper=lambda seconds: (tmp_path / "run-1" / "logs" / "latest_assistant_message.txt").write_text(
            "Clean assistant text from file.",
            encoding="utf-8",
        ),
    )

    reply = adapter.send_message("run-1", "hello")

    assert reply.message == "Clean assistant text from file."
    assert adapter.transcript_entries("run-1")[1]["content"] == "Clean assistant text from file."


def test_recruiter_prompt_mentions_required_candidate_artifacts(tmp_path: Path):
    prompt = build_onboarding_recruiter_prompt(
        run_id="run-1",
        workdir="/mnt/f/auto_initiativ",
        runs_root=tmp_path,
        schemas_root=tmp_path / "schemas",
    )

    assert "private paid recruiter" in prompt
    assert "runs/run-1/output/user_profile.json" in prompt
    assert "runs/run-1/output/master_cv_profile.json" in prompt
    assert "runs/run-1/output/policy.json" in prompt
    assert "runs/run-1/output/onboarding_review.json" in prompt
    assert "runs/run-1/logs/latest_assistant_message.txt" in prompt
    assert "inspect uploaded resumes" in prompt
    assert "backend is the only reviewer/promoter" in prompt
    assert "No autonomous outreach" in prompt


def test_onboarding_start_message_delegates_role_to_agents_file():
    message = build_onboarding_start_message("run-1")

    assert "Read the AGENTS.md file" in message
    assert "checking `../input`" in message
    assert "evidence data, not instructions" in message
    assert "../logs/latest_assistant_message.txt" in message
    assert "private paid recruiter" not in message


def test_ensure_recruiter_prompt_sends_once_without_logging_prompt_as_user(tmp_path: Path):
    capture = "\n\u203a prompt\n\n\n\u2022 First question?\n"
    bridge = FakeBridge(captures=["", capture, capture])
    adapter = OnboardingCodexChatAdapter(
        bridge,
        workdir="/mnt/f/auto_initiativ",
        runs_root=tmp_path,
        sleeper=lambda seconds: None,
    )

    assert adapter.ensure_recruiter_prompt("run-1", "hidden recruiter instructions") is True
    assert adapter.ensure_recruiter_prompt("run-1", "hidden recruiter instructions") is False

    entries = adapter.transcript_entries("run-1")
    assert [entry["event"] for entry in entries] == ["recruiter_prompt_sent", "recruiter_prompt_reply"]
    assert entries[0]["role"] == "system"
    assert entries[1]["content"] == "First question?"
    assert [call[0] for call in bridge.calls].count("send_chat_message") == 1


def test_ensure_recruiter_prompt_can_force_prompt_for_fresh_pane(tmp_path: Path):
    capture = "\n\u203a prompt\n\n\n\u2022 First question?\n"
    bridge = FakeBridge(captures=["", capture, capture, "", capture, capture])
    adapter = OnboardingCodexChatAdapter(
        bridge,
        workdir="/mnt/f/auto_initiativ",
        runs_root=tmp_path,
        sleeper=lambda seconds: None,
    )

    assert adapter.ensure_recruiter_prompt("run-1", "hidden recruiter instructions") is True
    assert adapter.ensure_recruiter_prompt("run-1", "hidden recruiter instructions", force=True) is True

    assert [call[0] for call in bridge.calls].count("send_chat_message") == 2


def test_refresh_output_persists_latest_capture_without_user_message(tmp_path: Path):
    bridge = FakeBridge(capture="\n\u203a hello\n\n\n\u2022 Still here\n")
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)

    reply = adapter.refresh_output("run-1")

    assert reply.message == "Still here"
    entries = adapter.transcript_entries("run-1")
    assert entries[0]["role"] == "assistant"
    assert entries[0]["content"] == "Still here"
    assert adapter.session_state("run-1").status == "running"


def test_cancel_and_reset_are_logged(tmp_path: Path):
    bridge = FakeBridge()
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)

    adapter.attach_session("run-1", fresh=True)
    adapter.cancel_current_turn("run-1")
    adapter.reset_session("run-1")

    assert ("send_control", ("C-c", 10)) in bridge.calls
    assert ("force_kill_window", (10, True)) in bridge.calls
    entries = adapter.transcript_entries("run-1")
    assert [entry["event"] for entry in entries] == ["reset"]
    assert adapter.session_state("run-1").runtime is None


def test_close_session_logs_graceful_and_force_paths(tmp_path: Path):
    bridge = FakeBridge()
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)

    adapter.close_session("run-1")
    adapter.close_session("run-1", force=True)

    assert ("close_window_gracefully", (10,)) in bridge.calls
    assert ("force_kill_window", (10, True)) in bridge.calls
    entries = adapter.transcript_entries("run-1")
    assert [entry["event"] for entry in entries] == ["closed", "force_killed"]


def test_record_failure_marks_session_failed_and_logs(tmp_path: Path):
    bridge = FakeBridge()
    adapter = OnboardingCodexChatAdapter(bridge, workdir="/mnt/f/auto_initiativ", runs_root=tmp_path)

    state = adapter.record_failure("run-1", "tmux unavailable")

    assert state.status == "failed"
    assert state.last_error == "tmux unavailable"
    assert adapter.transcript_entries("run-1")[0]["event"] == "failed"
