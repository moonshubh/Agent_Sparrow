/**
 * Supabase Client for FeedMe Frontend
 *
 * Provides typed operations for folder management, conversation persistence,
 * and example synchronization with Supabase.
 */

import {
  createClient,
  SupabaseClient as SupabaseClientType,
} from "@supabase/supabase-js";

// Environment variables
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  console.warn(
    "Missing Supabase configuration. Please set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY",
  );
}

// =====================================================
// TYPE DEFINITIONS
// =====================================================

export interface SupabaseFolder {
  id: number;
  parent_id: number | null;
  name: string;
  path: string[];
  color: string;
  description: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface SupabaseConversation {
  id: number;
  title: string;
  original_filename: string | null;
  raw_transcript: string;
  parsed_content: string | null;
  metadata: Record<string, any>;
  folder_id: number | null;
  processing_status: "pending" | "processing" | "completed" | "failed";
  error_message: string | null;
  total_examples: number;
  uploaded_by: string | null;
  uploaded_at: string;
  processed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SupabaseExample {
  id: number;
  conversation_id: number;
  question_text: string;
  answer_text: string;
  context_before: string | null;
  context_after: string | null;
  tags: string[];
  issue_type: string | null;
  resolution_type: string | null;
  confidence_score: number;
  usefulness_score: number;
  is_active: boolean;
  approved_at: string | null;
  approved_by: string | null;
  supabase_synced: boolean;
  supabase_sync_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface FolderStats {
  folder_id: number;
  folder_name: string;
  folder_path: string[];
  conversation_count: number;
  example_count: number;
  approved_example_count: number;
  last_conversation_added: string | null;
  last_example_approved: string | null;
}

export interface CreateFolderRequest {
  name: string;
  color?: string;
  description?: string;
  parent_id?: number | null;
  created_by?: string | null;
}

export interface UpdateFolderRequest {
  name?: string;
  color?: string;
  description?: string;
  parent_id?: number | null;
}

export interface ApprovalRequest {
  conversation_id: number;
  approved_by: string;
  example_ids?: number[];
}

export interface SearchExamplesRequest {
  query_embedding: number[];
  limit?: number;
  similarity_threshold?: number;
  folder_ids?: number[];
  only_approved?: boolean;
}

// =====================================================
// SUPABASE CLIENT CLASS
// =====================================================

class SupabaseClient {
  private client: SupabaseClientType | null = null;
  private missingTables = new Set<string>();

  constructor() {
    if (SUPABASE_URL && SUPABASE_ANON_KEY) {
      this.client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
        },
      });
    }
  }

  private ensureClient(): SupabaseClientType {
    if (!this.client) {
      throw new Error(
        "Supabase client not initialized. Check environment variables.",
      );
    }
    return this.client;
  }

  private normalizeTableName(name: string): string {
    return name.trim().toLowerCase();
  }

  private isMissingTableError(error: unknown, table: string): boolean {
    const message =
      typeof error === "string"
        ? error
        : (error as { message?: string })?.message || "";
    const haystack = message.toLowerCase();
    const normalized = this.normalizeTableName(table);
    const variants = [
      normalized,
      normalized.replace(/_/g, " "),
      normalized.replace(/_/g, ""),
    ];
    const signals = [
      "could not find the table",
      "schema cache",
      "does not exist",
      "relation",
    ];
    return (
      signals.some((sig) => haystack.includes(sig)) &&
      variants.some((variant) => haystack.includes(variant))
    );
  }

  private markMissingTable(error: unknown, table: string): boolean {
    if (!this.isMissingTableError(error, table)) return false;
    this.missingTables.add(this.normalizeTableName(table));
    return true;
  }

  private isTableMissing(table: string): boolean {
    return this.missingTables.has(this.normalizeTableName(table));
  }

  // =====================================================
  // FOLDER OPERATIONS
  // =====================================================

  async createFolder(request: CreateFolderRequest): Promise<SupabaseFolder> {
    const client = this.ensureClient();

    const { data, error } = await client
      .from("feedme_folders")
      .insert({
        name: request.name,
        color: request.color || "#0095ff",
        description: request.description,
        parent_id: request.parent_id,
        created_by: request.created_by,
      })
      .select()
      .single();

    if (error) {
      console.error("Error creating folder:", error);
      throw new Error(`Failed to create folder: ${error.message}`);
    }

    return data;
  }

