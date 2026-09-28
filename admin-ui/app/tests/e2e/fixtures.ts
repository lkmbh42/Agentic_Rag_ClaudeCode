import { test as base, expect } from "@playwright/test";

/**
 * Auth fixture for the Recherche UI.
 *
 * The usual Playwright storageState pattern does NOT work here: refresh tokens
 * are single-use (rotated and revoked on every /auth/refresh), so a saved
 * refresh cookie is spent by the first page load and every later test would
 * replay a revoked cookie. Instead each test logs in fresh — one login issues
 * one coherent session — via the API before the page loads. The httpOnly
 * refresh cookie lands in the browser context's cookie jar, so the app's own
 * restore-on-load flow picks it up exactly as in production.
 *
 * Credentials come from the dev seed (app/seed.py); override with
 * E2E_EMAIL / E2E_PASSWORD.
 */

const EMAIL = process.env.E2E_EMAIL ?? "admin@example.com";
const PASSWORD = process.env.E2E_PASSWORD ?? "admin-pass-123";

export const test = base.extend({
  page: async ({ page }, use) => {
    const res = await page.context().request.post("/api/auth/login", {
      data: { email: EMAIL, password: PASSWORD },
    });
    expect(res.ok(), `login failed: ${res.status()}`).toBeTruthy();
    await use(page);
  },
});

export { expect };
