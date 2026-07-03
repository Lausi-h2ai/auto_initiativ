const endpoints = {
  summary: "/dashboard/summary",
  profile: "/profile/summary",
  delivery: "/email-delivery/settings",
  companies: "/companies",
  contacts: "/contacts",
  fitEvaluations: "/fit-evaluations",
  emailDrafts: "/email-drafts",
  outboxDrafts: "/outbox/drafts",
  outboxSent: "/outbox/sent",
  sendIntents: "/send-intents",
  gateResults: "/gate-results",
  runs: "/runs",
  auditLogs: "/audit-logs",
  outreachRecords: "/outreach-records",
  sentMessages: "/sent-messages",
  companyResearch: "/campaigns/company-research",
  applicationDrafts: "/application-drafts",
  applicationDraftBatches: "/application-drafts/batches",
  outboxSendAll: "/outbox/send-all",
  gateEvaluationPrefix: "/gate/evaluations/",
};

const endpointCoverageReferences = [
  "/dashboard/summary",
  "/profile/summary",
  "/campaigns/company-research",
  "/campaigns/company-research/",
  "/application-drafts",
  "/application-drafts/",
  "/application-drafts/batches",
  "/launch",
  "/status",
  "/runs",
  "/onboarding/chat/",
  "/onboarding/runs/",
  "/artifacts",
  "/input-files",
  "/import-artifacts",
  "/promote",
  "/companies",
  "/contacts",
  "/fit-evaluations",
  "/email-drafts",
  "/outbox/drafts",
  "/outbox/sent",
  "/outbox/send-all",
  "/send-intents",
  "/gate/evaluations/",
  "/gate-results",
  "/outreach-records",
  "/audit-logs",
];

const primaryRoutes = [
  { id: "home", label: "Home" },
  { id: "profile", label: "Profile" },
  { id: "companies", label: "Companies" },
  { id: "applications", label: "Applications" },
];

const journeyStages = [
  { id: "profile", label: "Profile", description: "Build career context" },
  { id: "discover", label: "Discover", description: "Find good companies" },
  { id: "prepare", label: "Prepare", description: "Tailor applications" },
  { id: "send", label: "Send", description: "Approve outreach" },
];

const advancedSections = [
  { id: "companies", label: "Companies", endpoint: "/companies", columns: ["name", "company_id", "normalized_domain", "confidence", "send_gate_status"] },
  { id: "contacts", label: "Contacts", endpoint: "/contacts", columns: ["name", "contact_id", "external_company_id", "normalized_recipient_email", "confidence"] },
  { id: "fit", label: "Fit evaluations", endpoint: "/fit-evaluations", columns: ["evaluation_id", "external_company_id", "decision", "fit_score", "confidence"] },
  { id: "drafts", label: "Email drafts", endpoint: "/email-drafts", columns: ["draft_id", "external_company_id", "external_contact_id", "subject", "confidence"] },
  { id: "send-intents", label: "Send intents", endpoint: endpoints.sendIntents, columns: ["intent_id", "external_company_id", "normalized_recipient_email", "status", "confidence"] },
  { id: "gate-results", label: "Gate results", endpoint: "/gate-results", columns: ["gate_result_id", "external_intent_id", "status", "external_reservation_id", "evaluated_at"] },
  { id: "runs", label: "Runs", endpoint: "/runs", columns: ["run_id", "agent_type", "status", "output_path", "updated_at"] },
  { id: "outreach", label: "Outreach records", endpoint: "/outreach-records", columns: ["outreach_record_id", "normalized_recipient_email", "company_policy_key", "status", "occurred_at"] },
  { id: "sent", label: "Sent messages", endpoint: "/sent-messages", columns: ["sent_message_id", "external_company_id", "normalized_recipient_email", "status", "accepted_at"] },
  { id: "audit", label: "Audit logs", endpoint: "/audit-logs?limit=200", columns: ["action", "entity_type", "entity_id", "result_status", "created_at"] },
];

const state = {
  route: routeFromHash().route,
  routeDetail: routeFromHash().detail,
  data: null,
  loading: false,
  selectedCompanyId: null,
  guidedCompanyReviewId: null,
  researchDraft: null,
  researchStep: Number.parseInt(localStorage.getItem("guidedResearchStep") || "0", 10) || 0,
  launchInFlight: false,
  selectedDraftId: null,
  activeApplicationTab: "review",
  activeCompanyStage: "all",
  companySearch: "",
  companySort: "best",
  activeAdvancedSection: "companies",
  advancedRows: [],
  advancedSelectedIndex: 0,
  onboardingRunId: localStorage.getItem("onboardingRunId") || "onboarding-local",
  campaignRunId: localStorage.getItem("companyResearchRunId") || "",
  companyResearchPoll: null,
  applicationDraftPoll: null,
  lastApplicationRunId: localStorage.getItem("applicationDraftRunId") || "",
};

const RESEARCH_DRAFT_KEY = "guidedResearchBriefDraft";
const RESEARCH_BRIEF_KEY = "guidedResearchLastBrief";
const COMPANY_DECISIONS_KEY = "guidedCompanyDecisions";

const guidedResearchSteps = [
  { id: "location", label: "Location", question: "Where should your recruiter look?" },
  { id: "roles", label: "Role direction", question: "What kind of work should we prioritize?" },
  { id: "preferences", label: "Company preferences", question: "What kinds of companies should stand out?" },
  { id: "scope", label: "Search scope", question: "How broad should this search be?" },
  { id: "review", label: "Review brief", question: "Review the recruiter brief." },
];

const scopePresets = {
  focused: { label: "Focused", count: 15, minutes: 20, detail: "A tight pass for the strongest nearby matches." },
  balanced: { label: "Balanced", count: 30, minutes: 30, detail: "A practical search with enough range for comparison." },
  broad: { label: "Broad", count: 50, minutes: 60, detail: "A wider search when you want more options." },
};

const elements = {
  nav: document.querySelector("#primaryNav"),
  journey: document.querySelector("#journey"),
  page: document.querySelector("#page"),
  refresh: document.querySelector("#refreshButton"),
  accountButton: document.querySelector("#accountButton"),
  accountMenu: document.querySelector("#accountMenu"),
  environmentChip: document.querySelector("#environmentChip"),
  toast: document.querySelector("#toast"),
  modalBackdrop: document.querySelector("#modalBackdrop"),
  modalTitle: document.querySelector("#modalTitle"),
  modalBody: document.querySelector("#modalBody"),
  modalClose: document.querySelector("#modalClose"),
};

function init() {
  renderNav();
  elements.refresh.addEventListener("click", () => loadAndRender({ force: true }));
  elements.accountButton.addEventListener("click", toggleAccountMenu);
  elements.modalClose.addEventListener("click", closeModal);
  elements.modalBackdrop.addEventListener("click", (event) => {
    if (event.target === elements.modalBackdrop) closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeModal();
      closeAccountMenu();
    }
  });
  document.querySelectorAll("[data-route]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.disabled) return;
      setRoute(button.dataset.route);
      closeAccountMenu();
    });
  });
  window.addEventListener("hashchange", () => {
    const route = routeFromHash();
    state.route = route.route;
    state.routeDetail = route.detail;
    renderNav();
    loadAndRender();
  });
  if (!location.hash) history.replaceState(null, "", "#home");
  loadAndRender();
}

function routeFromHash() {
  const [routeName, detail = ""] = (location.hash || "#home").replace("#", "").split("/");
  const route = [...primaryRoutes.map((item) => item.id), "advanced", "settings"].includes(routeName) ? routeName : "home";
  return { route, detail };
}

function setRoute(route) {
  location.hash = route || "home";
}

function renderNav() {
  elements.nav.innerHTML = primaryRoutes
    .map(
      (route) => `
        <button class="nav-button ${state.route === route.id ? "active" : ""}" type="button" data-primary-route="${route.id}">
          ${escapeHtml(route.label)}
        </button>
      `,
    )
    .join("");
  document.querySelectorAll("[data-primary-route]").forEach((button) => {
    button.addEventListener("click", () => setRoute(button.dataset.primaryRoute));
  });
}

async function loadAndRender({ force = false } = {}) {
  if (state.loading) return;
  state.loading = true;
  renderLoading();
  try {
    if (force || state.route !== "advanced" || !state.data) {
      state.data = await loadProductData();
    }
    updateEnvironmentChip(state.data.delivery);
    renderJourney(state.data);
    if (state.route === "advanced") {
      await renderAdvanced();
    } else if (state.route === "profile") {
      renderProfile(state.data);
    } else if (state.route === "companies") {
      renderCompanies(state.data);
    } else if (state.route === "applications") {
      renderApplications(state.data);
    } else if (state.route === "settings") {
      renderSettings(state.data);
    } else {
      renderHome(state.data);
    }
  } catch (error) {
    renderError("The workspace could not be loaded.", error);
  } finally {
    state.loading = false;
  }
}

async function loadProductData() {
  const requests = {
    summary: fetchJson(endpoints.summary),
    profile: fetchJson(endpoints.profile),
    delivery: fetchJson(endpoints.delivery),
    companies: fetchJson(endpoints.companies),
    contacts: fetchJson(endpoints.contacts),
    fitEvaluations: fetchJson(endpoints.fitEvaluations),
    emailDrafts: fetchJson(endpoints.emailDrafts),
    outboxDrafts: fetchJson(endpoints.outboxDrafts),
    outboxSent: fetchJson(endpoints.outboxSent),
    sendIntents: fetchJson(endpoints.sendIntents),
    gateResults: fetchJson(endpoints.gateResults),
    outreachRecords: fetchJson(endpoints.outreachRecords),
    sentMessages: fetchJson(endpoints.sentMessages),
    onboardingStatus: safeFetchJson(`/onboarding/chat/${encodeURIComponent(state.onboardingRunId)}/status`),
    onboardingArtifacts: safeFetchJson(`/onboarding/chat/${encodeURIComponent(state.onboardingRunId)}/artifacts`),
    onboardingInputFiles: safeFetchJson(`/onboarding/chat/${encodeURIComponent(state.onboardingRunId)}/input-files`),
    onboardingSnapshots: safeFetchJson(`/onboarding/runs/${encodeURIComponent(state.onboardingRunId)}/snapshots`),
    campaignStatus: state.campaignRunId
      ? safeFetchJson(`${endpoints.companyResearch}/${encodeURIComponent(state.campaignRunId)}/status`)
      : Promise.resolve(null),
    applicationStatus: state.lastApplicationRunId
      ? safeFetchJson(`${endpoints.applicationDrafts}/${encodeURIComponent(state.lastApplicationRunId)}/status`)
      : Promise.resolve(null),
  };
  const entries = await Promise.all(Object.entries(requests).map(async ([key, promise]) => [key, await promise]));
  const data = Object.fromEntries(entries);
  data.companies = Array.isArray(data.companies) ? data.companies.filter((row) => !isInternalTestRecord(row)) : [];
  data.contacts = Array.isArray(data.contacts) ? data.contacts : [];
  data.fitEvaluations = Array.isArray(data.fitEvaluations) ? data.fitEvaluations : [];
  data.emailDrafts = Array.isArray(data.emailDrafts) ? data.emailDrafts.filter((row) => !isInternalTestRecord(row)) : [];
  data.outboxDrafts = Array.isArray(data.outboxDrafts) ? data.outboxDrafts.filter((row) => !isInternalTestRecord(row)) : [];
  data.outboxSent = Array.isArray(data.outboxSent) ? data.outboxSent.filter((row) => !isInternalTestRecord(row)) : [];
  data.sendIntents = Array.isArray(data.sendIntents) ? data.sendIntents.filter((row) => !isInternalTestRecord(row)) : [];
  data.gateResults = Array.isArray(data.gateResults) ? data.gateResults : [];
  data.outreachRecords = Array.isArray(data.outreachRecords) ? data.outreachRecords : [];
  data.sentMessages = Array.isArray(data.sentMessages) ? data.sentMessages.filter((row) => !isInternalTestRecord(row)) : [];
  return data;
}

function renderLoading() {
  elements.page.innerHTML = `
    <div class="loading-state" aria-busy="true">
      <span class="skeleton" style="width: min(420px, 80%);"></span>
      <span class="skeleton" style="width: min(680px, 100%);"></span>
      <span class="skeleton" style="width: min(520px, 92%);"></span>
    </div>
  `;
}

function renderError(title, error) {
  elements.page.innerHTML = `
    <section class="error-state">
      <h2>${escapeHtml(title)}</h2>
      <p>${escapeHtml(error?.message || "Unknown error")}</p>
      <button class="button secondary" type="button" data-retry>Try again</button>
    </section>
  `;
  document.querySelector("[data-retry]")?.addEventListener("click", () => loadAndRender({ force: true }));
}

function renderJourney(data) {
  elements.journey.innerHTML = "";
}

function nextStageId(completed) {
  const next = journeyStages.find((stage) => !completed[stage.id]);
  return next?.id || "send";
}

