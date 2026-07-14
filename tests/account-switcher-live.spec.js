import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";

const baseURL = process.env.LIVE_APP_URL;

test("local account chooser switches workspaces and can return", async ({ page }) => {
  test.skip(!baseURL, "Set LIVE_APP_URL to validate a running app with real data.");
  mkdirSync("artifacts/screenshots", { recursive: true });
  const browserErrors = [];
  const serverErrors = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("console", (message) => message.type() === "error" && browserErrors.push(message.text()));
  page.on("response", (response) => response.status() >= 500 && serverErrors.push(`${response.status()} ${response.url()}`));

  await page.setViewportSize({ width: 1600, height: 950 });
  await page.goto(`${baseURL}/register`, { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "Who is continuing?" })).toBeVisible();
  const accounts = page.getByLabel("Available local accounts").locator("button");
  test.skip(await accounts.count() < 2, "At least two local accounts are needed to exercise switching.");

  await page.screenshot({ path: "artifacts/screenshots/local-account-chooser.png", fullPage: true });

  const firstName = (await accounts.first().locator("strong").textContent()) || "";
  await accounts.first().click();
  await page.waitForURL(/\/dashboard/);
  await expect(page.locator(".account-summary strong")).toHaveText(firstName.split(" ")[0]);

  await page.goto(`${baseURL}/register`, { waitUntil: "networkidle" });
  const refreshedAccounts = page.getByLabel("Available local accounts").locator("button");
  await expect(refreshedAccounts.filter({ hasText: firstName })).toContainText("Current");
  const target = refreshedAccounts.filter({ hasNotText: "Current" }).first();
  const targetName = (await target.locator("strong").textContent()) || "";
  await target.click();
  await page.waitForURL(/\/dashboard/);
  await expect(page.locator(".account-summary strong")).toHaveText(targetName.split(" ")[0]);

  await page.goto(`${baseURL}/register`, { waitUntil: "networkidle" });
  const original = page.getByLabel("Available local accounts").locator("button").filter({ hasText: firstName });
  await original.click();
  await page.waitForURL(/\/dashboard/);
  await expect(page.locator(".account-summary strong")).toHaveText(firstName.split(" ")[0]);

  expect(serverErrors).toEqual([]);
  expect(browserErrors).toEqual([]);
});
