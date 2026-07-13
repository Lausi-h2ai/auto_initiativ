from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.app.agents.codex_tmux import TmuxCodexBridge, TmuxTarget


@dataclass(frozen=True)
class ChatTranscriptEntry:
    run_id: str
    role: str
    content: str
    created_at: str
    raw_capture: str | None = None
    event: str | None = None


@dataclass(frozen=True)
class ChatReply:
    message: str
    raw_capture: str
    transcript_path: Path


@dataclass(frozen=True)
class OnboardingSessionState:
    run_id: str
    status: str
    updated_at: str
    runtime: dict[str, object] | None = None
    last_error: str | None = None


Sleeper = Callable[[float], None]
Clock = Callable[[], float]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_latest_codex_reply(capture: str) -> str:
    cleaned_capture = _clean_terminal_capture(capture)
    lines = [line.rstrip() for line in cleaned_capture.splitlines()]
    bullet_prefixes = ("\u2022 ", "\u00e2\u20ac\u00a2 ")
    prompt_prefixes = ("\u203a ", "\u00e2\u20ac\u00ba ")
    last_bullet_index = None
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if any(stripped.startswith(prefix) for prefix in bullet_prefixes):
            last_bullet_index = index
    if last_bullet_index is None:
        return ""

    first_line = lines[last_bullet_index].lstrip()
    for prefix in bullet_prefixes:
        if first_line.startswith(prefix):
            first_line = first_line[len(prefix) :]
            break
    reply_lines = [first_line.strip()]
    for line in lines[last_bullet_index + 1 :]:
        stripped = line.strip()
        if not stripped:
            break
        if any(stripped.startswith(prefix) for prefix in prompt_prefixes):
            break
        if stripped.endswith("default \u00b7 /mnt/f/auto_initiativ"):
            break
        reply_lines.append(stripped)
    return "\n".join(line for line in reply_lines if line).strip()


def extract_codex_reply_from_delta(delta: str) -> str:
    cleaned_delta = _clean_terminal_capture(delta)
    bullet_reply = extract_latest_codex_reply(cleaned_delta)
    if bullet_reply and not _is_terminal_status_line(bullet_reply):
        return bullet_reply

    lines = cleaned_delta.splitlines()
    reply_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if reply_lines:
                reply_lines.append("")
            continue
        if _is_terminal_status_line(stripped) or _is_prompt_line(stripped):
            if reply_lines:
                break
            continue
        reply_lines.append(stripped)

    while reply_lines and not reply_lines[0]:
        reply_lines.pop(0)
    while reply_lines and not reply_lines[-1]:
        reply_lines.pop()
    return "\n".join(reply_lines).strip()


def _is_prompt_line(line: str) -> bool:
    return line.startswith((">", "\u203a", "\u2022", "Implement {feature}"))


def _is_terminal_status_line(line: str) -> bool:
    status_prefixes = (
        "Waited for background terminal",
        "Ran ",
        "$ ",
        "[",
        "...",
        "ctrl + t",
        "Working (",
    )
    if line.startswith(status_prefixes):
        return True
    if re.fullmatch(r"[─━_\-=]{6,}", line):
        return True
    return False


def _capture_delta(previous: str, current: str) -> str:
    if previous and current.startswith(previous):
        return current[len(previous) :]

    previous_lines = previous.splitlines()
    current_lines = current.splitlines()
    max_overlap = min(len(previous_lines), len(current_lines))
    for overlap in range(max_overlap, 0, -1):
        if previous_lines[-overlap:] == current_lines[:overlap]:
            return "\n".join(current_lines[overlap:])
    return current


def _strip_echoed_user_message(delta: str, sent_message: str) -> str:
    lines = delta.splitlines()
    sent_lines = [line.strip() for line in sent_message.splitlines() if line.strip()]
    if not sent_lines:
        return delta

    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines):
        return delta

    first = lines[index].strip()
    if first != sent_lines[0]:
        return delta

    index += 1
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            break
        if stripped in sent_lines:
            index += 1
            continue
        break
    while index < len(lines) and not lines[index].strip():
        index += 1
    return "\n".join(lines[index:])