function renderHome(data) {
  const attention = buildAttentionItems(data);
  const activeWork = buildActiveWork(data);
  const accomplishments = buildAccomplishments(data);
  const next = nextBestAction(data, attention);
  elements.page.innerHTML = `
    <section class="guided-home">
      <div class="home-intro">
        <p class="context-line">${escapeHtml(greeting())}</p>
        <h1>${escapeHtml(next.headline)}</h1>
        <p class="lead">${escapeHtml(next.supportingText)}</p>
      </div>

      <article class="guided-next-action" aria-labelledby="home-next-action">
        <div class="tight-stack">
          <p class="quiet-note">Next best step</p>
          <h2 id="home-next-action">${escapeHtml(next.title)}</h2>
          <p>${escapeHtml(next.body)}</p>
        </div>
        <div class="form-actions">
          <button class="primary-action" type="button" data-route-target="${escapeHtml(next.route)}">${escapeHtml(next.label)}</button>
          ${next.secondary ? `<button class="secondary-action" type="button" data-route-target="${escapeHtml(next.secondary.route)}">${escapeHtml(next.secondary.label)}</button>` : ""}
        </div>
      </article>

      ${activeWork.length ? `<section class="background-work" aria-label="Background work">${activeWork.map(backgroundActivityMarkup).join("")}</section>` : ""}

      <section class="home-secondary">
        <article>
          <h3>Needs your attention</h3>
          <div class="stack" style="margin-top: 14px;">
            ${attention.length ? attention.slice(0, 3).map(attentionItemMarkup).join("") : `<p class="muted">Nothing needs a decision right now.</p>`}
          </div>
        </article>

        <article>
          <h3>Completed recently</h3>
          <div class="stack" style="margin-top: 14px;">
            ${accomplishments.length ? accomplishments.map((item) => `<p class="muted">${escapeHtml(item.label)}</p>`).join("") : `<p class="muted">No completed work is available yet.</p>`}
          </div>
          <button class="text-action" type="button" data-route-target="advanced" style="margin-top: 16px;">View activity history</button>
        </article>
      </section>
    </section>
  `;
  bindRouteButtons();
}

function renderProfile(data) {
  const entries = data.onboardingStatus?.entries || [];
  const artifacts = data.onboardingArtifacts?.artifacts || [];
  const inputFiles = data.onboardingInputFiles?.files || [];
  const hasProfile = Boolean(data.profile?.has_approved_profile);
  elements.page.innerHTML = `
    <section class="page-header">
      <div>
        <span class="eyebrow">Profile</span>
        <h2>${hasProfile ? "Your career profile is ready" : "Build your career profile"}</h2>
        <p class="lead">${hasProfile ? "We know enough to start finding companies. You can still refine facts and preferences any time." : "Answer recruiter-style questions and add resume source material before company search."}</p>
      </div>
      <div class="actions">
        <button class="button secondary" type="button" data-profile-action="validate">Check profile files</button>
        <button class="button primary" type="button" data-profile-action="start">${entries.length ? "Continue conversation" : "Start profile conversation"}</button>
      </div>
    </section>

    <section class="profile-layout">
      <article class="raised-panel chat-panel">
        <div class="panel-header">
          <div>
            <h3>Recruiter conversation</h3>
            <p class="muted">${conversationStatusLabel(data.onboardingStatus)}</p>
          </div>
          <span class="status-chip ${hasProfile ? "success" : "warning"}">${hasProfile ? "Ready" : "In progress"}</span>
        </div>
        <div class="chat-messages" id="chatMessages">
          ${entries.length ? entries.map(messageMarkup).join("") : emptyMarkup("No conversation yet.", "Start with your target roles, preferred locations, and the kind of work you want.")}
        </div>
        <form class="chat-composer" id="profileComposer">
          <label class="sr-only" for="profileMessage">Message</label>
          <textarea id="profileMessage" placeholder="Tell the recruiter what changed, or answer the next question."></textarea>
          <button class="button primary" type="submit">Send</button>
        </form>
      </article>

      <div class="stack">
        <article class="panel">
          <div class="tight-stack">
            <span class="eyebrow">What we know</span>
            <h3>Structured profile</h3>
            <p class="muted">Confirmed information is used for search and tailoring. Inferred or missing information stays visible for review.</p>
          </div>
          <div class="stack" style="margin-top: 18px;">
            ${profileFact("Target roles", hasProfile ? "Machine Learning, Applied AI, Document AI, MLOps" : "Not confirmed yet", hasProfile ? "confirmed" : "missing")}
            ${profileFact("Location and relocation", hasProfile ? "Switzerland focus with relocation context" : "Not confirmed yet", hasProfile ? "confirmed" : "missing")}
            ${profileFact("Experience highlights", hasProfile ? "Production NLP, OCR pipelines, transformer extraction, evaluation, MLOps" : "Add a resume or describe your work history", hasProfile ? "confirmed" : "missing")}
            ${profileFact("Values and exclusions", data.profile?.approved_policy ? "Policy approved and available for company screening" : "Policy needs review", data.profile?.approved_policy ? "confirmed" : "missing")}
          </div>
        </article>

        <article class="panel">
          <div class="panel-header" style="padding: 0 0 16px; border-bottom: 0;">
            <div>
              <h3>Resume source material</h3>
              <p class="muted">${inputFiles.length ? `${inputFiles.length} source file${inputFiles.length === 1 ? "" : "s"} added.` : "Add resumes or notes for the recruiter to read."}</p>
            </div>
            <label class="button secondary" for="resumeUpload">Upload resume</label>
            <input class="visually-hidden" id="resumeUpload" type="file" accept=".pdf,.doc,.docx,.txt,.md,.json">
          </div>
          <div class="source-list">
            ${inputFiles.length ? inputFiles.map((file) => sourceRow(file.filename, formatBytes(file.size_bytes))).join("") : emptyMarkup("No resume uploaded.", "The conversation can still begin, but source material improves accuracy.")}
          </div>
        </article>

        <article class="panel">
          <div class="tight-stack">
            <span class="eyebrow">Review</span>
            <h3>Profile changes</h3>
          </div>
          <div class="stack" style="margin-top: 18px;">
            ${artifacts.length ? artifacts.map(artifactMarkup).join("") : emptyMarkup("No profile files waiting.", "Finish the conversation when you are ready to review structured profile changes.")}
          </div>
          <div class="actions" style="margin-top: 18px;">
            <button class="button secondary" type="button" data-profile-action="finish">Prepare profile changes</button>
            <button class="button primary" type="button" data-profile-action="approve" ${artifacts.length ? "" : "disabled"}>Approve meaningful changes</button>
          </div>
        </article>
      </div>
    </section>
  `;
  bindProfileActions();
}

function renderCompanies(data) {
  state.researchDraft = getResearchDraft(data);
  if (state.routeDetail === "brief" || (!state.routeDetail && !data.companies.length && !isResearchActive(data.campaignStatus))) {
    renderResearchBrief(data);
    return;
  }
  if (state.routeDetail === "progress" || (!state.routeDetail && isResearchActive(data.campaignStatus))) {
    renderResearchProgress(data);
    return;
  }
  if (state.routeDetail === "review" || (!state.routeDetail && data.companies.length)) {
    renderGuidedCompanyReview(data);
    return;
  }
  if (state.routeDetail === "list") {
    renderCompanyList(data);
    return;
  }
  renderResearchBrief(data);
}

function renderCompanyList(data) {
  const filtered = filteredCompanies(data);
  elements.page.innerHTML = `
    <section class="page-header">
      <div>
        <span class="eyebrow">Company discovery</span>
        <h2>All discovered companies</h2>
        <p class="lead">A clean list of company matches remains available when you need to compare more than one at a time.</p>
      </div>
      <div class="actions">
        <button class="secondary-action" type="button" data-route-target="companies/review">Review one at a time</button>
        <button class="primary-action" type="button" data-route-target="companies/brief">Start another search</button>
      </div>
    </section>

    <section class="editorial-list-shell">
      ${companyFiltersMarkup()}
      <div class="company-list editorial-company-list">
        ${filtered.length ? filtered.map((company) => companyRowMarkup(company, data)).join("") : emptyMarkup("No companies match these filters.", "Try another stage or clear the search.")}
      </div>
    </section>
  `;
  bindCompanyActions();
}

function renderApplications(data) {
  const reviewDrafts = data.outboxDrafts.filter((draft) => draft.status === "ready" || draft.status === "blocked");
  const sentRows = data.outboxSent;
  const activeRows = isApplicationActive(data.applicationStatus) ? [data.applicationStatus] : [];
  elements.page.innerHTML = `
    <section class="page-header">
      <div>
        <span class="eyebrow">Prepare and Send</span>
        <h2>Review applications before anything leaves</h2>
        <p class="lead">Every application stays under your control. The backend checks duplicates, evidence, attachments, and limits before approval can proceed.</p>
      </div>
      <div class="actions">
        <button class="button secondary" type="button" data-app-tab="sent">Sent history</button>
        <button class="button primary" type="button" data-app-tab="review">Review ready applications</button>
      </div>
    </section>

    <div class="section-tabs">
      <div class="segmented" role="tablist" aria-label="Application views">
        ${[
          ["review", "Needs review"],
          ["preparing", "Preparing"],
          ["send", "Ready for approval"],
          ["sent", "Sent"],
        ]
          .map(
            ([id, label]) => `<button type="button" class="${state.activeApplicationTab === id ? "active" : ""}" data-app-tab="${id}">${label}</button>`,
          )
          .join("")}
      </div>
    </div>

    ${applicationsTabMarkup(data, reviewDrafts, activeRows, sentRows)}
  `;
  bindApplicationActions();
}

function applicationsTabMarkup(data, reviewDrafts, activeRows, sentRows) {
  if (state.activeApplicationTab === "preparing") {
    return `
      <section class="layout-two">
        <article class="panel">
          <div class="tight-stack">
            <span class="eyebrow">Writing</span>
            <h3>Applications being prepared</h3>
            <p class="muted">Preparation includes company research, relevant experience selection, resume tailoring, draft writing, and claim checks.</p>
          </div>
          <div class="stack" style="margin-top: 18px;">
            ${activeRows.length ? activeRows.map(applicationActivityMarkup).join("") : emptyMarkup("Nothing is being prepared right now.", "Start from a promising company when you want a tailored application.")}
          </div>
        </article>
        <article class="panel">
          <h3>Batch preparation</h3>
          <p class="muted" style="margin-top: 8px;">Batch work is secondary. Review the company set before launching.</p>
          <div class="actions" style="margin-top: 18px;">
            <button class="button secondary" type="button" data-prepare-batch>Prepare missing applications</button>
          </div>
        </article>
      </section>
    `;
  }
  if (state.activeApplicationTab === "sent") {
    return `
      <section class="raised-panel">
        <div class="panel-header">
          <div>
            <h3>Sent applications</h3>
            <p class="muted">Successful and failed provider outcomes are shown separately when the backend reports them.</p>
          </div>
          <span class="status-chip success">${sentRows.length} sent</span>
        </div>
        <div class="panel-body application-list">
          ${sentRows.length ? sentRows.map(sentRowMarkup).join("") : emptyMarkup("No sent applications yet.", "Approved applications will appear here after the backend reports completion.")}
        </div>
      </section>
    `;
  }
  if (state.activeApplicationTab === "send") {
    const ready = data.outboxDrafts.filter((draft) => draft.status === "ready");
    const blocked = data.outboxDrafts.filter((draft) => draft.status === "blocked");
    return `
      <section class="layout-two">
        <article class="raised-panel">
          <div class="panel-header">
            <div>
              <h3>Ready for your approval</h3>
              <p class="muted">Inspect each recipient, subject, and resume before final approval.</p>
            </div>
            <span class="status-chip ${ready.length ? "warning" : "success"}">${ready.length} ready</span>
          </div>
          <div class="panel-body application-list">
            ${ready.length ? ready.map((draft) => applicationRowMarkup(draft, { approval: true })).join("") : emptyMarkup("Nothing is ready for approval.", "Prepared applications will appear here after checks pass.")}
          </div>
        </article>
        <aside class="stack">
          <article class="panel">
            <h3>Approval summary</h3>
            <p class="muted" style="margin-top: 8px;">${blocked.length} blocked or excluded. ${ready.length} can be reviewed for approval.</p>
            <div class="actions" style="margin-top: 18px;">
              <button class="button danger" type="button" data-approve-ready ${ready.length ? "" : "disabled"}>Review final confirmation</button>
            </div>
          </article>
          <article class="panel">
            <h3>Safety checks</h3>
            <ul class="plain-list" style="margin-top: 12px;">
              <li>Duplicate recipient and company checks stay in the backend.</li>
              <li>Attachments and claim references are checked before approval.</li>
              <li>No application is sent without your explicit confirmation.</li>
            </ul>
          </article>
        </aside>
      </section>
    `;
  }
  return `
    <section class="review-layout">
      <article class="raised-panel">
        <div class="panel-header">
          <div>
            <h3>Application review</h3>
            <p class="muted">Review email, recipient confidence, resume attachment, and blockers.</p>
          </div>
          <span class="status-chip warning">${reviewDrafts.length} to inspect</span>
        </div>
        <div class="panel-body application-list">
          ${reviewDrafts.length ? reviewDrafts.map((draft) => applicationRowMarkup(draft)).join("") : emptyMarkup("No applications need review.", "Prepared drafts will appear here.")}
        </div>
      </article>
      <aside class="stack">
        ${selectedDraftReviewMarkup(data)}
      </aside>
    </section>
  `;
}

