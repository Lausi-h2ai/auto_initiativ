from __future__ import annotations

import json
from pathlib import Path

from backend.app.agents.onboarding_chat import ChatReply, ChatTranscriptEntry, JsonlTranscriptStore, OnboardingSessionState
from backend.app.api.routes import (
    _chat_entry_response,
    _onboarding_artifact_repair_prompt,
    _onboarding_finalization_prompt,
    get_onboarding_chat_adapter,
)


def _valid_user_profile() -> dict[str, object]:
    provenance = {
        "source_type": "user_claim",
        "confidence": 0.9,
        "needs_review": False,
        "source_refs": ["onboarding_chat"],
    }
    return {
        "schema_version": "1.0",
        "profile_id": "profile-onboarding-api",
        "created_at": "2026-05-15T00:00:00+00:00",
        "identity": {"display_name": "Example User"},
        "preferences": {
            "target_roles": [{"value": "Backend engineer", "provenance": provenance}],
            "target_locations": [{"value": "Berlin", "provenance": provenance}],
            "remote_preferences": ["remote", "hybrid"],
            "communication_tone": {"value": "direct and concise", "provenance": provenance},
        },
        "provenance_summary": {
            "source_documents": [],
            "interview_notes": ["Captured during onboarding chat."],
        },
    }


def _valid_master_cv_profile() -> dict[str, object]:
    provenance = {
        "source_type": "user_claim",
        "confidence": 0.9,
        "needs_review": False,
        "source_refs": ["onboarding_chat"],
    }
    return {
        "schema_version": "1.0",
        "profile_id": "profile-onboarding-api",
        "created_at": "2026-05-15T00:00:00+00:00",
        "claims": [
            {
                "claim_id": "claim-backend",
                "category": "skill",
                "statement": "Experienced with backend engineering.",
                "provenance": provenance,
                "approved_for_tailoring": False,
                "tags": ["backend"],
            }
        ],
    }


def _valid_policy() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "policy_id": "policy-onboarding-api",
        "created_at": "2026-05-15T00:00:00+00:00",
        "exclusions": {
            "industries": [],
            "company_names": [],
            "domains": [],
            "keywords": [],
        },
        "outreach": {
            "allow_company_repeat": False,
            "allow_recipient_repeat": False,
            "company_dedupe_window_days": 365,
            "recipient_dedupe_window_days": 365,
            "require_manual_review_before_send": True,
        },
        "limits": {
            "daily_send_limit": 0,
            "weekly_send_limit": 0,
        },
        "review_thresholds": {
            "minimum_required_confidence": 0.8,
            "block_needs_review_required_fields": True,
        },
        "forbidden_claims": [],
    }


def _valid_onboarding_review(run_id: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "review_id": f"review-{run_id}",
        "run_id": run_id,
        "created_at": "2026-05-15T00:00:00+00:00",
        "items": [],
    }


def test_onboarding_finalization_prompt_uses_workspace_relative_paths():
    prompt = _onboarding_finalization_prompt("run-1")

    assert "../output/user_profile.json" in prompt
    assert "../output/master_cv_profile.json" in prompt
    assert "JSON Schemas:" in prompt
    assert "user_profile.schema.json" in prompt
    assert '"profile_id"' in prompt
    assert "runs/run-1/output" not in prompt


def test_onboarding_repair_prompt_includes_validation_failures_and_schema_definitions():
    prompt = _onboarding_artifact_repair_prompt(
        "run-1",
        [
            {
                "filename": "user_profile.json",
                "status": "schema_validation_failed",
                "errors": [{"path": "$", "message": "profile_id is required"}],
            }
        ],
        1,
        2,
    )

    assert "Validation failures JSON" in prompt
    assert "profile_id is required" in prompt
    assert "JSON Schemas:" in prompt
    assert "user_profile.schema.json" in prompt
    assert '"profile_id"' in prompt


def test_internal_onboarding_prompts_are_redacted_in_chat_responses():
    finish_entry = _chat_entry_response(
        {
            "run_id": "run-1",
            "role": "user",
            "content": _onboarding_finalization_prompt("run-1"),
            "created_at": "2026-05-15T00:00:00+00:00",
        }
    )
    repair_entry = _chat_entry_response(
        {
            "run_id": "run-1",
            "role": "user",
            "content": _onboarding_artifact_repair_prompt("run-1", [], 1, 2),
            "created_at": "2026-05-15T00:00:00+00:00",
        }
    )

    assert finish_entry.content == "Finish artifacts"
    assert repair_entry.content == "Repair artifacts"
    assert "JSON Schemas" not in finish_entry.content
    assert "Validation failures JSON" not in repair_entry.content