def _clean_terminal_capture(capture: str) -> str:
    without_ansi = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", capture)
    replacements = {
        "\u00a0": " ",
        "\u200b": "",
        "\u00e2\u20ac\u00a2": "\u2022",
        "\u00e2\u20ac\u00ba": "\u203a",
        "\u00e2\u20ac\u2122": "'",
        "\u00e2\u20ac\u0153": '"',
        "\u00e2\u20ac\u009d": '"',
        "\u00e2\u20ac\u201c": "-",
        "\u00e2\u20ac\u201d": "-",
        "\u00c2\u00b7": "\u00b7",
    }
    for bad, good in replacements.items():
        without_ansi = without_ansi.replace(bad, good)
    return without_ansi


class JsonlTranscriptStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, entry: ChatTranscriptEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(asdict(entry), sort_keys=True, separators=(",", ":")) + "\n")

    def read_entries(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


class JsonSessionStateStore:
    def __init__(self, path: Path, run_id: str) -> None:
        self.path = path
        self.run_id = run_id

    def read(self) -> OnboardingSessionState:
        if not self.path.exists():
            return OnboardingSessionState(run_id=self.run_id, status="not_started", updated_at=_utc_now())
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return OnboardingSessionState(
            run_id=str(data.get("run_id") or self.run_id),
            status=str(data.get("status") or "not_started"),
            updated_at=str(data.get("updated_at") or _utc_now()),
            runtime=(
                data.get("runtime")
                if isinstance(data.get("runtime"), dict)
                else data.get("tmux") if isinstance(data.get("tmux"), dict) else None
            ),
            last_error=data.get("last_error") if isinstance(data.get("last_error"), str) else None,
        )

    def write(
        self,
        status: str,
        *,
        runtime: dict[str, object] | None = None,
        last_error: str | None = None,
        clear_runtime: bool = False,
    ) -> OnboardingSessionState:
        current = self.read()
        state = OnboardingSessionState(
            run_id=self.run_id,
            status=status,
            updated_at=_utc_now(),
            runtime=None if clear_runtime else runtime if runtime is not None else current.runtime,
            last_error=last_error,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(state), indent=2, sort_keys=True), encoding="utf-8")
        return state


