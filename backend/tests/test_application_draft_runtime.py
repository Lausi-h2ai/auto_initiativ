from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.agents.application_draft import ApplicationDraftBrief, build_application_draft_inputs, build_application_draft_task
from backend.app.agents.application_draft_runtime import ApplicationDraftRuntime, safe_application_draft_env
from backend.app.core.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        RUNS_ROOT=tmp_path,
        SCHEMAS_ROOT=tmp_path / "schemas",
        PI_RPC_BINARY="pi",
        PI_RPC_APPLICATION_DRAFT_EXTENSION_PATH=Path("backend/pi_extensions/application_draft.ts"),
        PI_RPC_APPLICATION_DRAFT_TIMEOUT_SECONDS=45,
    )


def test_application_draft_runtime_builds_restricted_pi_command(tmp_path: Path):
    runtime = ApplicationDraftRuntime(settings=_settings(tmp_path), clients={}, client_factory=lambda command, cwd, env: None)

    command = runtime._command("run-1")

    assert command[:3] == ["pi", "--mode", "rpc"]
    assert "--extension" in command
    assert "application_draft.ts" in str(command)
    assert "--no-builtin-tools" in command
    assert "--no-extensions" in command
    assert "--no-approve" in command
    assert "--no-context-files" in command
    assert "--session-dir" in command
    assert command[command.index("--provider") + 1] == "openai-codex"
    assert command[command.index("--model") + 1] == "gpt-5.6-luna"
    assert command[command.index("--thinking") + 1] == "low"


def test_safe_application_draft_env_filters_secrets_and_sets_runtime_context(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("GMAIL_TOKEN", "secret")
    monkeypatch.setenv("PATH", "safe-path")

    env = safe_application_draft_env()

    assert env["PATH"] == "safe-path"
    assert "OPENAI_API_KEY" not in env
    assert "GMAIL_TOKEN" not in env
    assert "APPLICATION_DRAFT_REPO_ROOT" in env
    assert "APPLICATION_DRAFT_PYTHON" in env


def test_application_draft_extension_contains_attachment_guards():
    source = Path("backend/pi_extensions/application_draft.ts").read_text(encoding="utf-8")

    assert "MAX_COMMAND_OUTPUT_BYTES" in source
    assert "MAX_ATTACHMENT_BYTES" in source
    assert "assertChildPath(outputRoot, outputPath)" in source
    assert "application_draft_write_contact_candidate" in source
    assert "application_draft_write_email_draft" in source
    assert "application_draft_write_attachment" in source
    assert "application_draft_render_pdf" in source


def test_application_draft_inputs_redact_unwanted_education_honor():
    brief = ApplicationDraftBrief(
        run_id="run-1",
        draft_id="draft-run-1",
        company_id="company-1",
        contact_id="contact-1",
        company_slug="company-1",
    )

    inputs = build_application_draft_inputs(
        brief=brief,
        user_profile={},
        master_cv_profile={
            "claims": [
                {
                    "claim_id": "education-1",
                    "statement": "M.Sc. completed Summa Cum Laude with final grade 1.5",
                }
            ]
        },
        policy={},
        company={},
        contact={},
        fit_evaluation=None,
        email_draft_schema="{}",
        contact_schema="{}",
        master_cv_html="<div>Abschluss Marz 2024 | Summa Cum Laude | Abschlussnote 1,5</div>",
        handoff_docs={},
    )

    serialized = "\n".join(inputs.values())
    assert "draft_context.json" in inputs
    assert "Summa Cum Laude" not in serialized
    assert "Abschluss Marz 2024 | Abschlussnote 1,5" in inputs["master_cv/de_ch_master.html"]
    assert "final grade 1.5" in inputs["master_cv_profile.json"]


def test_application_draft_context_preserves_full_claim_ledger_and_review_state():
    extra_claims = [
        {
            "claim_id": f"claim-extra-{index}",
            "statement": f"Additional ledger claim {index}",
            "approved_for_tailoring": index % 2 == 0,
            "provenance": {"needs_review": index % 3 == 0, "source_type": "user_claim", "source_refs": ["onboarding_chat"]},
        }
        for index in range(80)
    ]
    inputs = build_application_draft_inputs(
        brief=ApplicationDraftBrief(
            run_id="run-claim-ledger",
            draft_id="draft-claim-ledger",
            company_id="company-1",
            contact_id="contact-1",
            company_slug="company-1",
        ),
        user_profile={},
        master_cv_profile={
            "claims": [
                {
                    "claim_id": "claim-approved",
                    "statement": "Approved claim",
                    "approved_for_tailoring": True,
                    "provenance": {"needs_review": False, "source_type": "verified_document", "source_refs": ["cv.pdf"]},
                },
                {
                    "claim_id": "claim-review-blocked",
                    "statement": "Review-blocked claim",
                    "approved_for_tailoring": False,
                    "provenance": {"needs_review": True, "source_type": "needs_review", "source_refs": ["onboarding_chat"]},
                },
                *extra_claims,
            ],
        },
        policy={},
        company={},
        contact={},
        fit_evaluation=None,
        email_draft_schema="{}",
        contact_schema="{}",
        master_cv_html="<div>Template</div>",
        handoff_docs={},
    )

    context = json.loads(inputs["draft_context.json"])
    claims = {claim["claim_id"]: claim for claim in context["approved_claims"]}

    assert len(claims) == 82
    assert {"claim-approved", "claim-review-blocked", "claim-extra-79"} <= set(claims)
    assert claims["claim-approved"]["approved_for_tailoring"] is True
    assert claims["claim-approved"]["needs_review"] is False
    assert claims["claim-review-blocked"]["approved_for_tailoring"] is False
    assert claims["claim-review-blocked"]["needs_review"] is True
    assert "claim-review-blocked" in inputs["master_cv_profile.json"]


def test_application_draft_task_forbids_honor_and_requires_fuller_page_use():
    task = build_application_draft_task(
        ApplicationDraftBrief(
            run_id="run-1",
            draft_id="draft-run-1",
            company_id="company-1",
            contact_id="contact-1",
            company_slug="company-1",
        )
    )

    assert "Never include the phrase `Summa Cum Laude`" in task
    assert "Read `../input/draft_context.json` first" in task
    assert "do not leave a visibly sparse lower third" in task
    assert "Do not render the resume as a screenshot, bitmap, canvas, PIL image, ReportLab drawing, or image-only PDF" in task
    assert "body text around 9-10pt" in task
    assert "historically named `approved_claims` ledger" in task


def test_application_draft_runtime_closes_client_after_prompt_failure(tmp_path: Path):
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
    runtime = ApplicationDraftRuntime(settings=_settings(tmp_path), clients={"run-1": client})
    runtime._mark_run = lambda *args, **kwargs: None

    runtime._run_agent("run-1")

    assert client.closed is True
    assert client.timeout_seconds == 45
    assert "run-1" not in runtime.clients
    state = json.loads((run_root / "logs" / "application_draft_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "failed"


def test_application_draft_runtime_detects_stale_orphaned_state(tmp_path: Path):
    runtime = ApplicationDraftRuntime(settings=_settings(tmp_path), clients={})
    stale_at = datetime.now(timezone.utc) - timedelta(seconds=4000)

    assert runtime._state_is_stale(
        "run-1",
        {"status": "running", "updated_at": stale_at.isoformat()},
        None,
    )
    assert not runtime._state_is_stale(
        "run-2",
        {"status": "running", "updated_at": datetime.now(timezone.utc).isoformat()},
        None,
    )
