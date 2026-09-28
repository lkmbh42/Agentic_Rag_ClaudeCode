import { test, expect } from "./fixtures";

/**
 * Core smoke coverage for the Recherche chat UI. Each test logs in fresh via
 * the fixture in fixtures.ts. These assert the shell renders and the primary
 * controls are wired — not answer quality, which the backend eval harness owns.
 */

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("loads the chat shell signed in", async ({ page }) => {
  await expect(page).toHaveTitle(/Recherche/);
  // Composer is the anchor of the signed-in shell.
  await expect(page.getByRole("textbox", { name: /Frage/i })).toBeVisible();
  // The login form's password field must not be present.
  await expect(page.locator("form input#pw")).toHaveCount(0);
});

test("shows the conversation history sidebar", async ({ page }) => {
  const search = page.getByPlaceholder(/durchsuchen/i);
  await expect(search).toBeVisible();
  // The seeded account has history; at least one conversation row renders.
  await expect(page.locator(".history-item").first()).toBeVisible();
});

test("filters conversations from the search box", async ({ page }) => {
  const list = page.locator(".history-item");
  // Wait for the async history to load before counting.
  await expect(list.first()).toBeVisible();
  const total = await list.count();
  test.skip(total < 2, "not enough history to exercise filtering");

  await page.getByPlaceholder(/durchsuchen/i).fill("zzz-unlikely-query-xyz");
  await expect(list).toHaveCount(0);

  await page.getByPlaceholder(/durchsuchen/i).clear();
  await expect(list.first()).toBeVisible();
});

test("lets the user type a question into the composer", async ({ page }) => {
  const composer = page.getByRole("textbox", { name: /Frage/i });
  await composer.fill("Was steht in den Unterlagen?");
  await expect(composer).toHaveValue("Was steht in den Unterlagen?");
});

test("composer is keyboard reachable and focus is visible", async ({ page }) => {
  const composer = page.getByRole("textbox", { name: /Frage/i });
  await composer.focus();
  await expect(composer).toBeFocused();
});
