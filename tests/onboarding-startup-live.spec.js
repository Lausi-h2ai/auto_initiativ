import { expect, test } from "@playwright/test";

const baseURL = process.env.PW_BASE_URL || "http://127.0.0.1:8000";
const smokeEmail = process.env.ONBOARDING_SMOKE_EMAIL || "onboarding-smoke@example.com";

test.skip(
  process.env.RUN_LIVE_ONBOARDING_SMOKE !== "1",
  "Set RUN_LIVE_ONBOARDING_SMOKE=1 to run against the real local Pi RPC runtime.",
);

test("new onboarding starts with an actual recruiter greeting", async ({ page }) => {
  test.setTimeout(180_000);
  const api = page.context().request;
  const registration = await api.post(`${baseURL}/auth/local/register`, {
    data: { display_name: "Onboarding Smoke", email: smokeEmail },
  });
  expect(registration.status()).toBe(201);

  const meResponse = await api.get(`${baseURL}/me`);
  expect(meResponse.ok()).toBeTruthy();
  const me = await meResponse.json();
  const runId = `onboarding-${me.workspace.id}`.replace(/[^a-zA-Z0-9_-]/g, "-");

  await api.post(`${baseURL}/onboarding/chat/${runId}/reset`);
  try {
    await page.goto(`${baseURL}/dashboard#/profile`);
    await expect(page.getByRole("button", { name: "Begin conversation" })).toBeVisible();

    const startResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith(`/onboarding/chat/${runId}/start`),
      { timeout: 120_000 },
    );
    await page.getByRole("button", { name: "Begin conversation" }).click();
    const startResponse = await startResponsePromise;
    const responseText = await startResponse.text();
    expect(startResponse.ok(), responseText).toBeTruthy();

    const payload = JSON.parse(responseText);
    expect(payload.session_state.runtime.runtime).toBe("pi_rpc");
    expect(payload.session_state.runtime.command).toContain("gpt-5.6-sol");
    const greeting = payload.entries.find(
      (entry) => entry.role === "assistant" && entry.content.trim().length > 0,
    );
    expect(greeting).toBeTruthy();
    expect(greeting.content.trim().length).toBeGreaterThan(20);
    await expect(page.locator(".chat-message.agent p").first()).toContainText(greeting.content);
  } finally {
    await api.post(`${baseURL}/onboarding/chat/${runId}/reset`);
  }
});
