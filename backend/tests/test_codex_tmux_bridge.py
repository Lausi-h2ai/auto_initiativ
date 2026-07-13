from __future__ import annotations

import pytest

import backend.app.agents.codex_tmux as codex_tmux
from backend.app.agents.codex_tmux import CommandResult, TmuxCodexBridge, TmuxCodexError, TmuxTarget


class FakeRunner:
    def __init__(self, result: CommandResult | None = None, results: list[CommandResult] | None = None) -> None:
        self.calls: list[tuple[list[str], float | None, str | None]] = []
        self.result = result or CommandResult(returncode=0, stdout="", stderr="")
        self.results = list(results or [])

    def __call__(self, args, timeout, stdin=None):
        self.calls.append((list(args), timeout, stdin))
        if self.results:
            return self.results.pop(0)
        return self.result


def test_build_codex_exec_command_quotes_prompt_and_file_paths():
    command = TmuxCodexBridge.build_codex_exec_command(
        "Reply with exactly: TMUX_CODEX_SMOKE_OK",
        workdir="/mnt/f/auto_initiativ",
        output_path="/tmp/auto initiativ/out.txt",
        output_schema_path="/mnt/f/auto_initiativ/schemas/user_profile.schema.json",
    )

    assert command == (
        "cd /mnt/f/auto_initiativ && codex exec --ephemeral --sandbox read-only "
        "--output-schema /mnt/f/auto_initiativ/schemas/user_profile.schema.json "
        "-o '/tmp/auto initiativ/out.txt' 'Reply with exactly: TMUX_CODEX_SMOKE_OK'"
    )


def test_start_codex_exec_pastes_command_then_enters_it():
    runner = FakeRunner()
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    command = bridge.start_codex_exec(
        "Summarize the onboarding notes",
        workdir="/mnt/f/auto_initiativ",
        output_path="/tmp/result.md",
    )

    assert "codex exec --ephemeral --sandbox read-only" in command
    assert runner.calls == [
        (
            [
                "wsl",
                "-d",
                "Ubuntu-24.04-bonsai-vllm",
                "--",
                "tmux",
                "load-buffer",
                "-",
            ],
            10,
            command,
        ),
        (
            [
                "wsl",
                "-d",
                "Ubuntu-24.04-bonsai-vllm",
                "--",
                "tmux",
                "paste-buffer",
                "-t",
                "codex:0.0",
            ],
            10,
            None,
        ),
        (
            [
                "wsl",
                "-d",
                "Ubuntu-24.04-bonsai-vllm",
                "--",
                "tmux",
                "send-keys",
                "-t",
                "codex:0.0",
                "C-m",
            ],
            10,
            None,
        ),
    ]


def test_send_chat_message_pastes_literal_message_then_enter():
    runner = FakeRunner()
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    bridge.send_chat_message("I prefer remote Python backend work.")

    assert runner.calls[0][0][-2:] == ["load-buffer", "-"]
    assert runner.calls[0][2] == "I prefer remote Python backend work."
    assert runner.calls[1][0][-3:] == ["paste-buffer", "-t", "codex:0.0"]
    assert runner.calls[2][0][-4:] == ["send-keys", "-t", "codex:0.0", "C-m"]


def test_send_chat_message_loads_large_prompt_via_stdin_not_argv():
    runner = FakeRunner()
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)
    prompt = "profile artifact instructions\n" * 400

    bridge.send_chat_message(prompt)

    load_buffer_call = runner.calls[0]
    assert load_buffer_call[0][-2:] == ["load-buffer", "-"]
    assert prompt not in load_buffer_call[0]
    assert load_buffer_call[2] == prompt


def test_capture_pane_returns_stdout():
    runner = FakeRunner(CommandResult(returncode=0, stdout="agent reply", stderr=""))
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    assert bridge.capture_pane(start_line=-40) == "agent reply"
    assert runner.calls[0][0][-6:] == ["capture-pane", "-t", "codex:0.0", "-p", "-S", "-40"]


def test_read_new_output_returns_suffix_when_capture_extends_previous_snapshot():
    runner = FakeRunner(CommandResult(returncode=0, stdout="line 1\nline 2\nline 3\n", stderr=""))
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    output = bridge.read_new_output("line 1\n", start_line=-20)

    assert output.text == "line 2\nline 3\n"
    assert output.line_count == 2
    assert runner.calls[0][0][-6:] == ["capture-pane", "-t", "codex:0.0", "-p", "-S", "-20"]


def test_pane_command_reads_current_tmux_command():
    runner = FakeRunner(CommandResult(returncode=0, stdout="[codex] 0:node, current pane 0 - (10:13 15-May-26)\n", stderr=""))
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    assert bridge.pane_command() == "node"
    assert runner.calls[0][0][-4:] == ["display-message", "-p", "-t", "codex:0.0"]