function renderSettings(data) {
  elements.page.innerHTML = `
    <section class="panel">
      <span class="eyebrow">Settings</span>
      <h2>Settings are intentionally limited</h2>
      <p class="lead">Policy, limits, and blocked domains are owned by backend-validated profile data. Use Advanced/Admin for raw inspection.</p>
      <div class="actions" style="margin-top: 18px;">
        <button class="button secondary" type="button" data-route-target="advanced">Open Advanced/Admin</button>
      </div>
    </section>
  `;
  bindRouteButtons();
  updateEnvironmentChip(data.delivery);
}

async function renderAdvanced() {
  const section = advancedSections.find((item) => item.id === state.activeAdvancedSection) || advancedSections[0];
  state.activeAdvancedSection = section.id;
  elements.journey.innerHTML = "";
  elements.page.innerHTML = `
    <section class="page-header">
      <div>
        <span class="eyebrow">Advanced/Admin</span>
        <h2>Operational records and debugging tools</h2>
        <p class="lead">This area intentionally uses backend terminology for diagnostics, audit, and repair.</p>
      </div>
      <div class="actions">
        <button class="button secondary" type="button" data-route-target="home">Return to Home</button>
      </div>
    </section>
    <section class="advanced-shell">
      <aside class="advanced-sidebar">
        <div class="advanced-warning">
          <strong>Administrative view</strong>
          <p style="margin-top: 6px;">Raw records, run IDs, paths, payloads, queue state, gate results, and audit logs are shown here.</p>
        </div>
        ${advancedSections
          .map((item) => `<button type="button" class="${item.id === section.id ? "active" : ""}" data-advanced-section="${item.id}">${escapeHtml(item.label)}</button>`)
          .join("")}
      </aside>
      <div class="stack">
        <article class="raised-panel">
          <div class="panel-header">
            <div>
              <h3>${escapeHtml(section.label)}</h3>
              <p class="muted">${escapeHtml(section.endpoint)}</p>
            </div>
            <button class="button secondary" type="button" data-advanced-refresh>Refresh records</button>
          </div>
          <div class="panel-body">
            <div class="table-wrap" id="advancedTableWrap">${loadingMarkup("Loading records")}</div>
          </div>
        </article>
        <article class="panel">
          <h3>Selected raw response</h3>
          <pre class="detail-json" id="advancedDetail">No record selected.</pre>
        </article>
      </div>
    </section>
  `;
  bindRouteButtons();
  bindAdvancedShell();
  await loadAdvancedRows(section);
}

async function loadAdvancedRows(section) {
  try {
    state.advancedRows = await fetchJson(section.endpoint);
    if (!Array.isArray(state.advancedRows)) state.advancedRows = [];
    state.advancedSelectedIndex = state.advancedRows.length ? Math.min(state.advancedSelectedIndex, state.advancedRows.length - 1) : 0;
    const wrap = document.querySelector("#advancedTableWrap");
    if (!wrap) return;
    wrap.innerHTML = advancedTableMarkup(section, state.advancedRows);
    bindAdvancedRows();
    renderAdvancedDetail();
  } catch (error) {
    document.querySelector("#advancedTableWrap").innerHTML = `<div class="error-state">${escapeHtml(error.message)}</div>`;
  }
}

function advancedTableMarkup(section, rows) {
  if (!rows.length) return emptyMarkup("No records found.", "This endpoint returned an empty list.");
  return `
    <table>
      <thead><tr>${section.columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead>
      <tbody>
        ${rows
          .map(
            (row, index) => `
              <tr class="${index === state.advancedSelectedIndex ? "selected" : ""}" data-advanced-row="${index}">
                ${section.columns.map((column) => `<td>${escapeHtml(formatCell(row[column]))}</td>`).join("")}
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderAdvancedDetail() {
  const detail = document.querySelector("#advancedDetail");
  if (!detail) return;
  const row = state.advancedRows[state.advancedSelectedIndex];
  detail.textContent = row ? JSON.stringify(row, null, 2) : "No record selected.";
}

function bindAdvancedShell() {
  document.querySelectorAll("[data-advanced-section]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.activeAdvancedSection = button.dataset.advancedSection;
      state.advancedSelectedIndex = 0;
      await renderAdvanced();
    });
  });
  document.querySelector("[data-advanced-refresh]")?.addEventListener("click", async () => {
    const section = advancedSections.find((item) => item.id === state.activeAdvancedSection) || advancedSections[0];
    await loadAdvancedRows(section);
  });
}

function bindAdvancedRows() {
  document.querySelectorAll("[data-advanced-row]").forEach((row) => {
    row.addEventListener("click", () => {
      state.advancedSelectedIndex = Number(row.dataset.advancedRow || 0);
      const section = advancedSections.find((item) => item.id === state.activeAdvancedSection) || advancedSections[0];
      document.querySelector("#advancedTableWrap").innerHTML = advancedTableMarkup(section, state.advancedRows);
      bindAdvancedRows();
      renderAdvancedDetail();
    });
  });
}

function buildAttentionItems(data) {
  const items = [];
  if ((data.profile?.candidate_user_profiles || []).length) {
    items.push({ title: "Confirm a profile change", body: "A candidate profile is waiting for review.", route: "profile", label: "Review" });
  }
  const readyDrafts = data.outboxDrafts.filter((draft) => draft.status === "ready");
  if (readyDrafts.length) {
    items.push({ title: `Review ${readyDrafts.length} tailored application${readyDrafts.length === 1 ? "" : "s"}`, body: "Recipient, subject, resume, and warnings are ready for your approval.", route: "applications", label: "Review" });
  }
  const blocked = data.outboxDrafts.filter((draft) => draft.status === "blocked").slice(0, 3);
  for (const draft of blocked) {
    items.push({ title: `Resolve ${draft.company_name}`, body: draft.status_label || "This application is blocked.", route: "applications", label: "Inspect" });
  }
  const reviewCompanies = data.companies.filter((company) => (company.review_flags || []).length && !company.has_been_contacted).slice(0, 3);
  if (reviewCompanies.length && !readyDrafts.length) {
    items.push({ title: `Review ${reviewCompanies.length} uncertain match${reviewCompanies.length === 1 ? "" : "es"}`, body: "Some company facts need a closer look before preparation.", route: "companies", label: "Review matches" });
  }
  if (!data.profile?.has_approved_profile) {
    items.push({ title: "Finish your career profile", body: "The recruiter needs confirmed context before company search.", route: "profile", label: "Continue" });
  }
  return items.slice(0, 3);
}

function buildActiveWork(data) {
  const items = [];
  if (isResearchActive(data.campaignStatus)) {
    const counts = data.campaignStatus?.artifact_counts || {};
    items.push({
      kind: "running",
      title: "Searching for companies",
      body: `${counts.companies || 0} companies found so far. You can leave this page; progress stays visible here.`,
      progress: progressFromCounts(counts.companies || 0, data.campaignStatus?.state?.target_company_count || 30),
    });
  }
  if (isApplicationActive(data.applicationStatus)) {
    items.push({
      kind: "running",
      title: "Preparing an application",
      body: applicationProgressText(data.applicationStatus),
      progress: 55,
    });
  }
  if (isOnboardingActive(data.onboardingStatus)) {
    items.push({
      kind: "running",
      title: "Waiting for profile response",
      body: "The recruiter conversation is active.",
      progress: 42,
    });
  }
  return items;
}

function buildAccomplishments(data) {
  const items = [];
  if (data.profile?.has_approved_profile) items.push({ label: "Career profile approved for company research." });
  if (data.companies.length) items.push({ label: "Company matches are ready to review." });
  if (data.outboxDrafts.length) items.push({ label: "Application drafts have been prepared for review." });
  if (data.outboxSent.length) items.push({ label: "Approved outreach history is available." });
  return items.slice(0, 3);
}

function nextBestAction(data, attention) {
  if ((data.profile?.candidate_user_profiles || []).length) {
    return {
      headline: "Your recruiter needs one profile decision.",
      supportingText: "Review the candidate profile change before using it for future search and preparation.",
      route: "profile",
      title: "Review profile changes",
      body: "A structured profile update is waiting for your confirmation.",
      label: "Review profile",
    };
  }
  const ready = data.outboxDrafts.filter((draft) => draft.status === "ready").length;
  if (ready) {
    return {
      headline: `${ready} application${ready === 1 ? " is" : "s are"} ready for review.`,
      supportingText: "Nothing leaves without your explicit approval and backend safety checks.",
      route: "applications",
      title: `Review ${ready} application${ready === 1 ? "" : "s"} before approval`,
      body: "Nothing leaves without your confirmation. Inspect recipients, subject lines, resumes, and warnings first.",
      label: "Review applications",
      secondary: { route: "companies", label: "Review companies" },
    };
  }
  const newMatches = data.companies.filter((company) => !company.has_application_draft && !company.has_been_contacted && !hasItems(company.policy_conflicts)).length;
  if (newMatches) {
    return {
      headline: "New company matches are ready.",
      supportingText: "Review one match at a time and decide which companies should move forward.",
      route: "companies/review",
      title: `Review ${newMatches} new match${newMatches === 1 ? "" : "es"}`,
      body: "Decide which companies should move into application preparation.",
      label: "Review matches",
      secondary: { route: "companies/list", label: "View all companies" },
    };
  }
  if (isResearchActive(data.campaignStatus)) {
    return {
      headline: "Your recruiter is searching for companies.",
      supportingText: researchProgressSentence(data),
      route: "companies/progress",
      title: "Check company search progress",
      body: "You can leave the page while research continues. New matches will appear after they are saved.",
      label: "View progress",
    };
  }
  if (data.profile?.has_approved_profile) {
    return {
      headline: "Ready to discover companies.",
      supportingText: "Brief your recruiter once, then let the search run in the background.",
      route: "companies/brief",
      title: "Start company search",
      body: "Choose location, role direction, company preferences, and search scope through a short guided brief.",
      label: "Start company search",
    };
  }
  return {
    headline: "Let us build your career profile first.",
    supportingText: "Company discovery works best after your recruiter has approved roles, locations, constraints, and resume context.",
    route: "profile",
    title: "Start your profile",
    body: "Answer recruiter-style questions and add source material before launching company discovery.",
    label: "Start profile",
  };
}

function homeHeadline(data) {
  if (isResearchActive(data.campaignStatus)) return "Your recruiter is searching for companies.";
  if (!data.profile?.has_approved_profile) return "Let us build your career profile first.";
  const ready = data.outboxDrafts.filter((draft) => draft.status === "ready").length;
  if (ready) return `${ready} application${ready === 1 ? " is" : "s are"} ready for your review.`;
  return "Your recruiter workspace is ready.";
}

function homeSubline(data) {
  const companyCount = data.companies.length;
  const prepared = data.outboxDrafts.length;
  const sent = data.outboxSent.length;
  return `${companyCount} companies reviewed - ${prepared} applications prepared - ${sent} sent. No application can be sent without your explicit approval.`;
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning, Laurent";
  if (hour < 18) return "Good afternoon, Laurent";
  return "Good evening, Laurent";
}

function attentionItemMarkup(item) {
  return `
    <div class="attention-item">
      <div class="tight-stack">
        <h4>${escapeHtml(item.title)}</h4>
        <p class="muted">${escapeHtml(item.body)}</p>
      </div>
      <button class="button secondary" type="button" data-route-target="${escapeHtml(item.route)}">${escapeHtml(item.label)}</button>
    </div>
  `;
}

function activityMarkup(item) {
  return `
    <div class="activity-item">
      <div class="activity-row">
        <span class="activity-dot ${item.kind === "running" ? "running" : ""}">${item.kind === "running" ? "..." : "OK"}</span>
        <div class="tight-stack">
          <h4>${escapeHtml(item.title)}</h4>
          <p class="muted">${escapeHtml(item.body)}</p>
          <div class="progress-track" aria-label="${escapeHtml(item.title)} progress">
            <div class="progress-bar" style="width: ${Math.max(5, Math.min(100, Number(item.progress || 25)))}%;"></div>
          </div>
        </div>
      </div>
    </div>
  `;
}

function backgroundActivityMarkup(item) {
  return `
    <article class="background-activity">
      <span class="pulse-dot" aria-hidden="true"></span>
      <div>
        <strong>${escapeHtml(item.title)}</strong>
        <p>${escapeHtml(item.body)}</p>
      </div>
    </article>
  `;
}

function guidedFlowShell({ stepIndex, title, explanation, assurance, body, nextPreview = "" }) {
  const step = guidedResearchSteps[stepIndex] || guidedResearchSteps[0];
  return `
    <section class="concept-shell workflow-shell guided-production">
      <p class="context-line">Research brief - ${stepIndex + 1} of ${guidedResearchSteps.length}</p>
      <section class="workflow-panel" aria-labelledby="guided-step-title">
        <div class="workflow-context">
          <p class="quiet-note">${escapeHtml(step.label)}</p>
          <h1 id="guided-step-title" tabindex="-1">${escapeHtml(title)}</h1>
          <p>${escapeHtml(explanation)}</p>
          ${assurance ? `<p class="assurance">${escapeHtml(assurance)}</p>` : ""}
        </div>
        <form class="guided-form" id="researchBriefForm" novalidate>
          ${body}
        </form>
      </section>
      ${nextPreview ? `<section class="next-preview" aria-live="polite">${nextPreview}</section>` : ""}
    </section>
  `;
}

