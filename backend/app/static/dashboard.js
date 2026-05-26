const apiPaths = {
  sendIntents: "/" + "send-intents",
};
// Dashboard API coverage: /send-intents and controlled backend send batches

const onboardingArtifactFiles = [
  "user_profile.json",
  "master_cv_profile.json",
  "policy.json",
  "onboarding_review.json",
];

const companyResearchStatusIntervalMs = 10000;
const applicationDraftStatusIntervalMs = 10000;

const sections = [
  {
    id: "profile",
    label: "Profile",
    title: "Profile Setup",
    navGroup: "Recruiter workflow",
    subtitle: "Create or review the local profile used for recruiting work",
    custom: "profileShell",
    filters: [],
    columns: [],
  },
  {
    id: "companies",
    label: "Companies",
    title: "Companies",
    navGroup: "Recruiter workflow",
    endpoint: "/companies",
    subtitle: "Company profiles with draft, queue, and contact state",
    filters: ["run_id", "min_confidence", "has_review_flags", "has_policy_conflicts", "draft_status"],
    columns: [
      { label: "Select", value: (r) => companySelectCheckbox(r) },
      { label: "Company", value: (r) => mainCell(r.name, r.company_id) },
      { label: "Domain", value: (r) => mainCell(r.normalized_domain || "No domain", r.company_policy_key) },
      { label: "Score", value: (r) => confidence(r.confidence) },
      { label: "Outreach", value: (r) => companyOutreachState(r) },
      { label: "Issues", value: (r) => companyIssues(r) },
      { label: "Draft", value: (r) => applicationDraftButton(r) },
    ],
  },
  {
    id: "contacts",
    label: "Contacts",
    title: "Contacts",
    navGroup: "Recruiter workflow",
    endpoint: "/contacts",
    subtitle: "Recipient candidates and sourced contact details",
    filters: ["run_id", "company_id", "email_source", "min_confidence", "has_review_flags"],
    columns: [
      { label: "Contact", value: (r) => mainCell(r.name || r.contact_id, r.role_title || r.contact_id) },
      { label: "Company", value: (r) => text(r.external_company_id, "mono") },
      { label: "Email", value: (r) => mainCell(r.normalized_recipient_email, r.email_source) },
      { label: "Confidence", value: (r) => confidence(r.confidence) },
      { label: "Review", value: (r) => tags(r.review_flags, "warn") },
      { label: "Sources", value: (r) => tags(r.source_refs) },
    ],
  },
  {
    id: "fit",
    label: "Fit evaluations",
    title: "Fit Evaluations",
    navGroup: "Recruiter workflow",
    endpoint: "/fit-evaluations",
    subtitle: "Fit scores, decisions, reasons, and risks",
    filters: ["run_id", "company_id", "decision", "min_confidence", "has_review_flags"],
    columns: [
      { label: "Evaluation", value: (r) => mainCell(r.evaluation_id, r.external_company_id) },
      { label: "Decision", value: (r) => statusTag(r.decision) },
      { label: "Score", value: (r) => confidence(r.fit_score) },
      { label: "Confidence", value: (r) => confidence(r.confidence) },
      { label: "Reasons", value: (r) => tags(r.reasons) },
      { label: "Risks", value: (r) => tags(r.risks, "warn") },
      { label: "Review", value: (r) => tags(r.review_flags, "warn") },
    ],
  },
  {
    id: "drafts",
    label: "Drafts",
    title: "Drafts",
    navGroup: "Recruiter workflow",
    endpoint: "/email-drafts",
    subtitle: "Read-only outreach draft content and evidence references",
    filters: ["run_id", "company_id", "contact_id", "min_confidence", "has_review_flags"],
    columns: [
      { label: "Draft", value: (r) => mainCell(r.draft_id, r.subject) },
      { label: "Company", value: (r) => text(r.external_company_id, "mono") },
      { label: "Contact", value: (r) => text(r.external_contact_id, "mono") },
      { label: "Tone", value: (r) => text(r.tone || "Unspecified") },
      { label: "Confidence", value: (r) => confidence(r.confidence) },
      { label: "Claims", value: (r) => tags(r.claim_refs) },
      { label: "Attachments", value: (r) => attachmentLinks(r) },
      { label: "Review", value: (r) => tags(r.review_flags, "warn") },
      { label: "Queue", value: (r) => queueDraftButton(r.draft_id) },
    ],
  },
  {
    id: "runs",
    label: "Runs",
    title: "Runs",
    navGroup: "Developer logs",
    endpoint: "/runs",
    subtitle: "Imports, output paths, and run lifecycle state",
    filters: ["run_id", "status"],
    clientFilters: true,
    columns: [
      { label: "Run", value: (r) => mainCell(r.run_id, r.agent_type || "Unknown type") },
      { label: "Status", value: (r) => statusTag(r.status) },
      { label: "Output", value: (r) => text(r.output_path, "mono") },
      { label: "Started", value: (r) => dateTime(r.started_at) },
      { label: "Completed", value: (r) => dateTime(r.completed_at) },
      { label: "Updated", value: (r) => dateTime(r.updated_at) },
    ],
    detail: loadRunDetail,
  },
  {
    id: "queue",
    label: "Send queue",
    title: "Send Queue",
    navGroup: "Developer logs",
    endpoint: apiPaths.sendIntents,
    subtitle: "Imported send intents, deterministic gate results, and controlled backend send actions",
    filters: ["run_id", "company_id", "contact_id", "status", "gate_status", "reason_code", "min_confidence", "has_review_flags"],
    columns: [
      { label: "Select", value: (r) => sendIntentSelectCheckbox(r.intent_id) },
      { label: "Intent", value: (r) => mainCell(r.intent_id, r.subject) },
      { label: "Recipient", value: (r) => mainCell(r.normalized_recipient_email, r.recipient_name || r.external_contact_id) },
      { label: "Company", value: (r) => mainCell(r.external_company_id, r.company_domain || "No domain") },
      { label: "Status", value: (r) => statusTag(r.status) },
      { label: "Gate", value: (r) => gateSummary(r.latest_gate_result) },
      { label: "Confidence", value: (r) => confidence(r.confidence) },
      { label: "Review", value: (r) => tags(r.review_flags, "warn") },
      { label: "Send", value: (r) => sendIntentButton(r.intent_id) },
    ],
  },
  {
    id: "blocked",
    label: "Blocked/review",
    title: "Blocked And Needs Review",
    navGroup: "Developer logs",
    endpoint: "/gate-results",
    subtitle: "Gate outcomes that require attention before any future action",
    filters: ["gate_status", "reason_code"],
    defaultParams: { gate_status: "" },
    clientFilter: (rows) => rows.filter((r) => ["blocked", "needs_review"].includes(r.status)),
    columns: [
      { label: "Gate result", value: (r) => mainCell(r.gate_result_id, r.external_intent_id) },
      { label: "Status", value: (r) => statusTag(r.status) },
      { label: "Reasons", value: (r) => tags(r.reasons, "danger") },
      { label: "Checks", value: (r) => tags(r.checks, "warn") },
      { label: "Evaluated", value: (r) => dateTime(r.evaluated_at) },
      { label: "Policy", value: (r) => text(r.external_policy_id || "None", "mono") },
    ],
  },
  {
    id: "gate",
    label: "Gate results",
    title: "Gate Results",
    navGroup: "Developer logs",
    endpoint: "/gate-results",
    subtitle: "All imported or backend-generated evaluate-only gate records",
    filters: ["run_id", "company_id", "contact_id", "intent_id", "gate_status", "reason_code"],
    columns: [
      { label: "Gate result", value: (r) => mainCell(r.gate_result_id, r.external_intent_id) },
      { label: "Status", value: (r) => statusTag(r.status) },
      { label: "Reasons", value: (r) => tags(r.reasons, "danger") },
      { label: "Checks", value: (r) => tags(r.checks, "warn") },
      { label: "Evaluated", value: (r) => dateTime(r.evaluated_at) },
      { label: "Policy", value: (r) => text(r.external_policy_id || "None", "mono") },
    ],
  },
  {
    id: "history",
    label: "Outreach history",
    title: "Outreach History",
    navGroup: "Developer logs",
    endpoint: "/outreach-records",
    subtitle: "Read-only historical/contacted state used by dedupe policy",
    filters: ["run_id", "company_id", "contact_id", "status"],
    columns: [
      { label: "Record", value: (r) => mainCell(r.outreach_record_id, r.channel) },
      { label: "Recipient", value: (r) => text(r.normalized_recipient_email, "mono") },
      { label: "Company key", value: (r) => text(r.company_policy_key, "mono") },
      { label: "Status", value: (r) => statusTag(r.status) },
      { label: "Dedupe", value: (r) => tags([`recipient:${r.dedupe_recipient}`, `company:${r.dedupe_company}`]) },
      { label: "Occurred", value: (r) => dateTime(r.occurred_at) },
      { label: "Resolve", value: (r) => outreachResolveButton(r) },
    ],
  },
  {
    id: "audit",
    label: "Audit logs",
    title: "Audit Logs",
    navGroup: "Developer logs",
    endpoint: "/audit-logs",
    subtitle: "Append-only backend audit trail",
    filters: ["run_id", "entity_type", "entity_id", "action", "result_status", "reason_code", "limit"],
    columns: [
      { label: "Event", value: (r) => mainCell(r.action, r.entity_type) },
      { label: "Entity", value: (r) => mainCell(r.entity_id || "None", r.run_id || "No run") },
      { label: "Result", value: (r) => statusTag(r.result_status) },
      { label: "Actor", value: (r) => text(r.actor_type) },
      { label: "Reasons", value: (r) => tags(r.reason_codes, "warn") },
      { label: "Created", value: (r) => dateTime(r.created_at) },
    ],
  },
];

const filterDefinitions = {
  run_id: { label: "Run ID", type: "text", placeholder: "run_..." },
  company_id: { label: "Company ID", type: "text", placeholder: "company_..." },
  contact_id: { label: "Contact ID", type: "text", placeholder: "contact_..." },
  intent_id: { label: "Intent ID", type: "text", placeholder: "intent_..." },
  entity_type: { label: "Entity type", type: "text", placeholder: "send_intent" },
  entity_id: { label: "Entity ID", type: "text", placeholder: "record id" },
  action: { label: "Action", type: "text", placeholder: "gate.evaluate" },
  status: { label: "Status", type: "text", placeholder: "imported" },
  gate_status: { label: "Gate status", type: "select", options: ["", "passed_evaluate_only", "reserved_for_send", "blocked", "needs_review"] },
  result_status: { label: "Result status", type: "text", placeholder: "success" },
  reason_code: { label: "Reason code", type: "text", placeholder: "missing_source" },
  email_source: { label: "Email source", type: "text", placeholder: "public" },
  decision: { label: "Decision", type: "text", placeholder: "pursue" },
  min_confidence: { label: "Min confidence", type: "number", min: "0", max: "1", step: "0.05", placeholder: "0.70" },
  has_review_flags: { label: "Review flags", type: "select", options: ["", "true", "false"] },
  has_policy_conflicts: { label: "Policy conflicts", type: "select", options: ["", "true", "false"] },
  draft_status: { label: "Draft status", type: "select", options: ["", "missing", "drafted"] },
  limit: { label: "Limit", type: "number", min: "1", max: "500", step: "1", placeholder: "100" },
};

