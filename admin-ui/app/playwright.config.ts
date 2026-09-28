import { defineConfig, devices } from "@playwright/test";

/**
 * E2E config for the Recherche admin UI.
 *
 * Tests run against the already-running admin-ui container at :8080 (the stable
 * target — the :5173 Vite dev server is a fragile Windows process). Bring the
 * dev stack up first:  docker compose -f docker-compose.dev.yml up -d
 *
 * Only Chromium is exercised: it is the sole browser whose binaries are
 * installed on this machine, and the app targets evergreen Chromium anyway.
 *
 * Auth: refresh tokens are single-use (rotated + revoked on every refresh), so
 * a saved storageState cookie can't be replayed across tests. Instead each
 * spec logs in fresh through the `test` fixture in fixtures.ts.
 */

const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:8080";

export default defineConfig({
  testDir: "./tests/e2e",
  // Safe to parallelize: each test logs in fresh in its own browser context
  // (see fixtures.ts), and login does not bump session_epoch, so concurrent
  // sessions for the seed user are independent and don't revoke each other.
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",

  use: {
    baseURL: BASE_URL,
    locale: "de-DE",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
