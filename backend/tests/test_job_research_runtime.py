from __future__ import annotations

import json
from pathlib import Path

import backend.app.agents.company_research_runtime as company_research_runtime
import backend.app.agents.job_research_runtime as job_research_runtime
from backend.app.agents.job_research_runtime import JobResearchRuntime
from backend.app.core.config import Settings


def test_job_research_continues_until_requested_breadth(tmp_path: Path, monkeypatch):
    prompts: list[str] = []
    import_counts: list[int] = []

    class PromptResult:
        text = "batch complete"
        events = [{"type": "agent_end", "stopReason": "stop"}]

    class Client:
        def __init__(self, output_root: Path) -> None:
            self.output_root = output_root
            self.closed = False

        def prompt(self, message: str, *, timeout_seconds: float):
            prompts.append(message)
            index = len(prompts)
            (self.output_root / "jobs" / f"job-{index}.json").write_text("{}", encoding="utf-8")
            (self.output_root / "job_fit_evaluations" / f"fit-{index}.json").write_text("{}", encoding="utf-8")
            return PromptResult()

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

        def import_run(self, run_id: str, *, run_type: str, incremental: bool = False):
            assert run_type == "job_research"
            assert incremental is True
            import_counts.append(len(list((output_root / "jobs").glob("*.json"))))
            return FakeImportResult()

    run_root = tmp_path / "run-1"
    output_root = run_root / "output"
    (run_root / "input").mkdir(parents=True)
    (output_root / "companies").mkdir(parents=True)
    (output_root / "jobs").mkdir()
    (output_root / "job_fit_evaluations").mkdir()
    (run_root / "task.md").write_text("# Task", encoding="utf-8")
    (run_root / "instructions.md").write_text("# Instructions", encoding="utf-8")
    (run_root / "input" / "campaign.json").write_text(
        json.dumps({"time_budget_minutes": 2, "max_jobs": 2}),
        encoding="utf-8",
    )
    monkeypatch.setattr(company_research_runtime, "Session", FakeSession)
    monkeypatch.setattr(job_research_runtime, "Session", FakeSession)
    monkeypatch.setattr(job_research_runtime, "RunImportService", FakeImportService)
    client = Client(output_root)
    runtime = JobResearchRuntime(
        settings=Settings(
            RUNS_ROOT=tmp_path,
            SCHEMAS_ROOT=tmp_path / "schemas",
            PI_RPC_RESEARCH_TIMEOUT_SECONDS=34,
        ),
        clients={"run-1": client},
    )
    runtime._mark_run = lambda *args, **kwargs: None

    runtime._run_agent("run-1")

    assert len(prompts) == 2
    assert "previous reply stopped before the requested breadth was met" in prompts[1]
    assert import_counts == [2]
    assert client.closed is True
    state = json.loads((run_root / "logs" / "company_research_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "imported"
    assert state["target_job_count"] == 2
    assert state["continuation_count"] == 1
