import { expect, test } from '@playwright/test';
import { watch } from './helpers';

test('?app=notepad opens just the app, filling the page, with no desktop', async ({ page }) => {
  const errors = watch(page);
  await page.goto('/?app=notepad');
  await expect(page.locator('.win[data-app=notepad] .win-body')).toBeVisible();
  await expect(page).toHaveTitle(/Notepad/);
  for (const sel of ['#desktop', '#dock', '#menubar', '#curtain']) await expect(page.locator(sel)).toHaveCount(0);
  await expect(page.locator('.win-titlebar')).toBeHidden();
  await expect.poll(async () => page.locator('.win').boundingBox()).toMatchObject({ x: 0, y: 0, width: 1440, height: 900 }); // after the open animation
  await expect(page.locator('.am-menu').first()).toBeVisible();
  expect(errors).toEqual([]);
});