function primaryActionBar({ back = true, continueLabel = "Continue", submitAction = "continue", disabled = false } = {}) {
  return `
    <div class="form-actions primary-action-bar">
      ${back ? `<button class="secondary-action" type="button" data-brief-back>Back</button>` : ""}
      <button class="primary-action" type="submit" data-brief-action="${escapeHtml(submitAction)}" ${disabled ? "disabled" : ""}>${escapeHtml(continueLabel)}</button>
    </div>
  `;
}

function inlineError(id) {
  return `<p class="inline-error" id="${escapeHtml(id)}" hidden></p>`;
}

function choiceGroup(name, options, selectedValues, { multiple = false } = {}) {
  const selected = new Set(Array.isArray(selectedValues) ? selectedValues : [selectedValues].filter(Boolean));
  return `
    <div class="choice-group">
      ${options
        .map((option) => {
          const checked = selected.has(option.value);
          const type = multiple ? "checkbox" : "radio";
          return `
            <label class="choice-card ${checked ? "selected" : ""}">
              <input type="${type}" name="${escapeHtml(name)}" value="${escapeHtml(option.value)}" ${checked ? "checked" : ""}>
              <span>
                <strong>${escapeHtml(option.label)}</strong>
                <small>${escapeHtml(option.detail || "")}</small>
              </span>
            </label>
          `;
        })
        .join("")}
    </div>
  `;
}

function reviewSummary(draft) {
  return `
    <article class="review-summary">
      <p>${escapeHtml(recruiterBriefText(draft))}</p>
      <div class="review-sections">
        ${[
          ["location", "Location", locationSummary(draft)],
          ["roles", "Role direction", rolesSummary(draft)],
          ["preferences", "Company preferences", preferencesSummary(draft)],
          ["scope", "Search scope", scopeSummary(draft)],
        ]
          .map(
            ([stepId, title, body]) => `
              <div class="review-section">
                <div>
                  <h3>${escapeHtml(title)}</h3>
                  <p>${escapeHtml(body)}</p>
                </div>
                <button class="text-action" type="button" data-edit-brief="${escapeHtml(stepId)}">Edit</button>
              </div>
            `,
          )
          .join("")}
      </div>
    </article>
  `;
}

function profileFact(title, body, status) {
  const tone = status === "confirmed" ? "success" : status === "inferred" ? "warning" : "";
  const label = status === "confirmed" ? "Confirmed" : status === "inferred" ? "Inferred" : "Missing";
  return `
    <div class="profile-fact">
      <div class="summary-line">
        <h4>${escapeHtml(title)}</h4>
        <span class="mini-chip ${tone}">${escapeHtml(label)}</span>
      </div>
      <p class="muted">${escapeHtml(body)}</p>
    </div>
  `;
}

function messageMarkup(entry) {
  const role = entry.role === "user" ? "user" : "assistant";
  const label = role === "user" ? "You" : "Recruiter";
  const content = userFacingTranscript(entry.content || "");
  return `
    <div class="message ${role}">
      <small>${escapeHtml(label)}</small>
      <div>${escapeHtml(content).replaceAll("\n", "<br>")}</div>
    </div>
  `;
}

function userFacingTranscript(content) {
  const normalized = String(content || "").trim();
  if (!normalized) return "";
  const lower = normalized.toLowerCase();
  if (normalized.startsWith("{") && (lower.includes("tmux") || lower.includes("workdir") || lower.includes("pane_ref"))) {
    return "Recruiter session started.";
  }
  if (lower.includes("tmux") || lower.includes("codex") || lower.includes("pane") || lower.includes("workdir")) {
    if (lower.includes("no new") || lower.includes("reply")) return "Waiting for the recruiter reply.";
    if (lower.includes("prompt sent")) return "Recruiter is ready to begin.";
    return "Recruiter session updated.";
  }
  if (lower.includes("finish artifacts")) return "Preparing profile changes for review.";
  if (lower.includes("repair artifacts")) return "Updating profile changes after validation.";
  return normalized;
}

function sourceRow(title, meta) {
  return `
    <div class="source-row">
      <div>
        <h4>${escapeHtml(title)}</h4>
        <p class="muted">${escapeHtml(meta)}</p>
      </div>
    </div>
  `;
}

function artifactMarkup(artifact) {
  const tone = artifact.review_state === "approved" || artifact.snapshot_status === "approved" ? "success" : artifact.status === "missing" ? "warning" : "info";
  return `
    <div class="source-row">
      <div>
        <h4>${escapeHtml(readableArtifactName(artifact.filename))}</h4>
        <p class="muted">${escapeHtml(artifactLabel(artifact))}</p>
      </div>
      <span class="status-chip ${tone}">${escapeHtml(humanStatus(artifact.review_state || artifact.status))}</span>
    </div>
  `;
}

function renderResearchBrief(data) {
  const draft = getResearchDraft(data);
  const stepIndex = Math.max(0, Math.min(guidedResearchSteps.length - 1, state.researchStep));
  if (stepIndex === 0) renderResearchLocationStep(draft);
  if (stepIndex === 1) renderResearchRoleStep(draft);
  if (stepIndex === 2) renderResearchPreferenceStep(draft);
  if (stepIndex === 3) renderResearchScopeStep(draft);
  if (stepIndex === 4) renderResearchReviewStep(draft);
  bindResearchBriefActions();
  focusGuidedHeading();
}

function renderResearchLocationStep(draft) {
  elements.page.innerHTML = guidedFlowShell({
    stepIndex: 0,
    title: "Where should your recruiter look?",
    explanation: "Location keeps the search focused on companies where an application could realistically move forward.",
    assurance: "These choices only affect this search brief. They do not rewrite your main profile.",
    body: `
      <fieldset>
        <legend>Search locations</legend>
        <label class="field">
          <span>Locations</span>
          <input id="briefLocations" value="${escapeHtml(draft.locations.join(", "))}" autocomplete="off" aria-describedby="briefLocationsError">
          ${inlineError("briefLocationsError")}
        </label>
        <div class="field">
          <span>Work model</span>
          ${choiceGroup(
            "remotePreference",
            [
              { value: "remote-friendly", label: "Remote-friendly", detail: "Prioritize companies with remote or hybrid flexibility." },
              { value: "hybrid", label: "Hybrid near target locations", detail: "Good when local presence still matters." },
              { value: "onsite", label: "Mostly onsite", detail: "Use only when you want a tighter local search." },
            ],
            draft.remotePreference,
          )}
        </div>
        <label class="check-row">
          <input id="briefRelocation" type="checkbox" ${draft.relocationOpen ? "checked" : ""}>
          <span>Include companies where relocation could make sense.</span>
        </label>
      </fieldset>
      ${primaryActionBar({ back: false })}
    `,
    nextPreview: `<strong>Next</strong><span>Choose the work your recruiter should prioritize.</span>`,
  });
}

function renderResearchRoleStep(draft) {
  const suggestedRoles = profileRoleSuggestions();
  elements.page.innerHTML = guidedFlowShell({
    stepIndex: 1,
    title: "What kind of work should we prioritize?",
    explanation: "A tighter role direction helps the recruiter judge fit instead of collecting loosely related companies.",
    assurance: "You can add a temporary role here without changing your approved profile.",
    body: `
      <fieldset>
        <legend>Role direction</legend>
        ${choiceGroup("roles", suggestedRoles.map((role) => ({ value: role, label: role, detail: "Suggested from the approved profile direction." })), draft.roles, { multiple: true })}
        <label class="field">
          <span>Optional custom role</span>
          <input id="briefCustomRole" value="${escapeHtml(draft.customRole || "")}" autocomplete="off" placeholder="e.g. Document Intelligence Engineer" aria-describedby="briefRolesError">
          ${inlineError("briefRolesError")}
        </label>
      </fieldset>
      ${primaryActionBar()}
    `,
    nextPreview: `<strong>Next</strong><span>Tell the recruiter which companies should stand out.</span>`,
  });
}

function renderResearchPreferenceStep(draft) {
  elements.page.innerHTML = guidedFlowShell({
    stepIndex: 2,
    title: "What kinds of companies should stand out?",
    explanation: "Preferences reduce noisy matches and keep the search aligned with the work you actually want.",
    assurance: "Exclusions are treated as search guidance, then backend policy still controls irreversible decisions later.",
    body: `
      <fieldset>
        <legend>Company preferences</legend>
        <label class="field">
          <span>Industries or domains</span>
          <input id="briefIndustries" value="${escapeHtml(draft.industries.join(", "))}" autocomplete="off" placeholder="Applied AI, document automation, computer vision">
        </label>
        <div class="field">
          <span>Characteristics</span>
          ${choiceGroup(
            "characteristics",
            [
              { value: "useful products", label: "Useful products", detail: "Companies solving concrete customer problems." },
              { value: "medium-sized teams", label: "Medium-sized teams", detail: "Enough structure without heavy corporate process." },
              { value: "strong engineering culture", label: "Strong engineering culture", detail: "Teams that value reliability and craft." },
            ],
            draft.characteristics,
            { multiple: true },
          )}
        </div>
        <label class="field">
          <span>Exclusions</span>
          <input id="briefExclusions" value="${escapeHtml(draft.exclusions.join(", "))}" autocomplete="off" placeholder="Defense, gambling, unsupported relocation">
        </label>
        <label class="field">
          <span>Optional instruction</span>
          <textarea id="briefNotes" rows="4" placeholder="Focus on medium-sized AI companies around Zurich that work on useful, non-defense products.">${escapeHtml(draft.notes || "")}</textarea>
        </label>
      </fieldset>
      ${primaryActionBar()}
    `,
    nextPreview: `<strong>Next</strong><span>Choose how broad this search should be.</span>`,
  });
}

function renderResearchScopeStep(draft) {
  elements.page.innerHTML = guidedFlowShell({
    stepIndex: 3,
    title: "How broad should this search be?",
    explanation: "Search scope controls how many companies the recruiter should try to find and how much time to spend.",
    assurance: "You do not need to understand runtime settings. Pick the amount of exploration you want.",
    body: `
      <fieldset>
        <legend>Scope preset</legend>
        ${choiceGroup(
          "scopePreset",
          Object.entries(scopePresets).map(([value, preset]) => ({ value, label: preset.label, detail: preset.detail })),
          draft.scopePreset,
        )}
        <label class="field">
          <span>Minimum company target</span>
          <input id="briefMinCompanies" type="number" min="1" max="100" step="1" value="${escapeHtml(draft.minCompanies)}" aria-describedby="briefScopeError">
          ${inlineError("briefScopeError")}
        </label>
      </fieldset>
      ${primaryActionBar({ continueLabel: "Review brief" })}
    `,
    nextPreview: `<strong>Next</strong><span>Review the final recruiter brief before launch.</span>`,
  });
}

function renderResearchReviewStep(draft) {
  elements.page.innerHTML = guidedFlowShell({
    stepIndex: 4,
    title: "Review the recruiter brief.",
    explanation: "This is what the company-search agent will use. Edit any section before starting.",
    assurance: "Starting this search does not create applications and cannot contact companies.",
    body: `
      ${reviewSummary(draft)}
      <div id="briefLaunchError" class="inline-error" hidden></div>
      ${primaryActionBar({ continueLabel: state.launchInFlight ? "Starting your search" : "Start company search", submitAction: "launch", disabled: state.launchInFlight })}
    `,
  });
}

function renderResearchProgress(data) {
  const status = data.campaignStatus;
  const active = isResearchActive(status);
  const counts = status?.artifact_counts || {};
  const target = status?.state?.target_company_count || getResearchDraft(data).minCompanies || 30;
  const companiesFound = Number(counts.companies ?? data.companies.length ?? 0);
  const complete = isResearchComplete(status);
  elements.page.innerHTML = `
    <section class="concept-shell progress-shell">
      <p class="context-line">Company discovery</p>
      <section class="progress-panel" aria-labelledby="research-progress-title">
        <div class="workflow-context">
          <p class="quiet-note">${complete ? "Search complete" : active ? "Searching for companies" : "Research status"}</p>
          <h1 id="research-progress-title">${escapeHtml(researchProgressTitle(data))}</h1>
          <p>${escapeHtml(researchProgressSentence(data))}</p>
          <p class="assurance">You can leave this page. The search will continue in the background.</p>
        </div>
        <div class="guided-form progress-card">
          <div class="progress-count">
            <strong>${escapeHtml(String(companiesFound))}</strong>
            <span>of at least ${escapeHtml(String(target))} companies found</span>
          </div>
          <p class="muted">${escapeHtml(researchStatusLabel(status))}</p>
          <div class="form-actions">
            <button class="secondary-action" type="button" data-company-action="import-research">Import latest findings</button>
            <button class="primary-action" type="button" data-route-target="companies/review" ${data.companies.length ? "" : "disabled"}>Review first company</button>
          </div>
        </div>
      </section>
      <details class="activity-details">
        <summary>Activity details</summary>
        <ul>
          ${safeResearchEvents(status).map((event) => `<li>${escapeHtml(event)}</li>`).join("")}
        </ul>
      </details>
    </section>
  `;
  bindCompanyActions();
}

