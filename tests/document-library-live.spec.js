import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";

const baseURL = process.env.LIVE_APP_URL;

test("restored documents are searchable, filterable, and previewable", async ({ page }) => {
  test.skip(!baseURL, "Set LIVE_APP_URL to validate a running app with real data.");
  mkdirSync("artifacts/screenshots", { recursive: true });
  const browserErrors = [];
  const serverErrors = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("console", (message) => message.type() === "error" && browserErrors.push(message.text()));
  page.on("response", (response) => response.status() >= 500 && serverErrors.push(`${response.status()} ${response.url()}`));

  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto(`${baseURL}/dashboard`, { waitUntil: "networkidle" });
  await page.getByRole("link", { name: /Documents/ }).click();
  await expect(page.getByRole("heading", { name: "Every document, ready when you need it" })).toBeVisible();
  await expect(page.locator(".document-card")).toHaveCount(24);
  await expect(page.getByText(/130 files/)).toBeVisible();
  await page.screenshot({ path: "artifacts/screenshots/document-library-restored.png", fullPage: true });

  await page.getByRole("button", { name: "My profile" }).click();
  await expect(page.locator(".document-card")).toHaveCount(3);
  await expect(page.getByRole("heading", { name: "Career profile" })).toBeVisible();
  await page.getByRole("button", { name: /Career profile/ }).click();
  await expect(page.locator(".document-modal iframe")).toBeVisible();
  await expect(page.frameLocator(".document-modal iframe").locator("body")).not.toBeEmpty();
  await page.screenshot({ path: "artifacts/screenshots/document-profile-preview.png", fullPage: true });
  await page.locator(".document-modal header button").click();

  await page.getByRole("button", { name: "Emails" }).click();
  await expect(page.locator(".document-card")).toHaveCount(24);
  await page.getByPlaceholder("Find a company or document").fill("this-will-not-match-any-document");
  await expect(page.getByRole("heading", { name: "No matching documents" })).toBeVisible();
  await page.getByPlaceholder("Find a company or document").fill("");
  await expect(page.locator(".document-card")).toHaveCount(24);
  await page.locator(".document-card").first().click();
  await expect(page.locator(".document-modal iframe")).toBeVisible();
  await expect(page.frameLocator(".document-modal iframe").locator("main")).toBeVisible();
  await page.screenshot({ path: "artifacts/screenshots/document-email-preview.png", fullPage: true });
  await page.locator(".document-modal header button").click();

  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Gmail connection needs configuration" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Connect Gmail" })).toBeDisabled();

  expect(serverErrors).toEqual([]);
  expect(browserErrors).toEqual([]);
});
