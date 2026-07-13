from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from backend.app.auth.context import scoped_runs_root
from backend.app.agents.onboarding_chat import (
    ChatReply,
    ChatTranscriptEntry,
    JsonSessionStateStore,
    JsonlTranscriptStore,
    OnboardingSessionState,
)
from backend.app.core.config import Settings, get_settings

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class PiRpcPromptResult:
    text: str
    events: list[dict[str, Any]]


class PiRpcError(RuntimeError):
    pass


class PiRpcClientProtocol(Protocol):
    def prompt(self, message: str, *, timeout_seconds: float) -> PiRpcPromptResult: ...

    def command(self, payload: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]: ...

    def close(self) -> None: ...


ProcessFactory = Callable[[Sequence[str], Path, Mapping[str, str]], subprocess.Popen[str]]
ClientFactory = Callable[[Sequence[str], Path, Mapping[str, str]], PiRpcClientProtocol]

_PI_RPC_CLIENTS: dict[str, PiRpcClientProtocol] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _default_process_factory(
    command: Sequence[str],
    cwd: Path,
    env: Mapping[str, str],
) -> subprocess.Popen[str]:
    resolved_command = list(command)
    resolved_binary = shutil.which(resolved_command[0], path=env.get("PATH"))
    if resolved_binary is not None:
        resolved_command[0] = resolved_binary
    return subprocess.Popen(
        resolved_command,
        cwd=cwd,
        env=dict(env),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )


