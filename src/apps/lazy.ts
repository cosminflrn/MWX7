import type { AppContext } from '../core/types';

type Impl = { impl: { mount(ctx: AppContext): void | (() => void) } };

const loaders: (() => Promise<unknown>)[] = [];

/**
 * Defers an app's code until its first launch. The window opens at once with an empty body; the app fills it when its
 * chunk arrives. The returned cleanup works even if the window is closed before the chunk has loaded.
 */
export function lazyMount(load: () => Promise<Impl>): (ctx: AppContext) => () => void {
  loaders.push(load);
  return (ctx) => {
    let closed = false;
    let cleanup: void | (() => void);
    void load().then((m) => {
      if (!closed) cleanup = m.impl.mount(ctx);
    });
    return () => {
      closed = true;
      if (typeof cleanup === 'function') cleanup();
    };
  };
}

/** Fetch every app chunk one at a time while the browser is idle, so the first launch is instant. */
export function preloadApps(): void {
  const idle: (cb: () => void) => void = (window as any).requestIdleCallback ?? ((cb) => setTimeout(cb, 200));
  const queue = [...loaders];
  const next = (): void => {
    const load = queue.shift();
    if (!load) return;
    idle(() => void load().catch(() => undefined).finally(next));
  };
  next();
}