class FakeOnboardingAdapter:
    def __init__(self, runs_root: Path) -> None:
        self.runs_root = runs_root
        self.states: dict[str, OnboardingSessionState] = {}
        self.prepared_workspaces: dict[str, str] = {}
        self.attach_fresh_values: list[bool] = []
        self.sent_messages: list[str] = []

    def _state(self, run_id: str, status: str | None = None, last_error: str | None = None) -> OnboardingSessionState:
        current = self.states.get(
            run_id,
            OnboardingSessionState(run_id=run_id, status="not_started", updated_at="2026-05-15T00:00:00+00:00"),
        )
        if status is None and last_error is None:
            return current
        updated = OnboardingSessionState(
            run_id=run_id,
            status=status or current.status,
            updated_at="2026-05-15T00:00:02+00:00",
            tmux=current.tmux,
            last_error=last_error,
        )
        self.states[run_id] = updated
        return updated

    def prepare_agent_workspace(self, run_id: str, instructions: str) -> dict[str, str]:
        self.prepared_workspaces[run_id] = instructions
        workspace = self.runs_root / run_id / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "AGENTS.md").write_text(instructions, encoding="utf-8")
        return {
            "host_workspace": str(workspace),
            "wsl_workspace": f"/mnt/f/auto_initiativ/runs/{run_id}/workspace",
            "agents_path": str(workspace / "AGENTS.md"),
        }

    def attach_session(self, run_id: str, fresh: bool = False, timeout: float | None = 10) -> dict[str, object]:
        self.attach_fresh_values.append(fresh)
        payload = {"app_session_id": run_id, "pane_ref": "codex:0.0", "status": "attached"}
        self.states[run_id] = OnboardingSessionState(
            run_id=run_id,
            status="running",
            updated_at="2026-05-15T00:00:00+00:00",
            tmux=payload,
        )
        return payload

    def start_or_attach(self, run_id: str | None = None, timeout: float | None = 10) -> str:
        for run_id in self.states:
            self._state(run_id, "running")
        return "attached"

    def accept_trust_prompt_if_present(self, timeout: float | None = 10) -> bool:
        return False

    def send_message(self, run_id: str, message: str, timeout: float | None = 10) -> ChatReply:
        self.sent_messages.append(message)
        self._state(run_id, "waiting")
        transcript = JsonlTranscriptStore(self.runs_root / run_id / "logs" / "onboarding_chat.jsonl")
        transcript.append(
            ChatTranscriptEntry(
                run_id=run_id,
                role="user",
                content=message,
                created_at="2026-05-15T00:00:00+00:00",
            )
        )
        reply_text = "Tell me more about your target roles."
        if "user_profile.json" in message:
            output_path = self.runs_root / run_id / "output"
            output_path.mkdir(parents=True, exist_ok=True)
            (output_path / "user_profile.json").write_text(json.dumps(_valid_user_profile()), encoding="utf-8")
            (output_path / "master_cv_profile.json").write_text(json.dumps(_valid_master_cv_profile()), encoding="utf-8")
            (output_path / "policy.json").write_text(json.dumps(_valid_policy()), encoding="utf-8")
            (output_path / "onboarding_review.json").write_text(json.dumps(_valid_onboarding_review(run_id)), encoding="utf-8")
            reply_text = "Wrote onboarding candidate artifacts."
        transcript.append(
            ChatTranscriptEntry(
                run_id=run_id,
                role="assistant",
                content=reply_text,
                created_at="2026-05-15T00:00:01+00:00",
                raw_capture=reply_text,
            )
        )
        self._state(run_id, "running")
        return ChatReply(message=reply_text, raw_capture=reply_text, transcript_path=transcript.path)

    def refresh_output(self, run_id: str, timeout: float | None = 10) -> ChatReply:
        transcript = JsonlTranscriptStore(self.runs_root / run_id / "logs" / "onboarding_chat.jsonl")
        transcript.append(
            ChatTranscriptEntry(
                run_id=run_id,
                role="assistant",
                content="Latest visible Codex output.",
                created_at="2026-05-15T00:00:03+00:00",
                raw_capture="Latest visible Codex output.",
            )
        )
        self._state(run_id, "running")
        return ChatReply(
            message="Latest visible Codex output.",
            raw_capture="Latest visible Codex output.",
            transcript_path=transcript.path,
        )

    def open_terminal(self, run_id: str) -> str:
        return "wsl -d Ubuntu-24.04-bonsai-vllm -- tmux new -A -s codex"

    def close_session(self, run_id: str, force: bool = False, timeout: float | None = 10) -> None:
        self._state(run_id, "closed")

    def reset_session(self, run_id: str, timeout: float | None = 10) -> None:
        self._state(run_id, "not_started")

    def record_failure(self, run_id: str, message: str) -> OnboardingSessionState:
        return self._state(run_id, "failed", message)

    def session_state(self, run_id: str) -> OnboardingSessionState:
        return self._state(run_id)

    def transcript_entries(self, run_id: str) -> list[dict[str, object]]:
        return JsonlTranscriptStore(self.runs_root / run_id / "logs" / "onboarding_chat.jsonl").read_entries()