function renderGuidedCompanyReview(data) {
  const companies = unreviewedCompanies(data);
  const company = selectedGuidedCompany(data, companies);
  if (!company) {
    elements.page.innerHTML = `
      <section class="concept-shell">
        <article class="empty-state">
          <h2>${data.companies.length ? "All current matches have been reviewed." : "No company matches yet."}</h2>
          <p>${data.companies.length ? "You can view the full list or start another search." : "Start a company search and return here when the first match appears."}</p>
          <div class="form-actions">
            <button class="secondary-action" type="button" data-route-target="companies/list" ${data.companies.length ? "" : "disabled"}>View all companies</button>
            <button class="primary-action" type="button" data-route-target="companies/brief">Start company search</button>
          </div>
        </article>
      </section>
    `;
    bindRouteButtons();
    return;
  }
  const fit = latestFit(company, data.fitEvaluations);
  const reasons = matchReasons(company, fit).slice(0, 2);
  const concerns = companyConcerns(company, fit).slice(0, 3);
  elements.page.innerHTML = `
    <section class="concept-shell company-review-shell">
      <p class="context-line">Company review - ${Math.max(1, data.companies.length - companies.length + 1)} of ${data.companies.length}</p>
      <section class="company-review-panel" aria-labelledby="company-review-title">
        <div class="workflow-context">
          <p class="quiet-note">${escapeHtml(fitLabel(company.confidence))}</p>
          <h1 id="company-review-title">${escapeHtml(company.name || company.company_id)}</h1>
          <p>${escapeHtml(company.description || "The recruiter did not provide a company description yet.")}</p>
          <p class="muted">${escapeHtml([firstValue(company.locations), domainLabel(company)].filter(Boolean).join(" - ") || "Location or website not verified yet")}</p>
          <div class="form-actions">
            ${company.raw?.website_url || company.raw_domain ? `<a class="secondary-action" href="${escapeHtml(company.raw?.website_url || "https://" + company.raw_domain)}" target="_blank" rel="noreferrer">Website</a>` : ""}
            <button class="text-action" type="button" data-route-target="companies/list">View all companies</button>
          </div>
        </div>
        <article class="guided-form company-review-card">
          <section>
            <h3>Why it may fit</h3>
            <ul class="reason-list">${reasons.length ? reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("") : "<li>Fit evidence has not been written yet.</li>"}</ul>
          </section>
          <section>
            <h3>Concerns or unknowns</h3>
            <ul class="reason-list">${concerns.length ? concerns.map((risk) => `<li>${escapeHtml(risk)}</li>`).join("") : "<li>No blocker is currently known.</li>"}</ul>
          </section>
          <section>
            <h3>Sources</h3>
            <div class="source-list">${(company.source_refs || []).length ? company.source_refs.slice(0, 3).map((source) => sourceLinkMarkup(source)).join("") : `<p class="muted">No source links are available yet.</p>`}</div>
          </section>
          <label class="field">
            <span>Optional reason if this is not a fit</span>
            <select id="rejectReason">
              <option value="">No reason selected</option>
              <option>Wrong location</option>
              <option>Wrong industry</option>
              <option>Poor role fit</option>
              <option>Company type</option>
              <option>Other</option>
            </select>
          </label>
          <div class="form-actions">
            <button class="primary-action" type="button" data-company-decision="saved" data-company-id="${escapeHtml(company.company_id)}">Save company</button>
            <button class="secondary-action" type="button" data-company-decision="rejected" data-company-id="${escapeHtml(company.company_id)}">Not for me</button>
            <button class="text-action" type="button" data-company-select="${escapeHtml(company.company_id)}" data-route-target="companies/list">View full details</button>
          </div>
        </article>
      </section>
    </section>
  `;
  bindCompanyActions();
}

function researchPanelMarkup(data) {
  const status = data.campaignStatus;
  const active = isResearchActive(status);
  const counts = status?.artifact_counts || {};
  const target = status?.state?.target_company_count || 30;
  return `
    <article class="panel">
      <div class="panel-header" style="padding: 0 0 16px; border-bottom: 0;">
        <div>
          <span class="eyebrow">Research brief</span>
          <h3>${active ? "Searching for companies" : "Brief your recruiter"}</h3>
          <p class="muted">${active ? "New companies will appear after the backend imports them." : "Set a clear search direction before launch."}</p>
        </div>
        <span class="status-chip ${active ? "info" : "success"}">${active ? "Running" : "Ready"}</span>
      </div>
      ${active ? `
        <div class="stack">
          ${activityMarkup({ kind: "running", title: "Company search in progress", body: `${counts.companies || 0} of about ${target} companies found so far.`, progress: progressFromCounts(counts.companies || 0, target) })}
          <div class="actions">
            <button class="button secondary" type="button" data-company-action="import-research">Import latest findings</button>
          </div>
        </div>
      ` : researchFormMarkup()}
    </article>
  `;
}

function researchFormMarkup() {
  return `
    <form class="form-grid" id="researchForm">
      <label class="field">
        <span>Location</span>
        <input id="researchLocations" value="Zurich, Switzerland" autocomplete="off">
      </label>
      <label class="field">
        <span>Target roles</span>
        <input id="researchRoles" value="Profile-aligned ML and Applied AI roles" autocomplete="off">
      </label>
      <label class="field">
        <span>Minimum companies</span>
        <input id="researchCount" type="number" min="1" max="100" step="1" value="30">
      </label>
      <label class="field">
        <span>Search depth</span>
        <select id="researchBudget">
          <option value="15">Light scan</option>
          <option value="30" selected>Standard search</option>
          <option value="60">Deep search</option>
        </select>
      </label>
      <label class="field wide">
        <span>Additional instruction</span>
        <textarea id="researchNotes" rows="3" placeholder="Focus on medium-sized AI companies around Zurich that work on useful, non-defense products."></textarea>
      </label>
      <div class="wide panel" style="box-shadow: none;">
        <h4>Search summary</h4>
        <p class="muted" id="researchSummary" style="margin-top: 6px;">Search for profile-aligned ML and Applied AI roles near Zurich, Switzerland with a standard time budget.</p>
      </div>
      <div class="actions wide">
        <button class="button primary" type="submit">Start search</button>
      </div>
    </form>
  `;
}

function companyFiltersMarkup() {
  const stages = [
    ["all", "All"],
    ["new", "New match"],
    ["saved", "Saved"],
    ["preparing", "Preparing"],
    ["review", "Needs review"],
    ["ready", "Ready"],
    ["sent", "Sent"],
    ["blocked", "Blocked"],
  ];
  return `
    <div class="filter-bar">
      <input class="search-input" id="companySearch" value="${escapeHtml(state.companySearch)}" placeholder="Search companies, locations, industries">
      <select id="companySort" class="search-input" style="max-width: 220px;">
        <option value="best" ${state.companySort === "best" ? "selected" : ""}>Best match</option>
        <option value="recent" ${state.companySort === "recent" ? "selected" : ""}>Recently found</option>
        <option value="name" ${state.companySort === "name" ? "selected" : ""}>Company name</option>
        <option value="stage" ${state.companySort === "stage" ? "selected" : ""}>Application status</option>
      </select>
    </div>
    <div class="section-tabs">
      <div class="segmented">
        ${stages.map(([id, label]) => `<button type="button" class="${state.activeCompanyStage === id ? "active" : ""}" data-company-stage="${id}">${label}</button>`).join("")}
      </div>
    </div>
  `;
}

function companyRowMarkup(company, data) {
  const stage = companyStage(company);
  const fit = latestFit(company, data.fitEvaluations);
  const reasons = matchReasons(company, fit).slice(0, 1);
  return `
    <article class="company-row">
      <div class="tight-stack">
        <div class="company-title">
          <div>
            <h3>${escapeHtml(company.name || company.company_id)}</h3>
            <p class="muted">${escapeHtml([firstValue(company.locations), firstValue(company.industry_tags)].filter(Boolean).join(" - ") || "Location or industry not verified")} - ${escapeHtml(stage)}</p>
          </div>
        </div>
        <p>${escapeHtml(shortText(company.description || "No company summary available.", 190))}</p>
        <p class="muted">${escapeHtml(reasons[0] || fitLabel(company.confidence))}</p>
      </div>
      <div class="actions">
        <button class="primary-action" type="button" data-guided-company="${escapeHtml(company.company_id)}">Review fit</button>
      </div>
    </article>
  `;
}

function companyDetailMarkup(company, data) {
  const fit = latestFit(company, data.fitEvaluations);
  const reasons = matchReasons(company, fit);
  const concerns = companyConcerns(company, fit);
  const contacts = data.contacts.filter((contact) => contact.external_company_id === company.company_id);
  return `
    <article class="panel">
      <div class="tight-stack">
        <span class="eyebrow">Company detail</span>
        <h2>${escapeHtml(company.name || company.company_id)}</h2>
        <p class="muted">${escapeHtml([firstValue(company.locations), domainLabel(company)].filter(Boolean).join(" - "))}</p>
      </div>
      <div class="actions" style="margin-top: 18px;">
        ${company.raw?.website_url || company.raw_domain ? `<a class="button secondary" href="${escapeHtml(company.raw?.website_url || "https://" + company.raw_domain)}" target="_blank" rel="noreferrer">Website</a>` : ""}
        <button class="button primary" type="button" data-prepare-company="${escapeHtml(company.company_id)}" ${company.can_draft_application ? "" : "disabled title=\"" + escapeHtml(applicationBlockText(company)) + "\""}>Prepare application</button>
      </div>
    </article>
    <article class="panel">
      <h3>Overview</h3>
      <p class="muted" style="margin-top: 8px;">${escapeHtml(company.description || "No summary available.")}</p>
      <div class="summary-line" style="margin-top: 14px;">
        ${(company.industry_tags || []).slice(0, 4).map((tag) => `<span class="mini-chip">${escapeHtml(readableTag(tag))}</span>`).join("")}
      </div>
    </article>
    <article class="panel">
      <h3>Why it matches</h3>
      <ul class="reason-list" style="margin-top: 12px;">
        ${reasons.length ? reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("") : "<li>Fit evidence has not been written yet.</li>"}
      </ul>
    </article>
    <article class="panel">
      <h3>Concerns and uncertainties</h3>
      <ul class="reason-list" style="margin-top: 12px;">
        ${concerns.length ? concerns.map((risk) => `<li>${escapeHtml(risk)}</li>`).join("") : "<li>No blocker is currently known.</li>"}
      </ul>
    </article>
    <article class="panel">
      <h3>Evidence</h3>
      <div class="source-list" style="margin-top: 12px;">
        ${(company.source_refs || []).length ? company.source_refs.slice(0, 5).map((source) => sourceLinkMarkup(source)).join("") : emptyMarkup("No sources listed.", "Review before acting on this company.")}
      </div>
    </article>
    <article class="panel">
      <h3>Application workspace</h3>
      <p class="muted" style="margin-top: 8px;">${contacts.length ? `${contacts.length} contact candidate${contacts.length === 1 ? "" : "s"} available.` : "No contact is verified yet."}</p>
      <div class="actions" style="margin-top: 18px;">
        <button class="button secondary" type="button" data-company-action="research-status">Research more deeply</button>
        <button class="button primary" type="button" data-prepare-company="${escapeHtml(company.company_id)}" ${company.can_draft_application ? "" : "disabled"}>Prepare application</button>
      </div>
    </article>
  `;
}

function researchProgressTitle(data) {
  const draft = getResearchDraft(data);
  const locations = draft.locations.length ? joinHuman(draft.locations) : "your target locations";
  const roles = rolesSummary(draft);
  return `Your recruiter is searching ${locations} for ${roles} companies.`;
}

function researchProgressSentence(data) {
  const status = data.campaignStatus;
  const counts = status?.artifact_counts || {};
  const target = status?.state?.target_company_count || getResearchDraft(data).minCompanies || 30;
  const companiesFound = Number(counts.companies ?? data.companies.length ?? 0);
  if (isResearchComplete(status)) return `${companiesFound} of at least ${target} companies have been found.`;
  if (isResearchActive(status)) return `${companiesFound} of at least ${target} companies found so far.`;
  return "No company search is currently running.";
}

function researchStatusLabel(status) {
  if (!status) return "Ready to start a search.";
  if (isResearchComplete(status)) return "Search complete.";
  if (isResearchActive(status)) {
    const count = Number(status.artifact_counts?.companies || 0);
    if (count > 0) return "New matches are appearing.";
    return "Searching for companies.";
  }
  if (status.status === "failed") return "The search needs attention.";
  return "Starting your search.";
}

function safeResearchEvents(status) {
  const events = ["Search started"];
  const counts = status?.artifact_counts || {};
  if (counts.companies) events.push("Candidate saved");
  if (counts.fit_evaluations) events.push("Fit evidence checked");
  if (isResearchComplete(status)) events.push("Search complete");
  if (!events.length) events.push("Waiting for activity");
  return events;
}

function isResearchComplete(status) {
  const value = status?.status || status?.import_state?.run_status || "";
  return ["imported", "completed", "succeeded"].includes(value);
}

function loadCompanyDecisions() {
  try {
    const parsed = JSON.parse(localStorage.getItem(COMPANY_DECISIONS_KEY) || "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function saveCompanyDecision(companyId, decision, reason = "") {
  const decisions = loadCompanyDecisions();
  decisions[companyId] = { decision, reason, decidedAt: new Date().toISOString() };
  localStorage.setItem(COMPANY_DECISIONS_KEY, JSON.stringify(decisions));
}

function unreviewedCompanies(data) {
  const decisions = loadCompanyDecisions();
  return data.companies.filter((company) => !decisions[company.company_id] && !company.has_been_contacted);
}

function selectedGuidedCompany(data, companies) {
  if (state.guidedCompanyReviewId) {
    const found = data.companies.find((company) => company.company_id === state.guidedCompanyReviewId);
    if (found) return found;
  }
  return companies[0] || null;
}

function filteredCompanies(data) {
  const needle = state.companySearch.trim().toLowerCase();
  let rows = data.companies.filter((company) => {
    if (state.activeCompanyStage !== "all" && stageKey(company) !== state.activeCompanyStage) return false;
    if (!needle) return true;
    const haystack = [company.name, company.description, company.remote_policy, ...(company.locations || []), ...(company.industry_tags || [])].join(" ").toLowerCase();
    return haystack.includes(needle);
  });
  rows = [...rows].sort((a, b) => {
    if (state.companySort === "name") return String(a.name || "").localeCompare(String(b.name || ""));
    if (state.companySort === "stage") return companyStage(a).localeCompare(companyStage(b));
    if (state.companySort === "recent") return String(b.created_at || "").localeCompare(String(a.created_at || ""));
    return Number(b.confidence || 0) - Number(a.confidence || 0);
  });
  return rows;
}

function selectedCompany(data, filtered) {
  if (state.selectedCompanyId) {
    const found = data.companies.find((company) => company.company_id === state.selectedCompanyId);
    if (found) return found;
  }
  return filtered[0] || data.companies[0] || null;
}

function applicationRowMarkup(draft, options = {}) {
  const tone = draft.status === "ready" ? "success" : draft.status === "sent" ? "success" : draft.status === "blocked" ? "danger" : "warning";
  return `
    <article class="application-row">
      <div class="tight-stack">
        <div class="application-title">
          <h3>${escapeHtml(draft.company_name || draft.company_id)}</h3>
          <span class="status-chip ${tone}">${escapeHtml(draft.status_label || humanStatus(draft.status))}</span>
          ${draft.cv ? '<span class="mini-chip success">Resume attached</span>' : '<span class="mini-chip warning">Missing resume</span>'}
        </div>
        <p>${escapeHtml(draft.subject || "No subject")}</p>
        <p class="muted">${escapeHtml(draft.email_address || "Recipient not verified")}</p>
      </div>
      <div class="actions">
        <button class="button secondary" type="button" data-review-draft="${escapeHtml(draft.draft_id)}">Inspect</button>
        ${options.approval ? `<button class="button danger" type="button" data-confirm-one="${escapeHtml(draft.intent_id || draft.draft_id)}">Approve</button>` : ""}
      </div>
    </article>
  `;
}

function selectedDraftReviewMarkup(data) {
  const draft = state.selectedDraftId
    ? data.outboxDrafts.find((item) => item.draft_id === state.selectedDraftId) || data.outboxDrafts[0]
    : data.outboxDrafts[0];
  if (!draft) return `<article class="panel">${emptyMarkup("Select an application.", "Email and resume details will appear here.")}</article>`;
  return `
    <article class="panel review-pane">
      <div class="tight-stack">
        <span class="eyebrow">Review workspace</span>
        <h3>${escapeHtml(draft.company_name)}</h3>
        <p class="muted">${escapeHtml(draft.email_address || "Recipient unknown")}</p>
      </div>
      <div class="stack" style="margin-top: 18px;">
        <div>
          <h4>Subject</h4>
          <p style="margin-top: 6px;">${escapeHtml(draft.subject || "No subject")}</p>
        </div>
        <div>
          <h4>Email draft</h4>
          <div class="email-document" style="margin-top: 8px;">${escapeHtml(draft.body_text || "No email body available.")}</div>
        </div>
        <div>
          <h4>Resume</h4>
          <div class="resume-frame" style="margin-top: 8px;">
            ${draft.cv ? `<a class="button secondary" href="${escapeHtml(draft.cv.url)}" target="_blank" rel="noopener">Open resume PDF</a>` : `<p class="muted">No resume attachment is available.</p>`}
          </div>
        </div>
        <div class="actions">
          <button class="button secondary" type="button" disabled title="Section regeneration is not available in this frontend yet.">Request changes</button>
          <button class="button primary" type="button" ${draft.status === "ready" ? "" : "disabled"} data-confirm-one="${escapeHtml(draft.intent_id || draft.draft_id)}">Approve for final checks</button>
        </div>
      </div>
    </article>
  `;
}

function sentRowMarkup(row) {
  return `
    <article class="application-row">
      <div class="tight-stack">
        <div class="application-title">
          <h3>${escapeHtml(row.company_name || row.company_id || "Company")}</h3>
          <span class="status-chip success">${escapeHtml(humanStatus(row.status || "sent"))}</span>
        </div>
        <p>${escapeHtml(row.subject || "No subject")}</p>
        <p class="muted">${escapeHtml(row.email_address || "Recipient unavailable")} - ${escapeHtml(dateLabel(row.sent_at))}</p>
      </div>
      <div class="actions">
        ${row.provider_url ? `<a class="button secondary" href="${escapeHtml(row.provider_url)}" target="_blank" rel="noreferrer">Open provider record</a>` : ""}
      </div>
    </article>
  `;
}

function applicationActivityMarkup(status) {
  return activityMarkup({
    kind: "running",
    title: "Preparing a tailored application",
    body: applicationProgressText(status),
    progress: 55,
  });
}

function bindRouteButtons() {
  document.querySelectorAll("[data-route-target]").forEach((button) => {
    button.addEventListener("click", () => setRoute(button.dataset.routeTarget));
  });
}

function bindProfileActions() {
  bindRouteButtons();
  const form = document.querySelector("#profileComposer");
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.querySelector("#profileMessage");
    const message = input?.value.trim();
    if (!message) return;
    await postOnboardingMessage(message);
  });
  document.querySelector("#resumeUpload")?.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    await uploadOnboardingFile(file);
  });
  document.querySelectorAll("[data-profile-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.profileAction;
      if (action === "start") await startOnboarding();
      if (action === "validate") await importOnboardingArtifacts();
      if (action === "finish") await finishOnboarding();
      if (action === "approve") await approveOnboarding();
    });
  });
  const chat = document.querySelector("#chatMessages");
  if (chat) chat.scrollTop = chat.scrollHeight;
}

function bindCompanyActions() {
  bindRouteButtons();
  document.querySelector("#companySearch")?.addEventListener("input", (event) => {
    state.companySearch = event.target.value;
    renderCompanies(state.data);
  });
  document.querySelector("#companySort")?.addEventListener("change", (event) => {
    state.companySort = event.target.value;
    renderCompanies(state.data);
  });
  document.querySelectorAll("[data-company-stage]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeCompanyStage = button.dataset.companyStage;
      renderCompanies(state.data);
    });
  });
  document.querySelectorAll("[data-company-select]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedCompanyId = button.dataset.companySelect;
      if (button.dataset.routeTarget) {
        setRoute(button.dataset.routeTarget);
      } else {
        renderCompanies(state.data);
      }
    });
  });
  document.querySelectorAll("[data-guided-company]").forEach((button) => {
    button.addEventListener("click", () => {
      state.guidedCompanyReviewId = button.dataset.guidedCompany;
      setRoute("companies/review");
    });
  });
  document.querySelectorAll("[data-prepare-company]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (button.disabled) return;
      await prepareApplicationForCompany(button.dataset.prepareCompany);
    });
  });
  document.querySelectorAll("[data-company-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.companyAction;
      if (action === "open-research") focusResearchForm();
      if (action === "research-status") await showResearchStatus();
      if (action === "import-research") await importResearch();
    });
  });
  document.querySelectorAll("[data-company-decision]").forEach((button) => {
    button.addEventListener("click", () => {
      const companyId = button.dataset.companyId;
      const decision = button.dataset.companyDecision;
      const reason = document.querySelector("#rejectReason")?.value || "";
      if (!companyId || !decision) return;
      saveCompanyDecision(companyId, decision, decision === "rejected" ? reason : "");
      state.guidedCompanyReviewId = null;
      showToast(decision === "saved" ? "Company saved." : "Company skipped.");
      renderGuidedCompanyReview(state.data);
    });
  });
  const form = document.querySelector("#researchForm");
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await launchResearch();
  });
  ["researchLocations", "researchRoles", "researchBudget", "researchCount", "researchNotes"].forEach((id) => {
    document.querySelector(`#${id}`)?.addEventListener("input", updateResearchSummary);
  });
}

