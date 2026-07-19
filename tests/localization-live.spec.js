import { expect, test } from "@playwright/test";

test("workspace language persists and switches the visible product copy", async ({ page }) => {
  const baseURL = process.env.PW_BASE_URL || String(test.info().project.use.baseURL);
  const email = `localization-${Date.now()}@example.com`;
  const registration = await page.context().request.post(`${baseURL}/auth/local/register`, {
    data: {
      display_name: "Localization Check",
      email,
      locale: "de-DE",
    },
  });
  expect(registration.status()).toBe(201);
  const initialMe = await page.context().request.get(`${baseURL}/me`);
  expect((await initialMe.json()).workspace.locale).toBe("de-DE");

  await page.goto(`${baseURL}/dashboard#/settings`);
  await expect(page.getByRole("heading", { name: "Einfache Einstellungen für die Arbeit deines Recruiters" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "de-DE");

  await page.getByRole("button", { name: "Englisch" }).click();
  await expect(page.getByRole("heading", { name: "Simple controls for how your recruiter works" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");

  await page.reload();
  await expect(page.getByRole("heading", { name: "Simple controls for how your recruiter works" })).toBeVisible();
  const me = await page.context().request.get(`${baseURL}/me`);
  expect((await me.json()).workspace.locale).toBe("en");
});
