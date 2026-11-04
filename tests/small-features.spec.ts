import { expect, test, type Page } from '@playwright/test';
import { boot, closeAll, watch } from './helpers';

const openFromStart = async (page: Page, name: string) => {
  await page.locator('.dock-orb').click();
  await page.locator('.start-menu .sm-app', { hasText: name }).first().click();
};

test('themes set wallpaper + window colour and ring the active tile', async ({ page }) => {
  const errors = watch(page);
  await boot(page);
  await closeAll(page);
  await page.locator('.dock-item[data-label="Settings"]').click();
  await expect(page.locator('.win[data-app=settings] .set-link').first()).toContainText('Themes');
  await expect(page.locator('.set-theme')).toHaveCount(4);
  await expect(page.locator('.set-theme.sel')).toHaveAttribute('data-theme', 'mwx7');
  await page.locator('.set-theme[data-theme="dusk"]').click();
  await expect(page.locator('.set-theme.sel')).toHaveAttribute('data-theme', 'dusk');
  await expect(page.locator('.set-theme.sel')).toHaveCount(1);
  // Changing the window colour by hand leaves no theme active.
  await page.locator('.set-swatch').first().click();
  await expect(page.locator('.set-theme.sel')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('recently opened files appear in the dock jump list and reopen', async ({ page }) => {
  const errors = watch(page);
  await boot(page);
  await closeAll(page);
  const dock = page.locator('.dock-item[data-label="Notepad"]');
  await dock.click({ button: 'right' });
  await expect(page.locator('.menu-item', { hasText: 'Recent' })).toHaveCount(0);
  await page.mouse.click(900, 600); // close the menu
  await page.mouse.click(900, 600, { button: 'right' });
  await page.locator('.menu-item', { hasText: 'New Text Document' }).click();
  await page.locator('.desk-icon', { hasText: 'New Text Document' }).dblclick();
  await expect(page.locator('.win[data-app=notepad]')).toHaveCount(1);
  await closeAll(page);
  await dock.click({ button: 'right' });
  const recent = page.locator('.menu-item', { hasText: 'New Text Document' });
  await expect(recent).toHaveCount(1);
  await recent.click();
  await expect(page.locator('.win[data-app=notepad]')).toHaveCount(1);
  expect(errors).toEqual([]);
});

test('Snipping Tool opens and New shows the selection overlay', async ({ page }) => {
  const errors = watch(page);
  await boot(page);
  await closeAll(page);
  await openFromStart(page, 'Snipping Tool');
  await expect(page.locator('.win[data-app=snip] .snip-new')).toBeVisible();
  await page.locator('.win[data-app=snip] .snip-new').click();
  await expect(page.locator('.snip-overlay')).toBeVisible();
  await page.locator('.snip-overlay').click({ button: 'right' }); // cancel
  await expect(page.locator('.snip-overlay')).toHaveCount(0);
  expect(errors).toEqual([]);
});
