"""Safe, application-owned adapters for the vendored resume designs.

The upstream HTML files are design references and deliberately remain unchanged.
They contain example people, so the application must never render them directly.
This module reuses their CSS, normalizes the page to A4, and supplies an empty,
structured document shell for validated Master CV content.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from types import MappingProxyType


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_UPSTREAM_ROOT = (
    _REPOSITORY_ROOT / "third_party" / "yanliudesign-resume-builder-skill"
).resolve()
_UPSTREAM_TEMPLATE_ROOT = (_UPSTREAM_ROOT / "templates").resolve()

_STYLE_PATTERN = re.compile(r"<style(?P<attrs>[^>]*)>(?P<css>.*?)</style>", re.I | re.S)
_LETTER_SIZE_PATTERN = re.compile(r"(?P<prefix>size\s*:\s*)letter\b", re.I)
_LETTER_WIDTH_PATTERN = re.compile(r"(?P<prefix>width\s*:\s*)8\.5in\b", re.I)
_LETTER_HEIGHT_PATTERN = re.compile(r"(?P<prefix>min-height\s*:\s*)11in\b", re.I)


@dataclass(frozen=True, slots=True)
class MasterCvTemplate:
    """Metadata used by the gallery, renderer, and deterministic policy checks."""

    template_id: str
    name: str
    description: str
    ats_compatibility: str
    density: str
    markets: tuple[str, ...]
    supports_photo: bool = True
    native_photo_layout: bool = False
    page_size: str = "A4"
    template_version: str = "1.0"
    supported_pages: tuple[int, ...] = (1, 2)
    supported_locales: tuple[str, ...] = ("de-DE", "de-CH", "en-CH", "en")
    role_families: tuple[str, ...] = ("general",)

    @property
    def portrait_placement(self) -> str:
        if self.template_id == "photo-corporate":
            return "banner_overlap"
        if self.template_id in {"modern-sidebar", "tech-compact"}:
            return "sidebar"
        return "header_right"

    @property
    def layout(self) -> str:
        if self.template_id in {"modern-sidebar", "photo-corporate", "tech-compact"}:
            return "sidebar"
        if self.template_id in {"pillar", "swiss"}:
            return "two_column"
        if self.template_id == "timeline":
            return "timeline"
        if self.template_id in {"atelier", "editorial-banner", "photo-minimal"}:
            return "editorial"
        return "single_column"

    @property
    def upstream_filename(self) -> str:
        return f"{self.template_id}.html"

    @property
    def upstream_relative_path(self) -> str:
        return f"templates/{self.upstream_filename}"


MASTER_CV_TEMPLATES: tuple[MasterCvTemplate, ...] = (
    MasterCvTemplate(
        "classic-ats", "Classic ATS", "Traditional single-column layout with maximum parser clarity.",
        "high", "balanced", ("international", "germany", "switzerland"),
    ),
    MasterCvTemplate(
        "atelier", "Atelier", "Editorial typography for creative and design-oriented profiles.",
        "medium", "balanced", ("international", "germany", "switzerland"),
    ),
    MasterCvTemplate(
        "editorial-banner", "Editorial Banner", "Distinctive banner and balanced editorial sections.",
        "medium", "balanced", ("international", "germany", "switzerland"),
    ),
    MasterCvTemplate(
        "elegant-serif", "Elegant Serif", "Refined serif treatment for experienced professional profiles.",
        "high", "balanced", ("international", "germany", "switzerland"),
    ),
    MasterCvTemplate(
        "executive", "Executive", "Structured leadership-focused layout with restrained visual hierarchy.",
        "high", "balanced", ("international", "germany", "switzerland"),
    ),
    MasterCvTemplate(
        "ledger", "Ledger", "Compact, precise layout for finance and operations experience.",
        "high", "compact", ("international", "germany", "switzerland"),
    ),
    MasterCvTemplate(
        "modern-sidebar", "Modern Sidebar", "Two-column modern layout with quick-scan supporting details.",
        "medium", "compact", ("international", "germany", "switzerland"),
    ),
    MasterCvTemplate(
        "photo-corporate", "Photo Corporate", "Corporate banner with a prominent circular portrait.",
        "medium", "balanced", ("germany", "switzerland", "international"),
        native_photo_layout=True,
    ),
    MasterCvTemplate(
        "photo-minimal", "Photo Minimal", "Minimal editorial composition with a dedicated portrait area.",
        "medium", "balanced", ("germany", "switzerland", "international"),
        native_photo_layout=True,
    ),
    MasterCvTemplate(
        "pillar", "Pillar", "Strong section pillars for achievement-led professional histories.",
        "medium", "compact", ("international", "germany", "switzerland"),
    ),
    MasterCvTemplate(
        "swiss", "Swiss", "Grid-led Swiss typography with clear information hierarchy.",
        "medium", "balanced", ("switzerland", "germany", "international"),
    ),
    MasterCvTemplate(
        "tech-compact", "Tech Compact", "Dense engineering layout optimized for technical evidence.",
        "high", "compact", ("international", "germany", "switzerland"),
    ),
    MasterCvTemplate(
        "timeline", "Timeline", "Chronological visual narrative for progressive career histories.",
        "medium", "compact", ("international", "germany", "switzerland"),
    ),
)

_TEMPLATES_BY_ID = MappingProxyType(
    {template.template_id: template for template in MASTER_CV_TEMPLATES}
)


def get_master_cv_template(template_id: str) -> MasterCvTemplate:
    """Return catalog metadata without accepting filesystem paths from callers."""

    try:
        return _TEMPLATES_BY_ID[template_id]
    except KeyError as exc:
        raise ValueError(f"Unknown Master CV template: {template_id!r}") from exc


def upstream_template_path(template_id: str) -> Path:
    """Resolve a catalog-owned upstream path and reject traversal or symlinks out."""

    template = get_master_cv_template(template_id)
    path = (_UPSTREAM_TEMPLATE_ROOT / template.upstream_filename).resolve(strict=True)
    if path.parent != _UPSTREAM_TEMPLATE_ROOT or path.suffix.lower() != ".html":
        raise ValueError("Master CV template path escaped the vendored template directory")
    return path


def upstream_skill_path() -> Path:
    """Return the pinned upstream skill instructions for agent workspace assembly."""

    path = (_UPSTREAM_ROOT / "SKILL.md").resolve(strict=True)
    if path.parent != _UPSTREAM_ROOT:
        raise ValueError("Upstream skill path escaped the vendored directory")
    return path


def upstream_prompt_path(prompt_name: str) -> Path:
    """Return one of the fixed upstream prompts; arbitrary relative paths are invalid."""

    allowed = {"beautify", "editable-version", "interview", "linkedin-import"}
    if prompt_name not in allowed:
        raise ValueError(f"Unknown upstream resume prompt: {prompt_name!r}")
    root = (_UPSTREAM_ROOT / "prompts").resolve()
    path = (root / f"{prompt_name}.md").resolve(strict=True)
    if path.parent != root:
        raise ValueError("Upstream prompt path escaped the vendored directory")
    return path


def _a4_css(upstream_html: str) -> str:
    match = _STYLE_PATTERN.search(upstream_html)
    if not match:
        raise ValueError("Vendored Master CV template has no style block")
    css = _LETTER_SIZE_PATTERN.sub(r"\g<prefix>A4", match.group("css"))
    css = _LETTER_WIDTH_PATTERN.sub(r"\g<prefix>210mm", css)
    css = _LETTER_HEIGHT_PATTERN.sub(r"\g<prefix>297mm", css)
    return css


_APP_SHELL_CSS = """
  @page { size: A4; margin: 0; }
  html, body { width: 210mm; min-height: 297mm; }
  .page { width: 210mm !important; min-height: 297mm !important; }
  .master-cv-portrait { width: 34mm; height: 42mm; overflow: hidden; }
  .master-cv-portrait img { width: 100%; height: 100%; object-fit: cover; }
  [data-master-cv-portrait="absent"] { display: none; }
