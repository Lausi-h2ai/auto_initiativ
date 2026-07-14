import { FormEvent, ReactNode, createContext, useContext, useEffect, useMemo, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useNavigate, useSearchParams } from "react-router-dom";
import {
  AgentTask,
  ApprovedProfileBundle,
  Campaign,
  Company,
  DocumentItem,
  ExceptionItem,
  loadWorkspace,
  mutate,
  request,
} from "./api";

type WorkspaceData = Awaited<ReturnType<typeof loadWorkspace>>;
type WorkspaceContextValue = WorkspaceData & { refresh: () => Promise<void> };

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);
const pipelineStages = ["discovered", "qualified", "preparing", "ready", "sent", "replied"];

export function App() {
  if (window.location.pathname === "/login") return <Login />;
  if (window.location.pathname === "/register") return <Registration />;
  return <WorkspaceProvider />;
}

function WorkspaceProvider() {
  const [data, setData] = useState<WorkspaceData | null>(null);
  const [error, setError] = useState("");

  const refresh = async () => {
    try {
      setData(await loadWorkspace());
      setError("");
    } catch (cause) {
      setError(messageOf(cause));
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (!data?.summary.active_tasks.length) return;
    const timer = window.setInterval(() => void refresh(), 7000);
    return () => window.clearInterval(timer);
  }, [data?.summary.active_tasks.length]);

  if (error) return <FatalError message={error} retry={refresh} />;
  if (!data) return <LoadingScreen />;

  return (
    <WorkspaceContext.Provider value={{ ...data, refresh }}>
      <Shell />
    </WorkspaceContext.Provider>
  );
}

function useWorkspace() {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("Workspace context is unavailable.");
  return value;
}

function Login() {
  return (
    <main className="login-page">
      <section className="login-story">
        <Brand />
        <div className="login-copy">
          <p className="eyebrow light">A recruiter that stays with you</p>
          <h1>Your search deserves a dedicated team.</h1>
          <p>
            Specialist agents discover companies, understand your fit, prepare every application, and keep the work moving—quietly and carefully.
          </p>
        </div>
        <div className="trust-line"><span /> Private workspace <span /> Evidence-backed work <span /> Gated delivery</div>
      </section>
      <section className="login-panel">
        <div className="login-card">
          <p className="eyebrow">Welcome to Auto Initiativ</p>
          <h2>Meet your recruiter.</h2>
          <p>Sign in with the invited Google account. Gmail access is requested separately only when you choose to connect a sender.</p>
          <a className="google-button" href="/auth/google/start">
            <span className="google-mark">G</span> Continue with Google
          </a>
          <small>Invite-only access · Your workspace is isolated from every other user.</small>
        </div>
      </section>
    </main>
  );
}

function Registration() {
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await mutate("/auth/local/register", "POST", { display_name: displayName, email });
      window.location.assign("/dashboard#/profile");
    } catch (cause) {
      setError(messageOf(cause));
      setBusy(false);
    }
  };
  return (
    <main className="login-page">
      <section className="login-story">
        <Brand />
        <div className="login-copy">
          <p className="eyebrow light">A clean workspace of your own</p>
          <h1>Start from the beginning.</h1>
          <p>Create a separate local account, then meet your recruiter and build your profile from scratch.</p>
        </div>
        <div className="trust-line"><span /> Local-only account <span /> Separate workspace <span /> No Google setup</div>
      </section>
      <section className="login-panel">
        <div className="login-card">
          <p className="eyebrow">Create a local account</p>
          <h2>Your fresh workspace.</h2>
          <p>This account is for local testing on this computer. It does not require a password or Google sign-in.</p>
          <form className="registration-form" onSubmit={(event) => void submit(event)}>
            <label><span>Your name</span><input autoFocus required minLength={2} maxLength={100} value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Laurent Hug" /></label>
            <label><span>Email</span><input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="fresh-test@example.com" /></label>
            <button className="primary-button" disabled={busy}>{busy ? "Creating workspace…" : "Create account"}</button>
          </form>
          {error && <InlineError message={error} />}
          <a className="registration-back" href="/dashboard">Back to the current workspace</a>
        </div>
      </section>
    </main>
  );
}

