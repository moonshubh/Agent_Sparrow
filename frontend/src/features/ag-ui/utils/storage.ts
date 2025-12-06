/**
 * Safe storage helpers for AG-UI (SSR-friendly).
 */

const hasWindow = typeof window !== 'undefined';

export function safeGetItem(key: string): string | null {
  if (!hasWindow) return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function safeSetItem(key: string, value: string): void {
  if (!hasWindow) return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // ignore storage errors
  }
}

export function safeParseJSON<T>(value: string | null, fallback: T): T {
  if (!value) return fallback;
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

