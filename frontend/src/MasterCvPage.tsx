import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { mutate, request } from "./api";

type BuilderTab = "coach" | "preview" | "inspector";
type InspectorTab = "design" | "content" | "claims" | "portrait" | "versions";
type PreviewZoom = "fit" | number;

type TemplateOption = {
  id: string;
  name: string;
  note: string;
  market: string;
  photo: boolean;
  ats: "High" | "Good";
};

const templates: TemplateOption[] = [
  { id: "atelier", name: "Atelier", note: "Expressive, airy portfolio", market: "Creative", photo: true, ats: "Good" },
  { id: "classic-ats", name: "Classic ATS", note: "Clean single-column structure", market: "Global", photo: false, ats: "High" },
  { id: "editorial-banner", name: "Editorial Banner", note: "Confident editorial hierarchy", market: "Leadership", photo: true, ats: "Good" },
  { id: "elegant-serif", name: "Elegant Serif", note: "Quiet, refined typography", market: "Europe", photo: true, ats: "Good" },
  { id: "executive", name: "Executive", note: "Formal and achievement-led", market: "Leadership", photo: true, ats: "High" },
  { id: "ledger", name: "Ledger", note: "Detailed and information-rich", market: "Specialist", photo: false, ats: "High" },
  { id: "modern-sidebar", name: "Modern Sidebar", note: "Compact visual navigation", market: "Europe", photo: true, ats: "Good" },
  { id: "photo-corporate", name: "Photo Corporate", note: "Professional portrait-forward", market: "DACH", photo: true, ats: "Good" },
  { id: "photo-minimal", name: "Photo Minimal", note: "Warm, understated portrait", market: "DACH", photo: true, ats: "Good" },
  { id: "pillar", name: "Pillar", note: "Strong modular sections", market: "Global", photo: true, ats: "Good" },
  { id: "swiss", name: "Swiss", note: "Precise modernist grid", market: "Switzerland", photo: true, ats: "High" },
  { id: "tech-compact", name: "Tech Compact", note: "Dense skills and experience", market: "Technology", photo: false, ats: "High" },
  { id: "timeline", name: "Timeline", note: "Chronological visual story", market: "Creative", photo: true, ats: "Good" },
];

type CvBlock = { id: string; type?: string; title?: string; content?: unknown; claim_refs?: string[] };
type CvSection = { section_id: string; type: string; title: string; blocks: Array<{ block_id: string; kind: string; text: string; claim_refs?: string[]; visible?: boolean }> };
type ClaimItem = { id: string; text?: string; value?: string; status?: string; needs_review?: boolean };
type BuilderSummary = {
  has_approved_profile?: boolean;
  candidate?: {
    id?: string;
    document_snapshot_id?: string;
    title?: string;
    template_id?: string;
    page_count?: number;
    preview_url?: string;
    updated_at?: string;
    blocks?: CvBlock[];
    revision?: number;
    lifecycle_status?: string;
    review_flags?: string[];
    design?: { template_id?: string; page_count?: number };
    sections?: CvSection[];
  } | null;
  approved?: { id?: string; document_snapshot_id?: string; version?: number; template_id?: string; preview_url?: string; updated_at?: string } | null;
  session?: { id?: string; session_id?: string; run_id?: string; status?: string; entries?: Array<{ id?: string; role: string; content: string }>; transcript?: Array<{ id?: string; role: string; content: string }> } | null;
  portrait?: { asset_id?: string; filename?: string; preview_url?: string; crop?: { x?: number; y?: number; zoom?: number; width?: number; height?: number }; focal_point?: { x?: number; y?: number } } | null;
  source_documents?: Array<{ id?: string; filename: string; size_bytes?: number; status?: string }>;
  versions?: Array<{ id?: string; document_snapshot_id?: string; version?: number; version_number?: number; status?: string; template_id?: string; created_at?: string; preview_url?: string }>;
  claims?: ClaimItem[];
  templates?: TemplateOption[];
};

function candidateBlocks(candidate: BuilderSummary["candidate"]): CvBlock[] {
  if (candidate?.blocks?.length) return candidate.blocks;
  if (!candidate?.sections?.length) return fallbackBlocks;
  return candidate.sections.flatMap((section) => section.blocks.filter((block) => block.visible !== false).map((block, index) => ({
    id: block.block_id,
    type: block.kind,
    title: index ? `${section.title} · ${index + 1}` : section.title,
    content: block.text,
    claim_refs: block.claim_refs,
  })));
}

