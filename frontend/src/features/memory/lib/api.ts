/**
 * Memory UI API Service
 *
 * Provides typed API functions for Memory UI operations.
 * Uses the existing APIClient pattern for consistency.
 */

import { apiClient, APIRequestError } from '@/services/api/api-client';
import { supabase } from '@/services/supabase';
import { ENTITY_COLORS } from '../types';
import type {
  Memory,
  MemoryEntity,
  MemoryRelationship,
  DuplicateCandidate,
  MemoryStats,
  MemoryMeResponse,
  GraphData,
  GraphNode,
  GraphLink,
  AddMemoryRequest,
  AddMemoryResponse,
  UpdateMemoryRequest,
  UpdateMemoryResponse,
  DeleteMemoryResponse,
  DeleteRelationshipResponse,
  MergeMemoriesRequest,
  MergeMemoriesResponse,
  MergeMemoriesArbitraryRequest,
  MergeMemoriesArbitraryResponse,
  SubmitFeedbackRequest,
  SubmitFeedbackResponse,
  ExportMemoriesRequest,
  ExportMemoriesResponse,
  DismissDuplicateRequest,
  DismissDuplicateResponse,
  ImportMemorySourcesRequest,
  ImportMemorySourcesResponse,
  ImportZendeskTaggedRequest,
  ImportZendeskTaggedResponse,
  ApproveMemoryResponse,
  ListMemoriesRequest,
  EntityType,
  ReviewStatus,
  UpdateRelationshipRequest,
  MergeRelationshipsRequest,
  MergeRelationshipsResponse,
  SplitRelationshipPreviewRequest,
  SplitRelationshipPreviewResponse,
  SplitRelationshipCommitRequest,
  SplitRelationshipCommitResponse,
  RelationshipAnalysisRequest,
  RelationshipAnalysisResponse,
} from '../types';

// =============================================================================
// Constants
// =============================================================================

/**
 * Memory API base URL - configurable via environment variable
 * @default '/api/v1/memory'
 */
const MEMORY_API_BASE =
  process.env.NEXT_PUBLIC_MEMORY_API_BASE || '/api/v1/memory';

/**
 * In local/dev auth bypass modes, the frontend may not have a real Supabase
 * session token even though backend endpoints work (local JWT or SKIP_AUTH).
 * In those cases, use backend read endpoints instead of direct Supabase reads.
 */
const USE_BACKEND_READS =
  process.env.NEXT_PUBLIC_LOCAL_AUTH_BYPASS === 'true' ||
  (process.env.NEXT_PUBLIC_BYPASS_AUTH === 'true' &&
    process.env.NEXT_PUBLIC_DEV_MODE === 'true');

/**
 * In dev/auth-bypass scenarios the UI may not have a Supabase session, which means
 * direct PostgREST reads run as `anon` and get filtered by RLS (often returning empty lists).
 * Fall back to backend read endpoints when there's no Supabase access token.
 */
async function shouldUseBackendReads(): Promise<boolean> {
  if (USE_BACKEND_READS) return true;
  try {
    const { data } = await supabase.auth.getSession();
    return !data.session?.access_token;
  } catch {
    return true;
  }
}

/** API limits to prevent excessive data fetching */
const API_LIMITS = {
  DEFAULT_MEMORIES: 50,
  SEARCH_RESULTS: 20,
  MAX_ENTITIES: 500,
  MAX_RELATIONSHIPS: 1000,
  DUPLICATE_CANDIDATES: 20,
} as const;

/** Timing constants for UI behavior */
export const TIMING = {
  /** Debounce delay for search input (ms) */
  SEARCH_DEBOUNCE_MS: 300,
  /** Polling interval for graph updates (ms) */
  GRAPH_POLL_INTERVAL_MS: 60000,
  /** Polling interval for stats updates (ms) */
  STATS_POLL_INTERVAL_MS: 120000,
  /** Stale time for graph data (ms) */
  GRAPH_STALE_TIME_MS: 60000,
  /** Stale time for stats data (ms) */
  STATS_STALE_TIME_MS: 120000,
} as const;

/**
 * Avoid fetching the 3072-dim `embedding` column to keep payloads small.
 * Supabase PostgREST supports selecting explicit columns.
 */
