from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.master_cv.templates import (
    MASTER_CV_TEMPLATES,
    adapted_template_html,
    get_master_cv_template,
    upstream_prompt_path,
    upstream_skill_path,
    upstream_template_path,
)


EXPECTED_TEMPLATE_IDS = {
    "atelier",
    "classic-ats",
    "editorial-banner",
    "elegant-serif",
    "executive",
    "ledger",
    "modern-sidebar",
    "photo-corporate",
    "photo-minimal",
    "pillar",
    "swiss",
    "tech-compact",
    "timeline",
}


def test_catalog_exposes_every_vendored_template_with_design_metadata() -> None:
    assert {template.template_id for template in MASTER_CV_TEMPLATES} == EXPECTED_TEMPLATE_IDS
    assert len(MASTER_CV_TEMPLATES) == len(EXPECTED_TEMPLATE_IDS)
    for template in MASTER_CV_TEMPLATES:
        assert template.page_size == "A4"
        assert template.ats_compatibility in {"high", "medium", "low"}
        assert template.density in {"comfortable", "compact"}
        assert template.supports_photo is True
        assert "international" in template.markets
        assert upstream_template_path(template.template_id).is_file()


def test_photo_first_templates_are_identified() -> None:
    native = {item.template_id for item in MASTER_CV_TEMPLATES if item.native_photo_layout}
    assert native == {"photo-corporate", "photo-minimal"}
    assert get_master_cv_template("swiss").markets[0] == "switzerland"


@pytest.mark.parametrize("template_id", sorted(EXPECTED_TEMPLATE_IDS))
def test_adapter_is_a4_structured_and_contains_no_upstream_sample_facts(
    template_id: str,
) -> None:
    html = adapted_template_html(template_id)
    lowered = html.lower()

    assert '@page { size: a4' in lowered
    assert 'width: 210mm' in lowered
    assert 'min-height: 297mm' in lowered
    assert 'data-slot="portrait"' in lowered
    assert 'data-collection="experience"' in lowered
    assert "8.5in" not in lowered
    assert "11in" not in lowered
    for upstream_example in (
        "jordan ellis",
        "lorna alvarado",
        "acme payments",
        "wardiere university",
        "san francisco, ca",
        "hello@example.com",
    ):
        assert upstream_example not in lowered


def test_catalog_lookups_reject_paths_and_unknown_resources() -> None:
    with pytest.raises(ValueError):
        get_master_cv_template("../classic-ats")
    with pytest.raises(ValueError):
        upstream_prompt_path("../interview")


def test_vendored_skill_prompts_and_license_are_present() -> None:
    skill = upstream_skill_path()
    assert skill.is_file()
    assert upstream_prompt_path("interview").is_file()
    assert (skill.parent / "LICENSE").is_file()
    assert (skill.parent / "schema" / "resume-data.md").is_file()
    assert (skill.parent / "guides" / "writing-tips.md").is_file()
    assert len(list((skill.parent / "docs" / "templates").glob("*.png"))) == 13


def test_upstream_metadata_pins_commit_and_preserves_attribution() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    metadata = (
        repository_root / "third_party" / "yanliudesign-resume-builder-skill.UPSTREAM.md"
    ).read_text(encoding="utf-8")
    assert "d981165a8c8801bb9c83aa68ff41cae4d03e0f58" in metadata
    assert "MIT" in metadata
