from __future__ import annotations

import re
import shlex
import subprocess
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class TmuxTarget:
    distro: str
    session: str = "codex"
    window: int = 0
    pane: int = 0

    @property
    def pane_ref(self) -> str:
        return f"{self.session}:{self.window}.{self.pane}"

    @property
    def window_ref(self) -> str:
        return f"{self.session}:{self.window}"

    def with_window(self, window: int) -> Self:
        return type(self)(distro=self.distro, session=self.session, window=window, pane=0)


@dataclass(frozen=True)
class TmuxSessionInfo:
    name: str
    windows: int
    created_at: str
    attached: bool


@dataclass(frozen=True)
class PaneOutputSnapshot:
    text: str
    line_count: int


@dataclass(frozen=True)
class TmuxAppSession:
    app_session_id: str
    target: TmuxTarget
    workdir: str
    status: str


class TmuxCodexError(RuntimeError):
    pass


Runner = Callable[[Sequence[str], float | None, str | None], CommandResult]


def _default_runner(args: Sequence[str], timeout: float | None, stdin: str | None = None) -> CommandResult:
    try:
        result = subprocess.run(
            list(args),
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TmuxCodexError(f"tmux command timed out after {timeout} seconds") from exc
    return CommandResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


class TmuxCodexBridge:
    """Drive a Codex CLI session through a WSL tmux pane.

    The bridge only sends terminal input and captures terminal output. It does
    not grant email access, mutate the database, or decide whether agent output
    is trustworthy.
    """

    def __init__(self, target: TmuxTarget, runner: Runner = _default_runner) -> None:
        self.target = target
        self._runner = runner

    def capture_pane(self, start_line: int = -200, timeout: float | None = 10) -> str:
        return self._run_tmux(
            "capture-pane",
            "-t",
            self.target.pane_ref,
            "-p",
            "-S",
            str(start_line),
            timeout=timeout,
        )

    def capture_snapshot(self, start_line: int = -200, timeout: float | None = 10) -> PaneOutputSnapshot:
        text = self.capture_pane(start_line=start_line, timeout=timeout)
        return PaneOutputSnapshot(text=text, line_count=len(text.splitlines()))

    def read_new_output(
        self,
        previous: PaneOutputSnapshot | str | None,
        *,
        start_line: int = -200,
        timeout: float | None = 10,
    ) -> PaneOutputSnapshot:
        current = self.capture_snapshot(start_line=start_line, timeout=timeout)
        previous_text = previous.text if isinstance(previous, PaneOutputSnapshot) else previous
        if previous_text and current.text.startswith(previous_text):
            return PaneOutputSnapshot(
                text=current.text[len(previous_text) :].lstrip("\r\n"),
                line_count=max(current.line_count - len(previous_text.splitlines()), 0),
            )
        return current

    def pane_command(self, timeout: float | None = 10) -> str:
        output = self._run_tmux(
            "display-message",
            "-p",
            "-t",
            self.target.pane_ref,
            timeout=timeout,
        ).strip()
        match = re.search(r"\]\s+\d+:([^,]+),", output)
        return match.group(1).strip() if match else output

    def is_alive(self, timeout: float | None = 10) -> bool:
        try:
            self._run_tmux("has-session", "-t", self.target.session, timeout=timeout)
            self._run_tmux("display-message", "-p", "-t", self.target.pane_ref, "#{pane_id}", timeout=timeout)
        except TmuxCodexError:
            return False
        return True

    def has_session(self, timeout: float | None = 10) -> bool:
        try:
            self._run_tmux("has-session", "-t", self.target.session, timeout=timeout)
        except TmuxCodexError:
            return False
        return True

    def list_sessions(self, timeout: float | None = 10) -> list[TmuxSessionInfo]:
        output = self._run_tmux(
            "list-sessions",
            "-F",
            "#{session_name}\t#{session_windows}\t#{session_created}\t#{session_attached}",
            timeout=timeout,
        )
        sessions: list[TmuxSessionInfo] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            name, windows, created_at, attached = (line.split("\t", 3) + ["", "", "", ""])[:4]
            sessions.append(
                TmuxSessionInfo(
                    name=name,
                    windows=int(windows) if windows.isdigit() else 0,
                    created_at=created_at,
                    attached=attached == "1",
                )
            )
        return sessions

    def open_attached_terminal(self, *, window: int | None = None) -> str:
        """Open a visible Windows terminal attached to the configured tmux session."""

        if window is None:
            script = f"exec tmux new -A -s {shlex.quote(self.target.session)}"
        else:
            window_ref = f"{self.target.session}:{window}"
            script = (
                f"tmux has-session -t {shlex.quote(self.target.session)} 2>/dev/null "
                f"&& tmux select-window -t {shlex.quote(window_ref)}; "
                f"exec tmux new -A -s {shlex.quote(self.target.session)}"
            )
        command = f"wsl -d {shlex.quote(self.target.distro)} -- sh -lc {shlex.quote(script)}"
        if os.name != "nt":
            raise TmuxCodexError("Opening a visible tmux terminal is only supported from the Windows local app host.")
        subprocess.Popen(
            [
                "cmd.exe",
                "/c",
                "start",
                "Auto Initiativ Codex",
                "wsl.exe",
                "-d",
                self.target.distro,
                "--",
                "sh",
                "-lc",
                script,
            ],
            close_fds=True,
        )
        return command

    def start_fresh_session(
        self,
        workdir: str,
        *,
        command: str = "bash -i",
        kill_existing: bool = True,
        timeout: float | None = 10,
    ) -> TmuxTarget:
        if kill_existing:
            self.force_kill_session(timeout=timeout, missing_ok=True)
        self._run_tmux("new-session", "-d", "-s", self.target.session, "-c", workdir, command, timeout=timeout)
        return self.target

    def start_fresh_window(
        self,
        workdir: str,
        *,
        window_name: str | None = None,
        command: str = "bash -i",
        timeout: float | None = 10,
    ) -> TmuxTarget:
        safe_window_name = _safe_tmux_window_name(window_name) if window_name else None
        if self.has_session(timeout=timeout):
            args = ["new-window", "-d", "-P", "-F", r"\#{window_index}", "-t", self.target.session, "-c", workdir]
            if safe_window_name is not None:
                args.extend(["-n", safe_window_name])
            args.append(command)
            output = self._run_tmux(*args, timeout=timeout).strip().lstrip("\\")
            window_index = int(output) if output.isdigit() else self.target.window + 1
        else:
            args = ["new-session", "-d", "-s", self.target.session, "-c", workdir]
            if safe_window_name is not None:
                args.extend(["-n", safe_window_name])
            args.append(command)
            self._run_tmux(*args, timeout=timeout)
            window_index = 0
        target = self.target.with_window(window_index)
        self.target = target
        return target

    def attach_app_session(
        self,
        app_session_id: str,
        workdir: str,
        *,
        fresh: bool = False,
        timeout: float | None = 10,
    ) -> TmuxAppSession:
        if fresh:
            target = self.start_fresh_window(workdir, window_name=app_session_id, timeout=timeout)
            return TmuxAppSession(app_session_id=app_session_id, target=target, workdir=workdir, status="started")
        if not self.is_alive(timeout=timeout):
            target = self.start_fresh_window(workdir, window_name=app_session_id, timeout=timeout)
            return TmuxAppSession(app_session_id=app_session_id, target=target, workdir=workdir, status="started")
        return TmuxAppSession(app_session_id=app_session_id, target=self.target, workdir=workdir, status="attached")

    def start_interactive_codex(
        self,
        workdir: str,
        timeout: float | None = 10,
        *,
        model: str | None = None,
        sandbox: str | None = None,
        approval_policy: str | None = None,
        additional_dirs: Sequence[str] = (),
    ) -> str:
        model_arg = f" --model {shlex.quote(model)}" if model else ""
        sandbox_arg = f" --sandbox {shlex.quote(sandbox)}" if sandbox else ""
        approval_arg = f" --ask-for-approval {shlex.quote(approval_policy)}" if approval_policy else ""
        add_dir_args = "".join(f" --add-dir {shlex.quote(path)}" for path in additional_dirs)
        command = f"cd {shlex.quote(workdir)} && codex{model_arg}{sandbox_arg}{approval_arg}{add_dir_args}"
        self._paste_literal(command, timeout=timeout)
        self._run_tmux("send-keys", "-t", self.target.pane_ref, "C-m", timeout=timeout)
        return command

    def send_chat_message(self, message: str, timeout: float | None = 10) -> None:
        self._paste_literal(message, timeout=timeout)
        self._run_tmux("send-keys", "-t", self.target.pane_ref, "C-m", timeout=timeout)

    def send_control(self, key: str, timeout: float | None = 10) -> None:
        self._run_tmux("send-keys", "-t", self.target.pane_ref, key, timeout=timeout)

    def close_session_gracefully(self, timeout: float | None = 10) -> None:
        self.send_control("C-c", timeout=timeout)
        self._paste_literal("exit", timeout=timeout)
        self._run_tmux("send-keys", "-t", self.target.pane_ref, "C-m", timeout=timeout)

    def close_window_gracefully(self, timeout: float | None = 10) -> None:
        self.close_session_gracefully(timeout=timeout)
        self.force_kill_window(timeout=timeout, missing_ok=True)

    def force_kill_session(self, timeout: float | None = 10, *, missing_ok: bool = False) -> None:
        try:
            self._run_tmux("kill-session", "-t", self.target.session, timeout=timeout)
        except TmuxCodexError:
            if not missing_ok:
                raise

    def force_kill_window(self, timeout: float | None = 10, *, missing_ok: bool = False) -> None:
        try:
            self._run_tmux("kill-window", "-t", self.target.window_ref, timeout=timeout)
        except TmuxCodexError:
            if not missing_ok:
                raise

    def reset_to_shell(self, workdir: str, timeout: float | None = 10) -> None:
        self._run_tmux(
            "respawn-pane",
            "-k",
            "-t",
            self.target.pane_ref,
            "-c",
            workdir,
            "bash",
            timeout=timeout,
        )

    def start_codex_exec(
        self,
        prompt: str,
        *,
        workdir: str,
        output_path: str | None = None,
        output_schema_path: str | None = None,
        sandbox: str = "read-only",
        ephemeral: bool = True,
        timeout: float | None = 10,
    ) -> str:
        command = self.build_codex_exec_command(
            prompt,
            workdir=workdir,
            output_path=output_path,
            output_schema_path=output_schema_path,
            sandbox=sandbox,
            ephemeral=ephemeral,
        )
        self._paste_literal(command, timeout=timeout)
        self._run_tmux("send-keys", "-t", self.target.pane_ref, "C-m", timeout=timeout)
        return command

    @staticmethod
    def build_codex_exec_command(
        prompt: str,
        *,
        workdir: str,
        output_path: str | None = None,
        output_schema_path: str | None = None,
        sandbox: str = "read-only",
        ephemeral: bool = True,
    ) -> str:
        args = ["codex", "exec"]
        if ephemeral:
            args.append("--ephemeral")
        args.extend(["--sandbox", sandbox])
        if output_schema_path is not None:
            args.extend(["--output-schema", output_schema_path])
        if output_path is not None:
            args.extend(["-o", output_path])
        args.append(prompt)

        quoted_args = " ".join(shlex.quote(arg) for arg in args)
        return f"cd {shlex.quote(workdir)} && {quoted_args}"

    def _paste_literal(self, text: str, timeout: float | None) -> None:
        self._run_tmux("load-buffer", "-", timeout=timeout, stdin=text)
        self._run_tmux("paste-buffer", "-t", self.target.pane_ref, timeout=timeout)

    def _run_tmux(self, *args: str, timeout: float | None, stdin: str | None = None) -> str:
        result = self._runner(
            ["wsl", "-d", self.target.distro, "--", "tmux", *args],
            timeout,
            stdin,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "tmux command failed"
            raise TmuxCodexError(detail)
        return result.stdout


def _safe_tmux_window_name(name: str | None) -> str | None:
    if name is None:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-")
    return cleaned[:64] or "codex-run"