function Shell() {
  const { me, summary } = useWorkspace();
  const firstName = me.display_name.split(" ")[0];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <nav className="main-nav" aria-label="Primary navigation">
          <NavItem to="/" label="Mission control" icon="◌" end />
          <NavItem to="/companies" label="Companies" icon="◇" count={sumValues(summary.pipeline)} />
          <NavItem to="/documents" label="Documents" icon="▱" count={summary.document_count} />
          <NavItem to="/profile" label="My story" icon="◎" />
          <NavItem to="/exceptions" label="Needs me" icon="!" count={summary.exception_count} accent />
        </nav>
        <div className="sidebar-spacer" />
        <nav className="secondary-nav">
          <NavItem to="/settings" label="Settings" icon="·" />
          {me.role === "admin" && <NavItem to="/admin" label="Administration" icon="⌘" />}
        </nav>
        <div className="account-summary">
          <Avatar name={me.display_name} src={me.avatar_url} />
          <div><strong>{firstName}</strong><small>{me.workspace.name}</small></div>
        </div>
      </aside>
      <main className="workspace">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/campaigns/new" element={<CampaignWizard />} />
          <Route path="/companies" element={<CompaniesPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/profile/view" element={<ProfileViewerPage />} />
          <Route path="/exceptions" element={<ExceptionsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

function Overview() {
  const { me, summary, profile, exceptions, refresh } = useWorkspace();
  const firstName = me.display_name.split(" ")[0];
  const campaign = summary.active_campaign;
  const hasPriorWork = sumValues(summary.pipeline) > 0 || summary.sent_count > 0;
  const nextAction = !profile.has_approved_profile ? "profile" : exceptions.length ? "exceptions" : campaign ? "progress" : hasPriorWork ? "history" : "campaign";

  return (
    <div className="page overview-page">
      <PageHeader
        eyebrow="Your personal recruiter"
        title={`Good ${dayPart()}, ${firstName}.`}
        aside={<button className="quiet-button" onClick={() => void refresh()}>Refresh activity</button>}
      />

      <section className={`concierge-hero ${nextAction}`}>
        <div className="hero-content">
          <p className="eyebrow">{heroEyebrow(nextAction)}</p>
          <h2>{heroTitle(nextAction, campaign, exceptions.length)}</h2>
          <p>{heroBody(nextAction, campaign)}</p>
          <HeroAction kind={nextAction} />
        </div>
        <AgentConstellation tasks={summary.active_tasks} />
      </section>

      {(campaign || hasPriorWork) && <Journey campaign={campaign} pipeline={summary.pipeline} />}

      <div className="overview-grid">
        <section className="panel activity-panel">
          <PanelHeading eyebrow="Your team" title="Working on your behalf" action={<Link to="/companies">View pipeline</Link>} />
          {summary.active_tasks.length ? (
            <div className="activity-list">
              {summary.active_tasks.map((task) => <AgentActivity key={task.id} task={task} />)}
            </div>
          ) : (
            <EmptyState title={hasPriorWork ? "Your previous work is organized" : "Your team is ready"} body={hasPriorWork ? "Review the companies and outreach already completed, or start a campaign when you want the specialists to continue." : "Start a campaign and the right specialists will take it from there."} />
          )}
        </section>

        <section className="panel pulse-panel">
          <PanelHeading eyebrow="Search pulse" title="Progress that matters" />
          <div className="metric-stack">
            <Metric value={sumValues(summary.pipeline)} label="Companies in your pipeline" tone="ink" />
            <Metric value={summary.pipeline.ready || 0} label="Applications ready" tone="amber" />
            <Metric value={summary.sent_count} label="Outreach sent" tone="green" />
            <Metric value={summary.exception_count} label="Decisions waiting" tone="rose" />
          </div>
        </section>
      </div>

      <section className="panel recent-panel">
        <PanelHeading eyebrow="Recruiter notes" title="A concise record of what happened" action={<Link to="/documents">Open documents</Link>} />
        <div className="notes-timeline">
          {summary.active_tasks.slice(0, 4).map((task) => (
            <div className="timeline-note" key={task.id}><span /><div><strong>{roleName(task.agent_role)}</strong><p>{task.narrative}</p></div><small>{task.status}</small></div>
          ))}
          {!summary.active_tasks.length && <p className="muted">Activity will appear here as your specialists begin their work.</p>}
        </div>
      </section>
    </div>
  );
}

function HeroAction({ kind }: { kind: string }) {
  if (kind === "profile") return <Link className="primary-button" to="/profile">Meet my onboarding recruiter <Arrow /></Link>;
  if (kind === "campaign") return <Link className="primary-button" to="/campaigns/new">Plan my first search <Arrow /></Link>;
  if (kind === "history") return <Link className="primary-button" to="/companies">Review my outreach history <Arrow /></Link>;
  if (kind === "exceptions") return <Link className="primary-button" to="/exceptions">Resolve what needs me <Arrow /></Link>;
  return <Link className="primary-button" to="/companies">See what my team found <Arrow /></Link>;
}

function Journey({ campaign, pipeline }: { campaign: Campaign | null; pipeline: Record<string, number> }) {
  const total = Math.max(sumValues(pipeline), 1);
  return (
    <section className="journey-panel">
      <div className="journey-title"><div><p className="eyebrow">{campaign ? "Active campaign" : "Existing outreach"}</p><h3>{campaign?.name || "Your restored search history"}</h3></div><StatusPill status={campaign?.status || "ready"} /></div>
      <div className="journey-stages">
        {pipelineStages.slice(0, 5).map((stage, index) => {
          const count = pipeline[stage] || 0;
          return <div className={`journey-stage ${count ? "populated" : ""}`} key={stage}><div className="stage-marker"><span>{index + 1}</span><i style={{ width: `${Math.min(100, (count / total) * 100 + (count ? 20 : 0))}%` }} /></div><strong>{human(stage)}</strong><small>{count} {count === 1 ? "company" : "companies"}</small></div>;
        })}
      </div>
    </section>
  );
}

function CompaniesPage() {
  const { summary } = useWorkspace();
  const campaign = summary.active_campaign;
  const [companies, setCompanies] = useState<Company[]>([]);
  const [selected, setSelected] = useState<Company | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const path = campaign ? `/campaigns/${campaign.id}/pipeline` : "/companies";
    request<Company[]>(path).then((items) => setCompanies(items.map(normalizeCompany))).finally(() => setLoading(false));
  }, [campaign?.id]);

  const grouped = useMemo(() => {
    const map = new Map<string, Company[]>();
    for (const stage of pipelineStages) map.set(stage, []);
    for (const company of companies) {
      const stage = company.stage || (company.has_been_contacted ? "sent" : company.has_application_draft ? "ready" : "discovered");
      if (!map.has(stage)) map.set(stage, []);
      map.get(stage)!.push({ ...company, stage });
    }
    return map;
  }, [companies]);

  return (
    <div className="page pipeline-page">
      <PageHeader eyebrow="Curated opportunity map" title="Companies your team is moving forward" aside={<Link className="secondary-button" to="/campaigns/new">New campaign</Link>} />
      <div className="pipeline-toolbar"><div><StatusPill status={campaign?.status || "ready"} /><span>{campaign?.name || "All discovered companies"}</span></div><p>{companies.length} opportunities · ranked by your approved profile</p></div>
      {loading ? <InlineLoading /> : companies.length ? (
        <div className="pipeline-board">
          {pipelineStages.slice(0, 5).map((stage) => (
            <section className="pipeline-column" key={stage}>
              <header><div><span className={`stage-dot ${stage}`} /><strong>{human(stage)}</strong></div><b>{grouped.get(stage)?.length || 0}</b></header>
              <div className="company-card-stack">
                {(grouped.get(stage) || []).map((company) => <CompanyCard key={String(company.id || company.company_id)} company={company} onClick={() => setSelected(company)} />)}
                {!(grouped.get(stage)?.length) && <div className="column-empty">Your team will place matches here.</div>}
              </div>
            </section>
          ))}
        </div>
      ) : <EmptyState title="No companies yet" body="Launch a search campaign and your research specialist will build a curated pipeline." action={<Link className="primary-button" to="/campaigns/new">Start company search</Link>} />}
      {selected && <CompanyDrawer company={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function CompanyCard({ company, onClick }: { company: Company; onClick: () => void }) {
  const score = company.fit_score == null ? null : Math.round(company.fit_score * 100);
  return (
    <button className="company-card" onClick={onClick}>
      <div className="company-card-top"><CompanyMark name={company.name} /><span className="card-menu">···</span></div>
      <h3>{company.name}</h3>
      <p className="company-domain">{company.domain || company.normalized_domain || "Domain being verified"}</p>
      <div className="tag-row">{toStrings(company.industry_tags).slice(0, 2).map((tag) => <span key={tag}>{tag}</span>)}</div>
      <p className="company-snippet">{company.description || "Your research agent is building a concise company brief."}</p>
      <div className="company-card-footer"><span>{score == null ? "Fit pending" : `${score}% fit`}</span><span>{company.stage === "sent" ? "Contacted" : company.has_draft || company.has_application_draft ? "Draft ready" : human(company.stage || "discovered")}</span></div>
    </button>
  );
}

function CompanyDrawer({ company, onClose }: { company: Company; onClose: () => void }) {
  return (
    <div className="drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside className="company-drawer">
        <button className="drawer-close" onClick={onClose} aria-label="Close">×</button>
        <div className="drawer-company"><CompanyMark name={company.name} large /><div><p className="eyebrow">{human(company.stage || "discovered")}</p><h2>{company.name}</h2><p>{company.domain || company.normalized_domain}</p></div></div>
        <div className="fit-callout"><strong>{company.fit_score == null ? "Fit analysis underway" : `${Math.round(company.fit_score * 100)}% profile fit`}</strong><p>{toStrings(company.fit_reasons)[0] || "The fit specialist is comparing this company with your approved experience and priorities."}</p></div>
        <DrawerSection title="Why your recruiter noticed it"><p>{company.description || "A sourced company brief is being prepared."}</p></DrawerSection>
        <DrawerSection title="Evidence-backed fit">{toStrings(company.fit_reasons).length ? <ul>{toStrings(company.fit_reasons).map((reason) => <li key={reason}>{reason}</li>)}</ul> : <p>Fit reasons will appear after evaluation.</p>}</DrawerSection>
        <DrawerSection title="Your application team"><div className="mini-agent-row"><RoleBadge role="Research" /><RoleBadge role="Fit" /><RoleBadge role="CV" /><RoleBadge role="Writing" /></div></DrawerSection>
        <div className="drawer-actions"><Link className="secondary-button" to={`/documents?company=${encodeURIComponent(String(company.id ?? company.company_id ?? ""))}&companyName=${encodeURIComponent(company.name)}`}>View documents</Link><button className="primary-button" onClick={onClose}>Keep moving forward</button></div>
      </aside>
    </div>
  );
}

function CampaignWizard() {
  const navigate = useNavigate();
  const { delivery, profile, refresh } = useWorkspace();
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ name: "My next opportunity", role_focus: "", locations: "", company_preferences: "", notes: "", max_companies: 30, sending_mode: "prepare_only" });
  const steps = ["Direction", "Places", "Character", "Autonomy", "Review"];

  if (!profile.has_approved_profile) {
    return (
      <div className="wizard-page">
        <button className="back-link" onClick={() => navigate(-1)}>← Leave setup</button>
        <section className="wizard-card campaign-prerequisite">
          <EmptyState
            title="First, let your recruiter learn your story"
            body="Campaigns use one approved career profile, CV source, and policy so every specialist can act confidently without asking you the same questions again."
            action={<Link className="primary-button" to="/profile">Meet my onboarding recruiter <Arrow /></Link>}
          />
        </section>
      </div>
    );
  }

  const submit = async () => {
    setBusy(true); setError("");
    try {
      await mutate("/campaigns", "POST", { ...form, locations: form.locations.split(",").map((item) => item.trim()).filter(Boolean) });
      await refresh();
      navigate("/");
    } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); }
  };

  return (
    <div className="wizard-page">
      <button className="back-link" onClick={() => step ? setStep(step - 1) : navigate(-1)}>← {step ? "Back" : "Leave setup"}</button>
      <div className="wizard-progress">{steps.map((label, index) => <div className={index <= step ? "active" : ""} key={label}><span>{index + 1}</span><small>{label}</small></div>)}</div>
      <section className="wizard-card">
        {step === 0 && <WizardStep eyebrow="First, give your recruiter direction" title="What kind of work should we pursue?" body="A broad direction is enough. Your specialists will use your approved story to make the detailed decisions."><Field label="Campaign name"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field><Field label="Role direction"><textarea autoFocus rows={4} placeholder="Applied AI engineering, technical product roles, ML systems…" value={form.role_focus} onChange={(e) => setForm({ ...form, role_focus: e.target.value })} /></Field></WizardStep>}
        {step === 1 && <WizardStep eyebrow="Define the search horizon" title="Where should your team look?" body="Add a few locations or remote regions. The research agent will handle variations and nearby matches."><Field label="Locations"><input autoFocus placeholder="Zurich, Basel, Remote Switzerland" value={form.locations} onChange={(e) => setForm({ ...form, locations: e.target.value })} /></Field><div className="suggestion-row">{["Zurich", "Switzerland", "Remote Europe"].map((place) => <button key={place} onClick={() => setForm({ ...form, locations: [form.locations, place].filter(Boolean).join(", ") })}>{place}</button>)}</div></WizardStep>}
        {step === 2 && <WizardStep eyebrow="Help matches feel like you" title="What should make a company stand out?" body="Describe the environment, mission, or work you want. This is guidance, not a complex filter form."><Field label="Company character"><textarea autoFocus rows={5} placeholder="Product-minded teams using AI for useful, concrete problems…" value={form.company_preferences} onChange={(e) => setForm({ ...form, company_preferences: e.target.value })} /></Field><div className="range-choice"><span>Search breadth</span>{[15, 30, 50].map((count) => <button className={form.max_companies === count ? "selected" : ""} onClick={() => setForm({ ...form, max_companies: count })} key={count}>{count === 15 ? "Focused" : count === 30 ? "Balanced" : "Broad"}<small>about {count} companies</small></button>)}</div></WizardStep>}
        {step === 3 && <WizardStep eyebrow="Choose once, then let the team work" title="How far should this campaign proceed?" body="Both modes research, evaluate, tailor CVs, and write emails autonomously."><label className={`mode-card ${form.sending_mode === "prepare_only" ? "selected" : ""}`}><input type="radio" checked={form.sending_mode === "prepare_only"} onChange={() => setForm({ ...form, sending_mode: "prepare_only" })} /><span><strong>Prepare everything for me</strong><small>Stop when each application is ready. You decide what gets sent.</small></span></label><label className={`mode-card ${form.sending_mode === "gated_autosend" ? "selected" : ""} ${!delivery.gmail_configured ? "disabled" : ""}`}><input type="radio" disabled={!delivery.gmail_configured} checked={form.sending_mode === "gated_autosend"} onChange={() => setForm({ ...form, sending_mode: "gated_autosend" })} /><span><strong>Gated autopilot</strong><small>{delivery.gmail_configured ? "Send automatically only after every deterministic check passes." : "Connect Gmail in settings to make this available."}</small></span></label></WizardStep>}
        {step === 4 && <WizardStep eyebrow="Your recruiter brief" title="Everything your team needs to begin" body="You can pause the campaign at any time. Only genuine exceptions will come back to you."><div className="brief-review"><ReviewRow label="Direction" value={form.role_focus || "Profile-aligned roles"} /><ReviewRow label="Places" value={form.locations || "From approved profile"} /><ReviewRow label="Character" value={form.company_preferences || "Use my approved preferences"} /><ReviewRow label="Breadth" value={`${form.max_companies} curated companies`} /><ReviewRow label="Autonomy" value={form.sending_mode === "gated_autosend" ? "Gated autopilot" : "Prepare through final drafts"} /></div></WizardStep>}
        {error && <InlineError message={error} />}
        <div className="wizard-actions"><button className="text-button" onClick={() => step ? setStep(step - 1) : navigate(-1)}>Back</button>{step < steps.length - 1 ? <button className="primary-button" disabled={step === 0 && !form.name.trim()} onClick={() => setStep(step + 1)}>Continue <Arrow /></button> : <button className="primary-button" disabled={busy} onClick={() => void submit()}>{busy ? "Bringing the team together…" : "Start my campaign"} <Arrow /></button>}</div>
      </section>
    </div>
  );
}

function ProfilePage() {
  const { profile, me, refresh } = useWorkspace();
  const [profileParams] = useSearchParams();
  const runId = `onboarding-${me.workspace.id}`.replace(/[^a-zA-Z0-9_-]/g, "-");
  const [status, setStatus] = useState<any>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [responding, setResponding] = useState(false);
  const [pendingMessage, setPendingMessage] = useState("");
  const [uploadedFiles, setUploadedFiles] = useState<Array<{ filename: string; size_bytes: number }>>([]);
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const [artifactContents, setArtifactContents] = useState<Record<string, any>>({});
  const [preparing, setPreparing] = useState(false);
  const [approving, setApproving] = useState(false);
  const [reviewConfirmed, setReviewConfirmed] = useState(false);
  const [promotionIssues, setPromotionIssues] = useState<any[]>([]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [refiningProfile, setRefiningProfile] = useState(profileParams.get("refine") === "1");

  const loadStatus = () => request<any>(`/onboarding/chat/${runId}/status`).then(setStatus).catch(() => undefined);
  const loadInputFiles = () => request<any>(`/onboarding/chat/${runId}/input-files`).then((result) => setUploadedFiles(result.files || [])).catch(() => undefined);
  const loadReview = async (nextArtifacts?: any[]) => {
    const reviewArtifacts = nextArtifacts || (await request<any>(`/onboarding/chat/${runId}/artifacts`)).artifacts || [];
    setArtifacts(reviewArtifacts);
    const available = reviewArtifacts.filter((artifact: any) => artifact.exists);
    const contents = await Promise.all(available.map((artifact: any) => request<any>(`/onboarding/chat/${runId}/artifacts/${encodeURIComponent(artifact.filename)}`)));
    setArtifactContents(Object.fromEntries(contents.map((content: any) => [content.filename, content.json_content])));
  };
  useEffect(() => { void loadStatus(); void loadInputFiles(); void loadReview().catch(() => undefined); }, []);
  const act = async (path: string, payload?: unknown) => { setBusy(true); setError(""); try { const result = await mutate<any>(`/onboarding/chat/${runId}/${path}`, "POST", payload); setStatus(result.session_state || status); await refresh(); return result; } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } };
  const beginRefinement = async () => {
    setRefiningProfile(true);
    await act("start");
  };
  const send = async (event: FormEvent) => {
    event.preventDefault();
    const text = message.trim();
    if (!text || responding) return;
    setMessage("");
    setPendingMessage(text);
    setResponding(true);
    setBusy(true);
    setError("");
    try {
      const result = await mutate<any>(`/onboarding/chat/${runId}/messages`, "POST", { message: text });
      setStatus(result.session_state || status);
      await refresh();
    } catch (cause) {
      setMessage(text);
      setError(messageOf(cause));
    } finally {
      setPendingMessage("");
      setResponding(false);
      setBusy(false);
    }
  };
  const uploadFile = async (file: File) => {
    setBusy(true);
    setError("");
    try {
      await request(`/onboarding/chat/${runId}/input-files/${encodeURIComponent(file.name)}`, { method: "PUT", headers: { "Content-Type": file.type || "application/octet-stream" }, body: file });
      await loadInputFiles();
    } catch (cause) {
      setError(messageOf(cause));
    } finally {
      setBusy(false);
    }
  };
  const prepareReview = async () => {
    setPreparing(true); setBusy(true); setError(""); setNotice(""); setPromotionIssues([]); setReviewConfirmed(false);
    try {
      const result = await mutate<any>(`/onboarding/chat/${runId}/finish`, "POST");
      setStatus(result.session_state || status);
      await loadReview(result.artifacts || []);
      if (result.import_result?.run?.status !== "imported") {
        setError("Your recruiter prepared the files, but backend validation found problems. Review the details below and continue the conversation to correct them.");
      } else {
        setNotice("Your review is ready. Check the summary and unresolved items below before approving it.");
      }
    } catch (cause) { setError(messageOf(cause)); }
    finally { setPreparing(false); setBusy(false); }
  };
  const requiredSnapshots = ["user_profile", "master_cv_profile", "policy"];
  const reviewReady = artifacts.length === 4 && artifacts.every((artifact: any) => artifact.exists && artifact.error_count === 0 && ["ready_for_review", "approved"].includes(artifact.status));
  const candidatesReady = requiredSnapshots.every((type) => artifacts.some((artifact: any) => artifact.snapshot_type === type && ["candidate", "approved"].includes(artifact.snapshot_status)));
  const canApprove = reviewReady && candidatesReady && reviewConfirmed && !busy;
  const approve = async () => {
    if (!canApprove) return;
    setApproving(true); setBusy(true); setError(""); setNotice(""); setPromotionIssues([]);
    try {
      const result = await mutate<any>(`/onboarding/runs/${runId}/promote`, "POST", { reviewer_id: String(me.id), confirm_user_profile: true, confirm_master_cv_profile: true, confirm_policy: true });
      if (result.status !== "approved") {
        setPromotionIssues(result.issues || []);
        setError("Approval is blocked. Nothing was approved; review the specific issues below.");
        return;
      }
      setNotice("Approved. Your profile is now the source of truth for your recruiter team.");
      await refresh();
      await loadReview();
    } catch (cause) { setError(messageOf(cause)); }
    finally { setApproving(false); setBusy(false); }
  };
  const entries = (status?.entries || []).filter((entry: any) => entry.role === "user" || entry.role === "assistant");
  const recruiterRunning = status?.status === "running" || status?.status === "waiting";

  return (
    <div className="page profile-page">
      <PageHeader eyebrow="The foundation for every application" title="Your story, understood once and used carefully" />
      {profile.has_approved_profile && !refiningProfile ? (
        <>
          <section className="profile-hero"><div><span className="approval-seal">✓</span><div><p className="eyebrow">Recruiter-approved foundation</p><h2>Your career story is ready for the team.</h2><p>Research, fit, CV, design, and writing specialists all work from this approved source. They cannot invent experience or claims.</p></div></div><div className="profile-hero-actions"><Link className="primary-button" to="/profile/view">View my profile</Link><button className="secondary-button" onClick={() => void beginRefinement()}>Update with my recruiter</button></div></section>
          <div className="profile-foundation-grid"><Link className="foundation-link" to="/profile/view?section=career"><FoundationCard index="01" title="Career identity" body="Verified experience, strengths, education, and approved claims." status="Approved" /></Link><Link className="foundation-link" to="/profile/view?section=direction"><FoundationCard index="02" title="Opportunity direction" body="Target roles, locations, preferences, and meaningful exclusions." status="Approved" /></Link><Link className="foundation-link" to="/profile/view?section=boundaries"><FoundationCard index="03" title="Voice and boundaries" body="How your team writes, what it emphasizes, and what it never claims." status="Approved" /></Link></div>
        </>
      ) : (
        <section className="onboarding-layout">
          <div className="onboarding-story"><p className="eyebrow">{profile.has_approved_profile ? "Refine your approved foundation" : "A thoughtful beginning"}</p><h2>{profile.has_approved_profile ? "Update your story with your recruiter." : "Talk with your onboarding recruiter."}</h2><p>{profile.has_approved_profile ? "Your current profile stays approved and in use until you review and approve the revised version." : "This is a conversation, not a long form. Share documents, answer naturally, and let the recruiter organize the details."}</p>{profile.has_approved_profile ? <button className="text-button" onClick={() => setRefiningProfile(false)}>Back to approved profile</button> : null}<div className="onboarding-promises"><span>One guided review at the end</span><span>Uncertain facts stay visibly flagged</span><span>Your approved claims become the source of truth</span></div></div>
          <div className="chat-card">
            <header><div><RoleAvatar letters="OR" active /><div><strong>Onboarding recruiter</strong><small>{status?.status === "running" ? "Listening" : "Ready when you are"}</small></div></div><StatusPill status={status?.status || "not started"} /></header>
            <div className="chat-uploads"><label className={busy ? "disabled" : ""}>+ Add CV or document<input type="file" disabled={busy} accept=".pdf,.doc,.docx,.txt,.md,.json" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadFile(file); event.currentTarget.value = ""; }} /></label><span>{uploadedFiles.length ? `${uploadedFiles.length} ${uploadedFiles.length === 1 ? "file" : "files"} shared` : "PDF, Word, or text - max 20 MB"}</span></div>
            {uploadedFiles.length ? <div className="chat-uploaded-files">{uploadedFiles.map((file) => <span key={file.filename} title={file.filename}>Uploaded: {file.filename}</span>)}</div> : null}
            <div className="chat-transcript">
              {entries.map((entry: any, index: number) => <div className={`chat-message ${entry.role === "user" ? "user" : "agent"}`} key={entry.id || index}><small>{entry.role === "user" ? "You" : "Your recruiter"}</small><p>{entry.content}</p></div>)}
              {pendingMessage && <div className="chat-message user pending"><small>You</small><p>{pendingMessage}</p><span>Sent</span></div>}
              {responding && <div className="chat-working" role="status" aria-live="polite"><i /><span>Your recruiter received your message and is working on a response...</span></div>}
              {!entries.length && !recruiterRunning && <div className="chat-welcome"><RoleAvatar letters="OR" /><h3>Let’s build the story your team can rely on.</h3><p>I’ll ask about your experience, what you want next, and any boundaries that matter. Uploading a CV helps, but it isn’t required.</p><button className="primary-button" disabled={busy} onClick={() => void act("start")}>{busy ? "Connecting…" : "Begin conversation"}</button></div>}
              {!entries.length && recruiterRunning && <div className="chat-welcome"><RoleAvatar letters="OR" active /><h3>Your recruiter is connected.</h3><p>If the first greeting has not appeared, reconnect the session or send a short introduction below.</p><button className="secondary-button" disabled={busy} onClick={() => void act("start")}>{busy ? "Reconnecting…" : "Reconnect recruiter"}</button></div>}
            </div>
            {entries.length || recruiterRunning ? <form className="chat-compose" onSubmit={(event) => void send(event)}><textarea rows={2} placeholder="Reply naturally…" value={message} onChange={(e) => setMessage(e.target.value)} /><button disabled={busy || !message.trim()}>Send</button></form> : null}
            {entries.length ? <footer className="onboarding-actions"><div><strong>1. Prepare</strong><small>The recruiter validates four draft files.</small></div><button className="primary-button" disabled={busy} onClick={() => void prepareReview()}>{preparing ? "Preparing your review..." : reviewReady ? "Prepare review again" : "Finish and prepare review"}</button></footer> : null}
            {preparing && <div className="onboarding-progress" role="status" aria-live="polite"><i /><div><strong>Preparing and validating your review</strong><span>This can take a few minutes. The review will appear here automatically.</span></div></div>}
            {notice && <div className="inline-success" role="status">{notice}</div>}
            {error && <div className="onboarding-error" role="alert"><InlineError message={error} /></div>}
          </div>
          {artifacts.some((artifact: any) => artifact.exists) ? <section className="onboarding-review" aria-labelledby="onboarding-review-title">
            <header><div><p className="eyebrow">Step 2 · Review</p><h2 id="onboarding-review-title">Review what your recruiter prepared</h2><p>These drafts are not used for tailoring until you approve them.</p></div><span className={`review-readiness ${reviewReady && candidatesReady ? "ready" : "blocked"}`}>{reviewReady && candidatesReady ? "Ready for your review" : "Needs correction"}</span></header>
            <div className="artifact-status-grid">{artifacts.map((artifact: any) => <article className={artifact.error_count ? "invalid" : "valid"} key={artifact.filename}><span>{artifact.error_count ? "!" : "✓"}</span><div><strong>{artifactLabel(artifact.filename)}</strong><small>{artifact.error_count ? `${artifact.error_count} validation ${artifact.error_count === 1 ? "issue" : "issues"}` : artifact.exists ? "Validated" : "Missing"}</small></div></article>)}</div>
            {artifacts.flatMap((artifact: any) => (artifact.errors || []).map((issue: any, index: number) => <div className="review-issue" key={`${artifact.filename}-${index}`}><strong>{artifactLabel(artifact.filename)}</strong><span>{issue.path ? `${issue.path}: ` : ""}{issue.message}</span></div>))}
            {artifactContents["user_profile.json"] && artifactContents["master_cv_profile.json"] && artifactContents["policy.json"] ? <ProfilePresentation userProfile={artifactContents["user_profile.json"]} masterCv={artifactContents["master_cv_profile.json"]} policy={artifactContents["policy.json"]} mode="candidate" /> : null}
            {artifactContents["onboarding_review.json"] ? <div className="review-documents"><details open><summary><span>Open questions</span><small>Items to resolve before or after approval</small></summary><pre>{JSON.stringify(artifactContents["onboarding_review.json"], null, 2)}</pre></details></div> : null}
            <div className="review-approval"><div><p className="eyebrow">Step 3 · Approve</p><h3>Make this your approved profile foundation</h3><p>Approval makes the validated profile, CV claims, and policy available to the recruiter team. Review flags remain visible and unapproved CV claims remain unavailable for tailoring.</p></div><label><input type="checkbox" checked={reviewConfirmed} disabled={!reviewReady || !candidatesReady || busy} onChange={(event) => setReviewConfirmed(event.target.checked)} /><span>I reviewed the prepared profile, CV claims, policy, and open questions.</span></label><button className="primary-button" disabled={!canApprove} onClick={() => void approve()}>{approving ? "Approving..." : "Approve my profile"}</button>{!reviewReady || !candidatesReady ? <small>Approval unlocks after all four files pass validation and the three candidate snapshots are ready.</small> : null}</div>
            {promotionIssues.map((issue: any, index: number) => <div className="review-issue" key={`${issue.code}-${index}`}><strong>{issue.snapshot_type ? artifactLabel(`${issue.snapshot_type}.json`) : "Approval"}</strong><span>{issue.field ? `${issue.field}: ` : ""}{issue.message}</span></div>)}
          </section> : null}
        </section>
      )}
    </div>
  );
}