def test_is_alive_checks_session_and_pane():
    runner = FakeRunner()
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    assert bridge.is_alive() is True

    assert runner.calls[0][0][-3:] == ["has-session", "-t", "codex"]
    assert runner.calls[1][0][-5:] == ["display-message", "-p", "-t", "codex:0.0", "#{pane_id}"]


def test_is_alive_returns_false_when_tmux_target_is_missing():
    runner = FakeRunner(CommandResult(returncode=1, stdout="", stderr="no session"))
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    assert bridge.is_alive() is False


def test_list_sessions_parses_tmux_rows():
    runner = FakeRunner(CommandResult(returncode=0, stdout="codex\t2\t1770000000\t1\nother\t1\t1770000100\t0\n", stderr=""))
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    sessions = bridge.list_sessions()

    assert [session.name for session in sessions] == ["codex", "other"]
    assert sessions[0].windows == 2
    assert sessions[0].attached is True
    assert sessions[1].attached is False


def test_open_attached_terminal_launches_visible_wsl_tmux(monkeypatch):
    launched = []

    def fake_popen(args, close_fds=True):
        launched.append((args, close_fds))
        return object()

    monkeypatch.setattr(codex_tmux.subprocess, "Popen", fake_popen)
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"))

    command = bridge.open_attached_terminal()

    assert command == "wsl -d Ubuntu-24.04-bonsai-vllm -- sh -lc 'exec tmux new -A -s codex'"
    assert launched == [
        (
            [
                "cmd.exe",
                "/c",
                "start",
                "Auto Initiativ Codex",
                "wsl.exe",
                "-d",
                "Ubuntu-24.04-bonsai-vllm",
                "--",
                "sh",
                "-lc",
                "exec tmux new -A -s codex",
            ],
            True,
        )
    ]


def test_open_attached_terminal_can_select_run_window(monkeypatch):
    launched = []

    def fake_popen(args, close_fds=True):
        launched.append((args, close_fds))
        return object()

    monkeypatch.setattr(codex_tmux.subprocess, "Popen", fake_popen)
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"))

    command = bridge.open_attached_terminal(window=7)

    assert "select-window -t codex:7" in command
    assert launched[0][0][-1] == "tmux has-session -t codex 2>/dev/null && tmux select-window -t codex:7; exec tmux new -A -s codex"


def test_start_fresh_session_kills_existing_session_then_creates_shell():
    runner = FakeRunner()
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    target = bridge.start_fresh_session("/mnt/f/auto_initiativ")

    assert target.pane_ref == "codex:0.0"
    assert runner.calls[0][0][-3:] == ["kill-session", "-t", "codex"]
    assert runner.calls[1][0][-7:] == [
        "new-session",
        "-d",
        "-s",
        "codex",
        "-c",
        "/mnt/f/auto_initiativ",
        "bash -i",
    ]


def test_start_fresh_window_returns_new_target():
    runner = FakeRunner(CommandResult(returncode=0, stdout="\\3\n", stderr=""))
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    target = bridge.start_fresh_window("/mnt/f/auto_initiativ", window_name="campaign-1")

    assert target.pane_ref == "codex:3.0"
    assert runner.calls[0][0][-3:] == ["has-session", "-t", "codex"]
    assert runner.calls[1][0][-12:] == [
        "new-window",
        "-d",
        "-P",
        "-F",
        r"\#{window_index}",
        "-t",
        "codex",
        "-c",
        "/mnt/f/auto_initiativ",
        "-n",
        "campaign-1",
        "bash -i",
    ]


def test_start_fresh_window_passes_tmux_format_after_f_flag():
    runner = FakeRunner(CommandResult(returncode=0, stdout="3\n", stderr=""))
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    bridge.start_fresh_window("/mnt/f/auto_initiativ", window_name="campaign-1")

    new_window_call = next(call for call, _timeout, _stdin in runner.calls if "new-window" in call)
    format_index = new_window_call.index("-F")
    assert format_index < len(new_window_call) - 1
    assert new_window_call[format_index + 1] == r"\#{window_index}"


def test_start_fresh_window_creates_base_session_when_missing():
    runner = FakeRunner(
        results=[
            CommandResult(returncode=1, stdout="", stderr="no session"),
            CommandResult(returncode=0, stdout="", stderr=""),
        ]
    )
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    target = bridge.start_fresh_window("/mnt/f/auto_initiativ", window_name="onboarding/local")

    assert target.pane_ref == "codex:0.0"
    assert runner.calls[1][0][-9:] == [
        "new-session",
        "-d",
        "-s",
        "codex",
        "-c",
        "/mnt/f/auto_initiativ",
        "-n",
        "onboarding-local",
        "bash -i",
    ]


