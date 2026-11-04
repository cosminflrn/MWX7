import { expect, test } from '@playwright/test';
import { boot, closeAll, watch } from './helpers';

test('boots to the desktop with the Welcome tour and no errors', async ({ page }) => {
  const errors = watch(page);
  await boot(page);
  await expect(page.locator('.win[data-app=welcome]')).toBeVisible();
  await expect(page.locator('#menubar')).toBeVisible();
  expect(errors).toEqual([]);
});

test('every app opens, goes full screen, minimizes, restores and closes', async ({ page }) => {
  const errors = watch(page);
  await boot(page);
  await closeAll(page);
  await page.locator('.dock-orb').click();
  const names = await page.locator('.start-menu .sm-app').allInnerTexts();
  await page.mouse.click(5, 450);
  expect(names.length).toBeGreaterThan(10);
  for (const raw of names) {
    const name = raw.trim();
    await page.locator('.dock-orb').click();
    await page.locator('.start-menu .sm-app', { hasText: name }).first().click();
    const win = page.locator('#windows > .win.active');
    await expect(win, name).toBeVisible();
    await page.waitForTimeout(500); // open animation + Start menu fade
    await expect(win.locator('.app-crash'), `${name} crashed`).toHaveCount(0);
    const got = win.locator('button', { hasText: 'Got it' });
    if (await got.count()) await got.click();
    if (!(await win.evaluate((w) => w.classList.contains('fixed')))) {
      await win.locator('.wc-max').click({ force: true });
      await expect(page.locator('#menubar')).toHaveClass(/fs/);
      await page.waitForTimeout(600); // the top-bar lights slide in
      await page.locator('#menubar .mb-wc .wc-max').click({ force: true });
      await expect(page.locator('#menubar')).not.toHaveClass(/fs/);
      await page.waitForTimeout(500); // restore animation
    }
    const id = await page.locator('#windows > .win.active').getAttribute('data-app');
    const mine = page.locator(`#windows > .win[data-app="${id}"]`).last();
    await mine.locator('.wc-min').click({ force: true });
    await expect(mine, `${name} minimizes`).toBeHidden({ timeout: 5000 });
    await page.locator(`.dock-item[data-label="${name}"]`).click();
    await expect(mine, `${name} restores`).toBeVisible({ timeout: 5000 });
    await closeAll(page);
    await page.waitForTimeout(400);
    const dlg = page.locator('.msgbox button').last();
    if (await dlg.count()) await dlg.click();
  }
  expect(errors).toEqual([]);
});

test('genie: window stays as it is, hides only when the animation shows, turns around on rapid clicks', async ({ page }) => {
  const errors = watch(page);
  await boot(page);
  await closeAll(page);
  await page.locator('.dock-item[data-label="My Computer"]').click();
  const win = page.locator('.win[data-app=explorer]');
  await expect(win).toBeVisible();
  await page.waitForTimeout(600);
  // While the frozen glass is prepared nothing extra may be on the page, and the window stays visible.
  await win.locator('.wc-min').click({ force: true });
  await expect(page.locator('.genie-layer')).toHaveCount(1, { timeout: 3000 });
  const state = await page.evaluate(() => {
    const l = document.querySelector<HTMLElement>('.genie-layer')!;
    const copies = [...l.querySelectorAll<HTMLElement>('.genie-strip > .win')];
    return {
      shown: l.style.visibility === '',
      liveBlur: copies.filter((c) => getComputedStyle(c).backdropFilter !== 'none').length,
      realHidden: getComputedStyle(document.querySelector('.win[data-app=explorer]')!).visibility,
      active: document.querySelector('.win[data-app=explorer]')!.classList.contains('active'),
    };
  });
  expect(state).toEqual({ shown: true, liveBlur: 0, realHidden: 'hidden', active: true });
  await expect(page.locator('.genie-layer')).toHaveCount(0, { timeout: 3000 });
  await expect(win).toBeHidden();
  // Rapid dock clicks: never more than one animation, and an odd number of clicks ends visible.
  const icon = page.locator('.dock-item[data-label="My Computer"]');
  let most = 0;
  for (let i = 0; i < 7; i++) {
    await icon.click();
    await page.waitForTimeout(110);
    most = Math.max(most, await page.locator('.genie-layer').count());
  }
  expect(most).toBeLessThanOrEqual(1);
  await expect(page.locator('.genie-layer')).toHaveCount(0, { timeout: 4000 });
  await expect(win).toBeVisible();
  await expect(win).toHaveClass(/active/);
  expect(errors).toEqual([]);
});

test('dragging moves the window with a transform and commits it on release', async ({ page }) => {
  await boot(page);
  await closeAll(page);
  await page.locator('.dock-item[data-label="My Computer"]').click();
  const win = page.locator('.win[data-app=explorer]');
  await page.waitForTimeout(600);
  const t = (await win.locator('.win-titlebar').boundingBox())!;
  const before = (await win.boundingBox())!;
  await page.mouse.move(t.x + 200, t.y + 12);
  await page.mouse.down();
  await page.mouse.move(t.x + 300, t.y + 72, { steps: 8 });
  await page.mouse.up();
  const after = (await win.boundingBox())!;
  expect(Math.round(after.x - before.x)).toBe(100);
  expect(Math.round(after.y - before.y)).toBe(60);
  expect(await win.evaluate((w) => w.style.transform)).toBe('');
});

test('Notepad asks to save in the OS dialog and keeps the text', async ({ page }) => {
  const errors = watch(page);
  await boot(page);
  await closeAll(page);
  await page.mouse.click(900, 600, { button: 'right' });
  await page.locator('.menu-item', { hasText: 'New Text Document' }).click();
  await page.locator('.desk-icon', { hasText: 'New Text Document' }).dblclick();
  await page.locator('.win[data-app=notepad] textarea').fill('Hello MWX');
  await page.locator('.win[data-app=notepad] .wc-close').click({ force: true });
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.locator('.win[data-app=notepad]')).toHaveCount(0);
  await page.locator('.desk-icon', { hasText: 'New Text Document' }).dblclick();
  await expect(page.locator('.win[data-app=notepad] textarea')).toHaveValue('Hello MWX');
  expect(errors).toEqual([]);
});

test('reload starts clean (nothing is remembered)', async ({ page }) => {
  await boot(page, 'Someone');
  await page.reload();
  await expect(page.locator('.power-btn')).toBeVisible();
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
});
