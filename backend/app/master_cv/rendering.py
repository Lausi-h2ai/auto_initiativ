from __future__ import annotations

from html import escape

from backend.app.master_cv.contracts import MasterCvDocument
from backend.app.master_cv.templates import adapted_template_html, get_master_cv_template


_TEMPLATE_STYLES: dict[str, str] = {
    "classic-ats": """
      .page[data-master-cv-document] { background:#fff; padding:15mm 17mm !important; font-family:Georgia,'Times New Roman',serif; }
      .master-cv-generated-header { justify-content:center; text-align:center; border-bottom:1.5px solid #222; padding-bottom:4mm; }
      main { display:block; } section { margin-bottom:4mm; } section h2 { border-bottom:1px solid #999; padding-bottom:1mm; }
    """,
    "atelier": """
      .page[data-master-cv-document] { background:#f6f0e4; padding:17mm 18mm 15mm 25mm !important; border-left:8mm solid var(--master-cv-accent); font-family:Georgia,'Times New Roman',serif; }
      .master-cv-generated-header { border-bottom:0; padding-bottom:5mm; } .master-cv-generated-header h1 { font-size:31pt; font-weight:400; font-style:italic; }
      main { display:grid; grid-template-columns:1fr 1fr; gap:5mm 10mm; } main section:first-child { grid-column:1 / -1; }
      section h2 { border:0; font-size:8.5pt; letter-spacing:3px; } .master-cv-block { border-top:1px solid #cabda8; padding-top:2mm; }
    """,
    "editorial-banner": """
      .page[data-master-cv-document] { background:#faf5ea; padding:0 !important; font-family:Georgia,'Times New Roman',serif; }
      .master-cv-generated-header { background:var(--master-cv-accent); color:#fffaf0; padding:15mm 17mm 10mm; margin:0 0 9mm !important; align-items:flex-end; }
      .master-cv-generated-header h1 { font-size:34pt; line-height:1; } .master-cv-generated-header .headline,.master-cv-generated-header .contact { color:inherit; }
      main { padding:0 17mm 14mm; display:grid; grid-template-columns:1fr 1fr 1fr; gap:7mm; }
      main section { border-top:2px solid var(--master-cv-accent); padding-top:3mm; } main section:first-child { grid-column:1 / -1; }
      section h2 { border:0; font-size:8pt; letter-spacing:3px; }
    """,
    "elegant-serif": """
      .page[data-master-cv-document] { background:#fffdf9; padding:18mm 20mm !important; font-family:'Palatino Linotype',Palatino,Georgia,serif; color:#302b27; }
      .master-cv-generated-header { justify-content:center; text-align:center; border-top:1px solid #9c8973; border-bottom:1px solid #9c8973; padding:7mm 0; }
      .master-cv-generated-header h1 { font-size:29pt; font-weight:400; letter-spacing:1px; }
      main { display:block; } section { margin:6mm 0; } section h2 { text-align:center; font-weight:400; letter-spacing:4px; border:0; }
    """,
    "executive": """
      .page[data-master-cv-document] { background:#fff; padding:13mm 16mm !important; font-family:Arial,Helvetica,sans-serif; border-top:7mm solid #172d42; }
      .master-cv-generated-header { border-bottom:3px solid #172d42; padding:3mm 0 6mm; } .master-cv-generated-header h1 { color:#172d42; font-size:28pt; text-transform:uppercase; letter-spacing:2px; }
      main { display:block; } section h2 { color:#fff !important; background:#172d42; padding:2mm 3mm; border:0; font-size:9pt; } .master-cv-block { padding-left:2mm; }
    """,
    "ledger": """
      .page[data-master-cv-document] { background:#f8f8f4; padding:14mm 15mm !important; font-family:'Courier New',monospace; color:#202521; }
      .master-cv-generated-header { border:2px solid #202521; padding:5mm; box-shadow:4px 4px 0 var(--master-cv-accent); }
      .master-cv-generated-header h1 { font-size:24pt; text-transform:uppercase; } main { display:grid; grid-template-columns:1fr 1fr; gap:5mm 8mm; }
      main section:first-child { grid-column:1 / -1; } section { border:1px solid #9da59f; padding:3mm; margin:0; } section h2 { border-bottom:1px dashed #68716b; padding-bottom:2mm; }
    """,
    "modern-sidebar": """
      .page[data-master-cv-document] { background:linear-gradient(90deg,#173f38 0 58mm,#fff 58mm); padding:13mm 14mm 14mm 68mm !important; font-family:Arial,Helvetica,sans-serif; }
      .master-cv-generated-header { min-height:35mm; border-bottom:4px solid var(--master-cv-accent); } .master-cv-generated-header h1 { font-size:27pt; color:#173f38; }
      main { display:grid; grid-template-columns:1fr 1fr; gap:5mm 8mm; } main section:first-child { grid-column:1 / -1; }
      section h2 { border:0; border-left:4px solid var(--master-cv-accent); padding-left:3mm; }
    """,
    "photo-corporate": """
      .page[data-master-cv-document] { background:#fff; padding:0 16mm 14mm !important; font-family:Arial,Helvetica,sans-serif; }
      .master-cv-generated-header { margin:0 -16mm 10mm !important; padding:14mm 16mm 11mm; background:#153d34; color:#fff; min-height:52mm; align-items:center; }
      .master-cv-generated-header h1 { font-size:30pt; } .master-cv-generated-header .headline,.master-cv-generated-header .contact { color:#dce8e3; }
      .master-cv-portrait { border-radius:50%; border:3px solid #fff; width:38mm; height:38mm; }
      main { display:grid; grid-template-columns:1.4fr .8fr; gap:7mm 10mm; } main section:first-child { grid-column:1 / -1; }
      section h2 { border-bottom:2px solid var(--master-cv-accent); }
    """,
    "photo-minimal": """
      .page[data-master-cv-document] { background:#fbfaf7; padding:18mm 20mm !important; font-family:'Helvetica Neue',Arial,sans-serif; color:#333; }
      .master-cv-generated-header { flex-direction:row-reverse; justify-content:space-between; border:0; margin-bottom:12mm !important; }
      .master-cv-generated-header h1 { font-size:25pt; font-weight:300; letter-spacing:2px; } .master-cv-portrait { width:30mm; height:38mm; border-radius:2px; }
      main { display:block; max-width:155mm; } section { display:grid; grid-template-columns:38mm 1fr; gap:7mm; border-top:1px solid #d8d3cb; padding-top:4mm; }
      section h2 { border:0; font-size:8pt; letter-spacing:2px; }
    """,
    "pillar": """
      .page[data-master-cv-document] { background:#fff; padding:14mm 15mm !important; font-family:Arial,Helvetica,sans-serif; }
      .master-cv-generated-header { background:#e9efe9; padding:7mm; border-left:8px solid var(--master-cv-accent); }
      .master-cv-generated-header h1 { font-size:28pt; color:#173f38; } main { display:grid; grid-template-columns:1fr 1fr; gap:6mm; }
      main section { border-left:7px solid var(--master-cv-accent); background:#f5f7f3; padding:4mm; margin:0; } main section:first-child { grid-column:1 / -1; }
      section h2 { border:0; color:#173f38 !important; }
    """,
    "swiss": """
      .page[data-master-cv-document] { background:#fff; padding:12mm 14mm !important; font-family:Helvetica,Arial,sans-serif; color:#111; border-top:10mm solid #e5392d; }
      .master-cv-generated-header { display:grid; grid-template-columns:2fr 1fr; border-bottom:5px solid #111; padding-bottom:7mm; }
      .master-cv-generated-header h1 { font-size:32pt; line-height:.95; text-transform:uppercase; letter-spacing:-1px; }
      main { display:grid; grid-template-columns:42mm 1fr; gap:0 8mm; } section { display:contents; } section h2 { border-top:2px solid #111; padding-top:3mm; margin-top:4mm; font-size:8pt; color:#111 !important; }
      section > div, section > ul { border-top:1px solid #aaa; padding-top:3mm; margin-top:4mm; }
    """,
    "tech-compact": """
      .page[data-master-cv-document] { background:#f4f7f6; padding:11mm 13mm !important; font-family:'Segoe UI',Arial,sans-serif; font-size:9pt; }
      .master-cv-generated-header { background:#10241f; color:#ecfff8; padding:7mm; border-bottom:4px solid #27b07d; }
      .master-cv-generated-header h1 { font-family:Consolas,'Courier New',monospace; font-size:25pt; } .master-cv-generated-header .headline,.master-cv-generated-header .contact { color:#bce2d5; }
      main { display:grid; grid-template-columns:1.25fr .75fr; gap:4mm 7mm; } main section:first-child { grid-column:1 / -1; }
      section { background:#fff; padding:3mm; margin:0; border:1px solid #d4dfdb; } section h2 { border:0; font-family:Consolas,'Courier New',monospace; font-size:8pt; }
    """,
    "timeline": """
      .page[data-master-cv-document] { background:#fffdf8; padding:15mm 18mm !important; font-family:Arial,Helvetica,sans-serif; }
      .master-cv-generated-header { border-bottom:2px solid var(--master-cv-accent); padding-bottom:7mm; } .master-cv-generated-header h1 { font-size:29pt; }
      main { margin-left:9mm; border-left:3px solid var(--master-cv-accent); padding-left:10mm; } section { position:relative; margin-bottom:6mm; }
      section::before { content:''; position:absolute; width:4mm; height:4mm; border-radius:50%; background:var(--master-cv-accent); left:-12.2mm; top:1mm; border:1mm solid #fffdf8; }
      section h2 { border:0; font-size:9pt; letter-spacing:2px; }
    """,
}


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

    generated = (
        f'<div class="page master-cv-density-{density} master-cv-template-{document.design.template_id}" '
        f'data-master-cv-document data-master-cv-layout="{get_master_cv_template(document.design.template_id).layout}">'
        f'{header}<main>{"".join(sections)}</main></div>'
    )
    start = shell.index('<div class="page" data-master-cv-document>')
    end = shell.index("</body>")
    shell = shell[:start] + generated + "\n" + shell[end:]
    additions = f"""
<style>
:root {{ --master-cv-accent: {accent}; }}
.page[data-master-cv-document], .page[data-master-cv-document] * {{ box-sizing:border-box; }}
html, body {{ width:210mm !important; min-height:297mm; margin:0 !important; overflow-x:hidden; }}
.page[data-master-cv-document] {{ width:210mm !important; min-height:297mm !important; margin:0 !important; display:block; line-height:1.45; }}
.master-cv-generated-header {{ display:flex; align-items:flex-start; gap:8mm; margin-bottom:7mm; }}
.master-cv-generated-header h1 {{ margin:0; }}
.master-cv-generated-header .contact {{ margin-top:2mm; }}
.master-cv-generated-header .master-cv-portrait {{ flex:0 0 auto; }}
.master-cv-generated-header .master-cv-portrait img {{ display:block; }}
.master-cv-block {{ white-space:pre-line; margin:0 0 2.2mm; }}
.master-cv-density-compact .master-cv-block {{ margin-bottom:1mm; }}
.master-cv-density-airy .master-cv-block {{ margin-bottom:3.2mm; }}
h2 {{ color:var(--master-cv-accent); }}
{_TEMPLATE_STYLES[document.design.template_id]}
</style>
"""
    shell = shell.replace('<html lang="en"', f'<html lang="{escape(document.locale, quote=True)}"')
    return shell.replace("</head>", additions + "</head>")