function bindApplicationActions() {
  bindRouteButtons();
  document.querySelectorAll("[data-app-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeApplicationTab = button.dataset.appTab;
      renderApplications(state.data);
    });
  });
  document.querySelectorAll("[data-review-draft]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedDraftId = button.dataset.reviewDraft;
      state.activeApplicationTab = "review";
      renderApplications(state.data);
    });
  });
  document.querySelectorAll("[data-confirm-one]").forEach((button) => {
    button.addEventListener("click", () => openSendConfirmation([button.dataset.confirmOne]));
  });
  document.querySelector("[data-approve-ready]")?.addEventListener("click", () => {
    const ids = state.data.outboxDrafts.filter((draft) => draft.status === "ready").map((draft) => draft.intent_id).filter(Boolean);
    openSendConfirmation(ids);
  });
  document.querySelector("[data-prepare-batch]")?.addEventListener("click", () => openBatchPrepareConfirmation());
}

async function startOnboarding() {
  await actionWithToast("Starting recruiter conversation", async () => {
    await fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboardingRunId)}/start`, { method: "POST" });
  });
}

async function postOnboardingMessage(message) {
  await actionWithToast("Sending message", async () => {
    await fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboardingRunId)}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
  });
}

async function finishOnboarding() {
  await actionWithToast("Preparing profile changes", async () => {
    await fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboardingRunId)}/finish`, { method: "POST" });
  });
}

async function importOnboardingArtifacts() {
  await actionWithToast("Checking profile files", async () => {
    await fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboardingRunId)}/import-artifacts`, { method: "POST" });
  });
}

async function approveOnboarding() {
  openModal(
    "Approve profile changes",
    `
      <div class="stack">
        <p>Approve the reviewed career profile, master resume material, and outreach policy for future research and preparation.</p>
        <p class="muted">This does not send applications or contact companies.</p>
        <div class="actions">
          <button class="button secondary" type="button" data-modal-cancel>Cancel</button>
          <button class="button primary" type="button" data-approve-profile>Approve profile</button>
        </div>
      </div>
    `,
  );
  document.querySelector("[data-modal-cancel]")?.addEventListener("click", closeModal);
  document.querySelector("[data-approve-profile]")?.addEventListener("click", async () => {
    await actionWithToast("Approving profile", async () => {
      await fetchJson(`/onboarding/runs/${encodeURIComponent(state.onboardingRunId)}/promote`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reviewer_id: "local-user",
          confirm_user_profile: true,
          confirm_master_cv_profile: true,
          confirm_policy: true,
        }),
      });
    });
    closeModal();
  });
}

async function uploadOnboardingFile(file) {
  await actionWithToast("Uploading resume source", async () => {
    await fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboardingRunId)}/input-files/${encodeURIComponent(file.name)}`, {
      method: "PUT",
      headers: { "Content-Type": file.type || "application/octet-stream" },
      body: await file.arrayBuffer(),
    });
  });
}

function defaultResearchDraft(data) {
  return {
    locations: data?.profile?.has_approved_profile ? ["Zurich, Switzerland"] : [],
    remotePreference: "remote-friendly",
    relocationOpen: true,
    roles: ["Machine Learning", "Applied AI", "Document Intelligence"],
    customRole: "",
    industries: ["Applied AI", "Document automation"],
    characteristics: ["useful products", "medium-sized teams"],
    exclusions: ["Defense"],
    notes: "",
    scopePreset: "balanced",
    minCompanies: 30,
    timeBudgetMinutes: 30,
  };
}

function getResearchDraft(data) {
  if (state.researchDraft) return state.researchDraft;
  let stored = null;
  try {
    stored = JSON.parse(localStorage.getItem(RESEARCH_DRAFT_KEY) || "null");
  } catch {
    stored = null;
  }
  state.researchDraft = { ...defaultResearchDraft(data), ...(stored && typeof stored === "object" ? stored : {}) };
  return state.researchDraft;
}

function saveResearchDraft(draft) {
  state.researchDraft = draft;
  localStorage.setItem(RESEARCH_DRAFT_KEY, JSON.stringify(draft));
}