const state = {
  activeSection: sections[0].id,
  rows: [],
  selectedIndex: null,
  controllers: new Map(),
  filters: {},
  selectedCompanyIds: new Set(),
  selectedIntentIds: new Set(),
  applicationDraftBatch: null,
  applicationDraft: {
    runId: "",
    status: null,
    pollTimer: null,
    batchPollTimer: null,
  },
  emailDelivery: null,
  onboarding: {
    runId: localStorage.getItem("onboardingRunId") || "onboarding-local",
    entries: [],
    sessionState: null,
    profile: null,
    artifacts: null,
    inputFiles: [],
    snapshots: [],
    selectedArtifact: null,
    promotionResult: null,
    lastResult: null,
  },
  campaign: {
    runId: localStorage.getItem("companyResearchRunId") || "",
    lastResult: null,
    status: null,
    pollTimer: null,
  },
};

const elements = {
  nav: document.querySelector("#sectionNav"),
  viewTitle: document.querySelector("#viewTitle"),
  summaryGrid: document.querySelector("#summaryGrid"),
  filtersPanel: document.querySelector("#filtersPanel"),
  tableTitle: document.querySelector("#tableTitle"),
  tableSubtitle: document.querySelector("#tableSubtitle"),
  tableHead: document.querySelector("#tableHead"),
  tableBody: document.querySelector("#tableBody"),
  recordCount: document.querySelector("#recordCount"),
  detailSubtitle: document.querySelector("#detailSubtitle"),
  detailJson: document.querySelector("#detailJson"),
  apiState: document.querySelector("#apiState"),
  refreshButton: document.querySelector("#refreshButton"),
};

function currentSection() {
  return sections.find((section) => section.id === state.activeSection) || sections[0];
}

function init() {
  renderNav();
  elements.refreshButton.addEventListener("click", () => refresh());
  refresh();
  if (state.campaign.runId) {
    startCompanyResearchPolling();
  }
}

async function refresh() {
  const section = currentSection();
  captureFilterValues(section);
  document.body.dataset.section = section.id;
  elements.viewTitle.textContent = section.title;
  elements.tableTitle.textContent = section.title;
  elements.tableSubtitle.textContent = section.subtitle;
  elements.apiState.textContent = "Loading API state";
  elements.apiState.className = "state-pill";

  if (section.custom === "profileShell") {
    await renderProfileShell();
    return;
  }

  if (section.custom === "onboardingChat") {
    await renderOnboardingChat();
    return;
  }

  renderFilters(section);
  renderTableLoading(section);

  try {
    const [summary, emailDelivery, rows] = await Promise.all([
      fetchJson("/dashboard/summary"),
      fetchJson("/email-delivery/settings"),
      loadRows(section),
    ]);
    state.emailDelivery = emailDelivery;
    renderSummary(summary);
    state.rows = rows;
    if (section.id === "companies") {
      const rowIds = new Set(rows.filter((row) => row.can_draft_application).map((row) => row.company_id));
      state.selectedCompanyIds = new Set([...state.selectedCompanyIds].filter((companyId) => rowIds.has(companyId)));
    }
    state.selectedIndex = rows.length ? 0 : null;
    renderTable(section, rows);
    renderDetail();
    elements.apiState.textContent = deliveryStateLabel(emailDelivery);
    elements.apiState.className = deliveryStateClass(emailDelivery);
  } catch (error) {
    elements.apiState.textContent = "API load failed";
    elements.apiState.className = "state-pill error";
    renderError(error);
  }
}

function renderNav() {
  elements.nav.innerHTML = "";
  let currentGroup = "";
  for (const section of sections) {
    if (section.navGroup && section.navGroup !== currentGroup) {
      currentGroup = section.navGroup;
      const heading = document.createElement("span");
      heading.className = "nav-group";
      heading.textContent = currentGroup;
      elements.nav.append(heading);
    }
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = section.label;
    button.className = section.id === state.activeSection ? "active" : "";
    button.addEventListener("click", () => {
      captureFilterValues(currentSection());
      state.activeSection = section.id;
      state.selectedIndex = null;
      renderNav();
      refresh();
    });
    elements.nav.append(button);
  }
}

function renderSummary(summary) {
  const metrics = [
    ["Companies", summary.companies],
    ["Contacts", summary.contacts],
    ["Fit evaluations", summary.fit_evaluations],
    ["Drafts", summary.email_drafts],
    ["Sent messages", summary.sent_messages],
    ["Runs", summary.runs],
  ];
  elements.summaryGrid.innerHTML = metrics
    .map(([label, value]) => `<article class="metric"><span>${escapeHtml(label)}</span><strong>${Number(value || 0)}</strong></article>`)
    .join("");
}

function renderFilters(section) {
  elements.filtersPanel.innerHTML = "";
  const filters = section.filters || [];
  if (!filters.length) {
    elements.filtersPanel.hidden = true;
    return;
  }
  elements.filtersPanel.hidden = false;

  for (const key of filters) {
    const definition = filterDefinitions[key];
    if (!definition) continue;
    const wrapper = document.createElement("div");
    wrapper.className = "filter-field";
    const label = document.createElement("label");
    label.htmlFor = `filter-${key}`;
    label.textContent = definition.label;
    const savedValue = state.filters[section.id]?.[key] ?? section.defaultParams?.[key] ?? "";
    const input = createFilterInput(key, definition, savedValue);
    wrapper.append(label, input);
    elements.filtersPanel.append(wrapper);
  }

  const wrapper = document.createElement("div");
  wrapper.className = "filter-field";
  const label = document.createElement("label");
  label.textContent = "Controls";
  const button = document.createElement("button");
  button.className = "action-button";
  button.type = "button";
  button.title = "Apply filters";
  button.textContent = "Apply";
  button.addEventListener("click", () => refresh());
  wrapper.append(label, button);
  if (section.id === "companies") {
    const selectedButton = document.createElement("button");
    selectedButton.className = "action-button";
    selectedButton.type = "button";
    selectedButton.textContent = "Draft selected";
    selectedButton.addEventListener("click", () => applicationDraftBatchSelected());
    const allMissingButton = document.createElement("button");
    allMissingButton.className = "action-button";
    allMissingButton.type = "button";
    allMissingButton.textContent = "Draft all missing";
    allMissingButton.addEventListener("click", () => applicationDraftBatchAllMissing());
    wrapper.append(selectedButton, allMissingButton);
  }
  if (section.id === "drafts") {
    const queueAllButton = document.createElement("button");
    queueAllButton.className = "action-button primary";
    queueAllButton.type = "button";
    queueAllButton.textContent = "Queue all shown";
    queueAllButton.addEventListener("click", () => queueAllShownDrafts());
    wrapper.append(queueAllButton);
  }
  if (section.id === "queue") {
    const sendSelectedButton = document.createElement("button");
    sendSelectedButton.className = "action-button primary";
    sendSelectedButton.type = "button";
    sendSelectedButton.textContent = "Send selected";
    sendSelectedButton.addEventListener("click", () => sendSelectedIntents());
    const sendAllButton = document.createElement("button");
    sendAllButton.className = "action-button primary";
    sendAllButton.type = "button";
    sendAllButton.textContent = "Send all shown";
    sendAllButton.addEventListener("click", () => sendAllShownIntents());
    wrapper.append(sendSelectedButton, sendAllButton);
  }
  elements.filtersPanel.append(wrapper);
}

function createFilterInput(key, definition, defaultValue = "") {
  let input;
  if (definition.type === "select") {
    input = document.createElement("select");
    for (const optionValue of definition.options) {
      const option = document.createElement("option");
      option.value = optionValue;
      option.textContent = optionValue === "" ? "Any" : optionValue;
      input.append(option);
    }
  } else {
    input = document.createElement("input");
    input.type = definition.type;
    input.placeholder = definition.placeholder || "";
    for (const attr of ["min", "max", "step"]) {
      if (definition[attr]) input.setAttribute(attr, definition[attr]);
    }
  }
  input.id = `filter-${key}`;
  input.name = key;
  input.value = defaultValue;
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") refresh();
  });
  input.addEventListener("change", () => refresh());
  return input;
}

function captureFilterValues(section) {
  if (!section?.filters?.length) return;
  state.filters[section.id] = state.filters[section.id] || {};
  for (const key of section.filters) {
    const input = document.querySelector(`#filter-${key}`);
    if (input) state.filters[section.id][key] = input.value;
  }
}

async function loadRows(section) {
  const params = new URLSearchParams();
  for (const key of section.filters || []) {
    const value = state.filters[section.id]?.[key]?.trim();
    if (value) params.set(key, value);
  }
  const url = `${section.endpoint}${params.toString() ? `?${params}` : ""}`;
  let rows = await fetchJson(url);

  if (section.clientFilters) {
    rows = applyClientFilters(section, rows);
  }
  if (section.clientFilter) {
    rows = section.clientFilter(rows);
  }
  return rows;
}

function applyClientFilters(section, rows) {
  const runId = document.querySelector("#filter-run_id")?.value?.trim();
  const status = document.querySelector("#filter-status")?.value?.trim();
  return rows.filter((row) => {
    if (runId && row.run_id !== runId) return false;
    if (status && row.status !== status) return false;
    return true;
  });
}