class RepairingOnboardingAdapter(FakeOnboardingAdapter):
    def send_message(self, run_id: str, message: str, timeout: float | None = 10) -> ChatReply:
        self.sent_messages.append(message)
        self._state(run_id, "waiting")
        transcript = JsonlTranscriptStore(self.runs_root / run_id / "logs" / "onboarding_chat.jsonl")
        transcript.append(ChatTranscriptEntry(run_id=run_id, role="user", content=message, created_at="2026-05-15T00:00:00+00:00"))
        output_path = self.runs_root / run_id / "output"
        output_path.mkdir(parents=True, exist_ok=True)
        if "Validation failures JSON" in message:
            (output_path / "user_profile.json").write_text(json.dumps(_valid_user_profile()), encoding="utf-8")
            (output_path / "master_cv_profile.json").write_text(json.dumps(_valid_master_cv_profile()), encoding="utf-8")
            (output_path / "policy.json").write_text(json.dumps(_valid_policy()), encoding="utf-8")
            (output_path / "onboarding_review.json").write_text(json.dumps(_valid_onboarding_review(run_id)), encoding="utf-8")
            reply_text = "Repaired onboarding candidate artifacts."
        elif "user_profile.json" in message:
            (output_path / "user_profile.json").write_text('{"schema_version":"1.0"}', encoding="utf-8")
            reply_text = "Wrote invalid draft artifacts."
        else:
            reply_text = "Tell me more about your target roles."
        transcript.append(ChatTranscriptEntry(run_id=run_id, role="assistant", content=reply_text, created_at="2026-05-15T00:00:01+00:00"))
        self._state(run_id, "running")
        return ChatReply(message=reply_text, raw_capture=reply_text, transcript_path=transcript.path)


def test_profile_summary_shows_no_approved_profile_before_onboarding(client):
    response = client.get("/profile/summary")

    assert response.status_code == 200
    assert response.json()["has_approved_profile"] is False
    assert response.json()["approved_user_profile"] is None