function saveCurrentResearchStep() {
  const draft = { ...getResearchDraft(state.data) };
  if (state.researchStep === 0) {
    draft.locations = splitInput(document.querySelector("#briefLocations")?.value);
    draft.remotePreference = document.querySelector("input[name='remotePreference']:checked")?.value || draft.remotePreference;
    draft.relocationOpen = Boolean(document.querySelector("#briefRelocation")?.checked);
  }
  if (state.researchStep === 1) {
    draft.roles = [...document.querySelectorAll("input[name='roles']:checked")].map((input) => input.value);
    draft.customRole = document.querySelector("#briefCustomRole")?.value.trim() || "";
  }
  if (state.researchStep === 2) {
    draft.industries = splitInput(document.querySelector("#briefIndustries")?.value);
    draft.characteristics = [...document.querySelectorAll("input[name='characteristics']:checked")].map((input) => input.value);
    draft.exclusions = splitInput(document.querySelector("#briefExclusions")?.value);
    draft.notes = document.querySelector("#briefNotes")?.value.trim() || "";
  }
  if (state.researchStep === 3) {
    const preset = document.querySelector("input[name='scopePreset']:checked")?.value || draft.scopePreset;
    const minCompanies = Number.parseInt(document.querySelector("#briefMinCompanies")?.value || "", 10);
    draft.scopePreset = preset;
    draft.minCompanies = Number.isFinite(minCompanies) ? minCompanies : draft.minCompanies;
    draft.timeBudgetMinutes = scopePresets[preset]?.minutes || draft.timeBudgetMinutes;
  }
  saveResearchDraft(draft);
}

function validateResearchStep(stepIndex) {
  clearInlineErrors();
  const draft = getResearchDraft(state.data);
  if (stepIndex === 0 && !draft.locations.length) return showInlineError("briefLocationsError", "Add at least one location.");
  if (stepIndex === 1 && !draft.roles.length && !draft.customRole) return showInlineError("briefRolesError", "Choose at least one role direction or add a custom role.");
  if (stepIndex === 3 && (draft.minCompanies < 1 || draft.minCompanies > 100)) return showInlineError("briefScopeError", "Choose a target between 1 and 100 companies.");
  return true;
}

function clearInlineErrors() {
  document.querySelectorAll(".inline-error").forEach((node) => {
    node.hidden = true;
    node.textContent = "";
  });
}

function showInlineError(id, message) {
  const target = document.querySelector(`#${id}`);
  if (target) {
    target.hidden = false;
    target.textContent = message;
    target.scrollIntoView({ block: "nearest" });
  }
  return false;
}

function profileRoleSuggestions() {
  return ["Machine Learning", "Applied AI", "Document Intelligence", "MLOps"];
}

function normalizedResearchBrief(draft) {
  const roles = [...draft.roles, draft.customRole].map((role) => role.trim()).filter(Boolean);
  const preferenceText = [
    draft.characteristics.length ? `Prioritize ${joinHuman(draft.characteristics)}.` : "",
    draft.industries.length ? `Look for ${joinHuman(draft.industries)} companies.` : "",
    draft.exclusions.length ? `Exclude ${joinHuman(draft.exclusions)}.` : "",
    draft.notes || "",
  ]
    .filter(Boolean)
    .join(" ");
  return {
    role_focus: roles.length ? roles.join(", ") : "Profile-aligned roles",
    locations: draft.locations,
    time_budget_minutes: Number(draft.timeBudgetMinutes || scopePresets[draft.scopePreset]?.minutes || 30),
    max_companies: Number(draft.minCompanies || scopePresets[draft.scopePreset]?.count || 30),
    notes: preferenceText || null,
  };
}

function recruiterBriefText(draft) {
  return `Search ${locationSummary(draft)} for ${rolesSummary(draft)} work. ${preferencesSummary(draft)} Find at least ${Number(draft.minCompanies || 30)} strong candidates.`;
}

function locationSummary(draft) {
  const model = draft.remotePreference === "remote-friendly" ? "remote-friendly companies" : draft.remotePreference === "hybrid" ? "hybrid-friendly companies" : "onsite roles";
  const relocation = draft.relocationOpen ? " and companies open to relocation" : "";
  return `${joinHuman(draft.locations.length ? draft.locations : ["your preferred locations"])} and nearby ${model}${relocation}`;
}

function rolesSummary(draft) {
  const roles = [...draft.roles, draft.customRole].map((role) => role.trim()).filter(Boolean);
  return joinHuman(roles.length ? roles : ["profile-aligned"]);
}

function preferencesSummary(draft) {
  const parts = [];
  if (draft.industries.length) parts.push(`Prioritize ${joinHuman(draft.industries)}`);
  if (draft.characteristics.length) parts.push(joinHuman(draft.characteristics));
  if (draft.exclusions.length) parts.push(`Exclude ${joinHuman(draft.exclusions)}`);
  if (draft.notes) parts.push(draft.notes);
  return parts.length ? `${parts.join(". ")}.` : "Prioritize companies with clear evidence of fit.";
}

function scopeSummary(draft) {
  const preset = scopePresets[draft.scopePreset] || scopePresets.balanced;
  return `${preset.label} search, aiming for at least ${Number(draft.minCompanies || preset.count)} companies.`;
}

function joinHuman(items) {
  const values = items.map((item) => String(item || "").trim()).filter(Boolean);
  if (values.length <= 1) return values[0] || "";
  if (values.length === 2) return `${values[0]} and ${values[1]}`;
  return `${values.slice(0, -1).join(", ")}, and ${values.at(-1)}`;
}

function friendlyLaunchError(error) {
  const message = error?.message || "";
  if (message.toLowerCase().includes("approved profile")) return "Approve your profile before starting company search.";
  if (message.toLowerCase().includes("already")) return "A company search is already starting. Refresh progress before launching another one.";
  return "The search could not be started. Please check the brief and try again.";
}

function focusGuidedHeading() {
  window.requestAnimationFrame(() => document.querySelector("#guided-step-title")?.focus());
}

function focusResearchForm() {
  state.researchStep = 0;
  localStorage.setItem("guidedResearchStep", "0");
  setRoute("companies/brief");
}

function bindResearchBriefActions() {
  document.querySelectorAll(".choice-card input").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.type === "radio") {
        document.querySelectorAll(`input[name="${CSS.escape(input.name)}"]`).forEach((groupInput) => {
          groupInput.closest(".choice-card")?.classList.toggle("selected", groupInput.checked);
        });
      } else {
        input.closest(".choice-card")?.classList.toggle("selected", input.checked);
      }
      saveCurrentResearchStep();
    });
  });
  document.querySelectorAll("#researchBriefForm input, #researchBriefForm textarea").forEach((input) => {
    input.addEventListener("input", saveCurrentResearchStep);
  });
  document.querySelector("[data-brief-back]")?.addEventListener("click", () => {
    saveCurrentResearchStep();
    state.researchStep = Math.max(0, state.researchStep - 1);
    localStorage.setItem("guidedResearchStep", String(state.researchStep));
    renderResearchBrief(state.data);
  });
  document.querySelectorAll("[data-edit-brief]").forEach((button) => {
    button.addEventListener("click", () => {
      state.researchStep = guidedResearchSteps.findIndex((step) => step.id === button.dataset.editBrief);
      localStorage.setItem("guidedResearchStep", String(state.researchStep));
      renderResearchBrief(state.data);
    });
  });
  const form = document.querySelector("#researchBriefForm");
  form?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.target?.tagName === "TEXTAREA") return;
    event.preventDefault();
    form.requestSubmit();
  });
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    saveCurrentResearchStep();
    if (!validateResearchStep(state.researchStep)) return;
    if (state.researchStep < guidedResearchSteps.length - 1) {
      state.researchStep += 1;
      localStorage.setItem("guidedResearchStep", String(state.researchStep));
      renderResearchBrief(state.data);
      return;
    }
    await confirmResearchLaunch();
  });
}

async function confirmResearchLaunch() {
  const draft = getResearchDraft(state.data);
  openModal(
    "Start company search",
    `
      <div class="stack">
        <p>${escapeHtml(recruiterBriefText(draft))}</p>
        <p class="muted">Your recruiter will search in the background. This cannot contact companies or approve applications.</p>
        <div class="actions">
          <button class="secondary-action" type="button" data-modal-cancel>Back</button>
          <button class="primary-action" type="button" data-confirm-launch>Start company search</button>
        </div>
      </div>
    `,
  );
  document.querySelector("[data-modal-cancel]")?.addEventListener("click", closeModal);
  document.querySelector("[data-confirm-launch]")?.addEventListener("click", async (event) => {
    await launchResearchFromBrief(event.currentTarget);
  });
}

async function launchResearchFromBrief(button) {
  if (state.launchInFlight) return;
  state.launchInFlight = true;
  if (button) button.disabled = true;
  try {
    const draft = getResearchDraft(state.data);
    const payload = normalizedResearchBrief(draft);
    const prepared = await fetchJson(endpoints.companyResearch, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await fetchJson(`${endpoints.companyResearch}/${encodeURIComponent(prepared.run_id)}/launch`, { method: "POST" });
    state.campaignRunId = prepared.run_id;
    localStorage.setItem("companyResearchRunId", prepared.run_id);
    localStorage.setItem(RESEARCH_BRIEF_KEY, JSON.stringify({ ...draft, runId: prepared.run_id, launchedAt: new Date().toISOString() }));
    closeModal();
    showToast("Starting your search.");
    startCompanyResearchPolling();
    setRoute("companies/progress");
  } catch (error) {
    const target = document.querySelector("#briefLaunchError");
    if (target) {
      target.hidden = false;
      target.textContent = friendlyLaunchError(error);
    } else {
      showToast(friendlyLaunchError(error));
    }
  } finally {
    state.launchInFlight = false;
    if (button) button.disabled = false;
  }
}

async function showResearchStatus() {
  if (!state.campaignRunId) {
    showToast("No current research run is loaded.");
    return;
  }
  const status = await fetchJson(`${endpoints.companyResearch}/${encodeURIComponent(state.campaignRunId)}/status`);
  openModal(
    "Research status",
    `
      <div class="stack">
        ${activityMarkup({
          kind: isResearchActive(status) ? "running" : "done",
          title: isResearchActive(status) ? "Searching for companies" : "Research complete",
          body: `${status.artifact_counts?.companies || 0} companies found. ${status.artifact_counts?.fit_evaluations || 0} fit explanations available.`,
          progress: progressFromCounts(status.artifact_counts?.companies || 0, status.state?.target_company_count || 30),
        })}
        <div class="actions">
          <button class="button secondary" type="button" data-modal-cancel>Close</button>
          <button class="button primary" type="button" data-import-research>Import latest findings</button>
        </div>
      </div>
    `,
  );
  document.querySelector("[data-modal-cancel]")?.addEventListener("click", closeModal);
  document.querySelector("[data-import-research]")?.addEventListener("click", async () => {
    await importResearch();
    closeModal();
  });
}

async function importResearch() {
  if (!state.campaignRunId) {
    showToast("No current research run is loaded.");
    return;
  }
  await actionWithToast("Importing latest findings", async () => {
    await fetchJson(`${endpoints.companyResearch}/${encodeURIComponent(state.campaignRunId)}/import`, { method: "POST" });
  });
}

function startCompanyResearchPolling() {
  if (state.companyResearchPoll) clearInterval(state.companyResearchPoll);
  state.companyResearchPoll = setInterval(async () => {
    if (!state.campaignRunId || !state.data) return;
    const status = await safeFetchJson(`${endpoints.companyResearch}/${encodeURIComponent(state.campaignRunId)}/status`);
    if (!status) return;
    state.data.campaignStatus = status;
    if ((status.artifact_counts?.companies || 0) > 0 || !isResearchActive(status)) {
      state.data = await loadProductData();
    }
    if (!isResearchActive(status)) clearInterval(state.companyResearchPoll);
    if (state.route === "home") renderHome(state.data);
    if (state.route === "companies") renderCompanies(state.data);
  }, 10000);
}

async function prepareApplicationForCompany(companyId) {
  if (!companyId) return;
  const company = state.data.companies.find((item) => item.company_id === companyId);
  openModal(
    "Prepare application",
    `
      <div class="stack">
        <p>Prepare a tailored resume and outreach draft for <strong>${escapeHtml(company?.name || companyId)}</strong>.</p>
        <label class="field">
          <span>Note for the writing agent</span>
          <textarea id="prepareNote" rows="4" placeholder="Emphasize document understanding and interest in relocating to Zurich."></textarea>
        </label>
        <div class="actions">
          <button class="button secondary" type="button" data-modal-cancel>Cancel</button>
          <button class="button primary" type="button" data-run-prepare>Start preparation</button>
        </div>
      </div>
    `,
  );
  document.querySelector("[data-modal-cancel]")?.addEventListener("click", closeModal);
  document.querySelector("[data-run-prepare]")?.addEventListener("click", async () => {
    const notes = document.querySelector("#prepareNote")?.value.trim() || null;
    await actionWithToast("Preparing application", async () => {
      const prepared = await fetchJson(endpoints.applicationDrafts, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company_id: companyId, notes }),
      });
      await fetchJson(`${endpoints.applicationDrafts}/${encodeURIComponent(prepared.run_id)}/launch`, { method: "POST" });
      state.lastApplicationRunId = prepared.run_id;
      localStorage.setItem("applicationDraftRunId", prepared.run_id);
      startApplicationDraftPolling(prepared.run_id);
    });
    closeModal();
    state.activeApplicationTab = "preparing";
    setRoute("applications");
  });
}

