from __future__ import annotations

from backend.app.agents.master_cv_builder_prompt import build_master_cv_builder_instructions
from backend.app.agents.onboarding_recruiter_prompt import build_onboarding_agent_instructions
from backend.app.localization import normalize_locale, output_language_contract


def test_locale_normalization_is_allowlisted() -> None:
    assert normalize_locale("de") == "de-DE"
    assert normalize_locale("de-CH") == "de-DE"
    assert normalize_locale("en-US") == "en"
    assert normalize_locale("fr") == "en"


def test_german_output_contract_preserves_source_and_machine_identifiers() -> None:
    contract = output_language_contract("de-DE")
    assert "idiomatic German" in contract
    assert "professional Du tone" in contract
    assert "external source material in their original language" in contract
    assert "JSON keys" in contract


def test_interactive_agent_prompts_receive_german_visible_output_contract(tmp_path) -> None:
    onboarding = build_onboarding_agent_instructions(
        run_id="onboarding-de",
        runs_root=tmp_path,
        schemas_root=tmp_path,
        output_locale="de-DE",
    )
    master_cv = build_master_cv_builder_instructions(
        run_id="master-cv-de",
        profile={},
        template_catalog=[],
        output_locale="de-DE",
    )
    assert "professional Du tone" in onboarding
    assert "professional Du tone" in master_cv


def test_workspace_locale_can_be_updated_and_is_returned_by_me(client) -> None:
    registration = client.post(
        "/auth/local/register",
        json={"display_name": "German User", "email": "german-user@example.com", "locale": "en"},
    )
    assert registration.status_code == 201
    me = client.get("/me")
    assert me.status_code == 200
    assert me.json()["workspace"]["locale"] == "en"
    response = client.patch(
        "/workspace/preferences",
        headers={"X-CSRF-Token": me.json()["csrf_token"]},
        json={"locale": "de-DE"},
    )
    assert response.status_code == 200
    assert response.json() == {"locale": "de-DE"}
    assert client.get("/me").json()["workspace"]["locale"] == "de-DE"


def test_workspace_locale_rejects_unsupported_values(client) -> None:
    registration = client.post(
        "/auth/local/register",
        json={"display_name": "Locale User", "email": "locale-user@example.com", "locale": "en"},
    )
    assert registration.status_code == 201
    me = client.get("/me").json()
    response = client.patch(
        "/workspace/preferences",
        headers={"X-CSRF-Token": me["csrf_token"]},
        json={"locale": "fr"},
    )
    assert response.status_code == 422