  async updateFolder(
    id: number,
    request: UpdateFolderRequest,
  ): Promise<SupabaseFolder> {
    const client = this.ensureClient();

    const { data, error } = await client
      .from("feedme_folders")
      .update(request)
      .eq("id", id)
      .select()
      .single();

    if (error) {
      console.error("Error updating folder:", error);
      throw new Error(`Failed to update folder: ${error.message}`);
    }

    return data;
  }

  async deleteFolder(id: number): Promise<void> {
    const client = this.ensureClient();

    const { error } = await client.from("feedme_folders").delete().eq("id", id);

    if (error) {
      console.error("Error deleting folder:", error);
      throw new Error(`Failed to delete folder: ${error.message}`);
    }
  }

  async listFolders(): Promise<FolderStats[]> {
    const client = this.ensureClient();

    const { data, error } = await client
      .from("feedme_folder_stats")
      .select("*")
      .order("folder_path");

    if (error) {
      console.error("Error listing folders:", error);
      throw new Error(`Failed to list folders: ${error.message}`);
    }

    return data || [];
  }

  // =====================================================
  // CONVERSATION OPERATIONS
  // =====================================================

  async createConversation(
    title: string,
    raw_transcript: string,
    folder_id?: number | null,
    metadata?: Record<string, any>,
    uploaded_by?: string | null,
  ): Promise<SupabaseConversation> {
    const client = this.ensureClient();

    const { data, error } = await client
      .from("feedme_conversations")
      .insert({
        title,
        raw_transcript,
        folder_id,
        metadata: metadata || {},
        uploaded_by,
        processing_status: "pending",
      })
      .select()
      .single();

    if (error) {
      console.error("Error creating conversation:", error);
      throw new Error(`Failed to create conversation: ${error.message}`);
    }

    return data;
  }

  async updateConversationFolder(
    conversationId: number,
    folderId: number | null,
  ): Promise<SupabaseConversation> {
    const client = this.ensureClient();

    const { data, error } = await client
      .from("feedme_conversations")
      .update({ folder_id: folderId })
      .eq("id", conversationId)
      .select()
      .single();

    if (error) {
      console.error("Error updating conversation folder:", error);
      throw new Error(`Failed to update conversation folder: ${error.message}`);
    }

    return data;
  }

  async bulkAssignConversationsToFolder(
    conversationIds: number[],
    folderId: number | null,
  ): Promise<number> {
    const client = this.ensureClient();

    const { data, error } = await client
      .from("feedme_conversations")
      .update({ folder_id: folderId })
      .in("id", conversationIds)
      .select();

    if (error) {
      console.error("Error bulk assigning conversations:", error);
      throw new Error(`Failed to bulk assign conversations: ${error.message}`);
    }

    return data?.length || 0;
  }

  // =====================================================
  // EXAMPLE OPERATIONS
  // =====================================================

  async insertExamples(
    examples: Partial<SupabaseExample>[],
    markApproved: boolean = true,
  ): Promise<SupabaseExample[]> {
    if (this.isTableMissing("feedme_examples")) {
      return [];
    }
    const client = this.ensureClient();

    // Add approval fields if marking as approved
    if (markApproved) {
      const now = new Date().toISOString();
      examples = examples.map((example) => ({
        ...example,
        approved_at: now,
        supabase_synced: true,
        supabase_sync_at: now,
      }));
    }

    const { data, error } = await client
      .from("feedme_examples")
      .insert(examples)
      .select();

    if (error) {
      if (this.markMissingTable(error, "feedme_examples")) {
        return [];
      }
      console.error("Error inserting examples:", error);
      throw new Error(`Failed to insert examples: ${error.message}`);
    }

    return data || [];
  }

  async approveConversationExamples(request: ApprovalRequest): Promise<{
    conversation_id: number;
    approved_count: number;
    approved_by: string;
    timestamp: string;
  }> {
    if (this.isTableMissing("feedme_examples")) {
      const now = new Date().toISOString();
      await this.updateConversationStatus(request.conversation_id, "approved");
      return {
        conversation_id: request.conversation_id,
        approved_count: 0,
        approved_by: request.approved_by,
        timestamp: now,
      };
    }
    const client = this.ensureClient();
    const now = new Date().toISOString();

    // Build the update query
    let query = client
      .from("feedme_examples")
      .update({
        approved_at: now,
        approved_by: request.approved_by,
        supabase_synced: true,
        supabase_sync_at: now,
      })
      .eq("conversation_id", request.conversation_id);

    // Filter by specific examples if provided
    if (request.example_ids && request.example_ids.length > 0) {
      query = query.in("id", request.example_ids);
    }

    const { data, error } = await query.select();

    if (error) {
      if (this.markMissingTable(error, "feedme_examples")) {
        await this.updateConversationStatus(request.conversation_id, "approved");
        return {
          conversation_id: request.conversation_id,
          approved_count: 0,
          approved_by: request.approved_by,
          timestamp: now,
        };
      }
      console.error("Error approving examples:", error);
      throw new Error(`Failed to approve examples: ${error.message}`);
    }

    // Update conversation status
    await this.updateConversationStatus(request.conversation_id, "approved");

    return {
      conversation_id: request.conversation_id,
      approved_count: data?.length || 0,
      approved_by: request.approved_by,
      timestamp: now,
    };
  }