class PiRpcClient:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self._events: queue.Queue[dict[str, Any]] = queue.Queue()
        self._stderr: queue.Queue[str] = queue.Queue()
        self._write_lock = threading.Lock()
        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    @classmethod
    def start(
        cls,
        command: Sequence[str],
        cwd: Path,
        env: Mapping[str, str],
        *,
        process_factory: ProcessFactory = _default_process_factory,
    ) -> "PiRpcClient":
        try:
            return cls(process_factory(command, cwd, env))
        except FileNotFoundError as exc:
            raise PiRpcError(f"Pi executable not found: {command[0]}") from exc

    def prompt(self, message: str, *, timeout_seconds: float) -> PiRpcPromptResult:
        request_id = f"prompt-{uuid.uuid4()}"
        self._send({"id": request_id, "type": "prompt", "message": message})
        deadline = time.monotonic() + timeout_seconds
        response_seen = False
        text_chunks: list[str] = []
        events: list[dict[str, Any]] = []

        while time.monotonic() < deadline:
            event = self._next_event(deadline)
            events.append(event)
            if event.get("type") == "response" and event.get("id") == request_id:
                if not event.get("success"):
                    raise PiRpcError(str(event.get("error") or "Pi rejected prompt"))
                response_seen = True
                continue
            if event.get("type") == "message_update":
                update = event.get("assistantMessageEvent")
                if isinstance(update, dict) and update.get("type") == "text_delta":
                    delta = update.get("delta")
                    if isinstance(delta, str):
                        text_chunks.append(delta)
                continue
            if event.get("type") == "agent_end":
                break

        if not response_seen:
            raise PiRpcError(f"Timed out waiting for Pi prompt acknowledgement. stderr: {self._stderr_tail()}")
        text = "".join(text_chunks).strip() or _extract_agent_end_text(events)
        return PiRpcPromptResult(text=text, events=events)

    def command(self, payload: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
        request_id = payload.get("id") if isinstance(payload.get("id"), str) else f"cmd-{uuid.uuid4()}"
        payload = {**payload, "id": request_id}
        self._send(payload)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            event = self._next_event(deadline)
            if event.get("type") == "response" and event.get("id") == request_id:
                if not event.get("success"):
                    raise PiRpcError(str(event.get("error") or "Pi command failed"))
                return event
        raise PiRpcError(f"Timed out waiting for Pi command response. stderr: {self._stderr_tail()}")

    def close(self) -> None:
        if self.process.poll() is not None:
            return
        try:
            self.process.terminate()
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()

    def _send(self, payload: dict[str, Any]) -> None:
        if self.process.poll() is not None:
            raise PiRpcError(f"Pi RPC process exited with code {self.process.returncode}. stderr: {self._stderr_tail()}")
        if self.process.stdin is None:
            raise PiRpcError("Pi RPC stdin is unavailable")
        with self._write_lock:
            self.process.stdin.write(_json_dumps(payload) + "\n")
            self.process.stdin.flush()

    def _next_event(self, deadline: float) -> dict[str, Any]:
        timeout = max(deadline - time.monotonic(), 0.01)
        try:
            return self._events.get(timeout=timeout)
        except queue.Empty as exc:
            raise PiRpcError(f"Timed out waiting for Pi RPC event. stderr: {self._stderr_tail()}") from exc

    def _read_stdout(self) -> None:
        if self.process.stdout is None:
            return
        for line in self.process.stdout:
            line = line.rstrip("\r\n")
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                event = {"type": "parse_error", "raw": line}
            self._events.put(event)

    def _read_stderr(self) -> None:
        if self.process.stderr is None:
            return
        for line in self.process.stderr:
            self._stderr.put(line.rstrip("\r\n"))

    def _stderr_tail(self, limit: int = 20) -> str:
        values: list[str] = []
        while True:
            try:
                values.append(self._stderr.get_nowait())
            except queue.Empty:
                break
        for value in values:
            self._stderr.put(value)
        return "\n".join(values[-limit:])


def _extract_agent_end_text(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        if event.get("type") != "agent_end":
            continue
        messages = event.get("messages")
        if not isinstance(messages, list):
            continue
        for message in reversed(messages):
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            parts: list[str] = []
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                        parts.append(item["text"])
            if parts:
                return "".join(parts).strip()
    return ""


class PiRpcOnboardingChatAdapter:
    """Drive onboarding chat through Pi RPC.

    Pi is transport only. It may create candidate files through the narrowly
    scoped onboarding extension, but the backend still imports, validates, and
    promotes those files through the normal deterministic path.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client_factory: ClientFactory | None = None,
        clients: dict[str, PiRpcClientProtocol] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.clients = clients if clients is not None else _PI_RPC_CLIENTS
        self.client_factory = client_factory or self._default_client_factory
        self.env = env

    def prepare_agent_workspace(self, run_id: str, instructions: str) -> dict[str, str]:
        run_root = scoped_runs_root(self.settings.runs_root) / run_id
        workspace = run_root / "workspace"
        for dirname in ("input", "output", "logs", "workspace"):
            (run_root / dirname).mkdir(parents=True, exist_ok=True)
        agents_path = workspace / "AGENTS.md"
        agents_path.write_text(instructions, encoding="utf-8")
        (workspace / "README.md").write_text(
            (
                f"# Onboarding Workspace\n\n"
                f"This folder is the dedicated Pi RPC workspace for onboarding run `{run_id}`.\n"
                "Follow `AGENTS.md`. Use the onboarding_* tools to inspect `../input`, write clean replies, "
                "and write candidate JSON artifacts under `../output`.\n"
            ),
            encoding="utf-8",
        )
        return {
            "host_workspace": str(workspace),
            "wsl_workspace": str(workspace),
            "agents_path": str(agents_path),
        }

    def attach_session(self, run_id: str, *, fresh: bool = False, timeout: float | None = 10) -> dict[str, object]:
        if fresh:
            self._close_client(run_id)
        payload = {
            "runtime": "pi_rpc",
            "status": "started" if fresh or run_id not in self.clients else "attached",
            "command": self._logged_command(run_id),
            "session_dir": str(self._session_dir(run_id)),
            "workdir": str(self._workspace(run_id)),
        }
        self._transcript_store(run_id).append(
            ChatTranscriptEntry(
                run_id=run_id,
                role="system",
                content=json.dumps(payload, sort_keys=True),
                created_at=_utc_now(),
                event="pi_rpc_attached",
            )
        )
        self._state_store(run_id).write("running", tmux=payload)
        return payload

    def start_or_attach(self, run_id: str | None = None, timeout: float | None = 10) -> str:
        if run_id is None:
            raise PiRpcError("run_id is required for Pi RPC onboarding sessions")
        status = "attached" if run_id in self.clients else "started"
        self._client(run_id)
        self._state_store(run_id).write("running")
        return status

    def accept_trust_prompt_if_present(self, timeout: float | None = 10) -> bool:
        return False

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
                content="Onboarding recruiter prompt sent to Pi RPC session.",
                created_at=_utc_now(),
                event="recruiter_prompt_sent",
            )
        )
        self._state_store(run_id).write("waiting")
        result = self._client(run_id).prompt(prompt, timeout_seconds=self.settings.pi_rpc_timeout_seconds)
        self._append_events(run_id, result.events)
        if result.text:
            transcript.append(
                ChatTranscriptEntry(
                    run_id=run_id,
                    role="assistant",
                    content=result.text,
                    created_at=_utc_now(),
                    raw_capture=_json_dumps({"runtime": "pi_rpc", "events": len(result.events)}),
                    event="recruiter_prompt_reply",
                )
            )
        self._state_store(run_id).write("running")
        return True

    def send_message(self, run_id: str, message: str, timeout: float | None = 10) -> ChatReply:
        transcript = self._transcript_store(run_id)
        transcript.append(ChatTranscriptEntry(run_id=run_id, role="user", content=message, created_at=_utc_now()))
        self._state_store(run_id).write("waiting")
        result = self._client(run_id).prompt(message, timeout_seconds=self.settings.pi_rpc_timeout_seconds)
        self._append_events(run_id, result.events)
        transcript.append(
            ChatTranscriptEntry(
                run_id=run_id,
                role="assistant",
                content=result.text,
                created_at=_utc_now(),
                raw_capture=_json_dumps({"runtime": "pi_rpc", "events": len(result.events)}),
            )
        )
        self._state_store(run_id).write("running")
        return ChatReply(message=result.text, raw_capture="", transcript_path=transcript.path)

    def refresh_output(self, run_id: str, timeout: float | None = 10) -> ChatReply:
        reply = self._read_plain_reply_file(run_id) or self._latest_assistant_content(run_id) or ""
        return ChatReply(message=reply, raw_capture="", transcript_path=self._transcript_store(run_id).path)

    def open_terminal(self, run_id: str) -> str:
        return " ".join(self._logged_command(run_id))

    def close_session(self, run_id: str, *, force: bool = False, timeout: float | None = 10) -> None:
        self._close_client(run_id)
        self._state_store(run_id).write("closed")
        self._transcript_store(run_id).append(
            ChatTranscriptEntry(
                run_id=run_id,
                role="system",
                content="Pi RPC onboarding session closed.",
                created_at=_utc_now(),
                event="closed",
            )
        )

    def reset_session(self, run_id: str, timeout: float | None = 10) -> None:
        self._close_client(run_id)
        self._transcript_store(run_id).clear()
        self._clear_session_dir(run_id)
        self._state_store(run_id).write("not_started", tmux=None)
        self._transcript_store(run_id).append(
            ChatTranscriptEntry(
                run_id=run_id,
                role="system",
                content="Pi RPC onboarding session reset and transcript cleared.",
                created_at=_utc_now(),
                event="reset",
            )
        )

    def record_failure(self, run_id: str, message: str) -> OnboardingSessionState:
        state = self._state_store(run_id).write("failed", last_error=message)
        self._transcript_store(run_id).append(
            ChatTranscriptEntry(run_id=run_id, role="system", content=message, created_at=_utc_now(), event="failed")
        )
        return state

    def session_state(self, run_id: str) -> OnboardingSessionState:
        return self._state_store(run_id).read()

    def transcript_entries(self, run_id: str) -> list[dict[str, object]]:
        return self._transcript_store(run_id).read_entries()

    def _client(self, run_id: str) -> PiRpcClientProtocol:
        client = self.clients.get(run_id)
        if client is not None:
            return client
        workspace = self._workspace(run_id)
        if not workspace.exists():
            raise PiRpcError(f"Onboarding workspace is missing: {workspace}")
        command = self._command(run_id)
        client = self.client_factory(command, workspace, self._safe_env())
        self.clients[run_id] = client
        self._append_runtime_log(run_id, {"type": "pi_rpc_started", "command": self._logged_command(run_id)})
        return client

    def _default_client_factory(
        self,
        command: Sequence[str],
        cwd: Path,
        env: Mapping[str, str],
    ) -> PiRpcClientProtocol:
        return PiRpcClient.start(command, cwd, env)

    def _close_client(self, run_id: str) -> None:
        client = self.clients.pop(run_id, None)
        if client is not None:
            client.close()

    def _command(self, run_id: str) -> list[str]:
        command = [
            self.settings.pi_rpc_binary,
            "--mode",
            "rpc",
            "--session-dir",
            str(self._session_dir(run_id)),
        ]
        if self._has_saved_pi_session(run_id):
            command.append("--continue")
        command.extend(["--extension", str(self.settings.pi_rpc_extension_path)])
        if self.settings.pi_rpc_no_builtin_tools:
            command.append("--no-builtin-tools")
        if self.settings.pi_rpc_provider:
            command.extend(["--provider", self.settings.pi_rpc_provider])
        if self.settings.pi_rpc_model:
            command.extend(["--model", self.settings.pi_rpc_model])
        return command

    def _logged_command(self, run_id: str) -> list[str]:
        return list(self._command(run_id))

    def _safe_env(self) -> Mapping[str, str]:
        if self.env is not None:
            return self.env
        allowed = {
            "APPDATA",
            "COMSPEC",
            "HOME",
            "LOCALAPPDATA",
            "ONBOARDING_PYTHON",
            "ONBOARDING_REPO_ROOT",
            "PATH",
            "PATHEXT",
            "PI_CODING_AGENT_DIR",
            "PI_OFFLINE",
            "PI_SKIP_VERSION_CHECK",
            "PI_TELEMETRY",
            "PYTHONPATH",
            "SYSTEMDRIVE",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "WINDIR",
        }
        env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
        env["ONBOARDING_REPO_ROOT"] = str(REPO_ROOT)
        env["ONBOARDING_PYTHON"] = sys.executable
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(REPO_ROOT) if not existing_pythonpath else f"{REPO_ROOT}{os.pathsep}{existing_pythonpath}"
        return env

    def _workspace(self, run_id: str) -> Path:
        return scoped_runs_root(self.settings.runs_root) / run_id / "workspace"

    def _session_dir(self, run_id: str) -> Path:
        return scoped_runs_root(self.settings.runs_root) / run_id / "logs" / "pi-session"

    def _has_saved_pi_session(self, run_id: str) -> bool:
        session_dir = self._session_dir(run_id)
        return session_dir.exists() and any(session_dir.glob("*.jsonl"))

    def _clear_session_dir(self, run_id: str) -> None:
        session_dir = self._session_dir(run_id).resolve()
        run_root = (scoped_runs_root(self.settings.runs_root) / run_id).resolve()
        if session_dir.exists() and session_dir.is_dir() and session_dir.is_relative_to(run_root):
            shutil.rmtree(session_dir)

    def _transcript_store(self, run_id: str) -> JsonlTranscriptStore:
        return JsonlTranscriptStore(scoped_runs_root(self.settings.runs_root) / run_id / "logs" / "onboarding_chat.jsonl")

    def _state_store(self, run_id: str) -> JsonSessionStateStore:
        return JsonSessionStateStore(scoped_runs_root(self.settings.runs_root) / run_id / "logs" / "onboarding_session.json", run_id)

    def _plain_reply_path(self, run_id: str) -> Path:
        return scoped_runs_root(self.settings.runs_root) / run_id / "logs" / "latest_assistant_message.txt"

    def _read_plain_reply_file(self, run_id: str) -> str:
        path = self._plain_reply_path(run_id)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def _latest_assistant_content(self, run_id: str) -> str | None:
        for entry in reversed(self._transcript_store(run_id).read_entries()):
            if entry.get("role") == "assistant" and isinstance(entry.get("content"), str):
                return entry["content"]
        return None

    def _append_events(self, run_id: str, events: list[dict[str, Any]]) -> None:
        for event in events:
            self._append_runtime_log(run_id, event)

    def _append_runtime_log(self, run_id: str, event: dict[str, Any]) -> None:
        log_path = scoped_runs_root(self.settings.runs_root) / run_id / "logs" / "pi_rpc_events.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as file:
            file.write(_json_dumps(event) + "\n")