function artifactLabel(filename: string) {
  return ({ "user_profile.json": "Career profile", "master_cv_profile.json": "Master CV claims", "policy.json": "Search and outreach policy", "onboarding_review.json": "Open questions" } as Record<string, string>)[filename] || filename.replaceAll("_", " ").replace(".json", "");
}

function ProfileViewerPage() {
  const [bundle, setBundle] = useState<ApprovedProfileBundle | null>(null);
  const [error, setError] = useState("");
  const [params] = useSearchParams();
  useEffect(() => {
    request<ApprovedProfileBundle>("/profile/approved").then(setBundle).catch((cause) => setError(messageOf(cause)));
  }, []);
  useEffect(() => {
    if (!bundle) return;
    const section = params.get("section");
    if (section) document.getElementById(`profile-${section}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [bundle, params]);

  if (error) return <div className="page"><PageHeader eyebrow="Your approved foundation" title="Your profile could not be opened" /><InlineError message={error} /><Link className="secondary-button" to="/profile">Back to My story</Link></div>;
  if (!bundle) return <InlineLoading />;
  const updatedAt = [bundle.user_profile.snapshot.created_at, bundle.master_cv_profile.snapshot.created_at, bundle.policy.snapshot.created_at].sort().at(-1);
  return (
    <div className="page profile-viewer-page">
      <PageHeader eyebrow="Your approved foundation" title="The story your recruiter team works from" aside={<div className="profile-viewer-actions"><Link className="secondary-button" to="/profile">Back to My story</Link><Link className="primary-button" to="/profile?refine=1">Update with my recruiter</Link></div>} />
      <div className="profile-viewer-meta"><span>✓ Approved source of truth</span>{updatedAt ? <small>Last prepared {new Date(updatedAt).toLocaleDateString()}</small> : null}</div>
      <ProfilePresentation userProfile={bundle.user_profile.content} masterCv={bundle.master_cv_profile.content} policy={bundle.policy.content} mode="approved" />
    </div>
  );
}

function ProfilePresentation({ userProfile, masterCv, policy, mode }: { userProfile: Record<string, any>; masterCv: Record<string, any>; policy: Record<string, any>; mode: "approved" | "candidate" }) {
  const identity = userProfile.identity || {};
  const preferences = userProfile.preferences || {};
  const claims = Array.isArray(masterCv.claims) ? masterCv.claims : [];
  const claimGroups = claims.reduce((groups: Record<string, any[]>, claim: any) => {
    (groups[claim.category || "other"] ||= []).push(claim);
    return groups;
  }, {});
  const exclusions = policy.exclusions || {};
  const reviewItems = Array.isArray(userProfile.review_items) ? userProfile.review_items : [];
  const needsReviewClaims = claims.filter((claim: any) => claim.provenance?.needs_review || !claim.approved_for_tailoring);
  return (
    <div className={`profile-presentation ${mode}`}>
      <section className="profile-identity" id="profile-career">
        <div><p className="eyebrow">Career identity</p><h2>{identity.display_name || "Your career profile"}</h2>{identity.headline ? <p className="profile-headline">{identity.headline}</p> : null}<div className="identity-details">{identity.location ? <span>Location · {identity.location}</span> : null}{identity.email ? <span>{identity.email}</span> : null}{identity.phone ? <span>{identity.phone}</span> : null}</div>{Array.isArray(identity.links) && identity.links.length ? <div className="profile-links">{identity.links.map((link: string) => <a href={link} target="_blank" rel="noreferrer" key={link}>{link.replace(/^https?:\/\//, "")}</a>)}</div> : null}</div>
        <SourceJson title="Career profile source JSON" value={userProfile} />
      </section>

      <section className="profile-section" id="profile-direction"><SectionHeading eyebrow="Direction" title="What you want next" body="The preferences your recruiter uses when deciding where to look and how to represent you." /><div className="profile-fact-grid"><ProfileValues title="Target roles" values={preferences.target_roles} /><ProfileValues title="Target locations" values={preferences.target_locations} /><ProfileValues title="Remote preferences" values={preferences.remote_preferences} /><ProfileValues title="Relocation" values={preferences.relocation_preferences} /><ProfileValues title="Work authorization" values={userProfile.work_authorization} /><ProfileValues title="Languages" values={userProfile.languages} language /><ProfileValues title="Availability" values={preferences.availability ? [preferences.availability] : []} /><ProfileValues title="Communication tone" values={preferences.communication_tone ? [preferences.communication_tone] : []} /></div></section>

      <section className="profile-section"><SectionHeading eyebrow="Approved evidence" title="Career claims your team can use" body="Claims are grouped for quick reading. Tailoring status determines whether a claim may appear in applications." />{Object.keys(claimGroups).length ? <div className="claim-groups">{Object.entries(claimGroups).map(([category, items]) => <div className="claim-group" key={category}><h3>{human(category)}</h3>{(items as any[]).map((claim: any) => <article className="claim-card" key={claim.claim_id}><div className="claim-card-top"><div>{claim.role ? <strong>{claim.role}</strong> : null}{claim.organization ? <span>{claim.organization}</span> : null}</div><span className={claim.approved_for_tailoring ? "tailoring-status approved" : "tailoring-status blocked"}>{claim.approved_for_tailoring ? "Usable in applications" : "Not approved for tailoring"}</span></div><p>{claim.statement}</p>{claim.start_date || claim.end_date ? <small>{[claim.start_date, claim.end_date || "Present"].filter(Boolean).join(" – ")}</small> : null}{Array.isArray(claim.tags) && claim.tags.length ? <div className="tag-row">{claim.tags.map((tag: string) => <span key={tag}>{tag}</span>)}</div> : null}<Evidence provenance={claim.provenance} /></article>)}</div>)}</div> : <p className="profile-empty-copy">No career claims are recorded yet.</p>}<SourceJson title="Master CV source JSON" value={masterCv} /></section>

      <section className="profile-section" id="profile-boundaries"><SectionHeading eyebrow="Boundaries and safeguards" title="How your recruiter must work" body="Exclusions and deterministic outreach limits remain in force for every campaign." /><div className="boundary-grid"><div className="boundary-card"><h3>Meaningful exclusions</h3>{["industries", "company_names", "domains", "keywords"].map((group) => <PolicyItems key={group} title={human(group)} items={exclusions[group]} />)}</div><div className="boundary-card"><h3>Outreach rules</h3><PolicyRule label="Daily send limit" value={policy.limits?.daily_send_limit} /><PolicyRule label="Weekly send limit" value={policy.limits?.weekly_send_limit} /><PolicyRule label="Company repeat" value={policy.outreach?.allow_company_repeat ? "Allowed within policy" : `Blocked for ${policy.outreach?.company_dedupe_window_days ?? 0} days`} /><PolicyRule label="Recipient repeat" value={policy.outreach?.allow_recipient_repeat ? "Allowed within policy" : `Blocked for ${policy.outreach?.recipient_dedupe_window_days ?? 0} days`} /><PolicyRule label="Manual review before send" value={policy.outreach?.require_manual_review_before_send ? "Required" : "Not required"} /><PolicyRule label="Minimum confidence" value={policy.review_thresholds?.minimum_required_confidence !== undefined ? `${Math.round(policy.review_thresholds.minimum_required_confidence * 100)}%` : undefined} /></div>{Array.isArray(policy.forbidden_claims) && policy.forbidden_claims.length ? <div className="boundary-card wide"><h3>Claims your team must never make</h3><ul>{policy.forbidden_claims.map((claim: string) => <li key={claim}>{claim}</li>)}</ul></div> : null}</div><SourceJson title="Policy source JSON" value={policy} /></section>

      {reviewItems.length || needsReviewClaims.length ? <section className="profile-attention"><p className="eyebrow">Needs attention</p><h2>Details that remain visible for review</h2>{reviewItems.map((item: any, index: number) => <div key={`${item.field}-${index}`}><strong>{human(item.field || "Profile item")}</strong><span>{item.reason}</span></div>)}{needsReviewClaims.map((claim: any) => <div key={claim.claim_id}><strong>{human(claim.category || "Claim")}</strong><span>{claim.statement}</span></div>)}</section> : null}
    </div>
  );
}

function SectionHeading({ eyebrow, title, body }: { eyebrow: string; title: string; body: string }) { return <header className="profile-section-heading"><p className="eyebrow">{eyebrow}</p><h2>{title}</h2><p>{body}</p></header>; }
function SourceJson({ title, value }: { title: string; value: unknown }) { return <details className="source-json"><summary>View source JSON</summary><div><strong>{title}</strong><pre>{JSON.stringify(value, null, 2)}</pre></div></details>; }
function ProfileValues({ title, values, language = false }: { title: string; values: any; language?: boolean }) {
  const list = Array.isArray(values) ? values : [];
  if (!list.length) return null;
  return <article className="profile-fact"><h3>{title}</h3>{list.map((item: any, index: number) => <div className="profile-fact-value" key={`${item?.value || item?.language || item}-${index}`}><span>{language ? `${item.language}${item.level ? ` · ${item.level}` : ""}` : typeof item === "string" ? item : item.value}</span><Evidence provenance={item?.provenance} /></div>)}</article>;
}
function Evidence({ provenance }: { provenance?: any }) {
  if (!provenance) return null;
  const labels: Record<string, string> = { verified_document: "Verified", user_claim: "User-provided", inferred: "Inferred", needs_review: "Needs review" };
  return <details className={`evidence ${provenance.needs_review ? "review" : ""}`}><summary>{labels[provenance.source_type] || human(provenance.source_type || "Evidence")}</summary><div><span>Confidence {Math.round(Number(provenance.confidence || 0) * 100)}%</span>{Array.isArray(provenance.source_refs) && provenance.source_refs.length ? <ul>{provenance.source_refs.map((source: string) => <li key={source}>{source}</li>)}</ul> : <span>No source reference recorded</span>}</div></details>;
}
function PolicyItems({ title, items }: { title: string; items: any }) { if (!Array.isArray(items) || !items.length) return null; return <div className="policy-items"><strong>{title}</strong>{items.map((item: any, index: number) => <div key={`${item.value}-${index}`}><span>{item.value}</span>{item.reason ? <small>{item.reason}</small> : null}<Evidence provenance={item.provenance} /></div>)}</div>; }
function PolicyRule({ label, value }: { label: string; value: unknown }) { if (value === undefined || value === null) return null; return <div className="policy-rule"><span>{label}</span><strong>{String(value)}</strong></div>; }

function DocumentsPage() {
  const { documents } = useWorkspace();
  const [searchParams, setSearchParams] = useSearchParams();
  const [selected, setSelected] = useState<DocumentItem | null>(null);
  const [filter, setFilter] = useState<"all" | "cv" | "email" | "profile">("all");
  const [query, setQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(24);
  const companyRef = searchParams.get("company")?.trim() || "";
  const companyId = Number(companyRef);
  const companyName = searchParams.get("companyName") || "this company";
  const hasCompanyScope = Boolean(companyRef);
  const availableDocuments = useMemo(
    () => {
      if (!hasCompanyScope) return documents;
      if (Number.isFinite(companyId) && companyId > 0) {
        return documents.filter((document) => document.company_id === companyId);
      }

      // Older/imported company records can expose only their stable string ID.
      // Document rows currently carry the internal numeric ID, so retain a
      // deterministic company-name fallback instead of dropping the scope.
      const normalizedCompanyName = companyName.trim().toLocaleLowerCase();
      return documents.filter((document) =>
        normalizedCompanyName !== "this company"
        && `${document.title} ${document.filename}`.toLocaleLowerCase().includes(normalizedCompanyName),
      );
    },
    [companyId, companyName, documents, hasCompanyScope],
  );
  const cvCount = availableDocuments.filter((document) => document.type === "tailored_cv").length;
  const emailCount = availableDocuments.filter((document) => document.type === "email_draft").length;
  const filteredDocuments = useMemo(() => {
    const profileTypes = new Set(["career_profile", "master_cv_profile", "outreach_policy"]);
    const needle = query.trim().toLocaleLowerCase();
    return availableDocuments.filter((document) => {
      const inCategory = filter === "all"
        || (filter === "cv" && document.type === "tailored_cv")
        || (filter === "email" && document.type === "email_draft")
        || (filter === "profile" && profileTypes.has(document.type));
      return inCategory && (!needle || `${document.title} ${document.filename} ${document.type}`.toLocaleLowerCase().includes(needle));
    });
  }, [availableDocuments, filter, query]);
  const selectFilter = (next: typeof filter) => { setFilter(next); setVisibleCount(24); };
  const visibleDocuments = filteredDocuments.slice(0, visibleCount);
  return (
    <div className="page documents-page">
      <PageHeader eyebrow={hasCompanyScope ? "Complete application file" : "Prepared by your application team"} title={hasCompanyScope ? `Documents prepared for ${companyName}` : "Every document, ready when you need it"} />
      {hasCompanyScope && <div className="document-scope"><div><span>Showing only</span><strong>{companyName}</strong><small>{availableDocuments.length} related {availableDocuments.length === 1 ? "document" : "documents"}</small></div><button onClick={() => { setSearchParams({}); setFilter("all"); setQuery(""); setVisibleCount(24); }}>Show all documents</button></div>}
      <div className="document-filter" aria-label="Document filters">
        <button className={filter === "all" ? "active" : ""} onClick={() => selectFilter("all")}>All <b>{availableDocuments.length}</b></button>
        <button className={filter === "cv" ? "active" : ""} onClick={() => selectFilter("cv")}>Tailored CVs <b>{cvCount}</b></button>
        <button className={filter === "email" ? "active" : ""} onClick={() => selectFilter("email")}>Emails <b>{emailCount}</b></button>
        {!hasCompanyScope && <button className={filter === "profile" ? "active" : ""} onClick={() => selectFilter("profile")}>My profile</button>}
        <label className="document-search"><span>Search documents</span><input type="search" placeholder="Find a company or document" value={query} onChange={(event) => { setQuery(event.target.value); setVisibleCount(24); }} /></label>
        <span>{filteredDocuments.length} {filteredDocuments.length === 1 ? "file" : "files"}</span>
      </div>
      {filteredDocuments.length ? <><div className="document-grid">{visibleDocuments.map((document) => <button className="document-card" key={document.id} onClick={() => setSelected(document)}><div className={`document-preview ${document.type}`}><span>{documentBadge(document)}</span><div className="paper-lines"><i /><i /><i /><i /></div></div><div><p className="eyebrow">{human(document.type)}</p><h3>{document.title}</h3><p>{formatBytes(document.size_bytes)} · {new Date(document.created_at).toLocaleDateString()}</p></div></button>)}</div>{visibleCount < filteredDocuments.length && <div className="document-more"><button className="secondary-button" onClick={() => setVisibleCount((count) => count + 24)}>Show 24 more</button><span>{visibleDocuments.length} of {filteredDocuments.length}</span></div>}</> : <EmptyState title={query ? "No matching documents" : "Nothing in this category yet"} body={query ? "Try a company name, email subject, or another document type." : "Your application team will place finished work here automatically."} />}
      {selected && <div className="document-modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && setSelected(null)}><section className="document-modal"><header><div><p className="eyebrow">{human(selected.type)}</p><h2>{selected.title}</h2></div><div className="document-modal-actions">{selected.download_url && <a href={selected.download_url} target="_blank" rel="noreferrer">Open PDF ↗</a>}<button onClick={() => setSelected(null)} aria-label="Close document">×</button></div></header><iframe title={selected.title} src={selected.preview_url} /></section></div>}
    </div>
  );
}

function ExceptionsPage() {
  const { exceptions, refresh } = useWorkspace();
  const [busy, setBusy] = useState("");
  const resolve = async (item: ExceptionItem, action: "retry" | "skip") => { setBusy(item.id); try { await mutate(`/exceptions/${item.id}/resolve`, "POST", { action }); await refresh(); } finally { setBusy(""); } };
  return (
    <div className="page exceptions-page">
      <PageHeader eyebrow="Only when your judgment matters" title="A short inbox, not another task list" />
      <section className="exception-intro"><div><strong>{exceptions.length}</strong><span>{exceptions.length === 1 ? "decision" : "decisions"} waiting</span></div><p>Your team already retried what it could. These items need a preference, a corrected fact, or permission to move on.</p></section>
      {exceptions.length ? <div className="exception-list">{exceptions.map((item) => <article className="exception-card" key={item.id}><div className="exception-icon">!</div><div className="exception-content"><p className="eyebrow">{human(item.category)}</p>{item.company_name ? <h3 className="exception-company">{item.company_name}</h3> : null}<strong className="exception-title">{item.title}</strong><p>{item.explanation}</p><div className="recommendation"><strong>Your recruiter recommends</strong><span>{item.recommended_action}</span></div><div className="exception-actions"><button className="primary-button" disabled={busy === item.id} onClick={() => void resolve(item, "retry")}>Retry with this guidance</button><button className="text-button" disabled={busy === item.id} onClick={() => void resolve(item, "skip")}>Skip this company</button></div></div></article>)}</div> : <EmptyState title="Nothing needs you right now" body="Your specialists are continuing independently. Genuine exceptions will appear here with a recommendation." />}
    </div>
  );
}

function SettingsPage() {
  const { me, delivery, refresh } = useWorkspace();
  const [busy, setBusy] = useState(false);
  const [connectionError, setConnectionError] = useState("");
  const connect = async () => { setBusy(true); setConnectionError(""); try { const result = await mutate<{ authorization_url: string }>("/auth/google/gmail/start", "POST"); window.location.href = result.authorization_url; } catch (cause) { setConnectionError(messageOf(cause)); } finally { setBusy(false); } };
  const disconnect = async () => { setBusy(true); try { await mutate("/gmail/connection", "DELETE"); await refresh(); } finally { setBusy(false); } };
  const canConnect = delivery.gmail_connection_available;
  const localFileConnection = delivery.gmail_connection_source === "local_file";
  const connectionCopy = localFileConnection
    ? "Using the existing Gmail token configured in your local .env. No additional Google sign-in is required."
    : canConnect
      ? "Sign-in and sending consent stay separate. Agents never receive access to your credentials."
      : "Add the Google OAuth client ID and secret to the local environment before connecting this workspace.";
  return <div className="page settings-page"><PageHeader eyebrow="Your workspace" title="Simple controls for how your recruiter works" /><div className="settings-grid"><section className="settings-card"><p className="eyebrow">Account</p><h3>{me.display_name}</h3><p>{me.email}</p>{me.local_registration_enabled && <a className="secondary-button account-create-link" href="/register">Create or switch local account</a>}<div className="setting-status"><span>Private workspace</span><b>Active</b></div></section><section className="settings-card"><p className="eyebrow">Sending connection</p><h3>{delivery.gmail_configured ? "Gmail is connected" : canConnect ? "Connect Gmail when you are ready" : "Gmail connection needs configuration"}</h3><p>{connectionCopy}</p>{delivery.gmail_configured && !localFileConnection ? <button className="secondary-button" disabled={busy} onClick={() => void disconnect()}>Disconnect Gmail</button> : !delivery.gmail_configured ? <button className="primary-button" disabled={busy || !canConnect} onClick={() => void connect()}>Connect Gmail</button> : null}{connectionError && <InlineError message={connectionError} />}</section><section className="settings-card wide"><p className="eyebrow">Delivery boundary</p><h3>Deterministic checks always stay in control.</h3><p>Autopilot campaigns can remove repetitive confirmations, but they cannot bypass dedupe, source, claim, attachment, limit, policy, reservation, or audit checks.</p><div className="guardrail-row">{["Duplicate protection", "Approved claims", "Send limits", "Audit trail"].map((label) => <span key={label}>✓ {label}</span>)}</div></section></div></div>;
}

function AdminPage() {
  const { me } = useWorkspace();
  const [workspaces, setWorkspaces] = useState<any[]>([]);
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => { if (me.role === "admin") request<any[]>("/admin/workspaces").then(setWorkspaces); }, [me.role]);
  if (me.role !== "admin") return <Navigate to="/" />;
  const invite = async (event: FormEvent) => { event.preventDefault(); await mutate("/admin/invitations", "POST", { email }); setMessage(`${email} can now sign in with Google.`); setEmail(""); };
  return <div className="page admin-page"><PageHeader eyebrow="Administration" title="Invites and audited workspace support" /><div className="admin-grid"><section className="panel"><PanelHeading eyebrow="Invite-only access" title="Add a user" /><form className="invite-form" onSubmit={(e) => void invite(e)}><input type="email" required placeholder="person@example.com" value={email} onChange={(e) => setEmail(e.target.value)} /><button className="primary-button">Allow Google sign-in</button></form>{message && <p className="success-message">{message}</p>}</section><section className="panel"><PanelHeading eyebrow="Workspaces" title={`${workspaces.length} private accounts`} /><div className="workspace-list">{workspaces.map((workspace) => <div key={workspace.id}><Avatar name={workspace.name} /><span><strong>{workspace.name}</strong><small>{workspace.owner_email}</small></span><StatusPill status={workspace.status} /></div>)}</div></section></div><p className="admin-notice">Administrator inspection is read-only and every cross-workspace access is recorded.</p></div>;
}

function NavItem({ to, label, icon, count, accent, end }: { to: string; label: string; icon: string; count?: number; accent?: boolean; end?: boolean }) {
  return <NavLink to={to} end={end} className={({ isActive }) => `${isActive ? "active" : ""} ${accent && count ? "attention" : ""}`}><span className="nav-icon">{icon}</span><span>{label}</span>{count ? <b>{count}</b> : null}</NavLink>;
}

function Brand() { return <Link className="brand" to="/"><span className="brand-mark"><i /><i /></span><span><strong>Auto Initiativ</strong><small>Personal recruiter</small></span></Link>; }
function PageHeader({ eyebrow, title, aside }: { eyebrow: string; title: string; aside?: ReactNode }) { return <header className="page-header"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1></div>{aside}</header>; }
function PanelHeading({ eyebrow, title, action }: { eyebrow: string; title: string; action?: ReactNode }) { return <header className="panel-heading"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div>{action}</header>; }
function AgentConstellation({ tasks }: { tasks: AgentTask[] }) { const roles = tasks.length ? tasks.slice(0, 4) : [{ id: "research", agent_role: "company_researcher", status: "ready", progress: 0, narrative: "" }, { id: "fit", agent_role: "fit_specialist", status: "ready", progress: 0, narrative: "" }, { id: "cv", agent_role: "cv_specialist", status: "ready", progress: 0, narrative: "" }, { id: "write", agent_role: "email_writer", status: "ready", progress: 0, narrative: "" }]; return <div className="agent-constellation"><div className="constellation-orbit" />{roles.map((role, index) => <div className={`orbit-agent agent-${index + 1}`} key={role.id}><RoleAvatar letters={roleLetters(role.agent_role)} active={role.status === "running"} /><span>{roleName(role.agent_role)}</span></div>)}<div className="constellation-center"><span>AI</span><small>Your team</small></div></div>; }
function AgentActivity({ task }: { task: AgentTask }) { return <article className="agent-activity"><RoleAvatar letters={roleLetters(task.agent_role)} active={task.status === "running"} /><div><div><strong>{roleName(task.agent_role)}</strong><StatusPill status={task.status} /></div><p>{task.narrative}</p><div className="progress-track"><span style={{ width: `${task.progress}%` }} /></div></div><b>{task.progress}%</b></article>; }
function RoleAvatar({ letters, active }: { letters: string; active?: boolean }) { return <span className={`role-avatar ${active ? "active" : ""}`}>{letters}<i /></span>; }
function RoleBadge({ role }: { role: string }) { return <div className="role-badge"><RoleAvatar letters={role.slice(0, 2).toUpperCase()} /><span>{role}</span></div>; }
function Avatar({ name, src }: { name: string; src?: string | null }) { return src ? <img className="avatar" src={src} alt="" /> : <span className="avatar">{initials(name)}</span>; }
function CompanyMark({ name, large }: { name: string; large?: boolean }) { return <span className={`company-mark ${large ? "large" : ""}`} style={{ "--company-hue": hueFor(name) } as any}>{initials(name)}</span>; }
function Metric({ value, label, tone }: { value: number; label: string; tone: string }) { return <div className={`metric ${tone}`}><strong>{value}</strong><span>{label}</span></div>; }
function StatusPill({ status }: { status: string }) { return <span className={`status-pill ${status.replaceAll("_", "-")}`}><i />{human(status)}</span>; }
function DrawerSection({ title, children }: { title: string; children: ReactNode }) { return <section className="drawer-section"><h3>{title}</h3>{children}</section>; }
function WizardStep({ eyebrow, title, body, children }: { eyebrow: string; title: string; body: string; children: ReactNode }) { return <div className="wizard-step"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="wizard-lead">{body}</p><div className="wizard-fields">{children}</div></div>; }
function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="field"><span>{label}</span>{children}</label>; }
function ReviewRow({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value}</strong></div>; }
function FoundationCard({ index, title, body, status }: { index: string; title: string; body: string; status: string }) { return <article className="foundation-card"><span>{index}</span><h3>{title}</h3><p>{body}</p><small>✓ {status}</small></article>; }
function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) { return <div className="empty-state"><span className="empty-orbit"><i /></span><h3>{title}</h3><p>{body}</p>{action}</div>; }
function Arrow() { return <span aria-hidden="true">→</span>; }
function InlineLoading() { return <div className="inline-loading"><i /><span>Gathering your recruiter’s latest work…</span></div>; }
function InlineError({ message }: { message: string }) { return <div className="inline-error">{message}</div>; }
function LoadingScreen() { return <main className="loading-screen"><Brand /><div className="loading-orbit"><i /><i /><span>AI</span></div><p>Bringing your recruiter team together…</p></main>; }
function FatalError({ message, retry }: { message: string; retry: () => Promise<void> }) { return <main className="fatal-error"><Brand /><h1>Your workspace could not be opened.</h1><p>{message}</p><button className="primary-button" onClick={() => void retry()}>Try again</button></main>; }

function heroEyebrow(kind: string) { return kind === "profile" ? "Your first conversation" : kind === "campaign" ? "Your team is assembled" : kind === "history" ? "Your existing work is here" : kind === "exceptions" ? "A little guidance needed" : "Your search is moving"; }
function heroTitle(kind: string, campaign: Campaign | null, exceptions: number) { if (kind === "profile") return "Let’s give your recruiter the full picture."; if (kind === "campaign") return "Ready to discover where you belong next."; if (kind === "history") return "Your search history is ready to pick up."; if (kind === "exceptions") return `${exceptions} ${exceptions === 1 ? "decision needs" : "decisions need"} your judgment.`; return campaign ? `Your team is advancing “${campaign.name}.”` : "Your specialists are working quietly."; }
function heroBody(kind: string, campaign: Campaign | null) { if (kind === "profile") return "A dedicated onboarding agent will learn your experience, priorities, voice, and boundaries—then prepare one clear summary for your approval."; if (kind === "campaign") return "Give your recruiter a simple direction once. Research, fit analysis, CV tailoring, design, and email writing will happen as coordinated handoffs."; if (kind === "history") return "Your discovered companies, prepared applications, and sent outreach are organized in one workspace. Start a new campaign whenever you want the agent team to continue."; if (kind === "exceptions") return "Your agents already tried to resolve these items. Each one comes with a concise explanation and a recommended next move."; return campaign?.sending_mode === "gated_autosend" ? "Research and preparation continue automatically. Outreach can leave only after the backend’s deterministic checks pass." : "Research and preparation continue automatically. Every finished application will collect in your document library."; }
function dayPart() { const hour = new Date().getHours(); return hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening"; }
function roleName(role: string) { const names: Record<string, string> = { company_researcher: "Research specialist", fit_specialist: "Fit analyst", cv_specialist: "CV specialist", resume_and_email_team: "Application team", email_writer: "Email writer", delivery_coordinator: "Delivery coordinator", onboarding_recruiter: "Onboarding recruiter" }; return names[role] || human(role); }
function roleLetters(role: string) { return roleName(role).split(" ").map((word) => word[0]).join("").slice(0, 2).toUpperCase(); }
function human(value: string) { return value.replaceAll("_", " ").replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function sumValues(values: Record<string, number>) { return Object.values(values).reduce((sum, value) => sum + Number(value || 0), 0); }
function initials(name: string) { return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join(""); }
function hueFor(value: string) { return [...value].reduce((sum, char) => sum + char.charCodeAt(0), 0) % 280 + 30; }
function toStrings(values: unknown[] | undefined) { return (values || []).map((value) => typeof value === "string" ? value : typeof value === "object" && value ? String((value as any).text || (value as any).name || "") : "").filter(Boolean); }
function normalizeCompany(company: Company): Company { return { ...company, id: company.id || company.company_id, domain: company.domain || company.normalized_domain, industry_tags: company.industry_tags || [], locations: company.locations || [] }; }
function formatBytes(size: number) { return size < 1024 ? `${size} B` : size < 1024 * 1024 ? `${(size / 1024).toFixed(1)} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`; }
function documentBadge(document: DocumentItem) { if (document.mime_type === "application/pdf") return "PDF"; if (document.type === "email_draft") return "EMAIL"; if (["career_profile", "master_cv_profile", "outreach_policy"].includes(document.type)) return "PROFILE"; return "DOC"; }
function messageOf(cause: unknown) { return cause instanceof Error ? cause.message : String(cause); }
