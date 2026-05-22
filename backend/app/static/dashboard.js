const apiPaths = {
  sendIntents: "/" + "send-intents",
};
// Read-only dashboard API coverage: /send-intents

const onboardingArtifactFiles = [
  "user_profile.json",
  "master_cv_profile.json",
  "policy.json",
  "onboarding_review.json",
];

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
    subtitle: "Imported company profiles, policy keys, evidence, and conflicts",
    filters: ["run_id", "min_confidence", "has_review_flags", "has_policy_conflicts"],
    columns: [
      { label: "Company", value: (r) => mainCell(r.name, r.company_id) },
      { label: "Domain", value: (r) => mainCell(r.normalized_domain || "No domain", r.company_policy_key) },
      { label: "Remote", value: (r) => text(r.remote_policy || "Unknown") },
      { label: "Confidence", value: (r) => confidence(r.confidence) },
      { label: "Review", value: (r) => tags(r.review_flags, "warn") },
      { label: "Conflicts", value: (r) => tags(r.policy_conflicts, "danger") },
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
      { label: "Review", value: (r) => tags(r.review_flags, "warn") },
    ],
  },
  {
    id: "runs",
    label: "Runs",
    title: "Runs",
    navGroup: "Developer logs",
    endpoint: "/runs",
    subtitle: "Imports, output paths, and run lifecycle state",
    filters: ["status"],
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
    subtitle: "Imported send intents and latest deterministic gate result",
    filters: ["run_id", "company_id", "contact_id", "status", "gate_status", "reason_code", "min_confidence", "has_review_flags"],
    columns: [
      { label: "Intent", value: (r) => mainCell(r.intent_id, r.subject) },
      { label: "Recipient", value: (r) => mainCell(r.normalized_recipient_email, r.recipient_name || r.external_contact_id) },
      { label: "Company", value: (r) => mainCell(r.external_company_id, r.company_domain || "No domain") },
      { label: "Status", value: (r) => statusTag(r.status) },
      { label: "Gate", value: (r) => gateSummary(r.latest_gate_result) },
      { label: "Confidence", value: (r) => confidence(r.confidence) },
      { label: "Review", value: (r) => tags(r.review_flags, "warn") },
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
  gate_status: { label: "Gate status", type: "select", options: ["", "passed_evaluate_only", "blocked", "needs_review"] },
  result_status: { label: "Result status", type: "text", placeholder: "success" },
  reason_code: { label: "Reason code", type: "text", placeholder: "missing_source" },
  email_source: { label: "Email source", type: "text", placeholder: "public" },
  decision: { label: "Decision", type: "text", placeholder: "pursue" },
  min_confidence: { label: "Min confidence", type: "number", min: "0", max: "1", step: "0.05", placeholder: "0.70" },
  has_review_flags: { label: "Review flags", type: "select", options: ["", "true", "false"] },
  has_policy_conflicts: { label: "Policy conflicts", type: "select", options: ["", "true", "false"] },
  limit: { label: "Limit", type: "number", min: "1", max: "500", step: "1", placeholder: "100" },
};

const state = {
  activeSection: sections[0].id,
  rows: [],
  selectedIndex: null,
  controllers: new Map(),
  filters: {},
  onboarding: {
    runId: localStorage.getItem("onboardingRunId") || "onboarding-local",
    entries: [],
    sessionState: null,
    profile: null,
    artifacts: null,
    inputFiles: [],
    lastResult: null,
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
    const [summary, rows] = await Promise.all([fetchJson("/dashboard/summary"), loadRows(section)]);
    renderSummary(summary);
    state.rows = rows;
    state.selectedIndex = rows.length ? 0 : null;
    renderTable(section, rows);
    renderDetail();
    elements.apiState.textContent = "Read-only API connected";
    elements.apiState.className = "state-pill ok";
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
  const status = document.querySelector("#filter-status")?.value?.trim();
  if (!status) return rows;
  return rows.filter((row) => row.status === status);
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
    const [summary, profile, sessionState, artifacts, inputFiles] = await Promise.all([
      fetchJson("/dashboard/summary"),
      fetchJson("/profile/summary"),
      fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/status`),
      fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/artifacts`),
      fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/input-files`),
    ]);
    renderSummary(summary);
    state.onboarding.profile = profile;
    state.onboarding.sessionState = sessionState;
    state.onboarding.entries = sessionState.entries || [];
    state.onboarding.artifacts = artifacts.artifacts || [];
    state.onboarding.inputFiles = inputFiles.files || [];
    renderProfileAndChat();
    bindOnboardingControls();
    elements.detailJson.textContent = JSON.stringify({ profile, session_state: sessionState, artifacts, input_files: inputFiles }, null, 2);
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
          ${renderAccountPanel()}
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
          ${renderInputFilesPanel()}
          ${renderProfileToolbar()}
          ${renderArtifactPanel()}
          ${renderOnboardingChatMarkup(sessionState.entries || state.onboarding.entries || [], `Session: ${status}`)}
        </div>
      </td>
    </tr>
  `;
  const messageList = document.querySelector("#onboardingMessages");
  if (messageList) messageList.scrollTop = messageList.scrollHeight;
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
          </tr>
        `;
      }).join("")
    : onboardingArtifactFiles.map((filename) => `
        <tr>
          <td>${escapeHtml(filename)}</td>
          <td>${statusTag("missing")}</td>
          <td>Artifact state has not loaded yet.</td>
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
          <tr><th>File</th><th>Status</th><th>Review</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </section>
  `;
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
  document.querySelector("#onboardingResumeUpload")?.addEventListener("change", (event) => onboardingUploadInputFile(event));
  document.querySelector("#onboardingComposer")?.addEventListener("submit", (event) => {
    event.preventDefault();
    onboardingPostMessage();
  });
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
  setOnboardingStatus("Finalizing candidate profile artifacts...");
  try {
    const result = await fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/finish`, { method: "POST" });
    state.onboarding.entries = result.entries || [];
    state.onboarding.artifacts = result.artifacts || state.onboarding.artifacts;
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
    state.onboarding.lastResult = result;
    rerenderActiveOnboarding(result.import_result?.run?.status || "Validation attempted");
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