function startApplicationDraftPolling(runId) {
  if (state.applicationDraftPoll) clearInterval(state.applicationDraftPoll);
  state.applicationDraftPoll = setInterval(async () => {
    const status = await safeFetchJson(`${endpoints.applicationDrafts}/${encodeURIComponent(runId)}/status`);
    if (!status || !state.data) return;
    state.data.applicationStatus = status;
    if (!isApplicationActive(status)) clearInterval(state.applicationDraftPoll);
    if (state.route === "home") renderHome(state.data);
    if (state.route === "applications") renderApplications(state.data);
  }, 10000);
}

function openBatchPrepareConfirmation() {
  const eligible = state.data.companies.filter((company) => company.can_draft_application && !company.has_application_draft).slice(0, 25);
  openModal(
    "Prepare missing applications",
    `
      <div class="stack">
        <p>Prepare tailored application packages for ${eligible.length} eligible companies. You will still review each application before approval.</p>
        <ul class="plain-list">${eligible.slice(0, 8).map((company) => `<li>${escapeHtml(company.name || company.company_id)}</li>`).join("")}</ul>
        <div class="actions">
          <button class="button secondary" type="button" data-modal-cancel>Cancel</button>
          <button class="button primary" type="button" data-run-batch ${eligible.length ? "" : "disabled"}>Start batch</button>
        </div>
      </div>
    `,
  );
  document.querySelector("[data-modal-cancel]")?.addEventListener("click", closeModal);
  document.querySelector("[data-run-batch]")?.addEventListener("click", async () => {
    await actionWithToast("Starting batch preparation", async () => {
      await fetchJson(endpoints.applicationDraftBatches, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "selected", company_ids: eligible.map((company) => company.company_id), concurrency: 2 }),
      });
    });
    closeModal();
  });
}

function openSendConfirmation(intentIds) {
  const ids = intentIds.filter(Boolean);
  const delivery = state.data.delivery;
  const ready = state.data.outboxDrafts.filter((draft) => ids.includes(draft.intent_id));
  openModal(
    "Final approval",
    `
      <div class="stack">
        <div class="error-state" style="${delivery?.mode === "gmail_real_recipients" ? "" : "display:none;"}">
          <h3>Real delivery mode is active</h3>
          <p>Approving here can deliver to company recipients after backend checks pass. This action is irreversible.</p>
        </div>
        <p>You are approving ${ids.length} application${ids.length === 1 ? "" : "s"} for backend validation, duplicate prevention, reservation, audit logging, and configured delivery.</p>
        <ul class="plain-list">
          ${ready.map((draft) => `<li>${escapeHtml(draft.company_name)} - ${escapeHtml(draft.email_address || "recipient unknown")} - ${escapeHtml(draft.subject || "No subject")}</li>`).join("")}
        </ul>
        <p class="muted">${escapeHtml(deliveryModeText(delivery))}</p>
        <div class="actions">
          <button class="button secondary" type="button" data-modal-cancel>Cancel</button>
          <button class="button danger" type="button" data-run-send ${ids.length ? "" : "disabled"}>Approve selected applications</button>
        </div>
      </div>
    `,
  );
  document.querySelector("[data-modal-cancel]")?.addEventListener("click", closeModal);
  document.querySelector("[data-run-send]")?.addEventListener("click", async () => {
    await actionWithToast("Submitting approval", async () => {
      await fetchJson("/send-batches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ intent_ids: ids, reviewer_id: "local-user" }),
      });
    });
    closeModal();
  });
}

async function actionWithToast(label, action) {
  showToast(label);
  try {
    await action();
    await loadAndRender({ force: true });
    showToast(`${label} complete.`);
  } catch (error) {
    showToast(error.message || `${label} failed.`);
  }
}

function openModal(title, body) {
  elements.modalTitle.textContent = title;
  elements.modalBody.innerHTML = body;
  elements.modalBackdrop.hidden = false;
  document.body.classList.add("modal-open");
  elements.modalClose.focus();
}

function closeModal() {
  elements.modalBackdrop.hidden = true;
  document.body.classList.remove("modal-open");
}

function toggleAccountMenu() {
  const expanded = elements.accountButton.getAttribute("aria-expanded") === "true";
  elements.accountButton.setAttribute("aria-expanded", String(!expanded));
  elements.accountMenu.hidden = expanded;
}

function closeAccountMenu() {
  elements.accountButton.setAttribute("aria-expanded", "false");
  elements.accountMenu.hidden = true;
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    elements.toast.hidden = true;
  }, 4500);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { Accept: "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) {
    let detail = `${url} returned ${response.status}`;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail || body);
    } catch {
      // Keep the status-based message.
    }
    throw new Error(detail);
  }
  return response.json();
}

async function safeFetchJson(url, options = {}) {
  try {
    return await fetchJson(url, options);
  } catch {
    return null;
  }
}

function updateEnvironmentChip(delivery) {
  if (!delivery) {
    elements.environmentChip.textContent = "Safety mode unknown";
    elements.environmentChip.className = "environment-chip warning";
    return;
  }
  if (!delivery.sending_enabled) {
    elements.environmentChip.textContent = "Sending disabled";
    elements.environmentChip.className = "environment-chip success";
  } else if (delivery.mode === "gmail_sandbox") {
    elements.environmentChip.textContent = "Sandbox delivery";
    elements.environmentChip.className = "environment-chip info";
  } else if (delivery.mode === "gmail_real_recipients") {
    elements.environmentChip.textContent = "Real delivery enabled";
    elements.environmentChip.className = "environment-chip warning";
  } else {
    elements.environmentChip.textContent = "Delivery blocked";
    elements.environmentChip.className = "environment-chip danger";
  }
}

function deliveryModeText(delivery) {
  if (!delivery?.sending_enabled) return "Sending is disabled. The backend will record approval checks but will not contact recipients.";
  if (delivery.mode === "gmail_sandbox") return `Sandbox delivery is active. Provider delivery goes to ${delivery.sandbox_recipient || "the configured sandbox recipient"}.`;
  if (delivery.mode === "gmail_real_recipients") return "Real-recipient delivery is active. Messages may be delivered to company recipients after backend checks pass.";
  return "Delivery is blocked by configuration.";
}

function companyStage(company) {
  if (company.has_been_contacted || company.outreach_status === "sent") return "Sent";
  if (hasItems(company.policy_conflicts) || company.send_gate_status === "blocked") return "Blocked";
  if (company.send_gate_status === "reserved_for_send" || company.send_intent_status === "queued_for_send") return "Ready for approval";
  if (company.has_send_intent || company.send_gate_status === "needs_review") return "Needs review";
  if (company.has_application_draft) return "Application prepared";
  if ((company.review_flags || []).length) return "Needs review";
  return "New match";
}

function stageKey(company) {
  const stage = companyStage(company);
  if (stage === "Sent") return "sent";
  if (stage === "Blocked") return "blocked";
  if (stage === "Ready for approval") return "ready";
  if (stage === "Needs review") return "review";
  if (stage === "Application prepared") return "preparing";
  return "new";
}

function stageTone(stage) {
  if (stage === "Sent") return "success";
  if (stage === "Blocked") return "danger";
  if (stage === "Needs review" || stage === "Ready for approval") return "warning";
  if (stage === "Application prepared") return "info";
  return "";
}

function fitLabel(value) {
  const number = Number(value || 0);
  if (number >= 0.82) return "Strong match";
  if (number >= 0.72) return "Good match";
  if (number >= 0.55) return "Possible match";
  return "Unclear fit";
}

function fitTone(value) {
  const number = Number(value || 0);
  if (number >= 0.75) return "success";
  if (number >= 0.55) return "warning";
  return "";
}

function latestFit(company, fits) {
  return fits.find((fit) => fit.external_company_id === company.company_id) || null;
}

function matchReasons(company, fit) {
  const reasons = [];
  for (const reason of fit?.reasons || []) {
    reasons.push(readableReason(reason));
  }
  if (!reasons.length && company.industry_tags?.length) reasons.push(`Relevant industry: ${readableTag(company.industry_tags[0])}`);
  if (company.locations?.length) reasons.push(`Location: ${readableTag(company.locations[0])}`);
  if (company.description) reasons.push(shortText(company.description, 90));
  return reasons.filter(Boolean);
}

function companyConcerns(company, fit) {
  const concerns = [];
  for (const risk of fit?.risks || []) concerns.push(readableReason(risk));
  for (const flag of company.review_flags || []) concerns.push(humanStatus(readableTag(flag)));
  for (const conflict of company.policy_conflicts || []) concerns.push(readableReason(conflict));
  if (!concerns.length && company.remote_policy) concerns.push(`Work model: ${company.remote_policy}`);
  return concerns.filter(Boolean);
}

function sourceLinkMarkup(source) {
  const value = readableTag(source);
  const isUrl = /^https?:\/\//.test(value);
  return `
    <div class="source-row">
      <div>
        <h4>${escapeHtml(isUrl ? new URL(value).hostname : value)}</h4>
        <p class="muted">${escapeHtml(value)}</p>
      </div>
      ${isUrl ? `<a class="button secondary" href="${escapeHtml(value)}" target="_blank" rel="noreferrer">Open</a>` : ""}
    </div>
  `;
}

function isResearchActive(status) {
  const value = status?.status || status?.import_state?.run_status || "";
  return ["running", "research_running", "prepared"].includes(value);
}

function isApplicationActive(status) {
  const value = status?.status || status?.import_state?.run_status || "";
  return ["running", "application_draft_running", "prepared"].includes(value);
}

function isOnboardingActive(status) {
  const value = status?.status || "";
  return ["running", "attached", "started"].includes(value);
}

function conversationStatusLabel(status) {
  if (!status) return "Conversation is not loaded yet.";
  if (isOnboardingActive(status)) return "Conversation is active.";
  if (status.status === "closed") return "Conversation is closed.";
  return "Ready when you are.";
}

function applicationProgressText(status) {
  const counts = status?.artifact_counts || {};
  if (!status) return "Preparation status is not available.";
  if (counts.email_draft || counts.cv_pdf) return "Drafting and resume tailoring are in progress.";
  if (counts.contact_candidate) return "Checking contact details.";
  return "Researching the company and selecting relevant experience.";
}

function progressFromCounts(count, target) {
  if (!target) return 25;
  return Math.max(12, Math.min(95, Math.round((Number(count || 0) / Number(target)) * 100)));
}

function applicationBlockText(company) {
  if (company.has_application_draft) return "Application already prepared";
  if (hasItems(company.policy_conflicts)) return "Policy conflict needs review";
  return "Preparation is not available for this company";
}

function splitInput(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function humanStatus(value) {
  return String(value || "unknown")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
    .replace("Passed Evaluate Only", "Passed checks")
    .replace("Reserved For Send", "Ready for approval")
    .replace("Queued For Send", "Ready for checks")
    .replace("Research Running", "Searching for companies")
    .replace("Application Draft Running", "Preparing application");
}

function readableArtifactName(filename) {
  if (filename === "user_profile.json") return "Career profile";
  if (filename === "master_cv_profile.json") return "Master resume material";
  if (filename === "policy.json") return "Search and outreach policy";
  if (filename === "onboarding_review.json") return "Unresolved profile questions";
  return filename || "Profile file";
}

function artifactLabel(artifact) {
  if (artifact.status === "missing") return "Not created yet";
  if (artifact.snapshot_status === "approved") return "Approved for future work";
  if (artifact.error_count) return `${artifact.error_count} issue${artifact.error_count === 1 ? "" : "s"} to review`;
  return "Ready for review";
}

function readableReason(value) {
  if (typeof value === "string") return humanStatus(value);
  if (value && typeof value === "object") {
    return value.text || value.message || value.reason || value.code || value.policy_value || JSON.stringify(value);
  }
  return "";
}

function readableTag(value) {
  if (typeof value === "string") return value.replaceAll("_", " ");
  if (value && typeof value === "object") return value.text || value.name || value.url || value.code || value.id || JSON.stringify(value);
  return String(value || "");
}

function firstValue(values) {
  return Array.isArray(values) && values.length ? readableTag(values[0]) : "";
}

function domainLabel(company) {
  return company.normalized_domain || company.raw_domain || "";
}

function initials(name) {
  return String(name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("");
}

function shortText(value, maxLength = 180) {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, Math.max(0, maxLength - 1)).trim()}...`;
}

function hasItems(value) {
  return Array.isArray(value) && value.length > 0;
}

function isInternalTestRecord(row) {
  const text = [
    row?.company_id,
    row?.company_name,
    row?.name,
    row?.draft_id,
    row?.intent_id,
    row?.external_company_id,
    row?.sent_message_id,
    row?.subject,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return text.includes("gmail-smoke") || text.includes("gmail gate smoke") || text.includes("smoke test");
}

function formatCell(value) {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return `${value.length} item${value.length === 1 ? "" : "s"}`;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function dateLabel(value) {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function formatBytes(value) {
  const size = Number(value || 0);
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function loadingMarkup(label) {
  return `
    <div class="loading-state" aria-busy="true">
      <span>${escapeHtml(label)}...</span>
      <span class="skeleton" style="width: 70%;"></span>
      <span class="skeleton" style="width: 45%;"></span>
    </div>
  `;
}

function emptyMarkup(title, body) {
  return `
    <div class="empty-state">
      <h4>${escapeHtml(title)}</h4>
      <p>${escapeHtml(body)}</p>
    </div>
  `;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

init();
