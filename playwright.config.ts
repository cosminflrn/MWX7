import { defineConfig } from '@playwright/test';

/** End-to-end checks of the whole OS. Run with `npm test` (builds, serves dist/, drives Chromium). */
export default defineConfig({
  testDir: 'tests',
  timeout: 90_000,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? 'github' : 'list',
  use: { baseURL: 'http://localhost:4173/', viewport: { width: 1440, height: 900 } },
  webServer: { command: 'npx vite preview --port 4173 --strictPort', url: 'http://localhost:4173/', reuseExistingServer: !process.env.CI },
});