async function renderProfileShell() {
  elements.filtersPanel.hidden = true;
  elements.filtersPanel.innerHTML = "";
  elements.tableHead.innerHTML = "";
  elements.recordCount.textContent = "Profile";
  elements.detailSubtitle.textContent = "Profile and session state";
  renderProfileAndChat({ loading: true });
  bindOnboardingControls();

  try {
    const [summary, profile, sessionState, artifacts, inputFiles, snapshots, campaignStatus] = await Promise.all([
      fetchJson("/dashboard/summary"),
      fetchJson("/profile/summary"),
      fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/status`),
      fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/artifacts`),
      fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/input-files`),
      fetchJson(`/onboarding/runs/${encodeURIComponent(state.onboarding.runId)}/snapshots`),
      state.campaign.runId
        ? fetchJson(`/campaigns/company-research/${encodeURIComponent(state.campaign.runId)}/status`).catch(() => null)
        : Promise.resolve(null),
    ]);
    renderSummary(summary);
    state.onboarding.profile = profile;
    state.onboarding.sessionState = sessionState;
    state.onboarding.entries = sessionState.entries || [];
    state.onboarding.artifacts = artifacts.artifacts || [];
    state.onboarding.inputFiles = inputFiles.files || [];
    state.onboarding.snapshots = snapshots || [];
    state.campaign.status = campaignStatus;
    if (campaignStatus) {
      state.campaign.lastResult = {
        ...(state.campaign.lastResult || {}),
        run_id: state.campaign.runId,
        output_path: campaignStatus.import_state?.output_path || `runs/${state.campaign.runId}/output`,
      };
      if (isCompanyResearchTerminal(campaignStatus)) {
        stopCompanyResearchPolling();
      } else {
        startCompanyResearchPolling();
      }
    }
    renderProfileAndChat();
    bindOnboardingControls();
    elements.detailJson.textContent = JSON.stringify({ profile, session_state: sessionState, artifacts, input_files: inputFiles, snapshots }, null, 2);
    elements.apiState.textContent = "Profile state loaded";
    elements.apiState.className = "state-pill ok";
  } catch (error) {
    elements.apiState.textContent = "Profile load failed";
    elements.apiState.className = "state-pill error";
    renderProfileAndChat({ error: error.message });
    bindOnboardingControls();
    elements.detailJson.textContent = error.stack || error.message;
  }
}

function renderProfileAndChat(options = {}) {
  const profile = state.onboarding.profile;
  const sessionState = state.onboarding.sessionState || { status: "not_started", entries: state.onboarding.entries || [] };
  const hasApprovedProfile = Boolean(profile?.has_approved_profile);
  const candidateCount = profile?.candidate_user_profiles?.length || 0;
  const status = options.loading ? "loading" : sessionState.status || "not_started";
  const lastError = options.error || sessionState.last_error || "";
  const profileTitle = hasApprovedProfile ? "Approved profile ready" : "No approved profile yet";
  const profileBody = hasApprovedProfile
    ? `Active profile snapshot: ${escapeHtml(profile.approved_user_profile?.external_id || "approved")}`
    : "Create a profile through the local Codex onboarding chat before starting campaign research.";
  elements.tableBody.innerHTML = `
    <tr>
      <td class="onboarding-cell">
        <div class="profile-shell">
          <section class="profile-status-panel ${hasApprovedProfile ? "ready" : "setup"}">
            <div>
              <span class="profile-kicker">Profile</span>
              <h3>${profileTitle}</h3>
              <p>${profileBody}</p>
            </div>
            <div class="profile-actions">
              <label class="filter-field run-id-field" for="onboardingRunId">
                <span>Run ID</span>
                <input id="onboardingRunId" type="text" value="${escapeHtml(state.onboarding.runId)}" placeholder="onboarding-local">
              </label>
              <div class="profile-state-stack">
                ${statusTag(status)}
                ${candidateCount ? tag(`${candidateCount} candidate`, "warn") : ""}
              </div>
            </div>
          </section>
          ${lastError ? `<div class="onboarding-failure">${escapeHtml(lastError)}</div>` : ""}
          ${renderProfileStepper(hasApprovedProfile, status)}
          ${renderCurrentProfileStep(hasApprovedProfile, status, sessionState)}
          ${renderTechnicalProfileDetails(hasApprovedProfile, sessionState, status)}
        </div>
      </td>
    </tr>
  `;
  const messageList = document.querySelector("#onboardingMessages");
  if (messageList) messageList.scrollTop = messageList.scrollHeight;
}

function renderProfileStepper(hasApprovedProfile, status) {
  const hasArtifacts = Array.isArray(state.onboarding.artifacts) && state.onboarding.artifacts.some((artifact) => artifact.exists);
  const hasCandidates = (state.onboarding.snapshots || []).some((snapshot) => snapshot.status === "candidate");
  const steps = [
    { key: "interview", label: "Interview", done: status !== "not_started" || hasArtifacts || hasApprovedProfile },
    { key: "validate", label: "Validate", done: hasArtifacts || hasCandidates || hasApprovedProfile },
    { key: "approve", label: "Approve", done: hasApprovedProfile },
    { key: "research", label: "Research", done: false },
  ];
  const activeKey = hasApprovedProfile ? "research" : hasCandidates || hasArtifacts ? "approve" : status === "running" || status === "waiting" ? "interview" : "interview";
  return `
    <nav class="workflow-stepper" aria-label="Profile workflow">
      ${steps.map((step, index) => `
        <div class="workflow-step ${step.done ? "done" : ""} ${step.key === activeKey ? "active" : ""}">
          <span>${step.done ? "✓" : index + 1}</span>
          <strong>${escapeHtml(step.label)}</strong>
        </div>
      `).join("")}
    </nav>
  `;
}

function renderCurrentProfileStep(hasApprovedProfile, status, sessionState) {
  if (hasApprovedProfile) {
    return `
      ${renderApprovedProfilePanel()}
      ${renderCompanyResearchPanel()}
    `;
  }
  const hasCandidateSnapshots = (state.onboarding.snapshots || []).some((snapshot) => snapshot.status === "candidate");
  const hasArtifacts = Array.isArray(state.onboarding.artifacts) && state.onboarding.artifacts.some((artifact) => artifact.exists);
  if (hasCandidateSnapshots || hasArtifacts) {
    return `
      <section class="workflow-panel">
        <div class="workflow-panel-header">
          <div>
            <span class="profile-kicker">Current step</span>
            <h3>Review and approve profile</h3>
          </div>
          <button class="action-button" id="onboardingValidateArtifacts" type="button">Validate artifacts</button>
        </div>
        ${renderReviewPanel()}
      </section>
    `;
  }
  return `
    <section class="workflow-panel">
      <div class="workflow-panel-header">
        <div>
          <span class="profile-kicker">Current step</span>
          <h3>Profile interview</h3>
        </div>
        ${renderProfileToolbar()}
      </div>
      ${renderInputFilesPanel()}
      ${renderOnboardingChatMarkup(sessionState.entries || state.onboarding.entries || [], `Session: ${status}`)}
    </section>
  `;
}

function renderApprovedProfilePanel() {
  const profile = state.onboarding.profile || {};
  const approved = [
    profile.approved_user_profile,
    profile.approved_master_cv_profile,
    profile.approved_policy,
  ].filter(Boolean);
  return `
    <section class="workflow-panel approved-profile-panel">
      <div class="workflow-panel-header">
        <div>
          <span class="profile-kicker">Approved context</span>
          <h3>Profile source of truth is ready</h3>
        </div>
      </div>
      <div class="approved-snapshot-grid">
        ${approved.map((snapshot) => `
          <div class="approved-snapshot">
            <span>${escapeHtml(snapshot.snapshot_type)}</span>
            <strong>${escapeHtml(snapshot.external_id)}</strong>
            ${statusTag(snapshot.status)}
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

function renderCompanyResearchPanel() {
  const result = state.campaign.lastResult;
  const status = state.campaign.status;
  const runId = result?.run_id || status?.run_id || state.campaign.runId || "";
  const counts = status?.artifact_counts || {};
  const importState = status?.import_state || {};
  const outputPath = result?.output_path || importState.output_path || "";
  const updatedAt = status?.state?.updated_at || "";
  const pollLabel = runId && status && !isCompanyResearchTerminal(status) ? "Auto-refreshing every 10 seconds" : "";
  return `
    <section class="workflow-panel company-research-panel">
      <div class="workflow-panel-header">
        <div>
          <span class="profile-kicker">Next step</span>
          <h3>Launch company research</h3>
        </div>
        <div class="campaign-actions">
          <button class="action-button" id="companyResearchLoad" type="button">Load run</button>
          <button class="action-button" id="companyResearchImport" type="button">Import artifacts</button>
          <button class="action-button primary" id="companyResearchLaunch" type="button">Launch company research</button>
        </div>
      </div>
      <div class="campaign-form">
        <label class="filter-field">
          <span>Run ID</span>
          <input id="companyResearchRunId" type="text" value="${escapeHtml(runId)}" placeholder="company-research-local">
        </label>
        <label class="filter-field">
          <span>Role focus</span>
          <input id="companyResearchRoleFocus" type="text" value="Profile-aligned roles">
        </label>
        <label class="filter-field">
          <span>Time budget</span>
          <input id="companyResearchTimeBudget" type="number" min="1" max="240" step="1" value="30">
        </label>
        <label class="filter-field campaign-notes">
          <span>Notes</span>
          <input id="companyResearchNotes" type="text" placeholder="Optional constraints or preferences">
        </label>
      </div>
      ${runId ? `
        <div class="campaign-result">
          <strong>${escapeHtml(runId)}</strong>
          <p>${escapeHtml(status?.status || result?.next_action || "Run loaded from local state. Import artifacts to update backend records.")}</p>
          <code>${escapeHtml(outputPath || `runs/${runId}/output`)}</code>
          ${status ? `
            <div class="campaign-status-grid">
              <span>${statusTag(status.status)}</span>
              <span>${escapeHtml(String(counts.companies || 0))} companies</span>
              <span>${escapeHtml(String(counts.contacts || 0))} contacts</span>
              <span>${escapeHtml(String(counts.fit_evaluations || 0))} fit evaluations</span>
              <span>${escapeHtml(importState.run_status || "not imported")}</span>
              <span>${escapeHtml(String(status.validation?.passed || 0))} valid files</span>
            </div>
            <p class="muted">${escapeHtml([updatedAt ? `Updated ${updatedAt}` : "", pollLabel].filter(Boolean).join(" · "))}</p>
          ` : ""}
          <div class="campaign-links">
            <button class="link-button" type="button" data-section-link="companies" data-run-filter="${escapeHtml(runId)}">Companies</button>
            <button class="link-button" type="button" data-section-link="contacts" data-run-filter="${escapeHtml(runId)}">Contacts</button>
            <button class="link-button" type="button" data-section-link="fit" data-run-filter="${escapeHtml(runId)}">Fit evaluations</button>
            <button class="link-button" type="button" data-section-link="runs" data-run-filter="${escapeHtml(runId)}">Run details</button>
          </div>
        </div>
      ` : ""}
    </section>
  `;
}

function renderTechnicalProfileDetails(hasApprovedProfile, sessionState, status) {
  return `
    <details class="technical-details">
      <summary>Generated files and transcript</summary>
      ${renderArtifactPanel()}
    </details>
  `;
}

function renderAccountPanel() {
  return `
    <section class="account-panel">
      <div>
        <span class="profile-kicker">Account</span>
        <h3>Local profile mode</h3>
        <p>Email and password sign-up is intentionally disabled until an external identity provider is configured. This app will not store passwords with custom auth code.</p>
      </div>
      <span class="tag warn">auth deferred</span>
    </section>
  `;
}

function renderProfileToolbar() {
  return `
    <section class="profile-toolbar" aria-label="Profile setup controls">
      <button class="action-button primary" id="onboardingStart" type="button">Start profile interview</button>
      <button class="action-button" id="onboardingFinish" type="button">Finish artifacts</button>
      <button class="action-button" id="onboardingValidateArtifacts" type="button">Validate artifacts</button>
      <button class="action-button" id="onboardingReset" type="button">Reset</button>
      <button class="action-button" id="onboardingClose" type="button">Close</button>
    </section>
  `;
}

function renderInputFilesPanel() {
  const files = state.onboarding.inputFiles || [];
  const fileRows = files.length
    ? files.map((file) => `
        <tr>
          <td>${escapeHtml(file.filename)}</td>
          <td>${escapeHtml(formatBytes(file.size_bytes))}</td>
        </tr>
      `).join("")
    : `<tr><td class="muted" colspan="2">No resume or profile document uploaded yet.</td></tr>`;
  return `
    <section class="artifact-panel input-files-panel">
      <div class="artifact-panel-header">
        <div>
          <span class="profile-kicker">Resume input</span>
          <h3>Source Documents</h3>
        </div>
        <label class="action-button file-upload-button" for="onboardingResumeUpload">Upload resume</label>
        <input id="onboardingResumeUpload" class="visually-hidden" type="file" accept=".pdf,.doc,.docx,.txt,.md,.json">
      </div>
      <table class="artifact-table">
        <thead><tr><th>File</th><th>Size</th></tr></thead>
        <tbody>${fileRows}</tbody>
      </table>
    </section>
  `;
}

async function renderOnboardingChat() {
  elements.filtersPanel.hidden = false;
  elements.filtersPanel.innerHTML = `
    <div class="filter-field onboarding-run-field">
      <label for="onboardingRunId">Run ID</label>
      <input id="onboardingRunId" type="text" value="${escapeHtml(state.onboarding.runId)}" placeholder="onboarding-local">
    </div>
    <div class="filter-field">
      <label>Controls</label>
      <div class="onboarding-controls">
        <button class="action-button" id="onboardingStart" type="button">Start</button>
        <button class="action-button" id="onboardingReload" type="button">Reload</button>
        <button class="action-button" id="onboardingReset" type="button">Reset</button>
        <button class="action-button" id="onboardingClose" type="button">Close</button>
        <button class="action-button" id="onboardingFinish" type="button">Finish</button>
        <button class="action-button" id="onboardingValidateArtifacts" type="button">Validate Artifacts</button>
      </div>
    </div>
  `;
  elements.tableHead.innerHTML = "";
  elements.recordCount.textContent = "Transcript";
  elements.detailSubtitle.textContent = "Onboarding output";
  elements.detailJson.textContent = state.onboarding.lastResult
    ? JSON.stringify(state.onboarding.lastResult, null, 2)
    : "No profile output validated yet.";
  renderOnboardingShell(state.onboarding.entries, "Loading transcript...");
  bindOnboardingControls();

  try {
    const [summary, sessionState, artifacts] = await Promise.all([
      fetchJson("/dashboard/summary"),
      fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/status`),
      fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/artifacts`),
    ]);
    renderSummary(summary);
    state.onboarding.sessionState = sessionState;
    state.onboarding.entries = sessionState.entries || [];
    state.onboarding.artifacts = artifacts.artifacts || [];
    renderOnboardingShell(state.onboarding.entries, `Session: ${sessionState.status}`);
    bindOnboardingControls();
    elements.apiState.textContent = "Onboarding chat ready";
    elements.apiState.className = "state-pill ok";
  } catch (error) {
    elements.apiState.textContent = "Onboarding load failed";
    elements.apiState.className = "state-pill error";
    renderOnboardingShell(state.onboarding.entries, error.message);
    bindOnboardingControls();
  }
}

function renderOnboardingShell(entries, statusText = "") {
  elements.tableBody.innerHTML = `
    <tr>
      <td class="onboarding-cell">
        ${renderArtifactPanel()}
        ${renderOnboardingChatMarkup(entries, statusText)}
      </td>
    </tr>
  `;
  const messageList = document.querySelector("#onboardingMessages");
  if (messageList) messageList.scrollTop = messageList.scrollHeight;
}

function renderArtifactPanel() {
  const artifacts = state.onboarding.artifacts;
  const rows = Array.isArray(artifacts) && artifacts.length
    ? artifacts.map((artifact) => {
        const reasonText = (artifact.reason_codes || []).slice(0, 2).join(", ") || artifact.review_state || "pending";
        return `
          <tr>
            <td>${escapeHtml(artifact.filename)}</td>
            <td>${statusTag(artifact.status)}</td>
            <td>${escapeHtml(reasonText)}</td>
            <td><button class="action-button compact" data-artifact-view="${escapeHtml(artifact.filename)}" type="button">Review</button></td>
          </tr>
        `;
      }).join("")
    : onboardingArtifactFiles.map((filename) => `
        <tr>
          <td>${escapeHtml(filename)}</td>
          <td>${statusTag("missing")}</td>
          <td>Artifact state has not loaded yet.</td>
          <td><button class="action-button compact" data-artifact-view="${escapeHtml(filename)}" type="button">Review</button></td>
        </tr>
      `).join("");
  return `
    <section class="artifact-panel">
      <div class="artifact-panel-header">
        <div>
          <span class="profile-kicker">Candidate artifacts</span>
          <h3>Profile Files</h3>
        </div>
        <button class="action-button" id="onboardingValidateArtifactsInline" type="button">Validate Artifacts</button>
      </div>
      <table class="artifact-table">
        <thead>
          <tr><th>File</th><th>Status</th><th>Review</th><th>Inspect</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </section>
  `;
}

function renderReviewPanel() {
  const snapshots = state.onboarding.snapshots || [];
  const requiredTypes = ["user_profile", "master_cv_profile", "policy"];
  const snapshotRows = requiredTypes.map((type) => {
    const snapshot = snapshots.find((item) => item.snapshot_type === type);
    return `
      <tr>
        <td>${escapeHtml(type)}</td>
        <td>${snapshot ? statusTag(snapshot.status) : statusTag("missing")}</td>
        <td>${escapeHtml(snapshot?.external_id || "No candidate imported yet")}</td>
      </tr>
    `;
  }).join("");
  const selected = state.onboarding.selectedArtifact;
  const selectedBlockers = collectReviewBlockers(selected?.json_content);
  const selectedBlockerMarkup = selectedBlockers.length
    ? `
      <div class="review-issues">
        <strong>Needs confirmation before approval</strong>
        <ul>
          ${selectedBlockers.map((issue) => `<li><span>${escapeHtml(issue.path)}</span>${escapeHtml(issue.reason)}</li>`).join("")}
        </ul>
      </div>
    `
    : "";
  const selectedMarkup = selected
    ? `${selectedBlockerMarkup}<pre class="artifact-preview">${escapeHtml(JSON.stringify(selected.json_content ?? selected.raw_text ?? "", null, 2))}</pre>`
    : `<p class="muted">Review each JSON artifact, then approve the three candidate snapshots when they match your profile.</p>`;
  const promotion = state.onboarding.promotionResult;
  const promotionIssues = promotion?.issues || [];
  const promotionMarkup = promotion
    ? `
      <div class="promotion-result ${promotion.status === "approved" ? "ready" : "blocked"}">
        <strong>${escapeHtml(promotion.status)}</strong>
        ${promotionIssues.length ? `
          <ul>
            ${promotionIssues.map((issue) => `
              <li>
                <span>${escapeHtml([issue.snapshot_type, issue.field].filter(Boolean).join(" "))}</span>
                ${escapeHtml(issue.message)}
              </li>
            `).join("")}
          </ul>
        ` : ""}
      </div>
    `
    : "";
  return `
    <section class="artifact-panel review-panel">
      <div class="artifact-panel-header">
        <div>
          <span class="profile-kicker">Review</span>
          <h3>Approve Profile Snapshots</h3>
        </div>
        <button class="action-button primary" id="onboardingApproveSnapshots" type="button">Approve reviewed profile</button>
      </div>
      <div class="review-layout">
        <div>
          <table class="artifact-table">
            <thead><tr><th>Snapshot</th><th>Status</th><th>ID</th></tr></thead>
            <tbody>${snapshotRows}</tbody>
          </table>
        </div>
        <div class="review-preview">
          ${selected ? `<h4>${escapeHtml(selected.filename)}</h4>` : ""}
          ${selectedMarkup}
          ${promotionMarkup}
        </div>
      </div>
    </section>
  `;
}

function collectReviewBlockers(value, path = "$") {
  const blockers = [];
  if (Array.isArray(value)) {
    value.forEach((item, index) => {
      blockers.push(...collectReviewBlockers(item, `${path}[${index}]`));
    });
    return blockers;
  }
  if (!value || typeof value !== "object") return blockers;

  const provenance = value.provenance;
  if (provenance && typeof provenance === "object") {
    if (provenance.needs_review === true || !["verified_document", "user_claim"].includes(provenance.source_type)) {
      blockers.push({
        path: `${path}.provenance`,
        reason: `source_type=${provenance.source_type || "missing"}, needs_review=${String(provenance.needs_review)}`,
      });
    }
  }
  Object.entries(value).forEach(([key, child]) => {
    blockers.push(...collectReviewBlockers(child, `${path}.${key}`));
  });
  return blockers;
}

function renderOnboardingChatMarkup(entries, statusText = "") {
  const messages = entries.filter((entry) => entry.role === "user" || (entry.role === "assistant" && entry.content));
  const messageHtml = messages.length
    ? messages.map((entry) => onboardingBubble(entry)).join("")
    : `<div class="onboarding-empty">No transcript yet.</div>`;
  return `
        <div class="onboarding-chat">
          <div class="onboarding-messages" id="onboardingMessages">${messageHtml}</div>
          <form class="onboarding-composer" id="onboardingComposer">
            <textarea id="onboardingMessage" rows="3" placeholder="Type the next onboarding answer or preference"></textarea>
            <button class="action-button" type="submit">Post</button>
          </form>
          <div class="onboarding-status" id="onboardingStatus">${escapeHtml(statusText)}</div>
        </div>
  `;
}

function onboardingBubble(entry) {
  const role = entry.role === "user" ? "user" : "assistant";
  const pending = entry.event === "pending_reply" ? " pending" : "";
  const label = role === "user" ? "You" : "Profile agent";
  const content = entry.content || "";
  return `
    <article class="onboarding-bubble ${role}${pending}">
      <span>${escapeHtml(label)}</span>
      <p>${escapeHtml(content || "No parsed reply yet.")}</p>
    </article>
  `;
}

function bindOnboardingControls() {
  const runInput = document.querySelector("#onboardingRunId");
  if (runInput) {
    runInput.addEventListener("change", () => {
      state.onboarding.runId = runInput.value.trim() || "onboarding-local";
      localStorage.setItem("onboardingRunId", state.onboarding.runId);
      state.onboarding.entries = [];
      state.onboarding.artifacts = null;
      state.onboarding.inputFiles = [];
      state.onboarding.snapshots = [];
      state.onboarding.selectedArtifact = null;
      state.onboarding.promotionResult = null;
      state.onboarding.lastResult = null;
      refresh();
    });
  }

  document.querySelector("#onboardingStart")?.addEventListener("click", () => onboardingStart());
  document.querySelector("#onboardingOpenTmux")?.addEventListener("click", () => onboardingOpenTmux());
  document.querySelector("#onboardingReadOutput")?.addEventListener("click", () => onboardingReadOutput());
  document.querySelector("#onboardingReload")?.addEventListener("click", () => refresh());
  document.querySelector("#onboardingReset")?.addEventListener("click", () => onboardingReset());
  document.querySelector("#onboardingClose")?.addEventListener("click", () => onboardingClose());
  document.querySelector("#onboardingFinish")?.addEventListener("click", () => onboardingFinish());
  document.querySelector("#onboardingValidateArtifacts")?.addEventListener("click", () => onboardingValidateArtifacts());
  document.querySelector("#onboardingValidateArtifactsInline")?.addEventListener("click", () => onboardingValidateArtifacts());
  document.querySelector("#onboardingApproveSnapshots")?.addEventListener("click", () => onboardingApproveSnapshots());
  document.querySelectorAll("[data-artifact-view]").forEach((button) => {
    button.addEventListener("click", () => onboardingViewArtifact(button.dataset.artifactView));
  });
  const companyRunInput = document.querySelector("#companyResearchRunId");
  if (companyRunInput) {
    companyRunInput.addEventListener("change", () => {
      state.campaign.runId = companyRunInput.value.trim();
      if (state.campaign.runId) localStorage.setItem("companyResearchRunId", state.campaign.runId);
      state.campaign.status = null;
    });
  }
  document.querySelector("#companyResearchLoad")?.addEventListener("click", () => companyResearchLoad());
  document.querySelector("#companyResearchImport")?.addEventListener("click", () => companyResearchImport());
  document.querySelector("#companyResearchLaunch")?.addEventListener("click", () => companyResearchLaunch());
  document.querySelectorAll("[data-section-link]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.sectionLink;
      const runFilter = button.dataset.runFilter;
      if (runFilter) {
        state.filters[target] = { ...(state.filters[target] || {}), run_id: runFilter };
      }
      state.activeSection = target;
      refresh();
    });
  });
  document.querySelector("#onboardingResumeUpload")?.addEventListener("change", (event) => onboardingUploadInputFile(event));
  document.querySelector("#onboardingComposer")?.addEventListener("submit", (event) => {
    event.preventDefault();
    onboardingPostMessage();
  });
}

async function companyResearchLaunch() {
  const runId = document.querySelector("#companyResearchRunId")?.value?.trim() || null;
  const roleFocus = document.querySelector("#companyResearchRoleFocus")?.value?.trim() || "Profile-aligned roles";
  const timeBudget = Number.parseInt(document.querySelector("#companyResearchTimeBudget")?.value || "30", 10);
  const notes = document.querySelector("#companyResearchNotes")?.value?.trim() || null;
  setOnboardingStatus("Launching company research run...");
  try {
    const prepared = await fetchJson("/campaigns/company-research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_id: runId,
        role_focus: roleFocus,
        time_budget_minutes: Number.isFinite(timeBudget) ? timeBudget : 30,
        notes,
      }),
    });
    const launched = await fetchJson(`/campaigns/company-research/${encodeURIComponent(prepared.run_id)}/launch`, { method: "POST" });
    const status = await fetchJson(`/campaigns/company-research/${encodeURIComponent(prepared.run_id)}/status`);
    state.campaign.runId = prepared.run_id;
    localStorage.setItem("companyResearchRunId", prepared.run_id);
    state.campaign.lastResult = { ...prepared, launch: launched };
    state.campaign.status = status;
    state.onboarding.lastResult = state.campaign.lastResult;
    startCompanyResearchPolling();
    rerenderActiveOnboarding("Company research launched.");
    elements.detailJson.textContent = JSON.stringify({ prepared, launched, status }, null, 2);
  } catch (error) {
    showOnboardingError(error);
  }
}

function isCompanyResearchTerminal(status) {
  const value = status?.status || status?.import_state?.run_status || "";
  return ["imported", "imported_with_errors", "import_failed", "research_failed", "failed"].includes(value);
}

function isApplicationDraftTerminal(status) {
  const value = status?.status || status?.import_state?.run_status || "";
  return ["imported", "imported_with_errors", "import_failed", "application_draft_failed", "failed"].includes(value);
}

function applicationDraftProgressLabel(status) {
  if (!status) return "Application draft status unavailable";
  const counts = status.artifact_counts || {};
  const valid = status.validation?.passed || 0;
  const failed = status.validation?.failed || 0;
  return [
    status.status || "unknown",
    `${counts.contact_candidate || 0} contact`,
    `${counts.email_draft || 0} draft`,
    `${counts.cv_pdf || 0} PDF`,
    `${valid} valid`,
    failed ? `${failed} failed` : "",
  ].filter(Boolean).join(" · ");
}

function stopApplicationDraftPolling() {
  if (!state.applicationDraft.pollTimer) return;
  clearInterval(state.applicationDraft.pollTimer);
  state.applicationDraft.pollTimer = null;
}

function startApplicationDraftPolling(runId) {
  if (!runId) return;
  state.applicationDraft.runId = runId;
  stopApplicationDraftPolling();
  state.applicationDraft.pollTimer = setInterval(() => {
    applicationDraftRefreshStatus(runId, { quiet: true });
  }, applicationDraftStatusIntervalMs);
}

async function applicationDraftRefreshStatus(runId, { quiet = false } = {}) {
  if (!runId) return null;
  try {
    const status = await fetchJson(`/application-drafts/${encodeURIComponent(runId)}/status`);
    state.applicationDraft.status = status;
    if (isApplicationDraftTerminal(status)) {
      stopApplicationDraftPolling();
    }
    const label = applicationDraftProgressLabel(status);
    elements.apiState.textContent = isApplicationDraftTerminal(status) ? `Application draft done: ${label}` : `Application draft running: ${label}`;
    elements.apiState.className = isApplicationDraftTerminal(status) ? "state-pill ok" : "state-pill";
    if (!quiet || elements.detailSubtitle.textContent === "Application draft progress") {
      elements.detailSubtitle.textContent = "Application draft progress";
      elements.detailJson.textContent = JSON.stringify(status, null, 2);
    }
    return status;
  } catch (error) {
    if (!quiet) {
      elements.apiState.textContent = "Application draft status failed";
      elements.apiState.className = "state-pill error";
      elements.detailSubtitle.textContent = "Application draft status error";
      elements.detailJson.textContent = error.stack || error.message;
    }
    return null;
  }
}

function isApplicationDraftBatchTerminal(batch) {
  if (!batch) return true;
  return batch.status === "completed" || ((batch.queued_count || 0) + (batch.launched_count || 0) === 0);
}

function applicationDraftBatchProgressLabel(batch) {
  if (!batch) return "Application draft batch unavailable";
  return [
    `${batch.queued_count || 0} queued`,
    `${batch.launched_count || 0} running`,
    `${batch.completed_count || 0} completed`,
    `${batch.skipped_count || 0} skipped`,
    `${batch.failed_count || 0} failed`,
  ].join(" · ");
}

function stopApplicationDraftBatchPolling() {
  if (!state.applicationDraft.batchPollTimer) return;
  clearInterval(state.applicationDraft.batchPollTimer);
  state.applicationDraft.batchPollTimer = null;
}

function startApplicationDraftBatchPolling(batchId) {
  if (!batchId) return;
  stopApplicationDraftBatchPolling();
  state.applicationDraft.batchPollTimer = setInterval(() => {
    applicationDraftBatchRefreshStatus(batchId, { quiet: true });
  }, applicationDraftStatusIntervalMs);
}

async function applicationDraftBatchRefreshStatus(batchId, { quiet = false } = {}) {
  if (!batchId) return null;
  try {
    const batch = await fetchJson(`/application-drafts/batches/${encodeURIComponent(batchId)}`);
    state.applicationDraftBatch = batch;
    const label = applicationDraftBatchProgressLabel(batch);
    elements.apiState.textContent = isApplicationDraftBatchTerminal(batch)
      ? `Application draft batch done: ${label}`
      : `Application draft batch running: ${label}`;
    elements.apiState.className = isApplicationDraftBatchTerminal(batch) ? "state-pill ok" : "state-pill";
    if (isApplicationDraftBatchTerminal(batch)) {
      stopApplicationDraftBatchPolling();
    }
    if (!quiet || elements.detailSubtitle.textContent === "Application draft batch progress") {
      elements.detailSubtitle.textContent = "Application draft batch progress";
      elements.detailJson.textContent = JSON.stringify(batch, null, 2);
    }
    return batch;
  } catch (error) {
    if (!quiet) {
      elements.apiState.textContent = "Application draft batch status failed";
      elements.apiState.className = "state-pill error";
      elements.detailSubtitle.textContent = "Application draft batch status error";
      elements.detailJson.textContent = error.stack || error.message;
    }
    return null;
  }
}

function stopCompanyResearchPolling() {
  if (!state.campaign.pollTimer) return;
  clearInterval(state.campaign.pollTimer);
  state.campaign.pollTimer = null;
}

function startCompanyResearchPolling() {
  if (!state.campaign.runId) return;
  stopCompanyResearchPolling();
  state.campaign.pollTimer = setInterval(() => {
    companyResearchRefreshStatus({ quiet: true });
  }, companyResearchStatusIntervalMs);
}

async function companyResearchRefreshStatus({ quiet = false } = {}) {
  const runId = state.campaign.runId;
  if (!runId) return null;
  try {
    const status = await fetchJson(`/campaigns/company-research/${encodeURIComponent(runId)}/status`);
    state.campaign.status = status;
    state.campaign.lastResult = {
      ...(state.campaign.lastResult || {}),
      run_id: runId,
      output_path: status.import_state?.output_path || `runs/${runId}/output`,
    };
    if (isCompanyResearchTerminal(status)) {
      stopCompanyResearchPolling();
    }
    if (currentSection().custom === "profileShell") {
      renderProfileAndChat();
      bindOnboardingControls();
    }
    if (!quiet) {
      elements.detailJson.textContent = JSON.stringify(status, null, 2);
    }
    return status;
  } catch (error) {
    if (!quiet) showOnboardingError(error);
    return null;
  }
}

function syncCompanyResearchRunId() {
  const input = document.querySelector("#companyResearchRunId");
  state.campaign.runId = input?.value?.trim() || state.campaign.runId || "";
  if (state.campaign.runId) localStorage.setItem("companyResearchRunId", state.campaign.runId);
  return state.campaign.runId;
}

async function companyResearchLoad() {
  const runId = syncCompanyResearchRunId();
  if (!runId) {
    setOnboardingStatus("Enter a company research run ID first.", "error");
    return;
  }
  setOnboardingStatus("Loading company research run...");
  try {
    const status = await companyResearchRefreshStatus();
    if (!status) return;
    state.campaign.status = status;
    state.campaign.lastResult = {
      ...(state.campaign.lastResult || {}),
      run_id: runId,
      output_path: status.import_state?.output_path || `runs/${runId}/output`,
    };
    if (!isCompanyResearchTerminal(status)) startCompanyResearchPolling();
    rerenderActiveOnboarding("Company research run loaded.");
    elements.detailJson.textContent = JSON.stringify(status, null, 2);
  } catch (error) {
    showOnboardingError(error);
  }
}

async function companyResearchImport() {
  const runId = syncCompanyResearchRunId();
  if (!runId) {
    setOnboardingStatus("Enter a company research run ID first.", "error");
    return;
  }
  setOnboardingStatus("Importing company research artifacts...");
  try {
    const result = await fetchJson(`/campaigns/company-research/${encodeURIComponent(runId)}/import`, { method: "POST" });
    state.campaign.status = result.status;
    state.campaign.lastResult = {
      ...(state.campaign.lastResult || {}),
      run_id: runId,
      output_path: result.status?.import_state?.output_path || `runs/${runId}/output`,
    };
    if (isCompanyResearchTerminal(result.status)) {
      stopCompanyResearchPolling();
    } else {
      startCompanyResearchPolling();
    }
    rerenderActiveOnboarding(result.import_result?.run?.status || "Company research artifacts imported.");
    elements.detailJson.textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    showOnboardingError(error);
  }
}

function setOnboardingStatus(message, tone = "") {
  const status = document.querySelector("#onboardingStatus");
  if (!status) return;
  status.textContent = message;
  status.className = `onboarding-status ${tone}`;
}

async function onboardingStart() {
  syncOnboardingRunId();
  state.onboarding.sessionState = { ...(state.onboarding.sessionState || {}), status: "waiting" };
  setOnboardingStatus("Starting profile agent...");
  try {
    const result = await fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/start`, { method: "POST" });
    state.onboarding.entries = result.entries || [];
    state.onboarding.sessionState = result.session_state || { status: result.status, entries: state.onboarding.entries };
    state.onboarding.lastResult = result;
    rerenderActiveOnboarding(`Session ${state.onboarding.sessionState.status || result.status}`);
    elements.detailJson.textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    showOnboardingError(error);
  }
}

async function onboardingUploadInputFile(event) {
  syncOnboardingRunId();
  const file = event.target?.files?.[0];
  if (!file) return;
  setOnboardingStatus(`Uploading ${file.name}...`);
  try {
    await fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/input-files/${encodeURIComponent(file.name)}`, {
      method: "PUT",
      headers: {
        "Content-Type": file.type || "application/octet-stream",
        Accept: "application/json",
      },
      body: file,
    });
    const inputFiles = await fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/input-files`);
    state.onboarding.inputFiles = inputFiles.files || [];
    rerenderActiveOnboarding("Resume uploaded. Start or continue the profile interview.");
    elements.detailJson.textContent = JSON.stringify(inputFiles, null, 2);
  } catch (error) {
    showOnboardingError(error);
  } finally {
    if (event.target) event.target.value = "";
  }
}

