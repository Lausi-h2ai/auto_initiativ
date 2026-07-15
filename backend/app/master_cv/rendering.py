from __future__ import annotations

from html import escape

from backend.app.master_cv.contracts import MasterCvDocument
from backend.app.master_cv.templates import adapted_template_html, get_master_cv_template


def render_master_cv_html(document: MasterCvDocument, *, portrait_data_uri: str | None = None) -> str:
    """Render validated structured content into an application-owned A4 shell."""

    get_master_cv_template(document.design.template_id)
    if portrait_data_uri is not None and not portrait_data_uri.startswith("data:image/jpeg;base64,"):
        raise ValueError("Only a verified application-owned JPEG portrait may be rendered")

    shell = adapted_template_html(document.design.template_id)
    accent = document.design.accent_color or "#245b52"
    density = document.design.density
    header_blocks = next((section.blocks for section in document.sections if section.type == "header"), [])
    header_text = [block.text for block in header_blocks if block.visible]
    name = header_text[0] if header_text else document.title
    subtitle = header_text[1] if len(header_text) > 1 else ""
    contact = " | ".join(header_text[2:])

    portrait = ""
    if document.design.photo.enabled and portrait_data_uri:
        portrait = (
            '<div class="master-cv-portrait" data-master-cv-portrait="present">'
            f'<img src="{portrait_data_uri}" alt="Candidate portrait" data-tailoring-required="true">'
            "</div>"
        )

    header = (
        '<header class="master-cv-generated-header" data-master-cv-block="identity">'
        f"{portrait}<div><h1>{escape(name)}</h1>"
        f'<div class="headline">{escape(subtitle)}</div>'
        f'<div class="contact">{escape(contact)}</div></div></header>'
    )
    sections: list[str] = []
    for section in document.sections:
        if section.type == "header":
            continue
        blocks = []
        for block in section.blocks:
            if not block.visible:
                continue
            claim_attr = escape(",".join(block.claim_refs), quote=True)
            tag = "li" if block.kind in {"bullet", "skill"} else "div"
            blocks.append(
                f'<{tag} class="master-cv-block master-cv-{escape(block.kind)}" '
                f'data-block-id="{escape(block.block_id, quote=True)}" data-claim-refs="{claim_attr}">'
                f"{escape(block.text)}</{tag}>"
            )
        if not blocks:
            continue
        body_tag = "ul" if all(block.kind in {"bullet", "skill"} for block in section.blocks if block.visible) else "div"
        sections.append(
            f'<section data-section-id="{escape(section.section_id, quote=True)}">'
            f"<h2>{escape(section.title)}</h2><{body_tag}>" + "".join(blocks) + f"</{body_tag}></section>"
        )

    generated = f'<div class="page master-cv-density-{density}" data-master-cv-document>{header}<main>{"".join(sections)}</main></div>'
    start = shell.index('<div class="page" data-master-cv-document>')
    end = shell.index("</body>")
    shell = shell[:start] + generated + "\n" + shell[end:]
    additions = f"""
<style>
:root {{ --master-cv-accent: {accent}; }}
.master-cv-generated-header {{ display:flex; align-items:flex-start; gap:8mm; margin-bottom:7mm; }}
.master-cv-generated-header h1 {{ margin:0; }}
.master-cv-generated-header .contact {{ margin-top:2mm; }}
.master-cv-generated-header .master-cv-portrait {{ flex:0 0 auto; }}
.master-cv-generated-header .master-cv-portrait img {{ display:block; }}
.master-cv-block {{ white-space:pre-line; margin:0 0 2.2mm; }}
.master-cv-density-compact .master-cv-block {{ margin-bottom:1mm; }}
.master-cv-density-airy .master-cv-block {{ margin-bottom:3.2mm; }}
h2 {{ color:var(--master-cv-accent); }}
</style>
"""
    return shell.replace("</head>", additions + "</head>")
