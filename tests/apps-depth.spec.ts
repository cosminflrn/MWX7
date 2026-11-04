import { expect, test } from '@playwright/test';
import { boot, closeAll, watch } from './helpers';

const openApp = async (page: import('@playwright/test').Page, label: string, app: string) => {
  await page.locator(`.dock-item[data-label="${label}"]`).click();
  const win = page.locator(`.win[data-app=${app}]`);
  await expect(win).toBeVisible();
  await page.waitForTimeout(700);
  return win;
};

test('My Computer: drag to sidebar, rectangle select, cut/paste, Properties', async ({ page }) => {
  const errors = watch(page);
  await boot(page);
  await closeAll(page);
  const win = await openApp(page, 'My Computer', 'explorer');
  await win.locator('[data-nav="/Music"]').click();
  const items = win.locator('.ex-scroll [data-path]');
  await expect(items.first()).toBeVisible();
  const total = await items.count();
  expect(total).toBeGreaterThan(4);

  // drag one file onto the Documents sidebar entry
  const first = items.first();
  const name = await first.getAttribute('data-path');
  await first.dragTo(win.locator('[data-nav="/Documents"]'));
  await expect(win.locator(`.ex-scroll [data-path="${name}"]`)).toHaveCount(0);
  await win.locator('[data-nav="/Documents"]').click();
  await expect(win.locator('.ex-scroll [data-path^="/Documents/Goldberg"]').first()).toBeVisible();

  // rectangle select in Music, then Cut + Paste into Pictures via the toolbar
  await win.locator('[data-nav="/Music"]').click();
  const box = await win.locator('.ex-scroll').boundingBox();
  await page.mouse.move(box!.x + box!.width - 30, box!.y + box!.height - 8);
  await page.mouse.down();
  await page.mouse.move(box!.x + 4, box!.y + 4, { steps: 8 });
  await page.mouse.up();
  const selected = await win.locator('.ex-scroll .selected').count();
  expect(selected).toBeGreaterThan(1);
  await win.locator('.ex-btn', { hasText: 'Cut' }).click();
  await win.locator('[data-nav="/Pictures"]').click();
  await win.locator('.ex-btn', { hasText: 'Paste' }).click();
  await expect(win.locator('.ex-scroll [data-path^="/Pictures/Goldberg"]').first()).toBeVisible();
  await win.locator('[data-nav="/Music"]').click();
  await expect(win.locator('.ex-scroll [data-path]')).toHaveCount(total - 1 - selected);
  await win.locator('[data-nav="/Pictures"]').click();
  // click on empty space clears the selection
  await page.mouse.click(box!.x + box!.width - 20, box!.y + box!.height - 10);
  await expect(win.locator('.ex-scroll .selected')).toHaveCount(0);

  // Properties dialog
  await win.locator('.ex-scroll [data-path]').first().click({ button: 'right' });
  await page.locator('.menu-pop >> text=Properties').click();
  const dlg = win.locator('.ex-pdlg');
  await expect(dlg).toBeVisible();
  for (const k of ['Type', 'Location', 'Size', 'Created', 'Modified']) await expect(dlg.locator('dt', { hasText: k })).toBeVisible();
  await dlg.locator('.ex-pdlg-ok').click();
  await win.locator('[data-nav="/Desktop"]').click();
  await win.locator('.ex-btn', { hasText: 'Properties' }).click();
  await expect(win.locator('.ex-pdlg dt', { hasText: 'Contains' })).toBeVisible();
  expect(errors).toEqual([]);
});

test('Internet: favorites, history page, blocked-page panel', async ({ page }) => {
  const errors = watch(page);
  await boot(page);
  await closeAll(page);
  const win = await openApp(page, 'Internet', 'browser');
  const addr = win.locator('.br-address');
  await addr.fill('https://github.com/');
  await addr.press('Enter');
  // blocked hosts are recognised at once, with a favicon/title and the big button
  await expect(win.locator('.br-blocked')).toBeVisible({ timeout: 2000 });
  await expect(win.locator('.br-blocked-site')).toHaveText('github.com');
  await expect(win.locator('.br-big', { hasText: 'Open in a new tab' })).toBeVisible();
  // favorite it
  await win.locator('.br-star').click();
  await expect(win.locator('.br-favbar .br-fav')).toHaveCount(1);
  await expect(win.locator('.br-star')).toHaveClass(/on/);
  await win.locator('.br-home, .br-tool[title=Home]').first().click();
  await expect(win.locator('.br-start')).toBeVisible();
  await win.locator('.br-fav').click();
  await expect(win.locator('.br-blocked')).toBeVisible();
  // history page lists it, clickable
  await win.locator('.br-histbtn').click();
  const row = win.locator('.br-hist-row', { hasText: 'github.com' }).first();
  await expect(row).toBeVisible();
  await row.click();
  await expect(win.locator('.br-blocked')).toBeVisible();
  expect(errors).toEqual([]);
});

test('Media Player: 8+ tracks with art, dock mini player menu', async ({ page }) => {
  const errors = watch(page);
  await boot(page);
  await closeAll(page);
  const win = await openApp(page, 'Media Player', 'mediaplayer');
  await expect(win.locator('.mp-item')).toHaveCount(8);
  await expect(win.locator('.mp-item .mp-art')).toHaveCount(8);
  const dock = page.locator('.dock-item[data-label="Media Player"]');
  await win.locator('.mp-item').nth(1).click();
  await expect(win.locator('.mp-title')).toContainText('Variatio 2');
  await dock.click({ button: 'right' });
  const menu = page.locator('.menu-pop');
  await expect(menu.getByText('Goldberg Variations: Variatio 2', { exact: true })).toBeVisible();
  await menu.getByText('Next', { exact: true }).click();
  await expect(win.locator('.mp-title')).toContainText('Variatio 4');
  await dock.click({ button: 'right' });
  await page.locator('.menu-pop').getByText('Previous', { exact: true }).click();
  await expect(win.locator('.mp-title')).toContainText('Variatio 2');
  await dock.click({ button: 'right' });
  await page.locator('.menu-pop').getByText('Pause', { exact: true }).click();
  await dock.click({ button: 'right' });
  await expect(page.locator('.menu-pop').getByText('Play', { exact: true })).toBeVisible();
  expect(errors.filter((e) => !/play\(\)|NotAllowed|media/i.test(e))).toEqual([]);
});