async function onboardingPostMessage() {
  syncOnboardingRunId();
  const input = document.querySelector("#onboardingMessage");
  const message = input?.value?.trim() || "";
  if (!message) return;
  if (input) input.value = "";
  const optimisticEntries = [
    ...(state.onboarding.entries || []),
    {
      run_id: state.onboarding.runId,
      role: "user",
      content: message,
      created_at: new Date().toISOString(),
      event: "local_pending",
    },
    {
      run_id: state.onboarding.runId,
      role: "assistant",
      content: "Waiting for profile agent reply...",
      created_at: new Date().toISOString(),
      event: "pending_reply",
    },
  ];
  state.onboarding.entries = optimisticEntries;
  state.onboarding.sessionState = { ...(state.onboarding.sessionState || {}), status: "waiting" };
  state.onboarding.sessionState.entries = optimisticEntries;
  rerenderActiveOnboarding("Waiting for profile agent reply...");
  setOnboardingStatus("Waiting for profile agent reply...");
  try {
    const result = await fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    state.onboarding.entries = result.entries || [];
    state.onboarding.sessionState = result.session_state || { status: "running", entries: state.onboarding.entries };
    state.onboarding.lastResult = result;
    rerenderActiveOnboarding(`Session: ${state.onboarding.sessionState.status || "running"}`);
    elements.detailJson.textContent = JSON.stringify(result, null, 2);
    if (!result.reply) {
      await onboardingPollForReply();
    }
  } catch (error) {
    showOnboardingError(error);
  }
}

