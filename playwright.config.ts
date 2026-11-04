import { defineConfig } from '@playwright/test';

// PW_PORT lets parallel worktrees run the suite side by side.
const PORT = process.env.PW_PORT ?? '4173';

/** End-to-end checks of the whole OS. Run with `npm test` (builds, serves dist/, drives Chromium). */
export default defineConfig({
  testDir: 'tests',
  timeout: 90_000,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? 'github' : 'list',
  use: { baseURL: `http://localhost:${PORT}/`, viewport: { width: 1440, height: 900 } },
  webServer: { command: `npx vite preview --port ${PORT} --strictPort`, url: `http://localhost:${PORT}/`, reuseExistingServer: !process.env.CI },
});
