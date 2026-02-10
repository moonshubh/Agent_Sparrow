import type { Memory } from "../types";

const EDITOR_METADATA_KEYS = [
  "edited_by_email",
  "updated_by_email",
  "editor_email",
  "edited_by",
  "updated_by",
  "edited_by_name",
  "updated_by_name",
] as const;

function metadataString(memory: Memory, key: (typeof EDITOR_METADATA_KEYS)[number]): string {
  const value = memory.metadata?.[key];
  if (typeof value === "string") {
    return value.trim();
  }
  return "";
}

function hasEditorIdentity(memory: Memory): boolean {
  const reviewedBy = typeof memory.reviewed_by === "string" ? memory.reviewed_by.trim() : "";
  if (reviewedBy) return true;

  return EDITOR_METADATA_KEYS.some((key) => metadataString(memory, key).length > 0);
}

function firstMetadataIdentity(memory: Memory): string | null {
  for (const key of EDITOR_METADATA_KEYS) {
    const value = metadataString(memory, key);
    if (value) return value;
  }
  return null;
}

/**
 * Returns an editor email if one is available in metadata or reviewer identity.
 */
export function getMemoryEditorEmail(memory: Memory): string | null {
  const reviewedBy = typeof memory.reviewed_by === "string" ? memory.reviewed_by.trim() : "";
  if (reviewedBy.includes("@")) {
    return reviewedBy.toLowerCase();
  }

  const metadataIdentity = firstMetadataIdentity(memory);
  if (metadataIdentity && metadataIdentity.includes("@")) {
    return metadataIdentity.toLowerCase();
  }

  return null;
}

/**
 * Returns a human-readable display name for the editor.
 */
export function getMemoryEditorDisplayName(memory: Memory): string | null {
  const preferred = [
    metadataString(memory, "edited_by_name"),
    metadataString(memory, "updated_by_name"),
    metadataString(memory, "edited_by"),
    metadataString(memory, "updated_by"),
  ].find((value) => Boolean(value));

  if (preferred) return preferred;

  const reviewedBy = typeof memory.reviewed_by === "string" ? memory.reviewed_by.trim() : "";
  if (reviewedBy) return reviewedBy;

  return getMemoryEditorEmail(memory);
}

/**
 * Determines whether a memory was edited by a human/admin.
 * Rule: updated_at > created_at AND at least one editor identity source exists.
 */
export function isMemoryEdited(memory: Memory): boolean {
  const createdMs = Date.parse(memory.created_at);
  const updatedMs = Date.parse(memory.updated_at);
  if (!Number.isFinite(createdMs) || !Number.isFinite(updatedMs)) return false;
  if (updatedMs <= createdMs) return false;
  return hasEditorIdentity(memory);
}