async function onboardingReadOutput() {
  syncOnboardingRunId();
  setOnboardingStatus("Reading latest profile agent reply...");
  try {
    const result = await fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/refresh`, { method: "POST" });
    state.onboarding.entries = result.entries || [];
    state.onboarding.sessionState = result.session_state || { status: "running", entries: state.onboarding.entries };
    state.onboarding.lastResult = result;
    rerenderActiveOnboarding(`Session: ${state.onboarding.sessionState.status || "running"}`);
    elements.detailJson.textContent = JSON.stringify(result, null, 2);
    if (!result.reply) {
      setOnboardingStatus("No complete profile agent reply found yet.");
    }
  } catch (error) {
    showOnboardingError(error);
  }
}

async function onboardingPollForReply(maxAttempts = 30) {
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    setOnboardingStatus(`Waiting for profile agent reply... ${attempt}/${maxAttempts}`);
    await delay(2000);
    try {
      const result = await fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/refresh`, { method: "POST" });
      state.onboarding.entries = result.entries || [];
      state.onboarding.sessionState = result.session_state || { status: "running", entries: state.onboarding.entries };
      state.onboarding.lastResult = result;
      rerenderActiveOnboarding(result.reply ? "Profile agent reply received." : "Still waiting for profile agent reply...");
      elements.detailJson.textContent = JSON.stringify(result, null, 2);
      if (result.reply) return;
    } catch (error) {
      showOnboardingError(error);
      return;
    }
  }
  setOnboardingStatus("Profile agent is still running. Reload this page to pull the latest transcript.", "error");
}

