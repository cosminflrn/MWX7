import { registerApp } from '../core/registry';
import { about } from './about/manifest';
import { browser } from './browser/manifest';
import { calculator } from './calculator/manifest';
import { explorer } from './explorer/manifest';
import { mediaplayer } from './mediaplayer/manifest';
import { mines, minesExpert, minesIntermediate } from './mines/manifest';
import { notepad } from './notepad/manifest';
import { paint } from './paint/manifest';
import { photos } from './photos/manifest';
import { pinball } from './pinball/manifest';
import { solitaire } from './solitaire/manifest';
import { settingsApp } from './settings/manifest';
import { stickynotes } from './stickynotes/manifest';
import { taskmgr } from './taskmgr/manifest';
import { welcome } from './welcome/manifest';

/**
 * App registry. To add an app: create src/apps/<id>/index.ts exporting an
 * AppManifest, then add ONE line here. Order = Start menu / dock order.
 */
export function registerAll(): void {
  [explorer, browser, mediaplayer, notepad, paint, calculator, photos, stickynotes, taskmgr, pinball, solitaire, mines, minesIntermediate, minesExpert, settingsApp, about, welcome].forEach(registerApp);
}
