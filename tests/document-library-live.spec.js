import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";

const baseURL = process.env.LIVE_APP_URL;
const fictionalCandidateName = "Alex Morgan";
const fictionalCompanyName = "Northstar Labs";

test("restored documents are searchable, filterable, and previewable", async ({ page }) => {
  test.skip(!baseURL, "Set LIVE_APP_URL to validate a running app with seeded fictional data.");
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
  await expect(page.getByText(/251 files/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Tailored CVs 124" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Emails 124" })).toBeVisible();
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

  await page.getByRole("link", { name: /Companies/ }).click();
  const companyCard = page.locator(".company-card").filter({ hasText: fictionalCompanyName });
  await expect(companyCard).toBeVisible();
  await companyCard.click();
  await page.getByRole("link", { name: "View documents" }).click();
  await expect(page).toHaveURL(/#\/documents\?company=[^&]+&companyName=Northstar(?:\+|%20)Labs/);
  await expect(page.getByRole("heading", { name: `Documents prepared for ${fictionalCompanyName}` })).toBeVisible();
  await expect(page.locator(".document-card")).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Tailored CVs 1" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Emails 1" })).toBeVisible();
  await page.screenshot({ path: "artifacts/screenshots/company-scoped-documents.png", fullPage: true });
  await page.getByRole("button", { name: `${fictionalCompanyName} — Tailored CV` }).click();
  await expect(page.locator(".document-modal iframe")).toBeVisible();
  await expect(page.getByRole("link", { name: /Open PDF/ })).toBeVisible();
  await expect(page.frameLocator(".document-modal iframe").locator("body")).toContainText(fictionalCandidateName);
  await page.screenshot({ path: "artifacts/screenshots/company-scoped-cv-preview.png", fullPage: true });

  expect(serverErrors).toEqual([]);
  expect(browserErrors).toEqual([]);
});