const fallbackBlocks: CvBlock[] = [
  { id: "profile", type: "summary", title: "Profile", content: "Your approved career summary will appear here. Work with the CV coach to shape it for clarity and voice." },
  { id: "experience", type: "experience", title: "Experience", content: "Verified roles and achievements from your profile are arranged here." },
  { id: "education", type: "education", title: "Education", content: "Education, certifications, and relevant training." },
  { id: "skills", type: "skills", title: "Skills", content: "Approved skills and languages." },
];

function asText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) return content.map((item) => typeof item === "string" ? item : JSON.stringify(item)).join("\n");
  if (content && typeof content === "object") return Object.values(content as Record<string, unknown>).map(asText).filter(Boolean).join("\n");
  return content == null ? "" : String(content);
}

export function MasterCvPage({ candidateName }: { candidateName: string }) {
  const [summary, setSummary] = useState<BuilderSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [message, setMessage] = useState("");
  const [mobileTab, setMobileTab] = useState<BuilderTab>("preview");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("design");
  const [editingBlock, setEditingBlock] = useState<string | null>(null);
  const [draftContent, setDraftContent] = useState("");
  const [crop, setCrop] = useState({ x: 50, y: 50, zoom: 100 });
  const [previewZoom, setPreviewZoom] = useState<PreviewZoom>(() => window.innerWidth > 900 ? 1 : "fit");
  const transcriptRef = useRef<HTMLDivElement>(null);

  const load = async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const data = await request<BuilderSummary>("/master-cv/summary");
      setSummary(data);
      const currentCrop = data.portrait?.crop;
      const focal = data.portrait?.focal_point;
      if (currentCrop || focal) setCrop({
        x: (focal?.x ?? 0.5) * 100,
        y: (focal?.y ?? 0.5) * 100,
        zoom: currentCrop?.zoom ?? (currentCrop?.width ? Math.round(100 / currentCrop.width) : 100),
      });
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The Master CV workspace could not be loaded.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const act = async (key: string, action: () => Promise<unknown>, success?: string) => {
    setBusy(key);
    setError("");
    setNotice("");
    try {
      await action();
      if (success) setNotice(success);
      await load(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "That change could not be saved.");
    } finally {
      setBusy("");
    }
  };

  const sessionId = summary?.session?.id || summary?.session?.session_id || summary?.session?.run_id;
  const blocks = candidateBlocks(summary?.candidate);
  const availableTemplates = summary?.templates?.length ? summary.templates : templates;
  const selectedTemplate = summary?.candidate?.template_id || summary?.candidate?.design?.template_id || summary?.approved?.template_id || "swiss";
  const selectedTemplateName = availableTemplates.find((item) => item.id === selectedTemplate)?.name || "Swiss";
  const entries = (summary?.session?.entries || summary?.session?.transcript || []).filter((entry) => entry.role === "user" || entry.role === "assistant");

  useEffect(() => {
    const transcript = transcriptRef.current;
    if (transcript) transcript.scrollTo({ top: transcript.scrollHeight, behavior: "smooth" });
  }, [entries.length]);

  const send = async (event: FormEvent) => {
    event.preventDefault();
    const text = message.trim();
    if (!text) return;
    setMessage("");
    if (!sessionId) {
      await act("message", () => mutate("/master-cv/sessions/start", "POST", { message: text }), "Your CV coach is preparing a first direction.");
      return;
    }
    await act("message", () => mutate(`/master-cv/sessions/${encodeURIComponent(sessionId)}/messages`, "POST", { message: text }));
  };

  const upload = async (kind: "source-documents" | "portrait", file: File) => {
    const path = kind === "portrait" ? "/master-cv/portrait" : `/master-cv/source-documents/${encodeURIComponent(file.name)}`;
    await act(kind, () => request(path, {
      method: kind === "portrait" ? "POST" : "PUT",
      headers: { "Content-Type": file.type || "application/octet-stream", ...(kind === "portrait" ? { "X-Filename": file.name } : {}) },
      body: file,
    }), kind === "portrait" ? "Portrait added. Adjust the crop before approving it." : "Source CV added for the coach to review.");
  };

  const chooseTemplate = (templateId: string) => act(
    `template-${templateId}`,
    () => request("/master-cv/candidate/design", { method: "PATCH", body: JSON.stringify({ template_id: templateId, expected_revision: summary?.candidate?.revision }) }),
    "Design updated. Your content and approved claims are unchanged.",
  );

  const editBlock = (block: CvBlock) => {
    setEditingBlock(block.id);
    setDraftContent(asText(block.content));
    setInspectorTab("content");
    setMobileTab("inspector");
  };

  const saveBlock = () => {
    if (!editingBlock) return;
    void act("block", () => request(`/master-cv/candidate/blocks/${encodeURIComponent(editingBlock)}`, {
      method: "PATCH",
      body: JSON.stringify({ text: draftContent, expected_revision: summary?.candidate?.revision }),
    }), "Section saved and queued for a fresh preview.").then(() => setEditingBlock(null));
  };

  const saveCrop = () => {
    const width = 100 / crop.zoom;
    const height = width;
    const assetId = summary?.portrait?.asset_id;
    if (!assetId) return Promise.resolve();
    return act("crop", () => request(`/master-cv/portrait/${encodeURIComponent(assetId)}/crop`, {
      method: "POST",
      body: JSON.stringify({
        crop: {
          x: (crop.x / 100) * (1 - width),
          y: (crop.y / 100) * (1 - height),
          width,
          height,
        },
        focal_point: { x: crop.x / 100, y: crop.y / 100 },
      }),
    }), "Portrait crop saved.");
  };

  const render = () => act("render", () => mutate("/master-cv/render", "POST"), "A fresh A4 preview is ready.");
  const approve = () => act("approve", () => mutate("/master-cv/approve", "POST", { confirm_claims: true, confirm_design: true }), "Approved. This version can now anchor tailored CVs.");
  const approvedId = summary?.approved?.document_snapshot_id || summary?.approved?.id;

  if (loading) return <div className="page master-cv-page"><div className="master-cv-loading"><i /><strong>Opening your CV studio…</strong><span>Loading designs, claims, and the latest version.</span></div></div>;

  return (
    <div className="page master-cv-page">
      <header className="master-cv-header">
        <div>
          <p className="eyebrow">Your reusable career document</p>
          <h1>Master CV studio</h1>
          <p>Build one beautiful, evidence-backed source CV with your coach. Tailored applications inherit its approved design, portrait, and claims.</p>
        </div>
        <div className="master-cv-header-actions">
          <span className={`master-cv-state ${summary?.approved ? "approved" : "draft"}`}><i />{summary?.approved ? `Approved v${summary.approved.version || 1}` : "Working draft"}</span>
          {approvedId && <a className="secondary-button" href={`/master-cv/documents/${encodeURIComponent(approvedId)}/download?format=html`}>Export HTML</a>}
          {approvedId && <a className="secondary-button" href={`/master-cv/documents/${encodeURIComponent(approvedId)}/download?format=pdf`}>Export PDF</a>}
          <button className="secondary-button" disabled={Boolean(busy)} onClick={() => void render()}>{busy === "render" ? "Rendering…" : "Refresh preview"}</button>
          <button className="primary-button" disabled={Boolean(busy) || !summary?.candidate} onClick={() => void approve()}>{busy === "approve" ? "Approving…" : "Approve version"}</button>
        </div>
      </header>

      {!summary?.has_approved_profile && (
        <div className="master-cv-foundation-callout">
          <span>Start with verified facts</span>
          <p>Your coach can explore layouts now, but only approved profile claims can enter a final CV.</p>
          <Link to="/profile">Finish My story →</Link>
        </div>
      )}
      {error && <div className="master-cv-alert error" role="alert"><span>!</span><p>{error}</p><button onClick={() => void load()}>Try again</button></div>}
      {notice && <div className="master-cv-alert success" role="status"><span>✓</span><p>{notice}</p></div>}

      <nav className="master-cv-mobile-tabs" aria-label="CV builder panels">
        {(["coach", "preview", "inspector"] as BuilderTab[]).map((tab) => <button key={tab} className={mobileTab === tab ? "active" : ""} onClick={() => setMobileTab(tab)}>{tab === "coach" ? "CV coach" : tab === "preview" ? "Preview" : "Edit"}</button>)}
      </nav>

      <section className="master-cv-workspace">
        <aside className={`master-cv-coach ${mobileTab === "coach" ? "mobile-active" : ""}`}>
          <header>
            <div className="master-cv-coach-avatar">CV<span /></div>
            <div><strong>Your CV coach</strong><small>{summary?.session?.status === "running" ? "Working on your draft" : "Ready to collaborate"}</small></div>
          </header>
          <div className="master-cv-sources">
            <p className="eyebrow">Starting material</p>
            <div className="master-cv-source-actions">
              <label className="master-cv-upload"><input type="file" accept=".pdf,.doc,.docx,.txt,.md" disabled={Boolean(busy)} onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload("source-documents", file); event.currentTarget.value = ""; }} /><span>＋</span><div><strong>Add an existing CV</strong><small>PDF, Word, or text</small></div></label>
              {summary?.source_documents?.map((source) => <div className="master-cv-source-file" key={source.id || source.filename}><span>DOC</span><div><strong>{source.filename}</strong><small>{source.status || "Available to your coach"}</small></div></div>)}
            </div>
          </div>
          <div className="master-cv-transcript" ref={transcriptRef}>
            {!entries.length && <div className="master-cv-welcome"><span>✦</span><h2>Let’s shape a CV that feels like you.</h2><p>I’ll work from your approved story and any CV you share. We can begin with structure, design, or the role you want this master version to express.</p><button className="secondary-button" disabled={Boolean(busy)} onClick={() => void act("start", () => mutate("/master-cv/sessions/start", "POST"))}>Start with my profile</button></div>}
            {entries.map((entry, index) => <article className={entry.role === "user" ? "user" : "agent"} key={entry.id || index}><small>{entry.role === "user" ? "You" : "CV coach"}</small><p>{entry.content}</p></article>)}
            {busy === "message" && <div className="master-cv-thinking"><i /><span>Reviewing the document and your approved story…</span></div>}
          </div>
          <form className="master-cv-compose" onSubmit={(event) => void send(event)}><textarea rows={3} value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Ask for a design change, rewrite, or content review…" /><button disabled={Boolean(busy) || !message.trim()} aria-label="Send message">↑</button></form>
        </aside>

        <main className={`master-cv-preview-pane ${mobileTab === "preview" ? "mobile-active" : ""}`}>
          <div className="master-cv-preview-toolbar">
            <div className="master-cv-preview-title"><strong>{summary?.candidate?.title || `${candidateName}'s Master CV`}</strong><small>{selectedTemplateName} · A4 · {summary?.candidate?.page_count || summary?.candidate?.design?.page_count || 1} page</small></div>
            <div className="master-cv-preview-tools">
              <div className="master-cv-zoom-controls" aria-label="Preview zoom">
                <button className={previewZoom === "fit" ? "active" : ""} onClick={() => setPreviewZoom("fit")}>Fit</button>
                <button aria-label="Zoom out" onClick={() => setPreviewZoom((current) => Math.max(.5, (current === "fit" ? 1 : current) - .1))}>−</button>
                <button className={previewZoom === 1 ? "active" : ""} title="Reset to 100%" onClick={() => setPreviewZoom(1)}>{previewZoom === "fit" ? "Fit" : `${Math.round(previewZoom * 100)}%`}</button>
                <button aria-label="Zoom in" onClick={() => setPreviewZoom((current) => Math.min(1.5, (current === "fit" ? 1 : current) + .1))}>+</button>
              </div>
              <span className="master-cv-live-state">Live draft</span>
            </div>
          </div>
          <div className="master-cv-canvas">
            {summary?.candidate?.preview_url ? <MasterCvPreviewFrame src={summary.candidate.preview_url} zoom={previewZoom} /> : (
              <article className={`master-cv-paper template-${selectedTemplate}`}>
                <header>
                  {summary?.portrait?.preview_url && <img src={summary.portrait.preview_url} alt={`${candidateName} portrait`} />}
                  <div><p>CURRICULUM VITAE</p><h2>{candidateName}</h2><span>Professional profile · Location · Contact</span></div>
                </header>
                <div className="master-cv-paper-body">{blocks.map((block) => <section key={block.id} onDoubleClick={() => editBlock(block)} title="Double-click to edit"><div><h3>{block.title || block.type || "Section"}</h3><button onClick={() => editBlock(block)} aria-label={`Edit ${block.title || "section"}`}>Edit</button></div><p>{asText(block.content) || "Ask your CV coach to develop this section."}</p></section>)}</div>
              </article>
            )}
          </div>
          <footer className="master-cv-preview-footer"><span>Double-click any section to edit</span><span>Claims stay linked to your approved profile</span></footer>
        </main>

        <aside className={`master-cv-inspector ${mobileTab === "inspector" ? "mobile-active" : ""}`}>
          <nav aria-label="CV settings">{(["design", "content", "claims", "portrait", "versions"] as InspectorTab[]).map((tab) => <button key={tab} className={inspectorTab === tab ? "active" : ""} onClick={() => setInspectorTab(tab)}>{tab}</button>)}</nav>
          <div className="master-cv-inspector-body">
            {inspectorTab === "design" && <DesignInspector current={selectedTemplate} options={availableTemplates} disabled={Boolean(busy)} choose={(id) => void chooseTemplate(id)} />}
            {inspectorTab === "content" && <ContentInspector blocks={blocks} editing={editingBlock} draft={draftContent} disabled={Boolean(busy)} select={editBlock} setDraft={setDraftContent} cancel={() => setEditingBlock(null)} save={saveBlock} />}
            {inspectorTab === "claims" && <ClaimsInspector claims={summary?.claims || []} />}
            {inspectorTab === "portrait" && <PortraitInspector portrait={summary?.portrait || null} crop={crop} disabled={Boolean(busy)} setCrop={setCrop} upload={(file) => void upload("portrait", file)} save={() => void saveCrop()} />}
            {inspectorTab === "versions" && <VersionsInspector approved={summary?.approved || null} versions={summary?.versions || []} />}
          </div>
        </aside>
      </section>
    </div>
  );
}