def test_attach_app_session_reuses_live_target():
    runner = FakeRunner()
    target = TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm")
    bridge = TmuxCodexBridge(target, runner=runner)

    app_session = bridge.attach_app_session("onboarding-1", "/mnt/f/auto_initiativ")

    assert app_session.app_session_id == "onboarding-1"
    assert app_session.target == target
    assert app_session.status == "attached"


def test_attach_app_session_starts_window_when_configured_pane_is_stale_but_session_exists():
    runner = FakeRunner(
        results=[
            CommandResult(returncode=0, stdout="", stderr=""),
            CommandResult(returncode=1, stdout="", stderr="can't find pane"),
            CommandResult(returncode=0, stdout="", stderr=""),
            CommandResult(returncode=0, stdout="4\n", stderr=""),
        ]
    )
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    app_session = bridge.attach_app_session("onboarding-local", "/mnt/f/auto_initiativ")

    assert app_session.status == "started"
    assert app_session.target.pane_ref == "codex:4.0"
    assert not any(call[0][-5:] == ["new-session", "-d", "-s", "codex", "-c"] for call in runner.calls)
    assert any("new-window" in call[0] for call in runner.calls)


def test_attach_app_session_fresh_always_starts_run_window():
    runner = FakeRunner(CommandResult(returncode=0, stdout="5\n", stderr=""))
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    app_session = bridge.attach_app_session("onboarding-local", "/mnt/f/auto_initiativ", fresh=True)

    assert app_session.status == "started"
    assert app_session.target.pane_ref == "codex:5.0"
    assert any("new-window" in call[0] for call in runner.calls)


def test_start_interactive_codex_pastes_cd_and_codex_command():
    runner = FakeRunner()
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    command = bridge.start_interactive_codex("/mnt/f/auto_initiativ")

    assert command == "cd /mnt/f/auto_initiativ && codex"
    assert runner.calls[0][2] == command
    assert runner.calls[2][0][-4:] == ["send-keys", "-t", "codex:0.0", "C-m"]


def test_start_interactive_codex_can_pin_supported_model_and_workspace_sandbox():
    runner = FakeRunner()
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    command = bridge.start_interactive_codex(
        "/mnt/f/auto_initiativ",
        model="gpt-5.4",
        sandbox="workspace-write",
        approval_policy="never",
        additional_dirs=("/mnt/f/auto_initiativ/runs/run-1/logs", "/mnt/f/auto_initiativ/runs/run-1/output"),
    )

    assert command == (
        "cd /mnt/f/auto_initiativ && codex --model gpt-5.4 --sandbox workspace-write "
        "--ask-for-approval never "
        "--add-dir /mnt/f/auto_initiativ/runs/run-1/logs "
        "--add-dir /mnt/f/auto_initiativ/runs/run-1/output"
    )
    assert runner.calls[0][2] == command


def test_cancel_and_reset_send_control_commands():
    runner = FakeRunner()
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    bridge.send_control("C-c")
    bridge.reset_to_shell("/mnt/f/auto_initiativ")

    assert runner.calls[0][0][-4:] == ["send-keys", "-t", "codex:0.0", "C-c"]
    assert runner.calls[1][0][-7:] == [
        "respawn-pane",
        "-k",
        "-t",
        "codex:0.0",
        "-c",
        "/mnt/f/auto_initiativ",
        "bash",
    ]


def test_close_session_gracefully_sends_cancel_and_exit():
    runner = FakeRunner()
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    bridge.close_session_gracefully()

    assert runner.calls[0][0][-4:] == ["send-keys", "-t", "codex:0.0", "C-c"]
    assert runner.calls[1][0][-2:] == ["load-buffer", "-"]
    assert runner.calls[1][2] == "exit"
    assert runner.calls[3][0][-4:] == ["send-keys", "-t", "codex:0.0", "C-m"]


def test_close_window_gracefully_exits_then_kills_window():
    runner = FakeRunner()
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm", window=7), runner=runner)

    bridge.close_window_gracefully()

    assert runner.calls[0][0][-4:] == ["send-keys", "-t", "codex:7.0", "C-c"]
    assert runner.calls[-1][0][-3:] == ["kill-window", "-t", "codex:7"]


def test_force_kill_session_allows_missing_session_when_requested():
    runner = FakeRunner(CommandResult(returncode=1, stdout="", stderr="no session"))
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    bridge.force_kill_session(missing_ok=True)

    assert runner.calls[0][0][-3:] == ["kill-session", "-t", "codex"]


def test_tmux_failures_raise_clear_error():
    runner = FakeRunner(CommandResult(returncode=1, stdout="", stderr="no session"))
    bridge = TmuxCodexBridge(TmuxTarget(distro="Ubuntu-24.04-bonsai-vllm"), runner=runner)

    with pytest.raises(TmuxCodexError, match="no session"):
        bridge.capture_pane()
