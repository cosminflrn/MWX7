import type { Settings } from './types';
import type { Win } from './wm';

export interface OSEvents {
  'window:open': Win;
  'window:close': Win;
  'window:focus': Win | null;
  'window:minimize': Win;
  'window:restore': Win;
  'window:title': Win;
  'window:menus': Win;
  'settings:change': Settings;
  'fs:change': { path: string };
  notify: { title: string; body?: string; icon?: string };
  'startmenu:toggle': { anchor?: DOMRect };
  'spotlight:open': { query?: string };
}

type Handler<T> = (payload: T) => void;

class EventBus {
  private handlers = new Map<keyof OSEvents, Set<Handler<never>>>();

  on<K extends keyof OSEvents>(event: K, handler: Handler<OSEvents[K]>): () => void {
    let set = this.handlers.get(event);
    if (!set) this.handlers.set(event, (set = new Set()));
    set.add(handler as Handler<never>);
    return () => set!.delete(handler as Handler<never>);
  }

  emit<K extends keyof OSEvents>(event: K, ...payload: OSEvents[K] extends void ? [] : [OSEvents[K]]): void {
    const set = this.handlers.get(event);
    if (!set) return;
    for (const h of [...set]) {
      try {
        (h as Handler<unknown>)(payload[0]);
      } catch (err) {
        console.error(`[bus] handler for "${event}" failed`, err);
      }
    }
  }
}

export const bus = new EventBus();