class OnboardingCodexChatAdapter:
    def __init__(
        self,
        bridge: TmuxCodexBridge,
        *,
        workdir: str,
        runs_root: Path,
        runs_workdir: str | None = None,
        model: str | None = None,
        sandbox: str | None = None,
        approval_policy: str | None = None,
        sleeper: Sleeper | None = None,
        reply_wait_seconds: float = 2,
        reply_timeout_seconds: float = 90,
        capture_start_line: int = -200,
        clock: Clock | None = None,
    ) -> None:
        self.bridge = bridge
        self.repo_workdir = workdir.rstrip("/")
        self.workdir = self.repo_workdir
        self.runs_root = runs_root
        self.runs_workdir = (runs_workdir or f"{self.repo_workdir}/runs").rstrip("/")
        self.model = model
        self.sandbox = sandbox
        self.approval_policy = approval_policy
        self.sleeper = sleeper or (lambda seconds: None)
        self.reply_wait_seconds = reply_wait_seconds
        self.reply_timeout_seconds = reply_timeout_seconds
        self.capture_start_line = capture_start_line
        self.clock = clock or time.monotonic

    def prepare_agent_workspace(self, run_id: str, instructions: str) -> dict[str, str]:
        run_root = self.runs_root / run_id
        workspace = run_root / "workspace"
        for dirname in ("input", "output", "logs", "workspace"):
            (run_root / dirname).mkdir(parents=True, exist_ok=True)
        agents_path = run_root / "AGENTS.md"
        agents_path.write_text(instructions, encoding="utf-8")
        readme_path = workspace / "README.md"
        readme_path.write_text(
            (
                f"# Onboarding Workspace\n\n"
                f"This folder is the dedicated Codex workspace for onboarding run `{run_id}`.\n"
                "Follow `../AGENTS.md`. User documents are in `../input`; candidate JSON artifacts belong in `../output`; clean assistant replies belong in `../logs/latest_assistant_message.txt`.\n"
            ),
            encoding="utf-8",
        )
        self.workdir = self._run_workdir(run_id)
        return {
            "host_workspace": str(workspace),
            "wsl_workspace": self.workdir,
            "agents_path": str(agents_path),
        }

    def start_or_attach(self, run_id: str | None = None, timeout: float | None = 10) -> str:
        if run_id is not None:
            self._restore_tmux_target(run_id)
        command = self.bridge.pane_command(timeout=timeout)
        if command not in {"node", "codex"}:
            if self.model or self.sandbox or self.approval_policy:
                additional_dirs = ()
                if run_id is not None:
                    run_root = f"{self.runs_workdir}/{run_id}"
                    additional_dirs = (f"{run_root}/logs", f"{run_root}/output")
                return self.bridge.start_interactive_codex(
                    self.workdir,
                    timeout=timeout,
                    model=self.model,
                    sandbox=self.sandbox,
                    approval_policy=self.approval_policy,
                    additional_dirs=additional_dirs,
                )
            return self.bridge.start_interactive_codex(self.workdir, timeout=timeout)
        return "attached"

    def attach_session(self, run_id: str, *, fresh: bool = False, timeout: float | None = 10) -> dict[str, object]:
        self._restore_tmux_target(run_id)
        app_session = self.bridge.attach_app_session(run_id, self.workdir, fresh=fresh, timeout=timeout)
        payload = {
            "app_session_id": app_session.app_session_id,
            "tmux_session": app_session.target.session,
            "tmux_window": app_session.target.window,
            "tmux_pane": app_session.target.pane,
            "pane_ref": app_session.target.pane_ref,
            "workdir": app_session.workdir,
            "status": app_session.status,
        }
        self._transcript_store(run_id).append(
            ChatTranscriptEntry(
                run_id=run_id,
                role="system",
                content=json.dumps(payload, sort_keys=True),
                created_at=_utc_now(),
                event="tmux_attached",
            )
        )
        self._state_store(run_id).write("running", runtime=payload)
        return payload

    def transport_is_alive(self, timeout: float | None = 10) -> bool:
        return self.bridge.is_alive(timeout=timeout)

    def transport_sessions(self, timeout: float | None = 10) -> list[dict[str, object]]:
        return [asdict(session) for session in self.bridge.list_sessions(timeout=timeout)]

    def open_terminal(self, run_id: str) -> str:
        state = self._restore_tmux_target(run_id)
        tmux_window = state.runtime.get("tmux_window") if state.runtime else None
        window = tmux_window if isinstance(tmux_window, int) else None
        return self.bridge.open_attached_terminal(window=window)

    def accept_trust_prompt_if_present(self, timeout: float | None = 10) -> bool:
        capture = self.bridge.capture_pane(start_line=-80, timeout=timeout)
        if "Do you trust the contents of this directory?" not in capture:
            return False
        if self.workdir not in capture:
            return False
        self.bridge.send_control("C-m", timeout=timeout)
        return True

    def accept_startup_prompt_if_present(self, timeout: float | None = 10) -> bool:
        capture = self.bridge.capture_pane(start_line=-80, timeout=timeout)
        return self._accept_startup_prompt(capture, timeout=timeout)

    def wait_until_codex_ready(
        self,
        *,
        startup_timeout_seconds: float = 15,
        timeout: float | None = 10,
    ) -> bool:
        deadline = self.clock() + startup_timeout_seconds
        accepted = False
        while True:
            capture = self.bridge.capture_pane(start_line=-80, timeout=timeout)
            if "OpenAI Codex (" in capture and re.search(r"(?m)^\s*›(?:\s|$)", capture):
                return accepted
            if self._accept_startup_prompt(capture, timeout=timeout):
                accepted = True
            if self.clock() >= deadline:
                return accepted
            time.sleep(0.2)

    def _accept_startup_prompt(self, capture: str, *, timeout: float | None) -> bool:
        if (
            "Choose how you'd like Codex to proceed." in capture
            and "Try new model" in capture
            and "Use existing model" in capture
        ):
            self.bridge.send_control("C-m", timeout=timeout)
            return True
        if "Update now" in capture and "Skip" in capture and "Press enter to continue" in capture:
            self.bridge.send_control("Down", timeout=timeout)
            self.bridge.send_control("C-m", timeout=timeout)
            return True
        if "Do you trust the contents of this directory?" in capture and self.workdir in capture:
            self.bridge.send_control("C-m", timeout=timeout)
            return True
        return False

    def send_message(self, run_id: str, message: str, timeout: float | None = 10) -> ChatReply:
        self._restore_tmux_target(run_id)
        transcript = self._transcript_store(run_id)
        transcript.append(ChatTranscriptEntry(run_id=run_id, role="user", content=message, created_at=_utc_now()))
        self._state_store(run_id).write("waiting")
        self._clear_plain_reply_file(run_id)
        previous_capture = self.bridge.capture_pane(start_line=self.capture_start_line, timeout=timeout)
        self.bridge.send_chat_message(message, timeout=timeout)
        reply, raw_capture = self._wait_for_reply(run_id, previous_capture, sent_message=message, timeout=timeout)
        if reply:
            transcript.append(
                ChatTranscriptEntry(
                    run_id=run_id,
                    role="assistant",
                    content=reply,
                    created_at=_utc_now(),
                    raw_capture=raw_capture,
                )
            )
        self._state_store(run_id).write("running")
        return ChatReply(message=reply, raw_capture=raw_capture, transcript_path=transcript.path)

    def ensure_recruiter_prompt(
        self,
        run_id: str,
        prompt: str,
        timeout: float | None = 10,
        *,
        force: bool = False,
        require_plain_reply: bool = False,
    ) -> bool:
        transcript = self._transcript_store(run_id)
        if not force and any(entry.get("event") == "recruiter_prompt_sent" for entry in transcript.read_entries()):
            return False

        transcript.append(
            ChatTranscriptEntry(
                run_id=run_id,
                role="system",
                content="Onboarding recruiter prompt sent to Codex tmux session.",
                created_at=_utc_now(),
                event="recruiter_prompt_sent",
            )
        )
        self._state_store(run_id).write("waiting")
        self._clear_plain_reply_file(run_id)
        previous_capture = self.bridge.capture_pane(start_line=self.capture_start_line, timeout=timeout)
        self.bridge.send_chat_message(prompt, timeout=timeout)
        reply, raw_capture = self._wait_for_reply(
            run_id,
            previous_capture,
            sent_message=prompt,
            timeout=timeout,
            require_plain_reply=require_plain_reply,
        )
        if reply:
            transcript.append(
                ChatTranscriptEntry(
                    run_id=run_id,
                    role="assistant",
                    content=reply,
                    created_at=_utc_now(),
                    raw_capture=raw_capture,
                    event="recruiter_prompt_reply",
                )
            )
        self._state_store(run_id).write("running")
        return True

    def refresh_output(self, run_id: str, timeout: float | None = 10) -> ChatReply:
        self._restore_tmux_target(run_id)
        raw_capture = self.bridge.capture_pane(start_line=self.capture_start_line, timeout=timeout)
        reply = self._read_plain_reply_file(run_id) or extract_latest_codex_reply(raw_capture) or extract_codex_reply_from_delta(raw_capture)
        transcript = self._transcript_store(run_id)
        if reply and self._latest_assistant_content(run_id) != reply:
            transcript.append(
                ChatTranscriptEntry(
                    run_id=run_id,
                    role="assistant",
                    content=reply,
                    created_at=_utc_now(),
                    raw_capture=raw_capture,
                )
            )
        self._state_store(run_id).write("running")
        return ChatReply(message=reply, raw_capture=raw_capture, transcript_path=transcript.path)

    def cancel_current_turn(self, run_id: str, timeout: float | None = 10) -> None:
        self._restore_tmux_target(run_id)
        self.bridge.send_control("C-c", timeout=timeout)
        self._state_store(run_id).write("running")
        self._transcript_store(run_id).append(
            ChatTranscriptEntry(
                run_id=run_id,
                role="system",
                content="Current Codex turn cancelled.",
                created_at=_utc_now(),
                event="cancelled",
            )
        )

    def reset_session(self, run_id: str, timeout: float | None = 10) -> None:
        self._restore_tmux_target(run_id)
        if hasattr(self.bridge, "force_kill_window"):
            self.bridge.force_kill_window(timeout=timeout, missing_ok=True)
        else:
            self.bridge.reset_to_shell(self.workdir, timeout=timeout)
        self._transcript_store(run_id).clear()
        self._state_store(run_id).write("not_started", clear_runtime=True)
        self._transcript_store(run_id).append(
            ChatTranscriptEntry(
                run_id=run_id,
                role="system",
                content="Codex tmux run pane reset and transcript cleared.",
                created_at=_utc_now(),
                event="reset",
            )
        )

    def close_session(self, run_id: str, *, force: bool = False, timeout: float | None = 10) -> None:
        self._restore_tmux_target(run_id)
        if force:
            if hasattr(self.bridge, "force_kill_window"):
                self.bridge.force_kill_window(timeout=timeout, missing_ok=True)
            else:
                self.bridge.force_kill_session(timeout=timeout, missing_ok=True)
            event = "force_killed"
            content = "Codex tmux run pane force-killed."
        else:
            if hasattr(self.bridge, "close_window_gracefully"):
                self.bridge.close_window_gracefully(timeout=timeout)
            else:
                self.bridge.close_session_gracefully(timeout=timeout)
            event = "closed"
            content = "Codex tmux run pane closed gracefully."
        self._state_store(run_id).write("closed")
        self._transcript_store(run_id).append(
            ChatTranscriptEntry(
                run_id=run_id,
                role="system",
                content=content,
                created_at=_utc_now(),
                event=event,
            )
        )

    def record_failure(self, run_id: str, message: str) -> OnboardingSessionState:
        state = self._state_store(run_id).write("failed", last_error=message)
        self._transcript_store(run_id).append(
            ChatTranscriptEntry(
                run_id=run_id,
                role="system",
                content=message,
                created_at=_utc_now(),
                event="failed",
            )
        )
        return state

    def session_state(self, run_id: str) -> OnboardingSessionState:
        return self._state_store(run_id).read()

    def transcript_entries(self, run_id: str) -> list[dict[str, object]]:
        return self._transcript_store(run_id).read_entries()

    def _transcript_store(self, run_id: str) -> JsonlTranscriptStore:
        return JsonlTranscriptStore(self.runs_root / run_id / "logs" / "onboarding_chat.jsonl")

    def _state_store(self, run_id: str) -> JsonSessionStateStore:
        return JsonSessionStateStore(self.runs_root / run_id / "logs" / "onboarding_session.json", run_id)

    def _plain_reply_path(self, run_id: str) -> Path:
        return self.runs_root / run_id / "logs" / "latest_assistant_message.txt"

    def _run_workdir(self, run_id: str) -> str:
        return f"{self.runs_workdir}/{run_id}"

    def _clear_plain_reply_file(self, run_id: str) -> None:
        path = self._plain_reply_path(run_id)
        if path.exists():
            path.unlink()

    def _read_plain_reply_file(self, run_id: str) -> str:
        path = self._plain_reply_path(run_id)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def _wait_for_reply(
        self,
        run_id: str,
        previous_capture: str,
        *,
        sent_message: str,
        timeout: float | None,
        require_plain_reply: bool = False,
    ) -> tuple[str, str]:
        deadline = self.clock() + self.reply_timeout_seconds
        last_capture = previous_capture
        last_reply = ""
        stable_reply_count = 0

        while True:
            self.sleeper(self.reply_wait_seconds)
            current_capture = self.bridge.capture_pane(start_line=self.capture_start_line, timeout=timeout)
            delta = _strip_echoed_user_message(_capture_delta(previous_capture, current_capture), sent_message)
            plain_reply = self._read_plain_reply_file(run_id)
            reply = plain_reply or ("" if require_plain_reply else extract_codex_reply_from_delta(delta))
            if reply and reply == last_reply and current_capture == last_capture:
                stable_reply_count += 1
            elif reply:
                stable_reply_count = 1
            else:
                stable_reply_count = 0

            if reply and stable_reply_count >= 2:
                return reply, current_capture
            if self.clock() >= deadline:
                return reply, current_capture
            last_capture = current_capture
            last_reply = reply

    def _latest_assistant_content(self, run_id: str) -> str | None:
        for entry in reversed(self._transcript_store(run_id).read_entries()):
            if entry.get("role") == "assistant" and isinstance(entry.get("content"), str):
                return entry["content"]
        return None

    def _restore_tmux_target(self, run_id: str) -> OnboardingSessionState:
        state = self._state_store(run_id).read()
        if not state.runtime:
            return state
        session = state.runtime.get("tmux_session")
        window = state.runtime.get("tmux_window")
        pane = state.runtime.get("tmux_pane")
        if isinstance(session, str) and isinstance(window, int) and isinstance(pane, int):
            self.bridge.target = TmuxTarget(
                distro=self.bridge.target.distro,
                session=session,
                window=window,
                pane=pane,
            )
        workdir = state.runtime.get("workdir")
        if isinstance(workdir, str) and workdir:
            self.workdir = workdir
        return state