  async searchExamples(
    request: SearchExamplesRequest,
  ): Promise<Array<SupabaseExample & { similarity: number }>> {
    if (this.isTableMissing("feedme_examples")) {
      return [];
    }
    const client = this.ensureClient();

    const { data, error } = await client.rpc("search_feedme_examples", {
      query_embedding: request.query_embedding,
      match_threshold: request.similarity_threshold || 0.7,
      match_count: request.limit || 5,
      folder_ids: request.folder_ids,
      only_approved: request.only_approved !== false,
    });

    if (error) {
      if (this.markMissingTable(error, "feedme_examples")) {
        return [];
      }
      console.error("Error searching examples:", error);
      throw new Error(`Failed to search examples: ${error.message}`);
    }

    return data || [];
  }

  // =====================================================
  // SYNC OPERATIONS
  // =====================================================

  async getUnsyncedExamples(limit: number = 100): Promise<SupabaseExample[]> {
    if (this.isTableMissing("feedme_examples")) {
      return [];
    }
    const client = this.ensureClient();

    const { data, error } = await client
      .from("feedme_examples")
      .select("*")
      .eq("supabase_synced", false)
      .not("approved_at", "is", null)
      .limit(limit);

    if (error) {
      if (this.markMissingTable(error, "feedme_examples")) {
        return [];
      }
      console.error("Error getting unsynced examples:", error);
      throw new Error(`Failed to get unsynced examples: ${error.message}`);
    }

    return data || [];
  }

  async markExamplesSynced(exampleIds: number[]): Promise<number> {
    if (this.isTableMissing("feedme_examples")) {
      return 0;
    }
    const client = this.ensureClient();

    const { data, error } = await client
      .from("feedme_examples")
      .update({
        supabase_synced: true,
        supabase_sync_at: new Date().toISOString(),
      })
      .in("id", exampleIds)
      .select();

    if (error) {
      if (this.markMissingTable(error, "feedme_examples")) {
        return 0;
      }
      console.error("Error marking examples as synced:", error);
      throw new Error(`Failed to mark examples as synced: ${error.message}`);
    }

    return data?.length || 0;
  }

  // =====================================================
  // UTILITY METHODS
  // =====================================================

  private async updateConversationStatus(
    conversationId: number,
    status: string,
  ): Promise<void> {
    const client = this.ensureClient();

    const { error } = await client
      .from("feedme_conversations")
      .update({ processing_status: status })
      .eq("id", conversationId);

    if (error) {
      console.warn("Failed to update conversation status:", error);
    }
  }

  async healthCheck(): Promise<{
    status: "healthy" | "unhealthy";
    folders_count?: number;
    error?: string;
    timestamp: string;
  }> {
    try {
      const client = this.ensureClient();

      // Test basic query
      const { count, error } = await client
        .from("feedme_folders")
        .select("*", { count: "exact", head: true });

      if (error) throw error;

      return {
        status: "healthy",
        folders_count: count || 0,
        timestamp: new Date().toISOString(),
      };
    } catch (error) {
      return {
        status: "unhealthy",
        error: error instanceof Error ? error.message : "Unknown error",
        timestamp: new Date().toISOString(),
      };
    }
  }

  // Real-time subscriptions
  subscribeToFolders(callback: (payload: any) => void) {
    const client = this.ensureClient();

    return client
      .channel("folders-changes")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "feedme_folders" },
        callback,
      )
      .subscribe();
  }

  subscribeToConversations(callback: (payload: any) => void) {
    const client = this.ensureClient();

    return client
      .channel("conversations-changes")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "feedme_conversations" },
        callback,
      )
      .subscribe();
  }
}

// Create singleton instance
let supabaseClient: SupabaseClient | null = null;

export function getSupabaseClient(): SupabaseClient {
  if (!supabaseClient) {
    supabaseClient = new SupabaseClient();
  }
  return supabaseClient;
}

// Export default instance
export default getSupabaseClient();
