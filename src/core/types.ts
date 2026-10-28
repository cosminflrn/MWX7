/**
 * MWX 7 public contracts.
 * Apps and shell components talk to the core ONLY through these types.
 * Changing anything here is a breaking change — see SPEC.md.
 */

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface MenuItem {
  label?: string;
  shortcut?: string;
  action?: () => void;
  disabled?: boolean;
  checked?: boolean;
  separator?: boolean;
}

export interface MenuDef {
  label: string;
  items: MenuItem[];
}

export interface WindowOptions {
  width?: number;
  height?: number;
  minWidth?: number;
  minHeight?: number;
  resizable?: boolean;
}

/** What every app exports from src/apps/<id>/index.ts */
export interface AppManifest {
  /** kebab-case, unique, equals the folder name */
  id: string;
  name: string;
  /** Inline SVG markup (see src/assets/icons.ts) */
  icon: string;
  description?: string;
  /** Extra words Spotlight should match */
  keywords?: string[];
  /** Shown in the dock even when not running */
  pinned?: boolean;
  /** Shown as a desktop icon */
  desktop?: boolean;
  /** Re-launching focuses the existing window instead of opening a new one */
  singleInstance?: boolean;
  /** Hidden from Start menu / Spotlight (e.g. helper apps) */
  hidden?: boolean;
  window?: WindowOptions;
  /** Build the UI into ctx.win.body. Return an optional cleanup function. */
  mount(ctx: AppContext): void | (() => void);
}

export interface WindowHandle {
  readonly id: string;
  /** The content area. Style your app inside it; it is position:relative. */
  readonly body: HTMLElement;
  setTitle(title: string): void;
  /** Menus shown in the top menu bar while this window is focused */
  setMenus(menus: MenuDef[]): void;
  close(): void;
  focus(): void;
  /** Return false to cancel a close (e.g. unsaved changes). */
  onBeforeClose(handler: () => boolean): void;
}

export interface FileEntry {
  path: string;
  name: string;
  /** '' for folders */
  content: string;
  modified: number;
  /** Absent means 'file' (v0.1 entries had no type). */
  type?: 'file' | 'dir';
}

export interface FileStat {
  type: 'file' | 'dir';
  modified: number;
  /** UTF-8 byte length of the content; 0 for folders */
  size: number;
}

/** Virtual filesystem. Paths are absolute, e.g. /Documents/Notes.txt */
export interface VFS {
  list(dir: string): Promise<FileEntry[]>;
  all(): Promise<FileEntry[]>;
  read(path: string): Promise<string | null>;
  write(path: string, content: string): Promise<void>;
  remove(path: string): Promise<void>;
  exists(path: string): Promise<boolean>;
  /** Creates the folder and any missing parents; no-op if it already exists. */
  mkdir(path: string): Promise<void>;
  /** Renames/moves a file or folder (recursively) to an exact new path. Fails if `to` exists. */
  rename(from: string, to: string): Promise<void>;
  /** Moves a file or folder into `toDir`, keeping its name. */
  move(from: string, toDir: string): Promise<void>;
  stat(path: string): Promise<FileStat | null>;
}

export interface Settings {
  wallpaper: string;
  userName: string;
  /** URL of the account picture ('' = generic silhouette) */
  avatar: string;
  /** Power button → BIOS → boot logo before the logon screen */
  bootSequence: boolean;
  sounds: boolean;
  /** 0..1 */
  volume: number;
}

export interface OSApi {
  launch(appId: string, args?: Record<string, unknown>): void;
  notify(title: string, body?: string, icon?: string): void;
  apps(): AppManifest[];
  settings: {
    get(): Settings;
    set(patch: Partial<Settings>): void;
  };
}

export interface AppContext {
  win: WindowHandle;
  args: Record<string, unknown>;
  fs: VFS;
  os: OSApi;
}
