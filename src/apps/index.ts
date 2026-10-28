import { registerApp } from '../core/registry';
import { about } from './about';
import { calculator } from './calculator';
import { notepad } from './notepad';
import { settingsApp } from './settings';

/**
 * App registry. To add an app: create src/apps/<id>/index.ts exporting an
 * AppManifest, then add ONE line here. Order = Start menu / dock order.
 */
export function registerAll(): void {
  [notepad, calculator, settingsApp, about].forEach(registerApp);
}