const A4_PREVIEW_WIDTH = 794;
const A4_PREVIEW_HEIGHT = 1123;

function MasterCvPreviewFrame({ src, zoom }: { src: string; zoom: PreviewZoom }) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [fitScale, setFitScale] = useState(1);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const resize = () => {
      const availableWidth = Math.max(240, viewport.clientWidth);
      setFitScale(Math.min(1, availableWidth / A4_PREVIEW_WIDTH));
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, []);
  const scale = zoom === "fit" ? fitScale : zoom;
  const overflowing = scale > fitScale + .001;

  return (
    <div className={`master-cv-frame-viewport ${overflowing ? "is-overflowing" : ""}`} ref={viewportRef}>
      <div
        className="master-cv-frame-scale"
        style={{ width: A4_PREVIEW_WIDTH * scale, height: A4_PREVIEW_HEIGHT * scale }}
      >
        <iframe
          title="Master CV preview"
          src={src}
          style={{
            width: A4_PREVIEW_WIDTH,
            height: A4_PREVIEW_HEIGHT,
            transform: `scale(${scale})`,
          }}
        />
      </div>
    </div>
  );
}

function DesignInspector({ current, options, disabled, choose }: { current: string; options: TemplateOption[]; disabled: boolean; choose: (id: string) => void }) {
  return <><div className="master-cv-inspector-heading"><p className="eyebrow">Design system</p><h2>Choose the character</h2><p>Every design uses the same structured, approved content.</p></div><div className="master-cv-template-grid">{options.map((template) => <button key={template.id} className={current === template.id ? "selected" : ""} disabled={disabled} onClick={() => choose(template.id)}><span className={`template-thumb ${template.id}`}><i /><i /><i /></span><div><strong>{template.name}</strong><small>{template.note}</small><em>{template.market} · ATS {template.ats}{template.photo ? " · Photo" : ""}</em></div>{current === template.id && <b>✓</b>}</button>)}</div></>;
}