def test_onboarding_chat_api_persists_transcript_state_and_imports_candidate_profile(client, runs_root):
    fake_adapter = FakeOnboardingAdapter(runs_root)
    client.app.dependency_overrides[get_onboarding_chat_adapter] = lambda: fake_adapter

    try:
        status = client.get("/onboarding/chat/onboarding-api/status")
        assert status.status_code == 200
        assert status.json()["status"] == "not_started"

        start = client.post("/onboarding/chat/onboarding-api/start")
        assert start.status_code == 200
        assert start.json()["status"] == "attached"
        assert start.json()["session_state"]["status"] == "running"
        assert start.json()["session_state"]["tmux"]["pane_ref"] == "codex:0.0"
        assert "Onboarding Recruiting Agent" in fake_adapter.prepared_workspaces["onboarding-api"]
        assert (runs_root / "onboarding-api" / "workspace" / "AGENTS.md").exists()
        assert fake_adapter.attach_fresh_values == [True]

        start_again = client.post("/onboarding/chat/onboarding-api/start")
        assert start_again.status_code == 200
        assert fake_adapter.attach_fresh_values == [True, False]

        terminal = client.post("/onboarding/chat/onboarding-api/open-terminal")
        assert terminal.status_code == 200
        assert terminal.json()["status"] == "opened"
        assert terminal.json()["command"] == "wsl -d Ubuntu-24.04-bonsai-vllm -- tmux new -A -s codex"

        message = client.post(
            "/onboarding/chat/onboarding-api/messages",
            json={"message": "I want backend roles in Berlin."},
        )
        assert message.status_code == 200
        assert message.json()["reply"] == "Tell me more about your target roles."
        assert message.json()["session_state"]["status"] == "running"

        transcript = client.get("/onboarding/chat/onboarding-api/transcript")
        assert transcript.status_code == 200
        assert [entry["role"] for entry in transcript.json()] == ["user", "assistant"]

        refresh = client.post("/onboarding/chat/onboarding-api/refresh")
        assert refresh.status_code == 200
        assert refresh.json()["reply"] == "Latest visible Codex output."

        close = client.post("/onboarding/chat/onboarding-api/close")
        assert close.status_code == 200
        assert close.json()["session_state"]["status"] == "closed"

        reset = client.post("/onboarding/chat/onboarding-api/reset")
        assert reset.status_code == 200
        assert reset.json()["session_state"]["status"] == "not_started"

        artifacts_before = client.get("/onboarding/chat/onboarding-api/artifacts")
        assert artifacts_before.status_code == 200
        assert {artifact["filename"]: artifact["status"] for artifact in artifacts_before.json()["artifacts"]} == {
            "user_profile.json": "missing",
            "master_cv_profile.json": "missing",
            "policy.json": "missing",
            "onboarding_review.json": "missing",
        }

        uploaded = client.put(
            "/onboarding/chat/onboarding-api/input-files/resume.txt",
            content=b"Resume text for onboarding.",
            headers={"Content-Type": "text/plain"},
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["filename"] == "resume.txt"
        assert (runs_root / "onboarding-api" / "input" / "resume.txt").read_text(encoding="utf-8") == "Resume text for onboarding."

        input_files = client.get("/onboarding/chat/onboarding-api/input-files")
        assert input_files.status_code == 200
        assert input_files.json()["files"][0]["filename"] == "resume.txt"

        finish = client.post("/onboarding/chat/onboarding-api/finish")
        assert finish.status_code == 200
        finish_payload = finish.json()
        assert finish_payload["import_result"]["run"]["status"] == "imported"
        assert {
            result["filename"]: result["status"] for result in finish_payload["import_result"]["results"]
        } == {
            "user_profile.json": "schema_validation_passed",
            "master_cv_profile.json": "schema_validation_passed",
            "policy.json": "schema_validation_passed",
            "onboarding_review.json": "schema_validation_passed",
        }
        assert {artifact["filename"]: artifact["status"] for artifact in finish_payload["artifacts"]} == {
            "user_profile.json": "ready_for_review",
            "master_cv_profile.json": "ready_for_review",
            "policy.json": "ready_for_review",
            "onboarding_review.json": "ready_for_review",
        }

        snapshots = client.get("/onboarding/runs/onboarding-api/snapshots")
        assert snapshots.status_code == 200
        assert {(snapshot["snapshot_type"], snapshot["external_id"], snapshot["status"]) for snapshot in snapshots.json()} == {
            ("user_profile", "profile-onboarding-api", "candidate"),
            ("master_cv_profile", "profile-onboarding-api", "candidate"),
            ("policy", "policy-onboarding-api", "candidate"),
        }

        import_again = client.post("/onboarding/chat/onboarding-api/import-artifacts")
        assert import_again.status_code == 200
        assert import_again.json()["import_result"]["run"]["status"] == "imported"

        summary = client.get("/profile/summary")
        assert summary.status_code == 200
        assert summary.json()["has_approved_profile"] is False
        assert summary.json()["candidate_user_profiles"][0]["external_id"] == "profile-onboarding-api"
    finally:
        client.app.dependency_overrides.pop(get_onboarding_chat_adapter, None)


def test_onboarding_finish_repairs_invalid_artifacts_until_validation_passes(client, runs_root):
    fake_adapter = RepairingOnboardingAdapter(runs_root)
    client.app.dependency_overrides[get_onboarding_chat_adapter] = lambda: fake_adapter

    try:
        start = client.post("/onboarding/chat/onboarding-repair/start")
        assert start.status_code == 200

        finish = client.post("/onboarding/chat/onboarding-repair/finish")

        assert finish.status_code == 200
        payload = finish.json()
        assert payload["import_result"]["run"]["status"] == "imported"
        assert [result["status"] for result in payload["import_result"]["results"]] == [
            "schema_validation_passed",
            "schema_validation_passed",
            "schema_validation_passed",
            "schema_validation_passed",
        ]
        assert len(fake_adapter.sent_messages) == 2
        assert "Validation failures JSON" in fake_adapter.sent_messages[-1]
        assert "missing_expected_file" in fake_adapter.sent_messages[-1]
        assert "schema_validation_failed" in fake_adapter.sent_messages[-1]
        assert "Repaired onboarding candidate artifacts." in payload["reply"]
    finally:
        client.app.dependency_overrides.pop(get_onboarding_chat_adapter, None)