const MEMORY_SELECT_COLUMNS =
  'id,content,metadata,source_type,review_status,reviewed_by,reviewed_at,confidence_score,retrieval_count,last_retrieved_at,feedback_positive,feedback_negative,resolution_success_count,resolution_failure_count,agent_id,tenant_id,created_at,updated_at';

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Escape LIKE metacharacters to prevent SQL injection
 * Supabase parameterizes queries, but LIKE patterns with user input
 * can still cause unexpected behavior or performance issues
 */
function escapeLikePattern(input: string): string {
  return input.replace(/[%_\\]/g, '\\$&');
}

function buildQueryString(
  params: Record<string, string | number | boolean | null | undefined>
): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined) return;
    qs.set(key, String(value));
  });
  const out = qs.toString();
  return out ? `?${out}` : '';
}

/**
 * Escape HTML entities to prevent XSS attacks
 */
export function escapeHtml(str: string): string {
  const escapeMap: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  };
  return str.replace(/[&<>"']/g, (char) => escapeMap[char] || char);
}

// =============================================================================
// Write Operations (via FastAPI)
// =============================================================================

/**
 * Add a new memory
 */
export async function addMemory(
  request: AddMemoryRequest
): Promise<AddMemoryResponse> {
  return apiClient.post<AddMemoryResponse, AddMemoryRequest>(
    `${MEMORY_API_BASE}/add`,
    request
  );
}

/**
 * Update an existing memory (admin only)
 */
export async function updateMemory(
  memoryId: string,
  request: UpdateMemoryRequest
): Promise<UpdateMemoryResponse> {
  return apiClient.put<UpdateMemoryResponse, UpdateMemoryRequest>(
    `${MEMORY_API_BASE}/${memoryId}`,
    request
  );
}

/**
 * Delete a memory (admin only)
 */
export async function deleteMemory(
  memoryId: string
): Promise<DeleteMemoryResponse> {
  return apiClient.delete<DeleteMemoryResponse>(`${MEMORY_API_BASE}/${memoryId}`);
}

/**
 * Delete a relationship (admin only)
 */
export async function deleteRelationship(
  relationshipId: string
): Promise<DeleteRelationshipResponse> {
  return apiClient.delete<DeleteRelationshipResponse>(
    `${MEMORY_API_BASE}/relationships/${relationshipId}`
  );
}

/**
 * Merge duplicate memories (admin only)
 */
export async function mergeMemories(
  request: MergeMemoriesRequest
): Promise<MergeMemoriesResponse> {
  return apiClient.post<MergeMemoriesResponse, MergeMemoriesRequest>(
    `${MEMORY_API_BASE}/merge`,
    request
  );
}

/**
 * Merge explicit memory IDs (admin only)
 */
export async function mergeMemoriesArbitrary(
  request: MergeMemoriesArbitraryRequest
): Promise<MergeMemoriesArbitraryResponse> {
  return apiClient.post<
    MergeMemoriesArbitraryResponse,
    MergeMemoriesArbitraryRequest
  >(`${MEMORY_API_BASE}/merge/arbitrary`, request);
}

/**
 * Get current user + roles for Memory UI gating
 */
export async function getMemoryMe(): Promise<MemoryMeResponse> {
  return apiClient.get<MemoryMeResponse>(`${MEMORY_API_BASE}/me`);
}

/**
 * Submit feedback for a memory
 */
export async function submitFeedback(
  memoryId: string,
  request: SubmitFeedbackRequest
): Promise<SubmitFeedbackResponse> {
  return apiClient.post<SubmitFeedbackResponse, SubmitFeedbackRequest>(
    `${MEMORY_API_BASE}/${memoryId}/feedback`,
    request
  );
}

/**
 * Export memories (admin only)
 */
export async function exportMemories(
  request: ExportMemoriesRequest
): Promise<ExportMemoriesResponse> {
  return apiClient.post<ExportMemoriesResponse, ExportMemoriesRequest>(
    `${MEMORY_API_BASE}/export`,
    request
  );
}

/**
 * Import solved Zendesk tickets tagged for MB_playbook learning (admin only)
 */
export async function importZendeskTagged(
  request: ImportZendeskTaggedRequest = {}
): Promise<ImportZendeskTaggedResponse> {
  return apiClient.post<ImportZendeskTaggedResponse, ImportZendeskTaggedRequest>(
    `${MEMORY_API_BASE}/import/zendesk-tagged`,
    request
  );
}

/**
 * Approve a pending-review memory (admin only)
 */
export async function approveMemory(
  memoryId: string
): Promise<ApproveMemoryResponse> {
  return apiClient.post<ApproveMemoryResponse>(
    `${MEMORY_API_BASE}/${encodeURIComponent(memoryId)}/approve`
  );
}

/**
 * Dismiss a duplicate candidate (admin only)
 */
export async function dismissDuplicate(
  candidateId: string,
  request: DismissDuplicateRequest
): Promise<DismissDuplicateResponse> {
  return apiClient.post<DismissDuplicateResponse, DismissDuplicateRequest>(
    `${MEMORY_API_BASE}/duplicate/${candidateId}/dismiss`,
    request
  );
}

/**
 * Import existing knowledge sources into the Memory UI schema (admin only)
 */
export async function importMemorySources(
  request: ImportMemorySourcesRequest
): Promise<ImportMemorySourcesResponse> {
  return apiClient.post<ImportMemorySourcesResponse, ImportMemorySourcesRequest>(
    `${MEMORY_API_BASE}/import`,
    request
  );
}

/**
 * Update relationship metadata (admin only)
 */
export async function updateRelationship(
  relationshipId: string,
  request: UpdateRelationshipRequest
): Promise<MemoryRelationship> {
  return apiClient.put<MemoryRelationship, UpdateRelationshipRequest>(
    `${MEMORY_API_BASE}/relationships/${relationshipId}`,
    request
  );
}

/**
 * Merge multiple relationships into one (admin only)
 */
export async function mergeRelationships(
  request: MergeRelationshipsRequest
): Promise<MergeRelationshipsResponse> {
  return apiClient.post<MergeRelationshipsResponse, MergeRelationshipsRequest>(
    `${MEMORY_API_BASE}/relationships/merge`,
    request
  );
}

/**
 * Preview an AI-assisted relationship split (admin only)
 */
export async function splitRelationshipPreview(
  relationshipId: string,
  request: SplitRelationshipPreviewRequest
): Promise<SplitRelationshipPreviewResponse> {
  return apiClient.post<SplitRelationshipPreviewResponse, SplitRelationshipPreviewRequest>(
    `${MEMORY_API_BASE}/relationships/${encodeURIComponent(relationshipId)}/split/preview`,
    request
  );
}

/**
 * Commit an AI-assisted relationship split (admin only)
 */
export async function splitRelationshipCommit(
  relationshipId: string,
  request: SplitRelationshipCommitRequest
): Promise<SplitRelationshipCommitResponse> {
  return apiClient.post<SplitRelationshipCommitResponse, SplitRelationshipCommitRequest>(
    `${MEMORY_API_BASE}/relationships/${encodeURIComponent(relationshipId)}/split/commit`,
    request
  );
}

/**
 * Analyze a relationship edge (admin only)
 */
export async function analyzeRelationship(
  relationshipId: string,
  request: RelationshipAnalysisRequest
): Promise<RelationshipAnalysisResponse> {
  return apiClient.post<RelationshipAnalysisResponse, RelationshipAnalysisRequest>(
    `${MEMORY_API_BASE}/relationships/${encodeURIComponent(relationshipId)}/analysis`,
    request
  );
}

/**
 * Mark an entity as acknowledged/reviewed.
 */
export async function acknowledgeEntity(entityId: string): Promise<MemoryEntity> {
  return apiClient.post<MemoryEntity>(
    `${MEMORY_API_BASE}/entities/${entityId}/acknowledge`
  );
}

/**
 * Mark a relationship as acknowledged/reviewed.
 */
export async function acknowledgeRelationship(
  relationshipId: string
): Promise<MemoryRelationship> {
  return apiClient.post<MemoryRelationship>(
    `${MEMORY_API_BASE}/relationships/${relationshipId}/acknowledge`
  );
}

/**
 * Get memory statistics
 */
export async function getMemoryStats(): Promise<MemoryStats> {
  return apiClient.get<MemoryStats>(`${MEMORY_API_BASE}/stats`);
}

// =============================================================================
// Read Operations (via Supabase Direct)
// =============================================================================

/**
 * List memories with optional filters and pagination
 */
export async function listMemories(
  params: ListMemoriesRequest = {}
): Promise<Memory[]> {
  const {
    limit = API_LIMITS.DEFAULT_MEMORIES,
    offset = 0,
    agent_id,
    tenant_id,
    source_type,
    review_status,
    sort_order = 'desc',
  } = params;

  // For review_status filtering (e.g., pending_review) always use backend reads so
  // admin-only gating works consistently across environments.
  if (review_status || (await shouldUseBackendReads())) {
    const qs = buildQueryString({
      limit,
      offset,
      agent_id,
      tenant_id,
      source_type: source_type || undefined,
      review_status: review_status || undefined,
      sort_order,
    });
    return apiClient.get<Memory[]>(`${MEMORY_API_BASE}/list${qs}`);
  }

  const ascending = sort_order === 'asc';

  let query = supabase
    .from('memories')
    .select(MEMORY_SELECT_COLUMNS)
    .order('created_at', { ascending })
    .range(offset, offset + limit - 1);

  if (agent_id) {
    query = query.eq('agent_id', agent_id);
  }
  if (tenant_id) {
    query = query.eq('tenant_id', tenant_id);
  }
  if (source_type) {
    query = query.eq('source_type', source_type);
  }
  if (review_status) {
    query = query.eq('review_status', review_status);
  }

  const { data, error } = await query;

  if (error) {
    console.error('Error listing memories:', error);
    throw new Error(error.message);
  }

  return (data || []) as Memory[];
}

/**
 * Get a single memory by ID
 */
export async function getMemoryById(memoryId: string): Promise<Memory | null> {
  if (await shouldUseBackendReads()) {
    try {
      return await apiClient.get<Memory>(
        `${MEMORY_API_BASE}/${encodeURIComponent(memoryId)}`
      );
    } catch (err: unknown) {
      if (err instanceof APIRequestError && err.status === 404) {
        return null;
      }
      throw err;
    }
  }

  const { data, error } = await supabase
    .from('memories')
    .select(MEMORY_SELECT_COLUMNS)
    .eq('id', memoryId)
    .maybeSingle();

  if (error) {
    console.error('Error getting memory:', error);
    throw new Error(error.message);
  }

  return (data ?? null) as Memory | null;
}

/**
 * Search memories using text search
 */
export async function searchMemories(
  query: string,
  limit: number = API_LIMITS.SEARCH_RESULTS,
  minConfidence: number = 0,
  reviewStatus?: ReviewStatus
): Promise<Memory[]> {
  const trimmed = (query || '').trim();
  if (!trimmed) {
    return [];
  }

  if (reviewStatus || (await shouldUseBackendReads())) {
    const qs = buildQueryString({
      query: trimmed,
      limit,
      min_confidence: minConfidence,
      review_status: reviewStatus || undefined,
    });
    return apiClient.get<Memory[]>(`${MEMORY_API_BASE}/search${qs}`);
  }

  const escapedQuery = escapeLikePattern(trimmed);

  const { data, error } = await supabase
    .from('memories')
    .select(MEMORY_SELECT_COLUMNS)
    .ilike('content', `%${escapedQuery}%`)
    .eq('review_status', reviewStatus || 'approved')
    .gte('confidence_score', minConfidence)
    .order('confidence_score', { ascending: false })
    .limit(limit);

  if (error) {
    console.error('Error searching memories:', error);
    throw new Error(error.message);
  }

  return (data || []) as Memory[];
}

/**
 * Get all entities
 */
export async function getEntities(
  entityTypes?: EntityType[],
  limit: number = API_LIMITS.MAX_ENTITIES
): Promise<MemoryEntity[]> {
  if (await shouldUseBackendReads()) {
    const qs = new URLSearchParams();
    qs.set('limit', String(limit));
    if (entityTypes && entityTypes.length > 0) {
      entityTypes.forEach((type) => qs.append('entity_types', type));
    }
    return apiClient.get<MemoryEntity[]>(
      `${MEMORY_API_BASE}/entities?${qs.toString()}`
    );
  }

  let query = supabase
    .from('memory_entities')
    .select('*')
    .order('occurrence_count', { ascending: false })
    .limit(limit);

  if (entityTypes && entityTypes.length > 0) {
    query = query.in('entity_type', entityTypes);
  }

  const { data, error } = await query;

  if (error) {
    console.error('Error getting entities:', error);
    throw new Error(error.message);
  }

  return (data || []) as MemoryEntity[];
}

/**
 * Get all relationships
 */
export async function getRelationships(
  limit: number = API_LIMITS.MAX_RELATIONSHIPS
): Promise<MemoryRelationship[]> {
  if (await shouldUseBackendReads()) {
    const qs = buildQueryString({ limit });
    return apiClient.get<MemoryRelationship[]>(
      `${MEMORY_API_BASE}/relationships${qs}`
    );
  }

  const { data, error } = await supabase
    .from('memory_relationships')
    .select('*')
    .order('occurrence_count', { ascending: false })
    .limit(limit);

  if (error) {
    console.error('Error getting relationships:', error);
    throw new Error(error.message);
  }

  return (data || []) as MemoryRelationship[];
}

/**
 * Get memories related to a given entity (via relationship provenance).
 */
export async function getEntityRelatedMemories(
  entityId: string,
  limit: number = 20
): Promise<Memory[]> {
  const trimmed = (entityId || '').trim();
  if (!trimmed) return [];

  if (await shouldUseBackendReads()) {
    const qs = buildQueryString({ limit });
    return apiClient.get<Memory[]>(
      `${MEMORY_API_BASE}/entities/${encodeURIComponent(trimmed)}/memories${qs}`
    );
  }

  const { data: relationships, error: relError } = await supabase
    .from('memory_relationships')
    .select('source_memory_id,last_seen_at')
    .or(`source_entity_id.eq.${trimmed},target_entity_id.eq.${trimmed}`)
    .not('source_memory_id', 'is', null)
    .order('last_seen_at', { ascending: false })
    .limit(1000);

  if (relError) {
    console.error('Error getting entity relationships:', relError);
    throw new Error(relError.message);
  }

  type RelationshipProvenanceRow = {
    source_memory_id: string | null;
    last_seen_at?: string;
  };

  const memoryIds: string[] = [];
  const seen = new Set<string>();
  ((relationships || []) as RelationshipProvenanceRow[]).forEach((row) => {
    const memoryId = row.source_memory_id;
    if (!memoryId) return;
    if (seen.has(memoryId)) return;
    seen.add(memoryId);
    memoryIds.push(memoryId);
  });

  const limitedIds = memoryIds.slice(0, Math.max(1, limit));
  if (limitedIds.length === 0) return [];

  const { data: memories, error: memError } = await supabase
    .from('memories')
    .select(MEMORY_SELECT_COLUMNS)
    .in('id', limitedIds);

  if (memError) {
    console.error('Error getting related memories:', memError);
    throw new Error(memError.message);
  }

  const memRows = (memories || []) as Memory[];
  const memMap = new Map(memRows.map((m) => [m.id, m]));
  return limitedIds
    .map((id) => memMap.get(id))
    .filter((m): m is Memory => Boolean(m));
}

/**
 * Get duplicate candidates for review
 */
export async function getDuplicateCandidates(
  status: 'pending' | 'all' = 'pending',
  limit: number = API_LIMITS.DUPLICATE_CANDIDATES
): Promise<DuplicateCandidate[]> {
  if (await shouldUseBackendReads()) {
    const qs = buildQueryString({ status, limit });
    return apiClient.get<DuplicateCandidate[]>(
      `${MEMORY_API_BASE}/duplicates${qs}`
    );
  }

  let query = supabase
    .from('memory_duplicate_candidates')
    .select('*')
    .order('similarity_score', { ascending: false })
    .limit(limit);

  if (status === 'pending') {
    query = query.eq('status', 'pending');
  }

  const { data, error } = await query;

  if (error) {
    console.error('Error getting duplicate candidates:', error);
    throw new Error(error.message);
  }

  const candidates = (data || []) as DuplicateCandidate[];

  const memoryIds = new Set<string>();
  candidates.forEach((candidate) => {
    memoryIds.add(candidate.memory_id_1);
    memoryIds.add(candidate.memory_id_2);
  });

  if (memoryIds.size > 0) {
    const { data: memories, error: memError } = await supabase
      .from('memories')
      .select(MEMORY_SELECT_COLUMNS)
      .in('id', Array.from(memoryIds));

    if (!memError && memories) {
      const memoryMap = new Map(memories.map((m) => [m.id, m as Memory]));
      candidates.forEach((candidate) => {
        candidate.memory1 = memoryMap.get(candidate.memory_id_1);
        candidate.memory2 = memoryMap.get(candidate.memory_id_2);
      });
    }
  }

  return candidates;
}

// =============================================================================
// Graph Data Operations
// =============================================================================

/**
 * Build graph data from entities and relationships
 */
export async function getGraphData(
  entityTypes?: EntityType[]
): Promise<GraphData> {
  const [entities, relationships] = await Promise.all([
    getEntities(entityTypes),
    getRelationships(),
  ]);

  const entityIds = new Set(entities.map((entity) => entity.id));

  const nodes: GraphNode[] = entities.map((entity) => ({
    id: entity.id,
    entityType: entity.entity_type,
    entityName: entity.entity_name,
    displayLabel: entity.display_label || entity.entity_name.substring(0, 50),
    occurrenceCount: entity.occurrence_count,
    metadata: entity.metadata,
    firstSeenAt: entity.first_seen_at,
    lastSeenAt: entity.last_seen_at,
    acknowledgedAt: entity.acknowledged_at ?? null,
    lastModifiedAt: entity.last_modified_at ?? null,
    createdAt: entity.created_at,
    updatedAt: entity.updated_at,
    color: ENTITY_COLORS[entity.entity_type] || '#6B7280',
    size: Math.max(4, Math.min(20, entity.occurrence_count * 2)),
  }));

  const links: GraphLink[] = relationships
    .filter(
      (rel) =>
        entityIds.has(rel.source_entity_id) &&
        entityIds.has(rel.target_entity_id)
    )
    .map((rel) => ({
      id: rel.id,
      source: rel.source_entity_id,
      target: rel.target_entity_id,
      relationshipType: rel.relationship_type,
      weight: rel.weight,
      occurrenceCount: rel.occurrence_count,
      acknowledgedAt: rel.acknowledged_at ?? null,
      lastModifiedAt: rel.last_modified_at ?? null,
    }));

  return { nodes, links };
}

/**
 * Get entity by ID with its relationships
 */
export async function getEntityWithRelationships(entityId: string): Promise<{
  entity: MemoryEntity;
  incomingRelationships: MemoryRelationship[];
  outgoingRelationships: MemoryRelationship[];
} | null> {
  const [entityResult, incomingResult, outgoingResult] = await Promise.all([
    supabase.from('memory_entities').select('*').eq('id', entityId).maybeSingle(),
    supabase.from('memory_relationships').select('*').eq('target_entity_id', entityId),
    supabase.from('memory_relationships').select('*').eq('source_entity_id', entityId),
  ]);

  if (entityResult.error || !entityResult.data) {
    return null;
  }

  return {
    entity: entityResult.data as MemoryEntity,
    incomingRelationships: (incomingResult.data || []) as MemoryRelationship[],
    outgoingRelationships: (outgoingResult.data || []) as MemoryRelationship[],
  };
}

// =============================================================================
// Export API object for convenience
// =============================================================================

export const memoryAPI = {
  // Write operations
  addMemory,
  updateMemory,
  deleteMemory,
  deleteRelationship,
  mergeMemories,
  mergeMemoriesArbitrary,
  submitFeedback,
  exportMemories,
  dismissDuplicate,
  importMemorySources,
  importZendeskTagged,
  approveMemory,
  updateRelationship,
  mergeRelationships,
  splitRelationshipPreview,
  splitRelationshipCommit,
  analyzeRelationship,
  getMemoryMe,
  acknowledgeEntity,
  acknowledgeRelationship,
  getMemoryStats,
  // Read operations
  listMemories,
  getMemoryById,
  searchMemories,
  getEntities,
  getRelationships,
  getEntityRelatedMemories,
  getDuplicateCandidates,
  getGraphData,
  getEntityWithRelationships,
};
