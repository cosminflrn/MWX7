import { registerApp } from '../core/registry';
import { about } from './about';
import { browser } from './browser';
import { calculator } from './calculator';
import { explorer } from './explorer';
import { mediaplayer } from './mediaplayer';
import { mines, minesExpert, minesIntermediate } from './mines';
import { notepad } from './notepad';
import { paint } from './paint';
import { pinball } from './pinball';
import { solitaire } from './solitaire';
import { settingsApp } from './settings';
import { welcome } from './welcome';

/**
 * App registry. To add an app: create src/apps/<id>/index.ts exporting an
 * AppManifest, then add ONE line here. Order = Start menu / dock order.
 */
export function registerAll(): void {
  [explorer, browser, mediaplayer, notepad, paint, calculator, pinball, solitaire, mines, minesIntermediate, minesExpert, settingsApp, about, welcome].forEach(registerApp);
}