async function onboardingOpenTmux() {
  syncOnboardingRunId();
  setOnboardingStatus("Inspecting agent runtime command...");
  try {
    const result = await fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/open-terminal`, { method: "POST" });
    state.onboarding.sessionState = result.session_state || state.onboarding.sessionState;
    state.onboarding.lastResult = result;
    rerenderActiveOnboarding(`Agent runtime command: ${result.command}`);
    elements.detailJson.textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    showOnboardingError(error);
  }
}

async function onboardingReset() {
  syncOnboardingRunId();
  setOnboardingStatus("Resetting profile agent session...");
  try {
    const result = await fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/reset`, { method: "POST" });
    state.onboarding.entries = result.entries || [];
    state.onboarding.sessionState = result.session_state || { status: result.status, entries: state.onboarding.entries };
    state.onboarding.lastResult = result;
    rerenderActiveOnboarding(`Session: ${state.onboarding.sessionState.status || result.status}`);
    elements.detailJson.textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    showOnboardingError(error);
  }
}

async function onboardingClose() {
  syncOnboardingRunId();
  setOnboardingStatus("Closing profile agent session...");
  try {
    const result = await fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/close`, { method: "POST" });
    state.onboarding.entries = result.entries || [];
    state.onboarding.sessionState = result.session_state || { status: result.status, entries: state.onboarding.entries };
    state.onboarding.lastResult = result;
    rerenderActiveOnboarding(`Session: ${state.onboarding.sessionState.status || result.status}`);
    elements.detailJson.textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    showOnboardingError(error);
  }
}

async function onboardingFinish() {
  syncOnboardingRunId();
  const optimisticEntries = [
    ...(state.onboarding.entries || []),
    {
      run_id: state.onboarding.runId,
      role: "user",
      content: "Finish artifacts",
      created_at: new Date().toISOString(),
      event: "local_pending",
    },
    {
      run_id: state.onboarding.runId,
      role: "assistant",
      content: "Finalizing candidate profile artifacts...",
      created_at: new Date().toISOString(),
      event: "pending_reply",
    },
  ];
  state.onboarding.entries = optimisticEntries;
  state.onboarding.sessionState = { ...(state.onboarding.sessionState || {}), status: "waiting", entries: optimisticEntries };
  rerenderActiveOnboarding("Finalizing candidate profile artifacts...");
  setOnboardingStatus("Finalizing candidate profile artifacts...");
  try {
    const result = await fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/finish`, { method: "POST" });
    state.onboarding.entries = result.entries || [];
    state.onboarding.artifacts = result.artifacts || state.onboarding.artifacts;
    state.onboarding.snapshots = await fetchJson(`/onboarding/runs/${encodeURIComponent(state.onboarding.runId)}/snapshots`);
    state.onboarding.lastResult = result;
    rerenderActiveOnboarding(result.import_result?.run?.status || "Finalization attempted");
    elements.detailJson.textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    showOnboardingError(error);
  }
}

async function onboardingValidateArtifacts() {
  syncOnboardingRunId();
  setOnboardingStatus("Validating candidate artifacts...");
  try {
    const result = await fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/import-artifacts`, { method: "POST" });
    state.onboarding.artifacts = result.artifacts || [];
    state.onboarding.snapshots = await fetchJson(`/onboarding/runs/${encodeURIComponent(state.onboarding.runId)}/snapshots`);
    state.onboarding.lastResult = result;
    rerenderActiveOnboarding(result.import_result?.run?.status || "Validation attempted");
    elements.detailJson.textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    showOnboardingError(error);
  }
}

async function onboardingViewArtifact(filename) {
  syncOnboardingRunId();
  if (!filename) return;
  setOnboardingStatus(`Loading ${filename}...`);
  try {
    const result = await fetchJson(
      `/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/artifacts/${encodeURIComponent(filename)}`,
    );
    state.onboarding.selectedArtifact = result;
    state.onboarding.lastResult = result;
    rerenderActiveOnboarding(result.exists ? `Reviewing ${filename}` : `${filename} is missing`);
    elements.detailJson.textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    showOnboardingError(error);
  }
}

async function onboardingApproveSnapshots() {
  syncOnboardingRunId();
  const reviewerId = localStorage.getItem("onboardingReviewerId") || "local-user";
  localStorage.setItem("onboardingReviewerId", reviewerId);
  setOnboardingStatus("Approving reviewed candidate snapshots...");
  try {
    const result = await fetchJson(`/onboarding/runs/${encodeURIComponent(state.onboarding.runId)}/promote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reviewer_id: reviewerId,
        confirm_user_profile: true,
        confirm_master_cv_profile: true,
        confirm_policy: true,
      }),
    });
    state.onboarding.promotionResult = result;
    state.onboarding.snapshots = await fetchJson(`/onboarding/runs/${encodeURIComponent(state.onboarding.runId)}/snapshots`);
    state.onboarding.profile = await fetchJson("/profile/summary");
    state.onboarding.selectedArtifact = null;
    state.onboarding.lastResult = result;
    rerenderActiveOnboarding(result.status === "approved" ? "Profile snapshots approved." : "Profile approval blocked.");
    elements.detailJson.textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    showOnboardingError(error);
  }
}

