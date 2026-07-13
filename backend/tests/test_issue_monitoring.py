from __future__ import annotations

import json

from backend.app.core.config import get_settings


def _issues() -> list[dict[str, object]]:
    path = get_settings().issue_log_path
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_browser_issue_endpoint_writes_only_to_the_issue_ledger(client):
    response = client.post(
        "/monitoring/client-errors",
        json={
            "kind": "javascript_error",
            "message": "Rendered component failed",
            "source": "workspace.tsx",
            "stack": "Error: Rendered component failed",
            "url": "http://127.0.0.1:8000/dashboard",
        },
    )

    assert response.status_code == 202
    issue = _issues()[-1]
    assert issue["kind"] == "frontend_javascript_error"
    assert issue["message"] == "Rendered component failed"


def test_backend_5xx_is_written_to_the_issue_ledger(client):
    response = client.get("/auth/google/start")

    assert response.status_code == 503
    issue = _issues()[-1]
    assert issue["kind"] == "backend_http_error"
    assert issue["source"] == "GET /auth/google/start"
