from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from sqlmodel import Session, select

from backend.app.auth.context import scoped_runs_root
from backend.app.agents.codex_exec import CodexExecRequest
from backend.app.core.config import Settings, get_settings
from backend.app.db.models import AuditLog, Run, utc_now


GENERATOR_VERSION = "1.0"

DEFAULT_AGENT_INSTRUCTIONS = """# Agent Instructions

You are working inside a prepared local run folder.

- Treat `input/` as the only task input context.
- Write safety-relevant outputs only under `output/`.
- Do not create files outside this run folder.
- Do not send emails or perform irreversible actions.
- Do not use Gmail, SMTP, external sending services, credentials, or secrets.
- If evidence is missing, ambiguous, contradictory, inferred, or low confidence, mark it for review in the structured output.
- The backend will schema validate files in `output/` before anything can affect application state.
"""

PROMPT_TEMPLATE = """Read `instructions.md` and `task.md`, then complete the task using only files under `input/`.

Write all structured task outputs under `output/`. Treat stdout as diagnostic output only.
"""

SECRET_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?<![a-z0-9])sk-[a-z0-9_\-]{12,}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"\b(openai_api_key|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret)\b\s*[:=]",
        r"\b(password|passwd|pwd)\b\s*[:=]",
    )
]

CAPABILITY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\busers\.messages\.send\b",
        r"\bsmtp://",
        r"\bsmtps://",
        r"\bsendgrid\b",
        r"\bmailgun\b",
    )
]


class RunFolderError(ValueError):
    pass


@dataclass(frozen=True)
class RunInputFile:
    relative_path: str
    content: str


@dataclass(frozen=True)
class RunFolderSpec:
    run_id: str
    task: str
    inputs: tuple[RunInputFile, ...] = ()
    instructions: str = DEFAULT_AGENT_INSTRUCTIONS
    expected_output_files: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunFolder:
    run_id: str
    path: Path
    input_dir: Path
    output_dir: Path
    logs_dir: Path
    task_path: Path
    instructions_path: Path
    prompt_path: Path
    manifest_path: Path

    def to_codex_exec_request(self, *, timeout_seconds: float | None = None) -> CodexExecRequest:
        return CodexExecRequest(
            run_id=self.run_id,
            run_dir=self.path,
            prompt=self.prompt_path.read_text(encoding="utf-8"),
            timeout_seconds=timeout_seconds,
        )


class RunFolderGenerator:
    def __init__(self, *, settings: Settings | None = None, session: Session | None = None) -> None:
        self.settings = settings or get_settings()
        self.session = session

    def prepare(self, spec: RunFolderSpec) -> RunFolder:
        self._validate_spec(spec)

        run_dir = scoped_runs_root(self.settings.runs_root) / spec.run_id
        input_dir = run_dir / "input"
        output_dir = run_dir / "output"
        logs_dir = run_dir / "logs"
        for directory in (input_dir, output_dir, logs_dir):
            directory.mkdir(parents=True, exist_ok=True)

        task_path = run_dir / "task.md"
        instructions_path = run_dir / "instructions.md"
        prompt_path = run_dir / "prompt.md"
        manifest_path = run_dir / "manifest.json"

        _write_text(task_path, _normalize_text(spec.task))
        _write_text(instructions_path, _normalize_text(spec.instructions))
        _write_text(prompt_path, PROMPT_TEMPLATE)

        written_inputs = []
        for input_file in sorted(spec.inputs, key=lambda item: item.relative_path):
            relative_path = _safe_relative_path(input_file.relative_path)
            destination = input_dir / Path(*relative_path.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            _write_text(destination, _normalize_text(input_file.content))
            written_inputs.append(
                {
                    "path": str(relative_path),
                    "sha256": _sha256_text(_normalize_text(input_file.content)),
                    "size_bytes": destination.stat().st_size,
                }
            )

        manifest = {
            "generator_version": GENERATOR_VERSION,
            "run_id": spec.run_id,
            "paths": {
                "input": "input",
                "output": "output",
                "logs": "logs",
                "task": "task.md",
                "instructions": "instructions.md",
                "prompt": "prompt.md",
            },
            "input_files": written_inputs,
            "expected_output_files": sorted(spec.expected_output_files),
            "metadata": spec.metadata,
        }
        _write_text(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")

        folder = RunFolder(
            run_id=spec.run_id,
            path=run_dir,
            input_dir=input_dir,
            output_dir=output_dir,
            logs_dir=logs_dir,
            task_path=task_path,
            instructions_path=instructions_path,
            prompt_path=prompt_path,
            manifest_path=manifest_path,
        )
        self._persist_prepared_run(folder)
        return folder

    def _validate_spec(self, spec: RunFolderSpec) -> None:
        if not spec.run_id or any(part in spec.run_id for part in ("/", "\\", "..")):
            raise RunFolderError("run_id must be a simple relative identifier.")
        _reject_unsafe_content("task", spec.task)
        _reject_unsafe_content("instructions", spec.instructions)
        for expected_output in spec.expected_output_files:
            _safe_relative_path(expected_output)
        for input_file in spec.inputs:
            _safe_relative_path(input_file.relative_path)
            _reject_unsafe_content(input_file.relative_path, input_file.content)

    def _persist_prepared_run(self, folder: RunFolder) -> None:
        if self.session is None:
            return
        run = self.session.exec(select(Run).where(Run.run_id == folder.run_id)).first()
        if run is None:
            run = Run(run_id=folder.run_id, output_path=str(folder.output_dir), status="prepared")
        else:
            run.output_path = str(folder.output_dir)
            run.status = "prepared"
            run.updated_at = utc_now()
        run.agent_type = "codex_exec"
        self.session.add(run)
        self.session.add(
            AuditLog(
                run_id=folder.run_id,
                actor_type="backend",
                action="run_folder_prepared",
                entity_type="run",
                entity_id=folder.run_id,
                result_status="prepared",
                metadata_json=json.dumps({"run_folder": str(folder.path), "manifest_path": str(folder.manifest_path)}, sort_keys=True),
            )
        )
        self.session.commit()


def _normalize_text(value: str) -> str:
    return value.replace("\r\n", "\n").rstrip() + "\n"


def _write_text(path: Path, value: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        file.write(value)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_relative_path(value: str) -> PurePosixPath:
    if "\\" in value:
        raise RunFolderError(f"Path '{value}' must use forward slashes.")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise RunFolderError(f"Path '{value}' must be a safe relative path.")
    return path


def _reject_unsafe_content(label: str, content: str) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(content):
            raise RunFolderError(f"{label} appears to contain a secret or credential.")
    for pattern in CAPABILITY_PATTERNS:
        if pattern.search(content):
            raise RunFolderError(f"{label} appears to include an external sending capability.")
