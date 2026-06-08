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
    id: "today",
    label: "Today",
    title: "Today",
    navGroup: "Workspace",
    subtitle: "Current agent work, pending decisions, recent outcomes, and profile readiness",
    custom: "todayWorkspace",
    filters: [],
    columns: [],
  },
  {
    id: "profile",
    label: "Profile",
    title: "Profile",
    navGroup: "Workspace",
    subtitle: "Approved profile facts, constraints, source files, and Guided edits through the profile agent",
    custom: "profileShell",
    filters: [],
    columns: [],
  },
  {
    id: "opportunities",
    label: "Opportunities",
    title: "Opportunities",
    navGroup: "Workspace",
    subtitle: "Companies grouped by where they are in the agent workflow",
    custom: "opportunitiesWorkspace",
    filters: [],
    columns: [],
  },
  {
    id: "outreach",
    label: "Outreach",
    title: "Outreach",
    navGroup: "Workspace",
    subtitle: "Prepared emails, confirmations, blockers, sent mail, and contacted history",
    custom: "outreachWorkspace",
    filters: [],
    columns: [],
  },
  {
    id: "advanced",
    label: "Advanced",
    title: "Advanced",
    navGroup: "Workspace",
    subtitle: "Raw backend records, audit logs, and troubleshooting tables",
    custom: "advancedWorkspace",
    filters: [],
    columns: [],
  },
];

