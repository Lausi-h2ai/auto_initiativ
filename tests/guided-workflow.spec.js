import { test, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const port = Number(process.env.GUIDED_WORKFLOW_PORT || 8876);
const baseURL = process.env.PW_BASE_URL || `http://127.0.0.1:${port}`;
const pythonExecutable = process.env.PYTHON || path.resolve(".venv", "Scripts", "python.exe");
let server;

const company = {
  id: 1,
  company_id: "company-latticeflow",
  name: "LatticeFlow",
  raw_domain: "latticeflow.ai",
  normalized_domain: "latticeflow.ai",
  normalized_name: "latticeflow",
  company_policy_key: "domain:latticeflow.ai",
  company_policy_key_kind: "domain",
  description: "Builds tools for evaluating and improving computer vision systems in regulated environments.",
  industry_tags: ["Applied AI"],
  locations: ["Zurich, Switzerland"],
  remote_policy: "Hybrid",
  source_refs: ["https://latticeflow.ai"],
  confidence: 0.9,
  review_flags: [],
  policy_conflicts: [],
  is_active_profile_scope: true,
  can_draft_application: true,
  application_draft_block_reason: null,
  has_application_draft: false,
  has_send_intent: false,
  send_intent_status: null,
  send_gate_status: null,
  has_been_contacted: false,
  outreach_status: null,
  raw: { website_url: "https://latticeflow.ai" },
  imported_file_id: 1,
  created_at: "2026-07-03T08:00:00Z",
  updated_at: "2026-07-03T08:00:00Z",
};

const fit = {
  id: 1,
  evaluation_id: "fit-latticeflow",
  company_id: 1,
  external_company_id: "company-latticeflow",
  user_profile_snapshot_id: 1,
  policy_snapshot_id: 1,
  fit_score: 0.88,
  decision: "in_scope",
  reasons: ["Practical AI product with Swiss presence", "Strong overlap with model quality work"],
  risks: ["Contact quality still needs verification"],
  source_refs: ["https://latticeflow.ai"],
  confidence: 0.86,
  review_flags: [],
  raw: {},
  imported_file_id: 1,
  created_at: "2026-07-03T08:00:00Z",
};

test.beforeAll(async () => {
  mkdirSync("artifacts/screenshots", { recursive: true });
  if (process.env.PW_BASE_URL) return;
  const root = mkdtempSync(path.join(tmpdir(), "auto-initiativ-guided-"));
  server = spawn(pythonExecutable, ["-m", "uvicorn", "backend.app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", String(port)], {
    cwd: path.resolve("."),
    env: {
      ...process.env,
      RUNS_ROOT: path.join(root, "runs"),
      DATABASE_URL: `sqlite:///${path.join(root, "test.db")}`,
      SCHEMAS_ROOT: path.resolve("schemas"),
      EMAIL_SENDING_ENABLED: "false",
      EMAIL_PROVIDER: "gmail_sandbox",
      EMAIL_ALLOW_REAL_RECIPIENTS: "false",
    },
    stdio: "ignore",
  });
  await waitForServer(`${baseURL}/health`);
});

test.afterAll(() => {
  server?.kill();
});

async function waitForServer(url) {
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
  }
  throw new Error(`Server did not start at ${url}`);
}

