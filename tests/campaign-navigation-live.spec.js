import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";

const baseURL = process.env.LIVE_APP_URL;

test("campaign workspaces stay separate and can be scoped", async ({ page }) => {
  test.skip(!baseURL, "Set LIVE_APP_URL to validate a running app with real data.");
  mkdirSync("artifacts/screenshots", { recursive: true });
  const browserErrors = [];
  const serverErrors = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("console", (message) => message.type() === "error" && browserErrors.push(message.text()));
  page.on("response", (response) => response.status() >= 500 && serverErrors.push(`${response.status()} ${response.url()}`));

  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto(`${baseURL}/dashboard#/companies`, { waitUntil: "networkidle" });

  await expect(page.getByRole("heading", { name: "Companies your team is moving forward" })).toBeVisible();
  await expect(page.getByLabel("Opportunity type").getByText("Company outreach", { exact: true })).toBeVisible();
  const companyCampaignOptions = page.getByLabel("Campaign", { exact: true }).locator("option:not([value='all'])");
  if (await companyCampaignOptions.count()) await expect(page.getByLabel("Campaign", { exact: true })).not.toHaveValue("all");
  else await expect(page.getByLabel("Campaign", { exact: true })).toHaveValue("all");
  await expect(page.locator(".company-card").first()).toBeVisible();
  await page.screenshot({ path: "artifacts/screenshots/company-campaign-switcher.png", fullPage: true });
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page.locator(".campaign-workspace")).toBeVisible();
  await page.screenshot({ path: "artifacts/screenshots/company-campaign-switcher-laptop.png", fullPage: true });
  await page.setViewportSize({ width: 1600, height: 1000 });

  await page.getByLabel("Campaign", { exact: true }).selectOption("all");
  await expect(page).toHaveURL(/campaign=all/);
  await expect(page.locator(".campaign-scope-summary > small")).toContainText(/Across|Workspace history/);

  await page.getByLabel("Opportunity type").getByText("Open positions", { exact: true }).click();
  await expect(page).toHaveURL(/#\/jobs$/);
  await expect(page.getByRole("heading", { name: "Open positions" })).toBeVisible();
  const jobCampaignOptions = page.getByLabel("Campaign", { exact: true }).locator("option:not([value='all'])");
  if (await jobCampaignOptions.count()) await expect(page.getByLabel("Campaign", { exact: true })).not.toHaveValue("all");
  else await expect(page.getByLabel("Campaign", { exact: true })).toHaveValue("all");
  await page.screenshot({ path: "artifacts/screenshots/job-campaign-switcher.png", fullPage: true });

  expect(serverErrors).toEqual([]);
  expect(browserErrors).toEqual([]);
});
