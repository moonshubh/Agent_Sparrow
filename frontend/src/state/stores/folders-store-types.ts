// Type definitions for folders store
export interface Folder {
  id: number;
  name: string;
  color?: string;
  conversationCount?: number;
  conversation_count?: number; // Legacy support
  created_at?: string;
  updated_at?: string;
  parent_id?: number | null;
}

// Helper to get conversation count with type safety
export function getConversationCount(folder: Folder): number {
  // Prefer the camelCase version, fallback to snake_case, default to 0
  return folder.conversationCount ?? folder.conversation_count ?? 0;
}