function ContentInspector({ blocks, editing, draft, disabled, select, setDraft, cancel, save }: { blocks: CvBlock[]; editing: string | null; draft: string; disabled: boolean; select: (block: CvBlock) => void; setDraft: (value: string) => void; cancel: () => void; save: () => void }) {
  const active = blocks.find((block) => block.id === editing);
  if (active) return <div className="master-cv-block-editor"><button className="text-button" onClick={cancel}>← All sections</button><p className="eyebrow">Direct edit</p><h2>{active.title || active.type}</h2><p>Edits are checked against linked claims before approval.</p><textarea autoFocus rows={15} value={draft} onChange={(event) => setDraft(event.target.value)} /><div><button className="secondary-button" onClick={cancel}>Cancel</button><button className="primary-button" disabled={disabled || !draft.trim()} onClick={save}>Save section</button></div></div>;
  return <><div className="master-cv-inspector-heading"><p className="eyebrow">Document structure</p><h2>Edit by section</h2><p>Rework the wording while keeping facts traceable.</p></div><div className="master-cv-block-list">{blocks.map((block, index) => <button key={block.id} onClick={() => select(block)}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{block.title || block.type}</strong><small>{asText(block.content).slice(0, 70) || "Empty section"}</small></div><b>→</b></button>)}</div></>;
}

