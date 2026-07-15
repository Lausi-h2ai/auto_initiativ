from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import backend.app.agents.company_research_runtime as company_research_runtime
from backend.app.agents.company_research_runtime import CompanyResearchRuntime, contain_path, safe_research_env
from backend.app.core.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        RUNS_ROOT=tmp_path,
        SCHEMAS_ROOT=tmp_path / "schemas",
        PI_RPC_BINARY="pi",
        PI_RPC_RESEARCH_EXTENSION_PATH=Path("backend/pi_extensions/company_research.ts"),
        PI_RPC_RESEARCH_TIMEOUT_SECONDS=34,
    )


def test_company_research_runtime_builds_restricted_pi_command(tmp_path: Path):
    runtime = CompanyResearchRuntime(settings=_settings(tmp_path), clients={}, client_factory=lambda command, cwd, env: None)

    command = runtime._command("run-1")

    assert command[:3] == ["pi", "--mode", "rpc"]
    assert "--extension" in command
    assert "company_research.ts" in str(command)
    assert "--no-builtin-tools" in command
    assert "--no-extensions" in command
    assert "--no-approve" in command
    assert "--no-context-files" in command
    assert "--session-dir" in command
    assert command[command.index("--provider") + 1] == "openai-codex"
    assert command[command.index("--model") + 1] == "gpt-5.6-terra"
    assert command[command.index("--thinking") + 1] == "medium"