function rerenderActiveOnboarding(statusText = "") {
  if (currentSection().custom === "profileShell") {
    renderProfileAndChat();
  } else {
    renderOnboardingShell(state.onboarding.entries, statusText);
  }
  bindOnboardingControls();
}

function showOnboardingError(error) {
  state.onboarding.sessionState = {
    ...(state.onboarding.sessionState || {}),
    status: "failed",
    last_error: error.message,
    entries: state.onboarding.entries || [],
  };
  rerenderActiveOnboarding(error.message);
  setOnboardingStatus(error.message, "error");
  elements.detailJson.textContent = error.stack || error.message;
}

function syncOnboardingRunId() {
  const runInput = document.querySelector("#onboardingRunId");
  state.onboarding.runId = runInput?.value?.trim() || state.onboarding.runId || "onboarding-local";
  localStorage.setItem("onboardingRunId", state.onboarding.runId);
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
      detail = typeof body.detail === "string" ? body.detail : detail;
    } catch {
      // Keep the status-based detail when the response body is not JSON.
    }
    throw new Error(detail);
  }
  return response.json();
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function renderTableLoading(section) {
  elements.tableHead.innerHTML = `<tr>${section.columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("")}</tr>`;
  elements.tableBody.innerHTML = `<tr><td class="empty-state" colspan="${section.columns.length}">Loading records...</td></tr>`;
  elements.recordCount.textContent = "Loading";
}

function renderTable(section, rows) {
  elements.tableHead.innerHTML = `<tr>${section.columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("")}</tr>`;
  elements.recordCount.textContent = `${rows.length} ${rows.length === 1 ? "record" : "records"}`;

  if (!rows.length) {
    elements.tableBody.innerHTML = `<tr><td class="empty-state" colspan="${section.columns.length}">No backend records match these filters.</td></tr>`;
    return;
  }

  elements.tableBody.innerHTML = "";
  rows.forEach((row, index) => {
    const tr = document.createElement("tr");
    if (index === state.selectedIndex) tr.className = "selected";
    tr.addEventListener("click", async () => {
      state.selectedIndex = index;
      renderTable(section, rows);
      await renderDetail();
    });
    for (const column of section.columns) {
      const td = document.createElement("td");
      td.innerHTML = column.value(row);
      tr.append(td);
    }
    elements.tableBody.append(tr);
  });
  bindTableActions();
}

async function renderDetail() {
  const section = currentSection();
  const row = state.selectedIndex === null ? null : state.rows[state.selectedIndex];
  if (!row) {
    elements.detailSubtitle.textContent = "Select a row to inspect raw fields";
    elements.detailJson.textContent = "No record selected.";
    return;
  }

  elements.detailSubtitle.textContent = "Backend JSON response";
  let detail = row;
  if (section.detail) {
    try {
      detail = await section.detail(row);
    } catch (error) {
      detail = { row, detail_error: error.message };
    }
  }
  elements.detailJson.textContent = JSON.stringify(detail, null, 2);
}

async function loadRunDetail(row) {
  const [run, files, validation_results] = await Promise.all([
    fetchJson(`/runs/${encodeURIComponent(row.run_id)}`),
    fetchJson(`/runs/${encodeURIComponent(row.run_id)}/files`),
    fetchJson(`/runs/${encodeURIComponent(row.run_id)}/validation-results`),
  ]);
  return { ...run, files, validation_results };
}

function renderError(error) {
  elements.tableBody.innerHTML = `<tr><td class="error-state" colspan="8">${escapeHtml(error.message)}</td></tr>`;
  elements.recordCount.textContent = "Error";
  elements.detailSubtitle.textContent = "Load error";
  elements.detailJson.textContent = error.stack || error.message;
}

function mainCell(primary, secondary) {
  return `<span class="cell-main"><strong>${escapeHtml(primary ?? "None")}</strong><span>${escapeHtml(secondary ?? "")}</span></span>`;
}

function companySelectCheckbox(row) {
  const checked = state.selectedCompanyIds.has(row.company_id) ? " checked" : "";
  const disabled = row.can_draft_application ? "" : " disabled";
  const title = row.can_draft_application ? "Select company" : applicationDraftBlockLabel(row.application_draft_block_reason);
  return `<input type="checkbox" data-company-select="${escapeHtml(row.company_id)}" aria-label="Select company" title="${escapeHtml(title)}"${checked}${disabled}>`;
}

function sendIntentSelectCheckbox(intentId) {
  const checked = state.selectedIntentIds.has(intentId) ? " checked" : "";
  return `<input type="checkbox" data-intent-select="${escapeHtml(intentId)}" aria-label="Select send intent"${checked}>`;
}

function draftStatus(hasApplicationDraft) {
  return hasApplicationDraft ? tag("drafted", "ok") : tag("not drafted", "warn");
}

function companyOutreachState(row) {
  const items = [
    row.has_application_draft ? tag("drafted", "ok") : tag("no draft", "warn"),
    row.is_active_profile_scope ? tag("in scope", "ok") : tag("out of scope", "danger"),
    row.has_send_intent
      ? tag(row.send_gate_status ? `queued: ${row.send_gate_status}` : row.send_intent_status || "queued", sendStateTone(row))
      : tag("not queued", "warn"),
    row.has_been_contacted ? tag(row.outreach_status || "contacted", "ok") : tag("not contacted", ""),
  ];
  return `<span class="tags workflow-tags">${items.join("")}</span>`;
}

function sendStateTone(row) {
  const value = `${row.send_gate_status || ""} ${row.send_intent_status || ""}`;
  if (value.includes("blocked") || value.includes("failed")) return "danger";
  if (value.includes("needs_review") || value.includes("disabled")) return "warn";
  return "ok";
}

function companyIssues(row) {
  const issueTags = [];
  if (Array.isArray(row.policy_conflicts) && row.policy_conflicts.length) {
    issueTags.push(tag(`${row.policy_conflicts.length} conflict${row.policy_conflicts.length === 1 ? "" : "s"}`, "danger"));
  }
  if (Array.isArray(row.review_flags) && row.review_flags.length) {
    issueTags.push(tag(`${row.review_flags.length} review`, "warn"));
  }
  return issueTags.length ? `<span class="tags">${issueTags.join("")}</span>` : tag("clear", "ok");
}

function applicationDraftButton(row) {
  if (row.has_application_draft) {
    return `<button class="action-button compact" type="button" disabled>Drafted</button>`;
  }
  if (!row.can_draft_application) {
    return `<button class="action-button compact" type="button" disabled>${escapeHtml(applicationDraftBlockLabel(row.application_draft_block_reason))}</button>`;
  }
  return `<button class="action-button compact" type="button" data-application-draft-company="${escapeHtml(row.company_id)}">Draft</button>`;
}

function applicationDraftBlockLabel(reason) {
  if (reason === "not_in_active_profile_scope") return "Out of scope";
  if (reason === "draft_already_exists") return "Drafted";
  if (reason === "policy_conflict_present") return "Policy conflict";
  return "Not draftable";
}

function sendIntentButton(intentId) {
  return `<button class="action-button compact" type="button" data-send-intent="${escapeHtml(intentId)}">Send</button>`;
}

function queueDraftButton(draftId) {
  const row = state.rows.find((item) => item.draft_id === draftId);
  if (row?.queued_send_intent_id) {
    const label = row.queued_gate_status ? `Queued: ${row.queued_gate_status}` : "Queued";
    return `<button class="action-button compact" type="button" disabled>${escapeHtml(label)}</button>`;
  }
  return `<button class="action-button compact" type="button" data-queue-draft="${escapeHtml(draftId)}">Queue</button>`;
}

function outreachResolveButton(row) {
  if (!["outcome_uncertain", "sent", "provider_accepted"].includes(row.status)) {
    return `<button class="action-button compact" type="button" disabled>Resolve</button>`;
  }
  return `<button class="action-button compact" type="button" data-outreach-resolve="${escapeHtml(row.outreach_record_id)}">Resolve</button>`;
}

function attachmentLinks(row) {
  const attachments = Array.isArray(row.attachments) ? row.attachments : [];
  const links = attachments
    .filter((item) => item && typeof item === "object" && item.attachment_id)
    .map((item) => {
      const href = `/application-drafts/${encodeURIComponent(row.draft_id)}/attachments/${encodeURIComponent(item.attachment_id)}`;
      const label = item.kind === "cv" ? "Open PDF" : item.attachment_id;
      return `<a class="tag ok" href="${href}" target="_blank" rel="noopener">${escapeHtml(label)}</a>`;
    });
  if (!links.length) return `<span class="muted">None</span>`;
  return `<span class="tags">${links.join("")}</span>`;
}

function bindTableActions() {
  document.querySelectorAll("[data-company-select]").forEach((checkbox) => {
    checkbox.addEventListener("click", (event) => {
      event.stopPropagation();
    });
    checkbox.addEventListener("change", (event) => {
      event.stopPropagation();
      const companyId = checkbox.dataset.companySelect;
      if (!companyId) return;
      if (checkbox.checked) {
        state.selectedCompanyIds.add(companyId);
      } else {
        state.selectedCompanyIds.delete(companyId);
      }
    });
  });
  document.querySelectorAll("[data-intent-select]").forEach((checkbox) => {
    checkbox.addEventListener("click", (event) => {
      event.stopPropagation();
    });
    checkbox.addEventListener("change", (event) => {
      event.stopPropagation();
      const intentId = checkbox.dataset.intentSelect;
      if (!intentId) return;
      if (checkbox.checked) {
        state.selectedIntentIds.add(intentId);
      } else {
        state.selectedIntentIds.delete(intentId);
      }
    });
  });
  document.querySelectorAll("[data-application-draft-company]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      await applicationDraftLaunchForCompany(button.dataset.applicationDraftCompany);
    });
  });
  document.querySelectorAll("[data-queue-draft]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const draftId = button.dataset.queueDraft;
      if (!draftId) return;
      await queueDraftForSend(draftId);
    });
  });
  document.querySelectorAll("[data-send-intent]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const intentId = button.dataset.sendIntent;
      if (!intentId) return;
      await sendIntentBatch([intentId]);
    });
  });
  document.querySelectorAll("[data-outreach-resolve]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const outreachRecordId = button.dataset.outreachResolve;
      if (!outreachRecordId) return;
      await resolveOutreachRecord(outreachRecordId);
    });
  });
}

async function sendSelectedIntents() {
  const intentIds = Array.from(state.selectedIntentIds);
  if (!intentIds.length) {
    elements.apiState.textContent = "Select send intents first";
    elements.apiState.className = "state-pill error";
    return;
  }
  await sendIntentBatch(intentIds);
}

async function sendAllShownIntents() {
  const intentIds = state.rows.map((row) => row.intent_id).filter(Boolean);
  if (!intentIds.length) {
    elements.apiState.textContent = "No send intents shown";
    elements.apiState.className = "state-pill error";
    return;
  }
  await sendIntentBatch(intentIds);
}

