from __future__ import annotations

import json

import pytest
from sqlmodel import select

from backend.app.agents.run_folder import RunFolderError, RunFolderGenerator, RunFolderSpec, RunInputFile
from backend.app.core.config import get_settings
from backend.app.db.models import AuditLog, Run


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()


def test_run_folder_generator_creates_reproducible_codex_exec_folder(runs_root):
    folder = RunFolderGenerator().prepare(
        RunFolderSpec(
            run_id="folder-basic",
            task="Research the scoped company candidate and write company_candidate.json.",
            inputs=(
                RunInputFile("company/source_notes.md", "Company site says it builds deterministic tools."),
                RunInputFile("policy.json", '{"schema_version":"1.0"}'),
            ),
            expected_output_files=("company_candidate.json",),
            metadata={"task_type": "company_research"},
        )
    )

    assert folder.path == runs_root / "folder-basic"
    assert folder.input_dir.is_dir()
    assert folder.output_dir.is_dir()
    assert folder.logs_dir.is_dir()
    assert folder.task_path.read_text(encoding="utf-8").endswith("\n")
    assert "Write safety-relevant outputs only under `output/`" in folder.instructions_path.read_text(encoding="utf-8")
    assert "Read `instructions.md` and `task.md`" in folder.prompt_path.read_text(encoding="utf-8")
    assert (folder.input_dir / "company" / "source_notes.md").read_text(encoding="utf-8").endswith("\n")

    manifest = json.loads(folder.manifest_path.read_text(encoding="utf-8"))
    assert manifest == {
        "generator_version": "1.0",
        "run_id": "folder-basic",
        "paths": {
            "input": "input",
            "output": "output",
            "logs": "logs",
            "task": "task.md",
            "instructions": "instructions.md",
            "prompt": "prompt.md",
        },
        "input_files": [
            {
                "path": "company/source_notes.md",
                "sha256": "bb8da68663400e3ee068481df604cf45c3787a1c270544a0c154bc058fc4f5c9",
                "size_bytes": 49,
            },
            {
                "path": "policy.json",
                "sha256": "4fde2c62eaeb82fe10581324384d0af72f965f0cc1d8375b234453bbd24c1857",
                "size_bytes": 25,
            },
        ],
        "expected_output_files": ["company_candidate.json"],
        "metadata": {"task_type": "company_research"},
    }

    request = folder.to_codex_exec_request(timeout_seconds=33)
    assert request.run_id == "folder-basic"
    assert request.run_dir == folder.path
    assert request.timeout_seconds == 33
    assert request.prompt == folder.prompt_path.read_text(encoding="utf-8")


def test_run_folder_generator_rewrites_same_spec_deterministically(runs_root):
    spec = RunFolderSpec(
        run_id="folder-repeat",
        task="Create a structured profile draft.",
        inputs=(RunInputFile("notes.md", "I prefer backend roles."),),
        expected_output_files=("user_profile.json",),
    )
    generator = RunFolderGenerator()

    first = generator.prepare(spec).manifest_path.read_text(encoding="utf-8")
    second = generator.prepare(spec).manifest_path.read_text(encoding="utf-8")

    assert first == second


@pytest.mark.parametrize(
    ("relative_path", "message"),
    [
        ("../secret.txt", "safe relative path"),
        ("/absolute.txt", "safe relative path"),
        ("nested\\windows.txt", "forward slashes"),
    ],
)
def test_run_folder_generator_rejects_unsafe_input_paths(relative_path, message):
    with pytest.raises(RunFolderError, match=message):
        RunFolderGenerator().prepare(
            RunFolderSpec(
                run_id="folder-unsafe-path",
                task="Task",
                inputs=(RunInputFile(relative_path, "content"),),
            )
        )


@pytest.mark.parametrize(
    "content",
    [
        "OPENAI_API_KEY=sk-this-is-a-secret-token",
        "refresh_token: abc123",
        "-----BEGIN PRIVATE KEY-----\nabc",
    ],
)
def test_run_folder_generator_rejects_secret_like_content(content):
    with pytest.raises(RunFolderError, match="secret or credential"):
        RunFolderGenerator().prepare(
            RunFolderSpec(
                run_id="folder-secret",
                task="Task",
                inputs=(RunInputFile("notes.md", content),),
            )
        )


def test_run_folder_generator_allows_company_names_containing_sk_prefix():
    folder = RunFolderGenerator().prepare(
        RunFolderSpec(
            run_id="folder-reprisk",
            task="Create draft for reprisk-20260525-123456 without exposing credentials.",
            expected_output_files=("email_draft.json",),
        )
    )

    assert folder.task_path.read_text(encoding="utf-8").startswith("Create draft for reprisk")


def test_run_folder_generator_rejects_external_sending_capability():
    with pytest.raises(RunFolderError, match="external sending capability"):
        RunFolderGenerator().prepare(
            RunFolderSpec(
                run_id="folder-send-capability",
                task="Use users.messages.send to contact a prospect.",
            )
        )


def test_run_folder_generator_persists_prepared_run_and_audit(db_session, runs_root):
    folder = RunFolderGenerator(session=db_session).prepare(
        RunFolderSpec(
            run_id="folder-audit",
            task="Prepare a scoped run.",
            inputs=(RunInputFile("notes.md", "No secrets here."),),
        )
    )

    run = db_session.exec(select(Run).where(Run.run_id == "folder-audit")).one()
    assert run.status == "prepared"
    assert run.agent_type == "codex_exec"
    assert run.output_path == str(folder.output_dir)
    audit = db_session.exec(select(AuditLog).where(AuditLog.action == "run_folder_prepared")).one()
    assert audit.result_status == "prepared"
    assert json.loads(audit.metadata_json)["manifest_path"] == str(folder.manifest_path)
