import { expect, test, type Page } from '@playwright/test';
import { boot, closeAll, watch } from './helpers';

const openFromStart = async (page: Page, name: string) => {
  await page.locator('.dock-orb').click();
  await page.locator('.start-menu .sm-app', { hasText: name }).first().click();
};

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

test('Snipping Tool window mode outlines the window under the pointer', async ({ page }) => {
  const errors = watch(page);
  await boot(page);
  await closeAll(page);
  await openFromStart(page, 'Snipping Tool');
  const w = page.locator('#windows > .win[data-app=snip]');
  await w.locator('.snip-mode').click();
  await page.locator('.menu-item', { hasText: 'Window Snip' }).click();
  await expect(page.locator('.snip-overlay.snip-window')).toBeVisible();
  // The window may still be animating open: wait until it has no running animation, then compare against its
  // live box on every poll (a box measured mid-animation made the outline never match).
  await expect.poll(() => w.evaluate((el) => el.getAnimations().length)).toBe(0);
  let nudge = 0;
  await expect.poll(async () => {
    const b = await w.boundingBox();
    if (!b) return Infinity;
    await page.mouse.move(b.x + b.width / 2 + (nudge++ % 2), b.y + b.height / 2);
    const sel = await page.locator('.snip-sel').boundingBox();
    return sel ? Math.max(Math.abs(sel.width - b.width), Math.abs(sel.height - b.height)) : Infinity;
  }, { timeout: 5000 }).toBeLessThan(2);
  await page.mouse.click(5, 5, { button: 'right' });
  await expect(page.locator('.snip-overlay')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('Media Player playlist titles are distinct and readable', async ({ page }) => {
  await boot(page);
  await closeAll(page);
  await openFromStart(page, 'Media Player');
  const items = page.locator('#windows > .win[data-app=mediaplayer] .mp-it b');
  await expect(items).toHaveCount(8); // the playlist fills in after the Music folder is read
  const titles = await items.allInnerTexts();
  expect(titles.length).toBeGreaterThan(5);
  expect(new Set(titles).size).toBe(titles.length);
  const arts = await page.locator('#windows > .win[data-app=mediaplayer] .mp-art').evaluateAll((els) => els.map((e) => (e as HTMLImageElement).src));
  expect(new Set(arts).size).toBe(arts.length);
});
