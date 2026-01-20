import type { Memory } from '../types';

// Hard-coded admin allowlist for edit attribution
const ADMIN_EDITORS = new Set([
  'shubham.patel@getmailbird.com',
  'oliver.jackson@getmailbird.com',
  'am@getmailbird.com',
]);

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function extractMetadataString(metadata: Record<string, unknown> | null | undefined, keys: string[]): string | null {
  if (!metadata) return null;
  for (const key of keys) {
    const value = metadata[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }
  return null;
}

function normalizeEmail(value: string | null | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed.includes('@')) return null;
  return trimmed.toLowerCase();
}

function normalizeUuid(value: string | null | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!UUID_PATTERN.test(trimmed)) return null;
  return trimmed.toLowerCase();
}

/**
 * Returns the email of the human editor if it is present and allow‑listed.
 */
export function getMemoryEditorEmail(memory: Memory): string | null {
  const metaEmail = normalizeEmail(
    extractMetadataString(memory.metadata, [
      'edited_by_email',
      'updated_by_email',
      'editor_email',
    ])
  );

  const metaNameAsEmail = normalizeEmail(
    extractMetadataString(memory.metadata, ['edited_by', 'updated_by'])
  );

  const reviewedByEmail = normalizeEmail((memory as Memory & { reviewed_by?: string | null }).reviewed_by);

  const candidates = [metaEmail, metaNameAsEmail, reviewedByEmail];
  for (const candidate of candidates) {
    if (candidate && ADMIN_EDITORS.has(candidate)) {
      return candidate;
    }
  }
  return null;
}

function getMemoryReviewerId(memory: Memory): string | null {
  const reviewedBy = (memory as Memory & { reviewed_by?: string | null }).reviewed_by;
  if (normalizeEmail(reviewedBy)) return null;
  return normalizeUuid(reviewedBy);
}

/**
 * Returns a human‑readable display name for the editor (email or name from metadata).
 */
export function getMemoryEditorDisplayName(memory: Memory): string | null {
  const editorEmail = getMemoryEditorEmail(memory);
  const name = extractMetadataString(memory.metadata, [
    'edited_by_name',
    'updated_by_name',
    'edited_by',
    'updated_by',
  ]);
  if (editorEmail) return name || editorEmail;
  return null;
}

/**
 * Determines whether a memory should be shown as "edited" by an allowed admin.
 * We require both: (a) a newer updated_at than created_at, and (b) a trusted editor identity.
 */
export function isMemoryEdited(memory: Memory): boolean {
  const createdMs = Date.parse(memory.created_at);
  const updatedMs = Date.parse(memory.updated_at);
  if (!Number.isFinite(createdMs) || !Number.isFinite(updatedMs)) return false;
  if (updatedMs <= createdMs) return false;
  return Boolean(getMemoryEditorEmail(memory) || getMemoryReviewerId(memory));
}

export const ADMIN_EDITOR_EMAILS = ADMIN_EDITORS;
