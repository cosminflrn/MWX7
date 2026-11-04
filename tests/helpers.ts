import { expect, type Page } from '@playwright/test';

/** Collects page errors, console errors and any native browser dialog (the OS must never use one). */
export function watch(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => m.type() === 'error' && errors.push(`console: ${m.text()}`));
  page.on('dialog', (d) => {
    errors.push(`native dialog: ${d.message()}`);
    void d.dismiss();
  });
  return errors;
}

/** Power switch → BIOS → setup → logon → desktop, the way a person does it. */
export async function boot(page: Page, name = 'Tester'): Promise<void> {
  await page.goto('/');
  await page.locator('.power-btn').click({ force: true });
  for (let i = 0; i < 60 && !(await page.locator('.oobe-input').count()); i++) {
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
  }
  await page.locator('.oobe-input').fill(name);
  await page.locator('.avatar-opt').nth(2).click();
  await page.locator('.oobe-next').click();
  await page.locator('.logon-tile').click();
  await expect(page.locator('#dock .dock-shelf')).toBeVisible();
  await page.waitForTimeout(2500);
}

export async function closeAll(page: Page): Promise<void> {
  await page.evaluate(() => document.querySelectorAll<HTMLElement>('#windows > .win .wc-close').forEach((b) => b.click()));
  await page.waitForTimeout(500); // close animation
}