def test_safe_research_env_filters_secrets_and_sets_runtime_context(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("GMAIL_TOKEN", "secret")
    monkeypatch.setenv("PATH", "safe-path")

    env = safe_research_env()

    assert env["PATH"] == "safe-path"
    assert "OPENAI_API_KEY" not in env
    assert "GMAIL_TOKEN" not in env
    assert "COMPANY_RESEARCH_REPO_ROOT" in env
    assert "COMPANY_RESEARCH_PYTHON" in env


def test_contain_path_allows_children_and_blocks_escapes(tmp_path: Path):
    root = tmp_path / "run" / "workspace"
    root.mkdir(parents=True)
    child = root / "notes.txt"
    child.write_text("ok", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("no", encoding="utf-8")

    assert contain_path(root, child) == child.resolve()
    with pytest.raises(ValueError):
        contain_path(root, outside)
    with pytest.raises(ValueError):
        contain_path(root, root)


def test_company_research_extension_contains_output_caps_and_blocked_write_guards():
    source = Path("backend/pi_extensions/company_research.ts").read_text(encoding="utf-8")

    assert "MAX_COMMAND_OUTPUT_BYTES" in source
    assert "MAX_COMMAND_TIMEOUT_MS" in source
    assert "assertChildPath(outputRoot, outputPath)" in source
    assert "safeEnv()" in source
    assert "company_research_write_contact" in source


def test_company_research_runtime_closes_client_after_prompt_failure(tmp_path: Path):
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
    runtime = CompanyResearchRuntime(settings=_settings(tmp_path), clients={"run-1": client})
    runtime._mark_run = lambda *args, **kwargs: None

    runtime._run_agent("run-1")

    assert client.closed is True
    assert client.timeout_seconds == pytest.approx(34, abs=0.1)
    assert "run-1" not in runtime.clients
    state = json.loads((run_root / "logs" / "company_research_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "failed"


def test_company_research_runtime_detects_run_orphaned_by_process_restart(tmp_path: Path, monkeypatch):
    runtime = CompanyResearchRuntime(settings=_settings(tmp_path), clients={})
    previous_process_time = datetime.now(timezone.utc) - timedelta(seconds=30)
    monkeypatch.setattr(company_research_runtime, "_PROCESS_STARTED_AT", previous_process_time)

    assert runtime._state_is_stale(
        "run-1",
        {"status": "running", "updated_at": (previous_process_time - timedelta(seconds=1)).isoformat()},
        None,
    )
    assert not runtime._state_is_stale(
        "run-2",
        {"status": "running", "updated_at": (previous_process_time + timedelta(seconds=1)).isoformat()},
        None,
    )


def test_company_research_watcher_imports_stable_artifacts_while_agent_is_running(tmp_path: Path, monkeypatch):
    imports: list[tuple[str, bool, bool]] = []

    class FakeSession:
        def __init__(self, engine) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeRun:
        status = "imported"

    class FakeResult:
        run = FakeRun()
        validation_results = []

    class FakeImportService:
        def __init__(self, *, session, settings) -> None:
            pass

        def import_run(self, run_id: str, *, run_type: str, incremental: bool = False, finalize: bool = True):
            imports.append((run_type, incremental, finalize))
            return FakeResult()

    output = tmp_path / "run-1" / "output" / "companies"
    output.mkdir(parents=True)
    (output / "company-1.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(company_research_runtime, "Session", FakeSession)
    monkeypatch.setattr(company_research_runtime, "RunImportService", FakeImportService)
    monkeypatch.setattr(company_research_runtime, "INCREMENTAL_IMPORT_POLL_SECONDS", 0.01)
    runtime = CompanyResearchRuntime(settings=_settings(tmp_path), clients={})
    runtime._mark_run = lambda *args, **kwargs: None
    stop = threading.Event()
    thread = threading.Thread(
        target=runtime._watch_research_artifacts,
        args=("run-1", "company_research", 50, time.monotonic(), stop),
    )

    thread.start()
    deadline = time.monotonic() + 1
    while not imports and time.monotonic() < deadline:
        time.sleep(0.01)
    stop.set()
    thread.join(timeout=1)

    assert imports == [("company_research", True, False)]


def test_company_research_runtime_cancel_closes_live_client_and_marks_run(tmp_path: Path):
    class Client:
        closed = False

        def close(self) -> None:
            self.closed = True

    client = Client()
    runtime = CompanyResearchRuntime(settings=_settings(tmp_path), clients={"run-1": client})
    marked = []
    runtime._mark_run = lambda run_id, status, **kwargs: marked.append((run_id, status, kwargs))

    assert runtime.cancel("run-1", reason="search_scope_changed") is True
    assert client.closed is True
    assert "run-1" not in runtime.clients
    assert marked[0][0:2] == ("run-1", "research_failed")
    state = json.loads((tmp_path / "run-1" / "logs" / "company_research_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "failed"
    assert state["last_error"] == "search_scope_changed"


def test_company_research_runtime_uses_campaign_time_budget_for_prompt_timeout(tmp_path: Path):
    run_root = tmp_path / "run-1"
    input_root = run_root / "input"
    input_root.mkdir(parents=True)
    (input_root / "campaign.json").write_text(json.dumps({"time_budget_minutes": 2}), encoding="utf-8")
    runtime = CompanyResearchRuntime(settings=_settings(tmp_path), clients={})

    assert runtime._prompt_timeout_seconds("run-1") == 34

    runtime = CompanyResearchRuntime(
        settings=Settings(
            RUNS_ROOT=tmp_path,
            SCHEMAS_ROOT=tmp_path / "schemas",
            PI_RPC_RESEARCH_TIMEOUT_SECONDS=1000,
        ),
        clients={},
    )

    assert runtime._prompt_timeout_seconds("run-1") == 180


def test_company_research_runtime_continues_until_target_company_count(tmp_path: Path, monkeypatch):
    import_counts = []

    class PromptResult:
        def __init__(self, text: str) -> None:
            self.text = text
            self.events = [{"type": "agent_end", "stopReason": "stop"}]

    class ContinuingClient:
        def __init__(self, output_root: Path) -> None:
            self.output_root = output_root
            self.prompts: list[str] = []
            self.closed = False

        def prompt(self, message: str, *, timeout_seconds: float):
            self.prompts.append(message)
            company_index = len(self.prompts)
            company_path = self.output_root / "companies" / f"company-{company_index}.json"
            company_path.write_text("{}", encoding="utf-8")
            return PromptResult(f"completed batch {company_index}")

        def command(self, payload, *, timeout_seconds: float):
            return {}

        def close(self) -> None:
            self.closed = True

    class FakeSession:
        def __init__(self, engine) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeRun:
        status = "imported"

    class FakeImportResult:
        run = FakeRun()
        validation_results = []

    class FakeImportService:
        def __init__(self, *, session, settings) -> None:
            pass

        def import_run(self, run_id: str, *, run_type: str, incremental: bool = False, finalize: bool = True):
            assert incremental is True
            assert finalize is True
            import_counts.append(len(list((output_root / "companies").glob("*.json"))))
            return FakeImportResult()

    run_root = tmp_path / "run-1"
    output_root = run_root / "output"
    (run_root / "input").mkdir(parents=True)
    (output_root / "companies").mkdir(parents=True)
    (output_root / "contacts").mkdir()
    (output_root / "fit_evaluations").mkdir()
    (run_root / "task.md").write_text("# Task", encoding="utf-8")
    (run_root / "instructions.md").write_text("# Instructions", encoding="utf-8")
    (run_root / "input" / "campaign.json").write_text(
        json.dumps({"time_budget_minutes": 2, "max_companies": 2}),
        encoding="utf-8",
    )
    monkeypatch.setattr(company_research_runtime, "Session", FakeSession)
    monkeypatch.setattr(company_research_runtime, "RunImportService", FakeImportService)
    client = ContinuingClient(output_root)
    runtime = CompanyResearchRuntime(settings=_settings(tmp_path), clients={"run-1": client})
    runtime._mark_run = lambda *args, **kwargs: None

    runtime._run_agent("run-1")

    assert len(client.prompts) == 2
    assert "Continue the prepared company research task" in client.prompts[1]
    assert import_counts == [2]
    assert client.closed is True
    state = json.loads((run_root / "logs" / "company_research_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "imported"
    assert state["last_company_count"] == 2
    assert state["target_company_count"] == 2
    assert state["continuation_count"] == 1


def test_company_research_runtime_imports_existing_partial_artifacts_before_prompting(tmp_path: Path, monkeypatch):
    import_counts = []
    mark_statuses = []

    class PromptResult:
        def __init__(self, text: str) -> None:
            self.text = text
            self.events = [{"type": "agent_end", "stopReason": "stop"}]

    class CompletingClient:
        def __init__(self, output_root: Path) -> None:
            self.output_root = output_root
            self.prompts: list[str] = []
            self.closed = False

        def prompt(self, message: str, *, timeout_seconds: float):
            self.prompts.append(message)
            company_path = self.output_root / "companies" / "company-2.json"
            company_path.write_text("{}", encoding="utf-8")
            return PromptResult("completed final company")

        def command(self, payload, *, timeout_seconds: float):
            return {}

        def close(self) -> None:
            self.closed = True

    class FakeSession:
        def __init__(self, engine) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeRun:
        status = "imported"

    class FakeImportResult:
        run = FakeRun()
        validation_results = []

    class FakeImportService:
        def __init__(self, *, session, settings) -> None:
            pass

        def import_run(self, run_id: str, *, run_type: str, incremental: bool = False, finalize: bool = True):
            assert incremental is True
            assert finalize is (len(list((output_root / "companies").glob("*.json"))) == 2)
            import_counts.append(len(list((output_root / "companies").glob("*.json"))))
            return FakeImportResult()

    run_root = tmp_path / "run-1"
    output_root = run_root / "output"
    (run_root / "input").mkdir(parents=True)
    (output_root / "companies").mkdir(parents=True)
    (output_root / "contacts").mkdir()
    (output_root / "fit_evaluations").mkdir()
    (run_root / "task.md").write_text("# Task", encoding="utf-8")
    (run_root / "instructions.md").write_text("# Instructions", encoding="utf-8")
    (run_root / "input" / "campaign.json").write_text(
        json.dumps({"time_budget_minutes": 2, "max_companies": 2}),
        encoding="utf-8",
    )
    (output_root / "companies" / "company-1.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(company_research_runtime, "Session", FakeSession)
    monkeypatch.setattr(company_research_runtime, "RunImportService", FakeImportService)
    client = CompletingClient(output_root)
    runtime = CompanyResearchRuntime(settings=_settings(tmp_path), clients={"run-1": client})
    runtime._mark_run = lambda run_id, status, **kwargs: mark_statuses.append(status)

    runtime._run_agent("run-1")

    assert import_counts == [1, 2]
    assert mark_statuses[:1] == ["research_running"]
    assert client.prompts == [runtime._prompt("run-1")]
    assert client.closed is True
    state = json.loads((run_root / "logs" / "company_research_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "imported"
    assert state["last_company_count"] == 2
    assert state["target_company_count"] == 2


def test_company_research_runtime_imports_existing_artifacts_without_prompting(tmp_path: Path, monkeypatch):
    class FakeSession:
        def __init__(self, engine) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeRun:
        status = "imported"

    class FakeImportResult:
        run = FakeRun()
        validation_results = []

    class FakeImportService:
        def __init__(self, *, session, settings) -> None:
            pass

        def import_run(self, run_id: str, *, run_type: str, incremental: bool = False, finalize: bool = True):
            assert incremental is True
            assert finalize is True
            return FakeImportResult()

    run_root = tmp_path / "run-1"
    output_root = run_root / "output"
    (run_root / "input").mkdir(parents=True)
    (output_root / "companies").mkdir(parents=True)
    (output_root / "contacts").mkdir()
    (output_root / "fit_evaluations").mkdir()
    (run_root / "input" / "campaign.json").write_text(
        json.dumps({"time_budget_minutes": 2, "max_companies": 2}),
        encoding="utf-8",
    )
    for index in range(2):
        (output_root / "companies" / f"company-{index}.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(company_research_runtime, "Session", FakeSession)
    monkeypatch.setattr(company_research_runtime, "RunImportService", FakeImportService)
    runtime = CompanyResearchRuntime(
        settings=_settings(tmp_path),
        clients={},
        client_factory=lambda command, cwd, env: (_ for _ in ()).throw(AssertionError("client should not start")),
    )
    runtime._mark_run = lambda *args, **kwargs: None

    runtime._run_agent("run-1")

    state = json.loads((run_root / "logs" / "company_research_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "imported"
    assert state["last_company_count"] == 2
    assert state["target_company_count"] == 2
    assert state["last_reply"].startswith("Skipped company research prompt")