"""


_EMPTY_DOCUMENT_SHELL = """<div class="page" data-master-cv-document>
  <header data-master-cv-block="identity">
    <div class="master-cv-portrait" data-master-cv-portrait="absent" data-slot="portrait"></div>
    <h1 data-field="identity.full_name"></h1>
    <div class="headline" data-field="identity.headline"></div>
    <div class="contact" data-field="identity.contact"></div>
  </header>
  <main>
    <section data-master-cv-block="summary">
      <h2 data-label="summary"></h2>
      <p class="summary" data-field="summary"></p>
    </section>
    <section data-master-cv-block="experience">
      <h2 data-label="experience"></h2>
      <div data-collection="experience"></div>
    </section>
    <section data-master-cv-block="education">
      <h2 data-label="education"></h2>
      <div data-collection="education"></div>
    </section>
    <section data-master-cv-block="skills">
      <h2 data-label="skills"></h2>
      <div data-collection="skills"></div>
    </section>
    <section data-master-cv-block="languages">
      <h2 data-label="languages"></h2>
      <div data-collection="languages"></div>
    </section>
  </main>
</div>"""


def adapted_template_html(template_id: str) -> str:
    """Build a sample-free A4 shell while retaining the selected upstream CSS.

    The result contains only empty, machine-addressable fields. Validated profile
    data and an approved portrait are inserted later by the deterministic renderer;
    callers cannot provide HTML, paths, URLs, or a portrait source here.
    """

    template = get_master_cv_template(template_id)
    upstream_html = upstream_template_path(template_id).read_text(encoding="utf-8")
    css = _a4_css(upstream_html)
    return (
        "<!doctype html>\n"
        f'<html lang="en" data-master-cv-template="{template.template_id}">\n'
        "<head>\n<meta charset=\"utf-8\">\n"
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{template.name}</title>\n<style>\n{css}\n{_APP_SHELL_CSS}\n</style>\n"
        f"</head>\n<body>\n{_EMPTY_DOCUMENT_SHELL}\n</body>\n</html>\n"
    )
