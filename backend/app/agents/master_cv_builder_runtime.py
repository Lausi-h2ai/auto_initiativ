from __future__ import annotations

import os
import sys
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

from backend.app.agents.onboarding_chat import ChatReply, ChatTranscriptEntry
from backend.app.agents.pi_rpc import PiRpcClient, PiRpcClientProtocol, PiRpcOnboardingChatAdapter
from backend.app.agents.pi_runtime import build_restricted_pi_rpc_command
from backend.app.auth.context import scoped_runs_root


REPO_ROOT = Path(__file__).resolve().parents[3]
MASTER_CV_EXTENSION = REPO_ROOT / "backend" / "pi_extensions" / "master_cv_builder.ts"


class PiRpcMasterCvBuilderAdapter(PiRpcOnboardingChatAdapter):
    """Restricted Pi RPC transport for master-CV design conversations.

    This intentionally reuses the battle-tested interactive transport while
    replacing its workspace, transcript, and extension boundaries. The agent
    can write only a candidate JSON document and its latest user-visible reply.
    """

    def prepare_agent_workspace(self, run_id: str, instructions: str) -> dict[str, str]:
        run_root = scoped_runs_root(self.settings.runs_root) / run_id
        workspace = run_root / "workspace"
        for dirname in ("input", "output", "logs", "workspace"):
            (run_root / dirname).mkdir(parents=True, exist_ok=True)
        agents_path = workspace / "AGENTS.md"
        agents_path.write_text(instructions, encoding="utf-8")
        (workspace / "README.md").write_text(
            (
                "# Master CV Builder Workspace\n\n"
                f"This is the restricted design workspace for `{run_id}`. Follow `AGENTS.md`. "
                "Use only the master_cv tools and write structured candidate JSON under `../output`.\n"
            ),
            encoding="utf-8",
        )
        return {"host_workspace": str(workspace), "wsl_workspace": str(workspace), "agents_path": str(agents_path)}

    def _default_client_factory(
        self,
        command: Sequence[str],
        cwd: Path,
        env: Mapping[str, str],
    ) -> PiRpcClientProtocol:
        return PiRpcClient.start(command, cwd, env)

    def _command(self, run_id: str) -> list[str]:
        return build_restricted_pi_rpc_command(
            binary=self.settings.pi_rpc_binary,
            session_dir=self._session_dir(run_id),
            extension_path=MASTER_CV_EXTENSION,
            provider=self.settings.pi_rpc_application_draft_provider,
            model=self.settings.pi_rpc_application_draft_model,
            thinking=self.settings.pi_rpc_application_draft_thinking,
            continue_session=self._has_saved_pi_session(run_id),
            trust_generated_context=True,
        )

    def send_message(self, run_id: str, message: str, timeout: float | None = 10) -> ChatReply:
        transcript = self._transcript_store(run_id)
        transcript.append(ChatTranscriptEntry(run_id=run_id, role="user", content=message, created_at=self._now()))
        self._state_store(run_id).write("waiting")
        result = self._client(run_id).prompt(
            message,
            timeout_seconds=self.settings.pi_rpc_application_draft_timeout_seconds,
        )
        self._append_events(run_id, result.events)
        transcript.append(
            ChatTranscriptEntry(
                run_id=run_id,
                role="assistant",
                content=result.text,
                created_at=self._now(),
                raw_capture=json.dumps({"runtime": "pi_rpc", "events": len(result.events)}, sort_keys=True),
            )
        )
        self._state_store(run_id).write("running")
        return ChatReply(message=result.text, raw_capture="", transcript_path=transcript.path)

    def ensure_recruiter_prompt(self, run_id: str, prompt: str, timeout: float | None = 10, **kwargs: object) -> bool:
        force = bool(kwargs.get("force", False))
        require_plain_reply = bool(kwargs.get("require_plain_reply", False))
        transcript = self._transcript_store(run_id)
        if not force and any(entry.get("event") == "builder_prompt_sent" for entry in transcript.read_entries()):
            return False
        transcript.append(
            ChatTranscriptEntry(
                run_id=run_id,
                role="system",
                content="Master CV builder prompt sent to Pi RPC session.",
                created_at=self._now(),
                event="builder_prompt_sent",
            )
        )
        self._state_store(run_id).write("waiting")
        result = self._client(run_id).prompt(
            prompt,
            timeout_seconds=self.settings.pi_rpc_application_draft_timeout_seconds,
        )
        self._append_events(run_id, result.events)
        if result.text:
            transcript.append(
                ChatTranscriptEntry(
                    run_id=run_id,
                    role="assistant",
                    content=result.text,
                    created_at=self._now(),
                    raw_capture=json.dumps({"runtime": "pi_rpc", "events": len(result.events)}, sort_keys=True),
                    event="builder_prompt_reply",
                )
            )
        if require_plain_reply and not result.text.strip():
            self._state_store(run_id).write("failed", last_error="Pi returned no builder greeting.")
            raise RuntimeError("Pi returned no builder greeting.")
        self._state_store(run_id).write("running")
        return True

    def _safe_env(self) -> Mapping[str, str]:
        if self.env is not None:
            return self.env
        allowed = {
            "APPDATA", "COMSPEC", "HOME", "LOCALAPPDATA", "PATH", "PATHEXT",
            "PI_CODING_AGENT_DIR", "PI_OFFLINE", "PI_SKIP_VERSION_CHECK", "PI_TELEMETRY",
            "SYSTEMDRIVE", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE", "WINDIR",
        }
        env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
        env["MASTER_CV_REPO_ROOT"] = str(REPO_ROOT)
        env["MASTER_CV_PYTHON"] = sys.executable
        return env

    def _transcript_store(self, run_id: str):
        from backend.app.agents.onboarding_chat import JsonlTranscriptStore

        return JsonlTranscriptStore(scoped_runs_root(self.settings.runs_root) / run_id / "logs" / "master_cv_chat.jsonl")

    def _state_store(self, run_id: str):
        from backend.app.agents.onboarding_chat import JsonSessionStateStore

        return JsonSessionStateStore(
            scoped_runs_root(self.settings.runs_root) / run_id / "logs" / "master_cv_session.json",
            run_id,
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