async function mockApi(page, { withCompanies = false, activeResearch = false, failLaunch = false, onboardingReview = false } = {}) {
  const forbidden = [];
  let launchCalls = 0;
  let promotionCalls = 0;
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;
    if (["/send-batches", "/outbox/send-all"].includes(pathname) || pathname.endsWith("/queue-send")) {
      forbidden.push(pathname);
      return route.fulfill({ status: 500, json: { detail: "Forbidden in guided workflow test" } });
    }
    if (pathname === "/dashboard/summary") return route.fulfill({ json: emptySummary() });
    if (pathname === "/profile/summary") {
      return route.fulfill({
        json: {
          has_approved_profile: !onboardingReview,
          approved_user_profile: onboardingReview ? null : { snapshot_type: "user_profile", id: 1, external_id: "profile-1", status: "approved", created_at: "2026-07-03T08:00:00Z" },
          candidate_user_profiles: onboardingReview ? [{ snapshot_type: "user_profile", id: 11, external_id: "profile-review", status: "candidate", created_at: "2026-07-03T08:00:00Z" }] : [],
          approved_master_cv_profile: onboardingReview ? null : { snapshot_type: "master_cv_profile", id: 2, external_id: "cv-1", status: "approved", created_at: "2026-07-03T08:00:00Z" },
          approved_policy: onboardingReview ? null : { snapshot_type: "policy", id: 3, external_id: "policy-1", status: "approved", created_at: "2026-07-03T08:00:00Z" },
        },
      });
    }
    if (pathname === "/email-delivery/settings") {
      return route.fulfill({ json: { sending_enabled: false, provider: "gmail_sandbox", allow_real_recipients: false, sandbox_recipient: null, gmail_configured: false, mode: "disabled" } });
    }
    if (pathname === "/companies") return route.fulfill({ json: withCompanies ? [company] : [] });
    if (pathname === "/fit-evaluations") return route.fulfill({ json: withCompanies ? [fit] : [] });
    if (["/contacts", "/email-drafts", "/outbox/drafts", "/outbox/sent", "/send-intents", "/gate-results", "/outreach-records", "/sent-messages"].includes(pathname)) {
      return route.fulfill({ json: [] });
    }
    if (pathname.includes("/onboarding/chat/") && pathname.endsWith("/status")) return route.fulfill({ json: { status: "closed", entries: [] } });
    if (pathname.includes("/onboarding/chat/") && pathname.endsWith("/artifacts")) return route.fulfill({ json: { artifacts: onboardingReview ? onboardingArtifacts() : [] } });
    if (pathname.includes("/onboarding/chat/") && pathname.includes("/artifacts/")) {
      const filename = decodeURIComponent(pathname.split("/").at(-1));
      return route.fulfill({ json: { filename, exists: true, json_content: filename === "onboarding_review.json" ? { run_id: "onboarding-review", items: [{ item_id: "missing-phone", item_type: "missing_information", summary: "Phone number will be added later." }] } : { schema_version: "1.0", prepared_for_review: true } } });
    }
    if (pathname.includes("/onboarding/chat/") && pathname.endsWith("/input-files")) return route.fulfill({ json: { files: [] } });
    if (pathname.includes("/onboarding/runs/") && pathname.endsWith("/snapshots")) return route.fulfill({ json: [] });
    if (pathname.includes("/onboarding/runs/") && pathname.endsWith("/promote") && request.method() === "POST") {
      promotionCalls += 1;
      return route.fulfill({ json: { run_id: "onboarding-review", status: "approved", promoted: [], issues: [] } });
    }
    if (pathname === "/campaigns/company-research" && request.method() === "POST") {
      if (failLaunch) return route.fulfill({ status: 409, json: { detail: "approved profile required" } });
      return route.fulfill({ json: { run_id: "research-safe-1", status: "prepared", run_path: "", input_path: "", output_path: "", prompt_path: "", import_endpoint: "", expected_output_files: [], next_action: "" } });
    }
    if (pathname === "/campaigns/company-research/research-safe-1/launch") {
      launchCalls += 1;
      return route.fulfill({ json: { run_id: "research-safe-1", status: "running", runtime: "pi_rpc", command: [], workdir: "", status_endpoint: "/campaigns/company-research/research-safe-1/status" } });
    }
    if (pathname === "/campaigns/company-research/research-safe-1/status") return route.fulfill({ json: researchStatus(activeResearch) });
    if (pathname === "/campaigns/company-research/research-safe-1/import") return route.fulfill({ json: { run_id: "research-safe-1", import_result: {}, status: researchStatus(false) } });
    return route.continue();
  });
  return { forbidden, launchCalls: () => launchCalls, promotionCalls: () => promotionCalls };
}

function onboardingArtifacts() {
  return [
    ["user_profile.json", "user_profile"],
    ["master_cv_profile.json", "master_cv_profile"],
    ["policy.json", "policy"],
    ["onboarding_review.json", null],
  ].map(([filename, snapshotType], index) => ({
    filename, exists: true, status: "ready_for_review", review_state: snapshotType ? "candidate" : "review_items_available",
    error_count: 0, errors: [], reason_codes: [], snapshot_type: snapshotType,
    snapshot_id: snapshotType ? index + 11 : null, snapshot_status: snapshotType ? "candidate" : null,
  }));
}

function emptySummary() {
  return {
    runs: 0,
    companies: 0,
    contacts: 0,
    fit_evaluations: 0,
    email_drafts: 0,
    send_intents: 0,
    gate_results: 0,
    outreach_records: 0,
    send_approval_snapshots: 0,
    sent_messages: 0,
    send_intents_by_status: {},
    gate_results_by_status: {},
    outreach_records_by_status: {},
  };
}

function researchStatus(active) {
  return {
    run_id: "research-safe-1",
    runtime: "pi_rpc",
    status: active ? "running" : "imported",
    state: { target_company_count: 30 },
    artifact_counts: { companies: active ? 18 : 30, fit_evaluations: active ? 8 : 30 },
    validation: {},
    import_state: { run_status: active ? "research_running" : "imported" },
    logs: [],
  };
}