async function queueAllShownDrafts() {
  const draftIds = state.rows.filter((row) => !row.queued_send_intent_id).map((row) => row.draft_id).filter(Boolean);
  if (!draftIds.length) {
    elements.apiState.textContent = "No unqueued drafts shown";
    elements.apiState.className = "state-pill warn";
    return;
  }
  await queueDraftsForSend(draftIds);
}

async function queueDraftForSend(draftId) {
  await queueDraftsForSend([draftId]);
}

async function queueDraftsForSend(draftIds) {
  const ok = window.confirm(`Queue ${draftIds.length} draft${draftIds.length === 1 ? "" : "s"} for backend send checks?`);
  if (!ok) return;
  elements.apiState.textContent = "Queueing drafts";
  elements.apiState.className = "state-pill";
  try {
    const reviewerId = localStorage.getItem("sendReviewerId") || "local-user";
    localStorage.setItem("sendReviewerId", reviewerId);
    const results = [];
    for (const draftId of draftIds) {
      results.push(
        await fetchJson(`/email-drafts/${encodeURIComponent(draftId)}/queue-send`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reviewer_id: reviewerId }),
        }),
      );
    }
    const passed = results.filter((result) => result.gate_result.status === "passed_evaluate_only").length;
    elements.apiState.textContent = `Queued ${results.length}: ${passed} passed checks`;
    elements.apiState.className = passed === results.length ? "state-pill ok" : "state-pill warn";
    elements.detailSubtitle.textContent = "Queued send intents";
    elements.detailJson.textContent = JSON.stringify(results, null, 2);
    state.activeSection = "queue";
    state.selectedIndex = null;
    await refresh();
  } catch (error) {
    elements.apiState.textContent = "Queueing failed";
    elements.apiState.className = "state-pill error";
    elements.detailSubtitle.textContent = "Queue error";
    elements.detailJson.textContent = error.stack || error.message;
  }
}

async function sendIntentBatch(intentIds) {
  const delivery = state.emailDelivery || (await fetchJson("/email-delivery/settings"));
  state.emailDelivery = delivery;
  const ok = window.confirm(
    `Approve and send ${intentIds.length} frozen email payload${intentIds.length === 1 ? "" : "s"}?\n\n${deliveryConfirmText(delivery)}`,
  );
  if (!ok) return;
  elements.apiState.textContent = "Submitting send batch";
  elements.apiState.className = "state-pill";
  try {
    const reviewerId = localStorage.getItem("sendReviewerId") || "local-user";
    localStorage.setItem("sendReviewerId", reviewerId);
    const result = await fetchJson("/send-batches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ intent_ids: intentIds, reviewer_id: reviewerId }),
    });
    elements.apiState.textContent = `Send batch ${result.status}: ${result.sent_count} sent, ${result.blocked_count} blocked`;
    elements.apiState.className = result.blocked_count ? "state-pill warn" : "state-pill ok";
    elements.detailSubtitle.textContent = "Send batch result";
    elements.detailJson.textContent = JSON.stringify(result, null, 2);
    await refresh();
  } catch (error) {
    elements.apiState.textContent = "Send batch failed";
    elements.apiState.className = "state-pill error";
    elements.detailSubtitle.textContent = "Send batch error";
    elements.detailJson.textContent = error.stack || error.message;
  }
}

function deliveryStateLabel(delivery) {
  if (!delivery) return "API connected";
  if (!delivery.sending_enabled) return "Sending disabled";
  if (delivery.mode === "gmail_sandbox") {
    return delivery.sandbox_recipient ? `Gmail sandbox: ${delivery.sandbox_recipient}` : "Gmail sandbox missing recipient";
  }
  if (delivery.mode === "gmail_real_recipients") return "Gmail real-recipient sending enabled";
  return `Email delivery blocked: ${delivery.provider}`;
}

function deliveryStateClass(delivery) {
  if (!delivery || !delivery.sending_enabled) return "state-pill warn";
  if (delivery.mode === "gmail_sandbox" && delivery.sandbox_recipient) return "state-pill ok";
  if (delivery.mode === "gmail_real_recipients") return "state-pill warn";
  return "state-pill error";
}

function deliveryConfirmText(delivery) {
  if (!delivery.sending_enabled) {
    return "Sending is disabled. The backend will freeze an approval snapshot and skip provider delivery.";
  }
  if (delivery.mode === "gmail_sandbox") {
    return `Gmail sandbox mode is active. Messages will be sent through Gmail to ${delivery.sandbox_recipient || "an unconfigured sandbox recipient"}, not to the company recipients.`;
  }
  if (delivery.mode === "gmail_real_recipients") {
    return "Gmail real-recipient mode is active. Messages may be delivered to the company recipients after the gate and reservation pass.";
  }
  return "Email delivery is blocked by configuration.";
}

async function resolveOutreachRecord(outreachRecordId) {
  const resolution = window.prompt("Resolution: mark_sent, mark_not_sent, keep_blocked, or void_record", "keep_blocked");
  if (!resolution) return;
  const comment = window.prompt("Resolution comment");
  if (!comment) return;
  elements.apiState.textContent = "Resolving outreach record";
  elements.apiState.className = "state-pill";
  try {
    const reviewerId = localStorage.getItem("sendReviewerId") || "local-user";
    const result = await fetchJson(`/outreach-records/${encodeURIComponent(outreachRecordId)}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resolution, reviewer_id: reviewerId, comment }),
    });
    elements.apiState.textContent = `Outreach resolved: ${result.outreach_record.status}`;
    elements.apiState.className = "state-pill ok";
    elements.detailSubtitle.textContent = "Outreach resolution";
    elements.detailJson.textContent = JSON.stringify(result, null, 2);
    await refresh();
  } catch (error) {
    elements.apiState.textContent = "Outreach resolution failed";
    elements.apiState.className = "state-pill error";
    elements.detailSubtitle.textContent = "Outreach resolution error";
    elements.detailJson.textContent = error.stack || error.message;
  }
}

async function applicationDraftLaunchForCompany(companyId) {
  if (!companyId) return;
  elements.apiState.textContent = "Launching application draft";
  elements.apiState.className = "state-pill";
  try {
    const prepared = await fetchJson("/application-drafts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_id: companyId }),
    });
    const launched = await fetchJson(`/application-drafts/${encodeURIComponent(prepared.run_id)}/launch`, { method: "POST" });
    const status = await fetchJson(`/application-drafts/${encodeURIComponent(prepared.run_id)}/status`);
    state.applicationDraft.runId = prepared.run_id;
    state.applicationDraft.status = status;
    startApplicationDraftPolling(prepared.run_id);
    elements.apiState.textContent = `Application draft running: ${applicationDraftProgressLabel(status)}`;
    elements.apiState.className = "state-pill ok";
    elements.detailSubtitle.textContent = "Application draft progress";
    elements.detailJson.textContent = JSON.stringify({ prepared, launched, status }, null, 2);
  } catch (error) {
    elements.apiState.textContent = "Application draft failed";
    elements.apiState.className = "state-pill error";
    elements.detailSubtitle.textContent = "Application draft error";
    elements.detailJson.textContent = error.stack || error.message;
  }
}

async function applicationDraftBatchSelected() {
  const draftableIds = new Set(state.rows.filter((row) => row.can_draft_application).map((row) => row.company_id));
  const companyIds = Array.from(state.selectedCompanyIds).filter((companyId) => draftableIds.has(companyId));
  if (!companyIds.length) {
    elements.apiState.textContent = "Select draftable in-scope companies first";
    elements.apiState.className = "state-pill error";
    return;
  }
  await applicationDraftBatchLaunch({ mode: "selected", company_ids: companyIds });
}

async function applicationDraftBatchAllMissing() {
  const ok = window.confirm("Draft application packages for all companies in the active profile scope that do not have a draft yet?");
  if (!ok) return;
  await applicationDraftBatchLaunch({ mode: "all_missing" });
}

async function applicationDraftBatchLaunch(payload) {
  elements.apiState.textContent = "Launching application draft batch";
  elements.apiState.className = "state-pill";
  try {
    const batch = await fetchJson("/application-drafts/batches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ concurrency: 2, ...payload }),
    });
    state.applicationDraftBatch = batch;
    startApplicationDraftBatchPolling(batch.batch_id);
    elements.apiState.textContent = `Application draft batch queued: ${applicationDraftBatchProgressLabel(batch)}`;
    elements.apiState.className = "state-pill ok";
    elements.detailSubtitle.textContent = "Application draft batch progress";
    elements.detailJson.textContent = JSON.stringify(batch, null, 2);
  } catch (error) {
    elements.apiState.textContent = "Application draft batch failed";
    elements.apiState.className = "state-pill error";
    elements.detailSubtitle.textContent = "Application draft batch error";
    elements.detailJson.textContent = error.stack || error.message;
  }
}

function text(value, className = "") {
  return `<span class="${escapeHtml(className)}">${escapeHtml(value ?? "None")}</span>`;
}

function statusTag(value) {
  const normalized = String(value || "unknown");
  const tone = ["blocked", "failed", "error", "invalid"].some((part) => normalized.includes(part))
    ? "danger"
    : ["needs_review", "warning", "pending", "candidate"].some((part) => normalized.includes(part))
      ? "warn"
      : ["allowed", "valid", "completed", "success", "ready"].some((part) => normalized.includes(part))
        ? "ok"
        : "";
  return tags([normalized], tone);
}

function gateSummary(result) {
  if (!result) return tags(["not_evaluated"], "warn");
  const reasonCodes = (result.reasons || []).map(readableTagValue).filter(Boolean).slice(0, 2);
  return `<div class="tags">${statusTag(result.status)}${reasonCodes.map((value) => tag(value, "warn")).join("")}</div>`;
}

function tags(values, tone = "") {
  const normalized = normalizeTags(values);
  if (!normalized.length) return `<span class="muted">None</span>`;
  return `<span class="tags">${normalized.slice(0, 5).map((value) => tag(value, tone)).join("")}</span>`;
}

function tag(value, tone = "") {
  return `<span class="tag ${escapeHtml(tone)}">${escapeHtml(value)}</span>`;
}

function normalizeTags(values) {
  if (!Array.isArray(values)) return [];
  return values.map(readableTagValue).filter(Boolean);
}

function readableTagValue(value) {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") {
    return value.code || value.id || value.claim_id || value.source_id || value.reason || JSON.stringify(value);
  }
  if (value === false || value === true) return String(value);
  return "";
}

function confidence(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return text("None", "muted");
  const number = Number(value);
  const tone = number >= 0.75 ? "ok" : number >= 0.5 ? "warn" : "danger";
  return tag(number.toFixed(2), tone);
}

function formatBytes(value) {
  const size = Number(value || 0);
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function dateTime(value) {
  if (!value) return text("None", "muted");
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return text(value);
  return text(date.toLocaleString(), "mono");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

init();