function ClaimsInspector({ claims }: { claims: ClaimItem[] }) {
  const needsReview = claims.filter((claim) => claim.needs_review || claim.status === "needs_review").length;
  return <><div className="master-cv-inspector-heading"><p className="eyebrow">Factual foundation</p><h2>{claims.length ? `${claims.length} linked claims` : "Claims stay traceable"}</h2><p>{needsReview ? `${needsReview} need your review before approval.` : "Only facts from your approved Master CV profile may be used."}</p></div>{claims.length ? <div className="master-cv-claim-list">{claims.map((claim) => <article key={claim.id}><span className={claim.needs_review ? "review" : "verified"}>{claim.needs_review ? "!" : "✓"}</span><div><p>{claim.text || claim.value || claim.id}</p><small>{claim.needs_review ? "Needs your review" : claim.status || "Approved source"}</small></div></article>)}</div> : <div className="master-cv-empty-small"><span>◎</span><h3>Protected by your profile</h3><p>Your coach cannot add credentials, dates, skills, or achievements that are not supported there.</p><Link to="/profile/view">Review approved claims →</Link></div>}</>;
}

function PortraitInspector({ portrait, crop, disabled, setCrop, upload, save }: { portrait: BuilderSummary["portrait"]; crop: { x: number; y: number; zoom: number }; disabled: boolean; setCrop: (crop: { x: number; y: number; zoom: number }) => void; upload: (file: File) => void; save: () => void }) {
  return <><div className="master-cv-inspector-heading"><p className="eyebrow">Portrait</p><h2>Professional, and optional</h2><p>German and Swiss CVs often include a photo. You decide when it appears.</p></div><label className="master-cv-portrait-upload"><input type="file" accept="image/jpeg,image/png,image/webp,.heic,.heif" disabled={disabled} onChange={(event) => { const file = event.target.files?.[0]; if (file) upload(file); event.currentTarget.value = ""; }} />{portrait?.preview_url ? <div className="master-cv-portrait-crop"><img src={portrait.preview_url} alt="Candidate portrait crop preview" style={{ objectPosition: `${crop.x}% ${crop.y}%`, transform: `scale(${crop.zoom / 100})` }} /></div> : <span>＋</span>}<strong>{portrait ? "Replace portrait" : "Add your portrait"}</strong><small>JPEG, PNG, WebP{portrait ? ` · ${portrait.filename || "Uploaded"}` : " · safely normalized"}</small></label>{portrait && <div className="master-cv-crop-controls"><label>Horizontal focus <input type="range" min="0" max="100" value={crop.x} onChange={(event) => setCrop({ ...crop, x: Number(event.target.value) })} /></label><label>Vertical focus <input type="range" min="0" max="100" value={crop.y} onChange={(event) => setCrop({ ...crop, y: Number(event.target.value) })} /></label><label>Zoom <input type="range" min="100" max="180" value={crop.zoom} onChange={(event) => setCrop({ ...crop, zoom: Number(event.target.value) })} /></label><button className="primary-button" disabled={disabled} onClick={save}>Save crop</button></div>}<div className="master-cv-privacy-note"><strong>Private by design</strong><p>Location metadata is removed. The coach works with the portrait slot, not your image bytes.</p></div></>;
}