test("guided research brief launches safely and restores progress", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const api = await mockApi(page, { withCompanies: false, activeResearch: true });
  await page.goto(`${baseURL}/dashboard`);
  await expect(page.getByRole("heading", { name: "Ready to discover companies." })).toBeVisible();
  await page.screenshot({ path: "artifacts/screenshots/home-start-company-search.png", fullPage: true });

  await page.getByRole("button", { name: "Start company search" }).first().click();
  await expect(page.getByRole("heading", { name: "Where should your recruiter look?" })).toBeVisible();
  await page.screenshot({ path: "artifacts/screenshots/research-step-1.png", fullPage: true });

  await page.locator("#briefLocations").fill("");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Add at least one location.")).toBeVisible();
  await page.locator("#briefLocations").fill("Zurich, Switzerland");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "What kind of work should we prioritize?" })).toBeVisible();
  await page.getByRole("button", { name: "Back" }).click();
  await expect(page.locator("#briefLocations")).toHaveValue("Zurich, Switzerland");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "What kinds of companies should stand out?" })).toBeVisible();
  await page.screenshot({ path: "artifacts/screenshots/research-step-3.png", fullPage: true });

  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Review brief" }).click();
  await expect(page.getByRole("heading", { name: "Review the recruiter brief." })).toBeVisible();
  await page.screenshot({ path: "artifacts/screenshots/research-brief-review.png", fullPage: true });

  await page.getByRole("button", { name: "Start company search" }).click();
  await page.getByRole("button", { name: "Start company search" }).last().dblclick();
  await expect(page.getByRole("heading", { name: /Your recruiter is searching/ })).toBeVisible();
  expect(api.launchCalls()).toBe(1);
  await page.reload();
  await expect(page.getByText("18 of at least 30 companies found so far.")).toBeVisible();
  await page.screenshot({ path: "artifacts/screenshots/research-running.png", fullPage: true });
  expect(api.forbidden).toEqual([]);
});

test("guided company review handles save, rejection, empty and partial data", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  const api = await mockApi(page, { withCompanies: true });
  await page.goto(`${baseURL}/dashboard#companies/review`);
  await expect(page.getByRole("heading", { name: "LatticeFlow", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "artifacts/screenshots/first-company-review.png", fullPage: true });
  await page.getByRole("button", { name: "Save company" }).click();
  await expect(page.getByRole("heading", { name: "All current matches have been reviewed." })).toBeVisible();

  await page.evaluate(() => localStorage.removeItem("guidedCompanyDecisions"));
  await page.reload();
  await page.locator("#rejectReason").selectOption("Wrong location");
  await page.getByRole("button", { name: "Not for me" }).click();
  await expect(page.getByText("All current matches have been reviewed.")).toBeVisible();
  expect(api.forbidden).toEqual([]);
});

test("mobile guided screens have no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page, { withCompanies: true });
  await page.goto(`${baseURL}/dashboard#companies/brief`);
  await expect(page.getByRole("heading", { name: "Where should your recruiter look?" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "artifacts/screenshots/mobile-research-step.png", fullPage: true });

  await page.goto(`${baseURL}/dashboard#companies/review`);
  await expect(page.getByRole("heading", { name: "LatticeFlow", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "artifacts/screenshots/mobile-company-review.png", fullPage: true });
});

test("failed launch is understandable", async ({ page }) => {
  await mockApi(page, { failLaunch: true });
  await page.goto(`${baseURL}/dashboard#companies/brief`);
  for (const name of ["Continue", "Continue", "Continue", "Review brief"]) {
    await page.getByRole("button", { name }).click();
  }
  await page.getByRole("button", { name: "Start company search" }).click();
  await page.getByRole("button", { name: "Start company search" }).last().click();
  await expect(page.getByText("Approve your profile before starting company search.")).toBeVisible();
});

test("onboarding review is visible and approval requires confirmation", async ({ page }) => {
  const state = await mockApi(page, { onboardingReview: true });
  await page.goto(`${baseURL}/dashboard#/profile`);

  await expect(page.getByRole("heading", { name: "Review what your recruiter prepared" })).toBeVisible();
  await expect(page.getByText("Ready for your review", { exact: true })).toBeVisible();
  await expect(page.getByText("Phone number will be added later.")).toBeVisible();

  const approve = page.getByRole("button", { name: "Approve my profile" });
  await expect(approve).toBeDisabled();
  await page.getByLabel("I reviewed the prepared profile, CV claims, policy, and open questions.").check();
  await expect(approve).toBeEnabled();
  await approve.click();
  await expect.poll(() => state.promotionCalls()).toBe(1);
  await expect(page.getByText("Approved. Your profile is now the source of truth for your recruiter team.")).toBeVisible();
});