const advancedSections = [
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
      { label: "Confirm", value: (r) => sendIntentButton(r.intent_id) },
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
    id: "sent",
    label: "Sent mail",
    title: "Sent Mail",
    navGroup: "Developer logs",
    endpoint: "/sent-messages",
    subtitle: "Provider delivery ledger with frozen approved subject/body and Gmail references",
    filters: ["run_id", "company_id", "contact_id", "status"],
    columns: [
      { label: "Message", value: (r) => mainCell(r.sent_message_id, r.external_intent_id || "No intent") },
      { label: "Recipient", value: (r) => mainCell(r.normalized_recipient_email, r.external_company_id || r.company_policy_key) },
      { label: "Subject", value: (r) => text(r.subject || "No subject") },
      { label: "Provider", value: (r) => mainCell(r.provider, r.provider_message_id || "No provider ID") },
      { label: "Status", value: (r) => statusTag(r.status) },
      { label: "Sent", value: (r) => dateTime(r.accepted_at || r.created_at) },
      { label: "Open", value: (r) => providerLink(r) },
    ],
    detail: loadSentMessageDetail,
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
  activeAdvancedSection: advancedSections[0].id,
  rows: [],
  workspaceDraftIds: [],
  workspaceIntentIds: [],
  workspaceBlockedIntentIds: [],
  activeOutboxTab: "drafted",
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

function currentDataSection() {
  if (state.activeSection !== "advanced") return currentSection();
  return advancedSections.find((section) => section.id === state.activeAdvancedSection) || advancedSections[0];
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
  captureFilterValues(currentDataSection());
  document.body.dataset.section = section.id;
  elements.viewTitle.textContent = section.title;
  elements.tableTitle.textContent = section.title;
  elements.tableSubtitle.textContent = section.subtitle;
  elements.apiState.textContent = "Loading API state";
  elements.apiState.className = "state-pill";

  if (section.custom === "todayWorkspace") {
    await renderTodayWorkspace();
    return;
  }

  if (section.custom === "profileShell") {
    await renderProfileShell();
    return;
  }

  if (section.custom === "opportunitiesWorkspace") {
    await renderOpportunitiesWorkspace();
    return;
  }

  if (section.custom === "outreachWorkspace") {
    await renderOutreachWorkspace();
    return;
  }

  if (section.custom === "advancedWorkspace") {
    await renderAdvancedWorkspace();
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
      const rowIds = new Set(rows.filter((row) => isCompanyDraftable(row)).map((row) => row.company_id));
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
    sendSelectedButton.textContent = "Confirm selected";
    sendSelectedButton.addEventListener("click", () => sendSelectedIntents());
    const sendAllButton = document.createElement("button");
    sendAllButton.className = "action-button primary";
    sendAllButton.type = "button";
    sendAllButton.textContent = "Confirm all shown";
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

function resetWorkspaceChrome(recordLabel = "Workspace") {
  elements.filtersPanel.hidden = true;
  elements.filtersPanel.innerHTML = "";
  elements.tableHead.innerHTML = "";
  elements.recordCount.textContent = recordLabel;
  elements.detailSubtitle.textContent = "Context";
  elements.detailJson.textContent = "Select an item or open Advanced for raw records.";
}

function renderWorkspaceBody(html) {
  elements.tableBody.innerHTML = `
    <tr>
      <td class="workspace-cell">
        ${html}
      </td>
    </tr>
  `;
}

function workspaceLoading(label) {
  resetWorkspaceChrome(label);
  renderWorkspaceBody(`<div class="workspace-loading">Loading ${escapeHtml(label.toLowerCase())}...</div>`);
}

async function loadWorkspaceData(options = {}) {
  const requests = [
    ["summary", fetchJson("/dashboard/summary")],
    ["profile", fetchJson("/profile/summary")],
    ["emailDelivery", fetchJson("/email-delivery/settings")],
    ["companies", fetchJson("/companies")],
    ["drafts", fetchJson("/email-drafts")],
    ["sendIntents", fetchJson(apiPaths.sendIntents)],
    ["gateResults", fetchJson("/gate-results")],
    ["outreachRecords", fetchJson("/outreach-records")],
    ["sentMessages", fetchJson("/sent-messages")],
  ];
  if (options.includeOnboarding !== false) {
    requests.push(
      ["onboardingStatus", fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/status`).catch(() => null)],
      ["onboardingArtifacts", fetchJson(`/onboarding/chat/${encodeURIComponent(state.onboarding.runId)}/artifacts`).catch(() => null)],
    );
  }
  if (state.campaign.runId) {
    requests.push([
      "campaignStatus",
      fetchJson(`/campaigns/company-research/${encodeURIComponent(state.campaign.runId)}/status`).catch(() => null),
    ]);
  }
  const entries = await Promise.all(requests.map(async ([key, promise]) => [key, await promise]));
  return Object.fromEntries(entries);
}

async function renderTodayWorkspace() {
  workspaceLoading("Today");
  try {
    const data = await loadWorkspaceData();
    state.emailDelivery = data.emailDelivery;
    state.onboarding.profile = data.profile;
    state.onboarding.sessionState = data.onboardingStatus;
    state.onboarding.artifacts = data.onboardingArtifacts?.artifacts || [];
    state.campaign.status = data.campaignStatus;
    renderSummary(data.summary);
    renderWorkspaceBody(todayWorkspaceMarkup(data));
    bindWorkspaceActions();
    elements.apiState.textContent = deliveryStateLabel(data.emailDelivery);
    elements.apiState.className = deliveryStateClass(data.emailDelivery);
    elements.detailJson.textContent = JSON.stringify(todayDetail(data), null, 2);
  } catch (error) {
    elements.apiState.textContent = "Workspace load failed";
    elements.apiState.className = "state-pill error";
    renderError(error);
  }
}

function todayWorkspaceMarkup(data) {
  const pendingActions = buildPendingActions(data);
  const activeWork = buildActiveWork(data);
  const recentOutreach = [...(data.sentMessages || []), ...(data.outreachRecords || [])].slice(0, 5);
  return `
    <div class="assistant-workspace today-workspace">
      <section class="workspace-hero">
        <div>
          <span class="profile-kicker">Today</span>
          <h3>${escapeHtml(todayHeadline(data))}</h3>
          <p>${escapeHtml(todaySubline(data, pendingActions))}</p>
        </div>
        <div class="workspace-status-strip">
          ${statusMetric("Needs you", pendingActions.length, "warn")}
          ${statusMetric("Companies", data.summary?.companies || 0, "")}
          ${statusMetric("Contacted", data.summary?.outreach_records || 0, "ok")}
          ${statusMetric("Sent", data.summary?.sent_messages || 0, "ok")}
        </div>
      </section>
      <div class="workspace-columns">
        <section class="workflow-panel action-queue-panel">
          <div class="workflow-panel-header">
            <div>
              <span class="profile-kicker">Review queue</span>
              <h3>Decisions waiting for you</h3>
            </div>
            <button class="action-button" type="button" data-workspace-link="outreach">Open queue</button>
          </div>
          ${pendingActions.length ? pendingActions.map(actionCard).join("") : emptyWorkspaceState("Nothing needs confirmation right now.", "Agents can keep researching and drafting while this stays clear.")}
        </section>
        <section class="workflow-panel activity-panel">
          <div class="workflow-panel-header">
            <div>
              <span class="profile-kicker">Agent work</span>
              <h3>What is happening</h3>
            </div>
          </div>
          ${activeWork.length ? activeWork.map(activityCard).join("") : emptyWorkspaceState("No active agent run loaded.", "Start profile setup or launch company research from the Profile area.")}
        </section>
      </div>
      <section class="workflow-panel">
        <div class="workflow-panel-header">
          <div>
            <span class="profile-kicker">Recent outcomes</span>
            <h3>Who has been contacted</h3>
          </div>
          <button class="action-button" type="button" data-workspace-link="outreach">View outreach</button>
        </div>
        ${recentOutreach.length ? recentOutreach.map(outcomeCard).join("") : emptyWorkspaceState("No contacted history yet.", "Confirmed outreach will appear here with the company and recipient.")}
      </section>
    </div>
  `;
}

function todayHeadline(data) {
  if (!data.profile?.has_approved_profile) return "Set up your profile before agents start outreach.";
  const pending = buildPendingActions(data).length;
  if (pending) return `${pending} item${pending === 1 ? "" : "s"} need your decision.`;
  if (data.campaignStatus && !isCompanyResearchTerminal(data.campaignStatus)) return "Company research is running.";
  return "Your outreach workspace is up to date.";
}

function todaySubline(data, pendingActions) {
  if (!data.profile?.has_approved_profile) return "Chat with the profile agent, upload source documents, then approve the generated profile context.";
  if (pendingActions.length) return "Review prepared actions, edit through the agent when something looks off, or confirm when the backend gate is clear.";
  return "Use Opportunities to inspect leads and Outreach to confirm prepared messages.";
}

function buildPendingActions(data) {
  const actions = [];
  for (const intent of data.sendIntents || []) {
    const gate = intent.latest_gate_result || latestGateForIntent(intent.intent_id, data.gateResults || []);
    if (gate?.status === "passed_evaluate_only" || gate?.status === "reserved_for_send") {
      actions.push({
        type: "confirm",
        title: intent.subject || "Prepared outreach",
        subtitle: `${intent.normalized_recipient_email || intent.raw_recipient_email || "recipient"} · ${intent.external_company_id || "company"}`,
        status: gate.status,
        detail: "Backend gate passed. Review the draft and confirm when ready.",
        action: `<button class="action-button primary compact" type="button" data-send-intent="${escapeHtml(intent.intent_id)}">Confirm</button>`,
      });
    } else if (gate?.status === "blocked" || gate?.status === "needs_review") {
      actions.push({
        type: "fix",
        intentId: intent.intent_id,
        title: intent.subject || intent.intent_id,
        subtitle: intent.external_company_id || intent.normalized_recipient_email || "outreach",
        status: gate.status,
        detail: remediationSummary(gate),
        remediation: remediationList(gate),
        action: `
          <button class="action-button compact" type="button" data-remediation-toggle="${escapeHtml(intent.intent_id)}">Show fix details</button>
          ${intent.external_email_draft_id ? `<button class="action-button compact" type="button" data-advanced-link="drafts">Open draft</button>` : ""}
        `,
      });
    }
  }
  const candidateCount = data.profile?.candidate_user_profiles?.length || 0;
  if (candidateCount) {
    actions.unshift({
      type: "profile",
      title: "Review profile updates",
      subtitle: `${candidateCount} candidate profile snapshot${candidateCount === 1 ? "" : "s"}`,
      status: "candidate",
      detail: "Generated profile files are ready to validate and approve.",
      action: `<button class="action-button compact" type="button" data-workspace-link="profile">Open profile</button>`,
    });
  }
  return actions.slice(0, 8);
}

function confirmableIntentIds(data) {
  return (data.sendIntents || [])
    .filter((intent) => {
      const gate = intent.latest_gate_result || latestGateForIntent(intent.intent_id, data.gateResults || []);
      return gate?.status === "passed_evaluate_only" || gate?.status === "reserved_for_send";
    })
    .map((intent) => intent.intent_id)
    .filter(Boolean);
}

function blockedIntentIds(data) {
  return (data.sendIntents || [])
    .filter((intent) => {
      const gate = intent.latest_gate_result || latestGateForIntent(intent.intent_id, data.gateResults || []);
      return gate?.status === "blocked" || gate?.status === "needs_review";
    })
    .map((intent) => intent.intent_id)
    .filter(Boolean);
}

function buildActiveWork(data) {
  const items = [];
  if (data.onboardingStatus) {
    items.push({
      title: "Profile agent",
      status: data.onboardingStatus.status,
      detail: `${data.onboardingStatus.entries?.length || 0} transcript entries`,
      action: "Profile",
    });
  }
  if (data.campaignStatus) {
    const counts = data.campaignStatus.artifact_counts || {};
    items.push({
      title: "Company research",
      status: data.campaignStatus.status,
      detail: `${counts.companies || 0} companies · ${counts.contacts || 0} contacts · ${counts.fit_evaluations || 0} evaluations`,
      action: "Opportunities",
    });
  }
  return items;
}

function todayDetail(data) {
  return {
    profile_ready: Boolean(data.profile?.has_approved_profile),
    pending_actions: buildPendingActions(data).length,
    delivery_mode: data.emailDelivery?.mode,
    summary: data.summary,
  };
}

async function renderOpportunitiesWorkspace() {
  workspaceLoading("Opportunities");
  try {
    const data = await loadWorkspaceData({ includeOnboarding: false });
    state.emailDelivery = data.emailDelivery;
    renderSummary(data.summary);
    state.rows = data.companies || [];
    renderWorkspaceBody(opportunitiesWorkspaceMarkup(data));
    bindWorkspaceActions();
    elements.apiState.textContent = "Opportunities loaded";
    elements.apiState.className = "state-pill ok";
    elements.detailJson.textContent = JSON.stringify(opportunityCounts(data.companies || []), null, 2);
  } catch (error) {
    elements.apiState.textContent = "Opportunity load failed";
    elements.apiState.className = "state-pill error";
    renderError(error);
  }
}

function opportunitiesWorkspaceMarkup(data) {
  const groups = groupOpportunities(data.companies || []);
  return `
    <div class="assistant-workspace">
      <section class="workspace-hero">
        <div>
          <span class="profile-kicker">Opportunities</span>
          <h3>Companies move through agent-managed stages.</h3>
          <p>Use this page to see where each company stands and start drafting for good leads.</p>
        </div>
        <div class="workspace-status-strip">
          ${statusMetric("Ready", groups.ready.length, "ok")}
          ${statusMetric("Needs contact", groups.needsContact.length, "warn")}
          ${statusMetric("Blocked", groups.blocked.length, "danger")}
        </div>
      </section>
      <div class="pipeline-grid">
        ${opportunityColumn("Ready to draft", groups.ready, "ok")}
        ${opportunityColumn("Needs contact", groups.needsContact, "warn")}
        ${opportunityColumn("Drafted or queued", groups.drafted, "")}
        ${opportunityColumn("Blocked or contacted", [...groups.blocked, ...groups.contacted], "danger")}
      </div>
      <section class="workflow-panel">
        <div class="workflow-panel-header">
          <div>
            <span class="profile-kicker">Batch work</span>
            <h3>Draft applications</h3>
          </div>
          <div class="workspace-actions">
            <button class="action-button" type="button" data-advanced-link="companies">Open records</button>
            <button class="action-button primary" type="button" data-draft-all-missing>Draft all missing</button>
          </div>
        </div>
      </section>
    </div>
  `;
}

function groupOpportunities(companies) {
  const groups = { ready: [], needsContact: [], drafted: [], blocked: [], contacted: [] };
  for (const company of companies) {
    if (company.has_been_contacted) groups.contacted.push(company);
    else if (hasItems(company.policy_conflicts) || company.send_gate_status === "blocked") groups.blocked.push(company);
    else if (company.has_application_draft || company.has_send_intent) groups.drafted.push(company);
    else if (company.application_draft_block_reason === "missing_contact" || company.contact_count === 0) groups.needsContact.push(company);
    else groups.ready.push(company);
  }
  return groups;
}

function opportunityCounts(companies) {
  const groups = groupOpportunities(companies);
  return Object.fromEntries(Object.entries(groups).map(([key, value]) => [key, value.length]));
}

function opportunityColumn(title, rows, tone) {
  return `
    <section class="workflow-panel pipeline-column ${tone}">
      <div class="workflow-panel-header">
        <div>
          <span class="profile-kicker">${rows.length} ${rows.length === 1 ? "company" : "companies"}</span>
          <h3>${escapeHtml(title)}</h3>
        </div>
      </div>
      <div class="pipeline-list">
        ${rows.length ? rows.slice(0, 12).map(opportunityCard).join("") : emptyWorkspaceState("Nothing here.", "Companies will appear as agents produce or update records.")}
      </div>
    </section>
  `;
}

function opportunityCard(row) {
  return `
    <article class="workspace-card">
      <div>
        <strong>${escapeHtml(row.name || row.company_id)}</strong>
        <p>${escapeHtml(row.normalized_domain || row.company_policy_key || "No domain")}</p>
      </div>
      <div class="workspace-card-meta">
        ${confidence(row.confidence)}
        ${companyOutreachState(row)}
      </div>
      <div class="workspace-card-actions">
        ${applicationDraftButton(row)}
        <button class="action-button compact" type="button" data-advanced-link="companies">Details</button>
      </div>
    </article>
  `;
}

async function renderOutreachWorkspace() {
  workspaceLoading("Outreach");
  try {
    const [summary, emailDelivery, drafts, sent] = await Promise.all([
      fetchJson("/dashboard/summary"),
      fetchJson("/email-delivery/settings"),
      fetchJson("/outbox/drafts"),
      fetchJson("/outbox/sent"),
    ]);
    const data = { summary, emailDelivery, drafts, sent };
    state.emailDelivery = data.emailDelivery;
    state.rows = state.activeOutboxTab === "sent" ? data.sent : data.drafts;
    renderSummary(data.summary);
    renderWorkspaceBody(outreachWorkspaceMarkup(data));
    bindWorkspaceActions();
    elements.apiState.textContent = deliveryStateLabel(data.emailDelivery);
    elements.apiState.className = deliveryStateClass(data.emailDelivery);
    elements.detailJson.textContent = JSON.stringify({
      delivery: data.emailDelivery,
      drafted: data.drafts.length,
      ready: data.drafts.filter((row) => row.status === "ready").length,
      sent: data.sent.length,
    }, null, 2);
  } catch (error) {
    elements.apiState.textContent = "Outreach load failed";
    elements.apiState.className = "state-pill error";
    renderError(error);
  }
}

function outreachWorkspaceMarkup(data) {
  const drafts = data.drafts || [];
  const sent = data.sent || [];
  const readyCount = drafts.filter((row) => row.status === "ready").length;
  const blockedCount = drafts.filter((row) => row.status === "blocked").length;
  const shownRows = state.activeOutboxTab === "sent" ? sent : drafts;
  return `
    <div class="assistant-workspace">
      <section class="workspace-hero">
        <div>
          <span class="profile-kicker">Outreach</span>
          <h3>Drafted emails and sent history.</h3>
          <p>Send completed email and CV drafts, and keep contacted companies out of future sends.</p>
        </div>
        <div class="workspace-status-strip">
          ${statusMetric("Ready", readyCount, "ok")}
          ${statusMetric("Blocked", blockedCount, "warn")}
          ${statusMetric("Sent", sent.length, "ok")}
        </div>
      </section>
      <section class="workflow-panel">
        <div class="workflow-panel-header">
          <div>
            <span class="profile-kicker">${state.activeOutboxTab === "sent" ? "Sent" : "Drafted"}</span>
            <h3>${state.activeOutboxTab === "sent" ? "Companies already contacted" : "Completed email and CV drafts"}</h3>
          </div>
          <div class="workspace-actions">
            <button class="advanced-tab ${state.activeOutboxTab === "drafted" ? "active" : ""}" type="button" data-outbox-tab="drafted">Drafted</button>
            <button class="advanced-tab ${state.activeOutboxTab === "sent" ? "active" : ""}" type="button" data-outbox-tab="sent">Sent</button>
            ${state.activeOutboxTab === "drafted"
              ? `<button class="action-button primary" type="button" data-outbox-send-all${readyCount ? "" : " disabled"}>${readyCount ? `Send all (${readyCount})` : "Nothing ready to send"}</button>`
              : ""}
          </div>
        </div>
        ${shownRows.length ? outboxTableMarkup(shownRows, state.activeOutboxTab) : emptyWorkspaceState(
          state.activeOutboxTab === "sent" ? "No sent emails yet." : "No completed drafts yet.",
          state.activeOutboxTab === "sent" ? "Sent emails will appear here after the backend accepts or records them." : "Completed email and CV drafts will appear here when the drafting agent finishes.",
        )}
      </section>
    </div>
  `;
}

function outboxTableMarkup(rows, tab) {
  const isSent = tab === "sent";
  return `
    <table class="artifact-table outbox-table">
      <thead>
        <tr>
          <th>Company</th>
          <th>Email address</th>
          <th>${isSent ? "Sent date" : "Drafted date"}</th>
          <th>Status</th>
          <th>Email text</th>
          <th>CV</th>
          ${isSent ? "<th>Provider</th>" : ""}
        </tr>
      </thead>
      <tbody>
        ${rows.map((row) => isSent ? outboxSentRow(row) : outboxDraftRow(row)).join("")}
      </tbody>
    </table>
  `;
}

function outboxDraftRow(row) {
  return `
    <tr>
      <td>${mainCell(row.company_name || row.company_id, row.company_id)}</td>
      <td>${text(row.email_address || "Missing")}</td>
      <td>${dateTime(row.drafted_at)}</td>
      <td>${outboxStatus(row)}</td>
      <td><button class="action-button compact" type="button" data-outbox-email="${escapeHtml(row.draft_id)}">Open email</button></td>
      <td>${outboxCvLink(row.cv)}</td>
    </tr>
  `;
}

function outboxSentRow(row) {
  return `
    <tr>
      <td>${mainCell(row.company_name || row.company_id || row.company_policy_key, row.company_id || "")}</td>
      <td>${text(row.email_address)}</td>
      <td>${dateTime(row.sent_at)}</td>
      <td>${statusTag(row.status)}</td>
      <td><button class="action-button compact" type="button" data-outbox-email="${escapeHtml(row.sent_message_id)}">Open email</button></td>
      <td>${outboxCvLink(row.cv)}</td>
      <td>${row.provider_url ? `<a class="action-button compact" href="${escapeHtml(row.provider_url)}" target="_blank" rel="noreferrer">Open</a>` : text("None", "muted")}</td>
    </tr>
  `;
}

function outboxStatus(row) {
  if (row.status === "ready") return tag(row.status_label || "Ready", "ok");
  if (row.status === "sent") return tag(row.status_label || "Sent", "ok");
  return tag(row.status_label || "Blocked", "warn");
}

function outboxCvLink(cv) {
  if (!cv || !cv.url) return text("Missing", "muted");
  return `<a class="action-button compact" href="${escapeHtml(cv.url)}" target="_blank" rel="noopener">${escapeHtml(cv.label || "Open PDF")}</a>`;
}

function generatedDraftCard(draft) {
  const queued = draft.queued_send_intent_id
    ? tag(`queued: ${draft.queued_gate_status || "pending gate"}`, draft.queued_gate_status === "blocked" ? "danger" : "ok")
    : tag("not queued", "warn");
  return `
    <article class="workspace-card draft-card">
      <div>
        <strong>${escapeHtml(draft.subject || draft.draft_id)}</strong>
        <p>${escapeHtml(draft.external_company_id || "company")} · ${escapeHtml(draft.external_contact_id || "contact")}</p>
      </div>
      <div class="workspace-card-meta">
        ${confidence(draft.confidence)}
        ${queued}
        ${tags(draft.review_flags, "warn")}
      </div>
      <div class="draft-preview">${escapeHtml(shortText(draft.body_text || "", 320))}</div>
      <div class="workspace-card-actions">
        ${attachmentLinks(draft)}
        ${draft.queued_send_intent_id
          ? `<button class="action-button compact" type="button" disabled>${escapeHtml(draft.queued_gate_status ? `Queued: ${draft.queued_gate_status}` : "Queued")}</button>`
          : queueDraftButton(draft.draft_id)}
      </div>
    </article>
  `;
}

function draftActionCard(draft) {
  return `
    <article class="workspace-card">
      <div>
        <strong>${escapeHtml(draft.subject || draft.draft_id)}</strong>
        <p>${escapeHtml(draft.external_company_id || "company")} · ${escapeHtml(draft.external_contact_id || "contact")}</p>
      </div>
      <div class="workspace-card-meta">${confidence(draft.confidence)}${tags(draft.review_flags, "warn")}</div>
      <div class="workspace-card-actions">
        ${attachmentLinks(draft)}
        ${queueDraftButton(draft.draft_id)}
      </div>
    </article>
  `;
}

async function renderAdvancedWorkspace() {
  const section = currentDataSection();
  renderFilters(section);
  renderAdvancedTabs();
  renderTableLoading(section);
  elements.tableTitle.textContent = section.title;
  elements.tableSubtitle.textContent = section.subtitle;
  try {
    const [summary, emailDelivery, rows] = await Promise.all([
      fetchJson("/dashboard/summary"),
      fetchJson("/email-delivery/settings"),
      loadRows(section),
    ]);
    state.emailDelivery = emailDelivery;
    renderSummary(summary);
    state.rows = rows;
    state.selectedIndex = rows.length ? 0 : null;
    renderTable(section, rows);
    renderDetail();
    elements.apiState.textContent = deliveryStateLabel(emailDelivery);
    elements.apiState.className = deliveryStateClass(emailDelivery);
  } catch (error) {
    elements.apiState.textContent = "Advanced load failed";
    elements.apiState.className = "state-pill error";
    renderError(error);
  }
}

function renderAdvancedTabs() {
  const tabs = advancedSections.map((section) => `
    <button class="advanced-tab ${section.id === state.activeAdvancedSection ? "active" : ""}" type="button" data-advanced-tab="${escapeHtml(section.id)}">
      ${escapeHtml(section.label)}
    </button>
  `).join("");
  elements.filtersPanel.hidden = false;
  elements.filtersPanel.insertAdjacentHTML("afterbegin", `<div class="advanced-tabs">${tabs}</div>`);
  document.querySelectorAll("[data-advanced-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      captureFilterValues(currentDataSection());
      state.activeAdvancedSection = button.dataset.advancedTab;
      state.selectedIndex = null;
      refresh();
    });
  });
}

function bindWorkspaceActions() {
  bindTableActions();
  document.querySelectorAll("[data-workspace-link]").forEach((button) => {
    button.addEventListener("click", () => {
      const sectionId = button.dataset.workspaceLink;
      if (!sections.some((section) => section.id === sectionId)) return;
      state.activeSection = sectionId;
      state.selectedIndex = null;
      renderNav();
      refresh();
    });
  });
  document.querySelectorAll("[data-advanced-link]").forEach((button) => {
    button.addEventListener("click", () => {
      const advancedId = button.dataset.advancedLink;
      if (advancedSections.some((section) => section.id === advancedId)) {
        state.activeAdvancedSection = advancedId;
      }
      state.activeSection = "advanced";
      renderNav();
      refresh();
    });
  });
  document.querySelectorAll("[data-remediation-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const intentId = button.dataset.remediationToggle || "";
      const panel = document.querySelector(`[data-remediation-details="${cssEscape(intentId)}"]`);
      if (!panel) return;
      const nextHidden = !panel.hidden;
      panel.hidden = nextHidden;
      button.textContent = nextHidden ? "Show fix details" : "Hide fix details";
    });
  });
  document.querySelectorAll("[data-draft-all-missing]").forEach((button) => {
    button.addEventListener("click", () => applicationDraftBatchAllMissing());
  });
  document.querySelectorAll("[data-queue-all-drafts]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!state.workspaceDraftIds.length) {
        elements.apiState.textContent = "No unqueued drafts";
        elements.apiState.className = "state-pill warn";
        return;
      }
      await queueDraftsForSend(state.workspaceDraftIds);
    });
  });
  document.querySelectorAll("[data-recheck-blocked]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!state.workspaceBlockedIntentIds.length) {
        elements.apiState.textContent = "No blocked drafts to recheck";
        elements.apiState.className = "state-pill warn";
        return;
      }
      await recheckBlockedIntents(state.workspaceBlockedIntentIds);
    });
  });
  document.querySelectorAll("[data-confirm-all-shown]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!state.workspaceIntentIds.length) {
        elements.apiState.textContent = "No prepared outreach";
        elements.apiState.className = "state-pill warn";
        return;
      }
      await sendIntentBatch(state.workspaceIntentIds);
    });
  });
  document.querySelectorAll("[data-outbox-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeOutboxTab = button.dataset.outboxTab || "drafted";
      refresh();
    });
  });
  document.querySelectorAll("[data-outbox-send-all]").forEach((button) => {
    button.addEventListener("click", () => outboxSendAll());
  });
  document.querySelectorAll("[data-outbox-email]").forEach((button) => {
    button.addEventListener("click", () => showOutboxEmail(button.dataset.outboxEmail || ""));
  });
}

function showOutboxEmail(id) {
  const row = state.rows.find((item) => item.draft_id === id || item.sent_message_id === id);
  if (!row) return;
  elements.detailSubtitle.textContent = row.subject || "Email text";
  elements.detailJson.textContent = row.body_text || "No email body recorded.";
}

async function outboxSendAll() {
  const readyCount = state.rows.filter((row) => row.status === "ready").length;
  if (!readyCount) {
    elements.apiState.textContent = "Nothing ready to send";
    elements.apiState.className = "state-pill warn";
    return;
  }
  const delivery = state.emailDelivery || (await fetchJson("/email-delivery/settings"));
  state.emailDelivery = delivery;
  const ok = window.confirm(`Send ${readyCount} ready email${readyCount === 1 ? "" : "s"}?\n\n${deliveryConfirmText(delivery)}`);
  if (!ok) return;
  elements.apiState.textContent = "Sending ready drafts";
  elements.apiState.className = "state-pill";
  try {
    const reviewerId = localStorage.getItem("sendReviewerId") || "local-user";
    localStorage.setItem("sendReviewerId", reviewerId);
    const result = await fetchJson("/outbox/send-all", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer_id: reviewerId }),
    });
    elements.apiState.textContent = `Send all complete: ${result.sent_count} sent, ${result.blocked_count} blocked`;
    elements.apiState.className = result.blocked_count ? "state-pill warn" : "state-pill ok";
    elements.detailSubtitle.textContent = "Send all result";
    elements.detailJson.textContent = JSON.stringify(result.batch || result, null, 2);
    await refresh();
  } catch (error) {
    elements.apiState.textContent = "Send all failed";
    elements.apiState.className = "state-pill error";
    elements.detailSubtitle.textContent = "Send all error";
    elements.detailJson.textContent = error.stack || error.message;
  }
}

async function recheckBlockedIntents(intentIds) {
  elements.apiState.textContent = `Rechecking ${intentIds.length} blocked draft${intentIds.length === 1 ? "" : "s"}`;
  elements.apiState.className = "state-pill";
  try {
    const results = [];
    for (const intentId of intentIds) {
      results.push(await fetchJson(`/gate/evaluations/${encodeURIComponent(intentId)}`, { method: "POST" }));
    }
    const passed = results.filter((result) => result.status === "passed_evaluate_only").length;
    const blocked = results.filter((result) => result.status === "blocked" || result.status === "needs_review").length;
    elements.apiState.textContent = `Rechecked ${results.length}: ${passed} confirmable, ${blocked} still blocked`;
    elements.apiState.className = blocked ? "state-pill warn" : "state-pill ok";
    elements.detailSubtitle.textContent = "Gate recheck result";
    elements.detailJson.textContent = JSON.stringify(results, null, 2);
    await refresh();
  } catch (error) {
    elements.apiState.textContent = "Gate recheck failed";
    elements.apiState.className = "state-pill error";
    elements.detailSubtitle.textContent = "Gate recheck error";
    elements.detailJson.textContent = error.stack || error.message;
  }
}

function statusMetric(label, value, tone) {
  return `<div class="status-metric ${tone || ""}"><span>${escapeHtml(label)}</span><strong>${Number(value || 0)}</strong></div>`;
}

function actionCard(action) {
  const remediation = action.type === "fix" && Array.isArray(action.remediation)
    ? `
      <div class="remediation-details" data-remediation-details="${escapeHtml(action.intentId || "")}" hidden>
        <strong>What needs to be fixed</strong>
        <ul>
          ${action.remediation.map((item) => `
            <li>
              <span>${escapeHtml([item.code, item.field].filter(Boolean).join(" · "))}</span>
              ${escapeHtml(item.message)}
            </li>
          `).join("")}
        </ul>
        <p>Use the draft/profile agent to repair the missing claims, low confidence, review flags, or contact evidence, then re-run the gate.</p>
      </div>
    `
    : "";
  return `
    <article class="workspace-card action-card ${escapeHtml(action.type)}">
      <div>
        <strong>${escapeHtml(action.title)}</strong>
        <p>${escapeHtml(action.subtitle)}</p>
      </div>
      <div class="workspace-card-meta">
        ${statusTag(action.status)}
        <span>${escapeHtml(action.detail)}</span>
      </div>
      <div class="workspace-card-actions">${action.action}</div>
      ${remediation}
    </article>
  `;
}

function activityCard(item) {
  return `
    <article class="workspace-card">
      <div>
        <strong>${escapeHtml(item.title)}</strong>
        <p>${escapeHtml(item.detail)}</p>
      </div>
      <div class="workspace-card-meta">${statusTag(item.status)}</div>
    </article>
  `;
}

function outcomeCard(item) {
  const recipient = item.normalized_recipient_email || item.recipient_email || item.raw_recipient_email || item.external_intent_id || "recipient";
  const subject = item.subject || item.outreach_record_id || item.sent_message_id || "outreach record";
  const company = item.external_company_id || item.company_policy_key || item.company_id || "company";
  return `
    <article class="workspace-card outcome-card">
      <div>
        <strong>${escapeHtml(subject)}</strong>
        <p>${escapeHtml(recipient)} · ${escapeHtml(company)}</p>
      </div>
      <div class="workspace-card-meta">
        ${statusTag(item.status || "recorded")}
        <span>${escapeHtml(item.provider || item.channel || "")}</span>
      </div>
    </article>
  `;
}

function emptyWorkspaceState(title, body) {
  return `<div class="empty-workspace"><strong>${escapeHtml(title)}</strong><p>${escapeHtml(body)}</p></div>`;
}

function latestGateForIntent(intentId, gateResults) {
  return gateResults.find((gate) => gate.external_intent_id === intentId || gate.intent_id === intentId) || null;
}

function reasonSummary(reasons) {
  if (!Array.isArray(reasons) || !reasons.length) return "Backend gate needs attention.";
  return reasons.map((reason) => reason.code || reason.message || reason).slice(0, 3).join(", ");
}

function cssEscape(value) {
  if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(value);
  return String(value).replace(/["\\]/g, "\\$&");
}

function remediationSummary(gate) {
  const reasons = Array.isArray(gate?.reasons) ? gate.reasons : [];
  if (!reasons.length) return "The backend gate did not provide a specific reason.";
  return reasons
    .map((reason) => reason.message || reason.code || String(reason))
    .slice(0, 2)
    .join(" ");
}

function remediationList(gate) {
  const reasons = Array.isArray(gate?.reasons) ? gate.reasons : [];
  if (!reasons.length) {
    return [{ code: "unknown", message: "No gate reason was recorded. Open Advanced for the raw gate result." }];
  }
  return reasons.map((reason) => ({
    code: reason.code || "gate_reason",
    field: reason.field || "",
    message: reason.message || reason.code || String(reason),
  }));
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
  const section = currentDataSection();
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

async function loadSentMessageDetail(row) {
  return fetchJson(`/sent-messages/${encodeURIComponent(row.sent_message_id)}`);
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
  const draftable = isCompanyDraftable(row);
  const disabled = draftable ? "" : " disabled";
  const title = draftable ? "Select company" : applicationDraftBlockLabel(applicationDraftBlockReason(row));
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
    row.is_active_profile_scope ? tag("in scope", "ok") : tag("not scoped", ""),
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
  if (!isCompanyDraftable(row)) {
    return `<button class="action-button compact" type="button" disabled>${escapeHtml(applicationDraftBlockLabel(applicationDraftBlockReason(row)))}</button>`;
  }
  return `<button class="action-button compact" type="button" data-application-draft-company="${escapeHtml(row.company_id)}">Draft</button>`;
}

function isCompanyDraftable(row) {
  if (typeof row.can_draft_application === "boolean") return row.can_draft_application;
  return !row.has_application_draft && !hasItems(row.policy_conflicts);
}

function hasItems(value) {
  return Array.isArray(value) && value.length > 0;
}

function applicationDraftBlockReason(row) {
  if (row.application_draft_block_reason) return row.application_draft_block_reason;
  if (row.has_application_draft) return "draft_already_exists";
  if (hasItems(row.policy_conflicts)) return "policy_conflict_present";
  return null;
}

function applicationDraftBlockLabel(reason) {
  if (reason === "draft_already_exists") return "Drafted";
  if (reason === "policy_conflict_present") return "Policy conflict";
  return "Not draftable";
}

function sendIntentButton(intentId) {
  return `<button class="action-button compact" type="button" data-send-intent="${escapeHtml(intentId)}">Confirm</button>`;
}

function queueDraftButton(draftId) {
  const row = state.rows.find((item) => item.draft_id === draftId);
  if (row?.queued_send_intent_id) {
    const label = row.queued_gate_status ? `Queued: ${row.queued_gate_status}` : "Queued";
    return `<button class="action-button compact" type="button" disabled>${escapeHtml(label)}</button>`;
  }
  return `<button class="action-button compact" type="button" data-queue-draft="${escapeHtml(draftId)}">Queue</button>`;
}

function providerLink(row) {
  if (!row.provider_url) return text("Unavailable");
  return `<a class="action-button compact" href="${escapeHtml(row.provider_url)}" target="_blank" rel="noreferrer">Open</a>`;
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
    return "Gmail real-recipient mode is active. Messages will be delivered to the company recipients after the gate and reservation pass. This is irreversible.";
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
  const draftableIds = new Set(state.rows.filter((row) => isCompanyDraftable(row)).map((row) => row.company_id));
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

function shortText(value, maxLength = 180) {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, Math.max(0, maxLength - 1)).trim()}...`;
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