function VersionsInspector({ approved, versions }: { approved: BuilderSummary["approved"]; versions: NonNullable<BuilderSummary["versions"]> }) {
  const items = versions.length ? versions : approved?.id ? [{ id: approved.id, version: approved.version, status: "approved", template_id: approved.template_id, created_at: approved.updated_at, preview_url: approved.preview_url }] : [];
  return <><div className="master-cv-inspector-heading"><p className="eyebrow">Version history</p><h2>Safe iterations</h2><p>Approving creates an immutable source for future tailored CVs.</p></div>{items.length ? <div className="master-cv-version-list">{items.map((version) => <article key={version.id || version.document_snapshot_id}><span>v{version.version || version.version_number || 1}</span><div><strong>{version.status === "approved" ? "Approved master" : "Saved draft"}</strong><small>{version.template_id || "Design"} · {version.created_at ? new Date(version.created_at).toLocaleDateString() : "Current"}</small></div>{version.preview_url && <a href={version.preview_url} target="_blank" rel="noreferrer">Open</a>}</article>)}</div> : <div className="master-cv-empty-small"><span>↺</span><h3>Your first version starts here</h3><p>Approve the finished design to create a stable reference for tailoring.</p></div>}<Link className="master-cv-documents-link" to="/documents">See all generated documents →</Link></>;
}
