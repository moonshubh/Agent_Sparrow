/**
 * Memory UI Custom Hooks
 *
 * React Query hooks for fetching and mutating memory data.
 * Provides caching, polling, and optimistic updates.
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseMutationOptions,
} from "@tanstack/react-query";
import { memoryAPI, TIMING } from "../lib/api";
import type {
  Memory,
  MemoryMeResponse,
  MemoryStats,
  GraphData,
  DuplicateCandidate,
  EntityType,
  AddMemoryRequest,
  AddMemoryResponse,
  UpdateMemoryRequest,
  MergeMemoriesRequest,
  MergeMemoriesArbitraryRequest,
  MergeMemoriesArbitraryResponse,
  SubmitFeedbackRequest,
  FeedbackType,
  ListMemoriesRequest,
  ListMemoriesResponse,
  ImportMemorySourcesRequest,
  ImportZendeskTaggedRequest,
  UpdateRelationshipRequest,
  MergeRelationshipsRequest,
  SplitRelationshipPreviewRequest,
  SplitRelationshipPreviewResponse,
  SplitRelationshipCommitRequest,
  SplitRelationshipCommitResponse,
  RelationshipAnalysisRequest,
  RelationshipAnalysisResponse,
} from "../types";

// =============================================================================
// Query Keys
// =============================================================================

export const memoryKeys = {
  all: ["memory"] as const,
  me: () => [...memoryKeys.all, "me"] as const,
  lists: () => [...memoryKeys.all, "list"] as const,
  list: (filters: ListMemoriesRequest) =>
    [...memoryKeys.lists(), filters] as const,
  details: () => [...memoryKeys.all, "detail"] as const,
  detail: (id: string) => [...memoryKeys.details(), id] as const,
  stats: () => [...memoryKeys.all, "stats"] as const,
  entityMemories: (entityId: string, limit: number) =>
    [...memoryKeys.all, "entity-memories", entityId, limit] as const,
  // Base graph key for invalidation (matches all graph queries regardless of entityTypes)
  graphBase: () => [...memoryKeys.all, "graph"] as const,
  graph: (entityTypes?: EntityType[]) =>
    [...memoryKeys.graphBase(), entityTypes] as const,
  // Base duplicates key for invalidation (matches both 'pending' and 'all')
  duplicatesBase: () => [...memoryKeys.all, "duplicates"] as const,
  duplicates: (status: "pending" | "all") =>
    [...memoryKeys.duplicatesBase(), status] as const,
  searches: () => [...memoryKeys.all, "search"] as const,
  search: (query: string) => [...memoryKeys.searches(), query] as const,
};

// =============================================================================
// Query Hooks
// =============================================================================

/**
 * Hook to fetch memory statistics
 */
export function useMemoryStats(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: memoryKeys.stats(),
    queryFn: () => memoryAPI.getMemoryStats(),
    staleTime: TIMING.STATS_STALE_TIME_MS,
    refetchInterval: TIMING.STATS_POLL_INTERVAL_MS,
    enabled: options?.enabled ?? true,
  });
}

/**
 * Hook to fetch current user + roles for Memory UI gating
 */
export function useMemoryMe(options?: { enabled?: boolean }) {
  return useQuery<MemoryMeResponse>({
    queryKey: memoryKeys.me(),
    queryFn: () => memoryAPI.getMemoryMe(),
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
    enabled: options?.enabled ?? true,
  });
}

/**
 * Hook to fetch graph data for visualization
 */
export function useMemoryGraph(options?: {
  entityTypes?: EntityType[];
  enabled?: boolean;
  pollInterval?: number;
}) {
  const {
    entityTypes,
    enabled = true,
    pollInterval = TIMING.GRAPH_POLL_INTERVAL_MS,
  } = options || {};

  return useQuery({
    queryKey: memoryKeys.graph(entityTypes),
    queryFn: () => memoryAPI.getGraphData(entityTypes),
    staleTime: TIMING.GRAPH_STALE_TIME_MS,
    refetchInterval: pollInterval,
    enabled,
  });
}

/**
 * Hook to fetch list of memories
 */
export function useMemories(
  params?: ListMemoriesRequest,
  options?: {
    enabled?: boolean;
  },
) {
  return useQuery<ListMemoriesResponse>({
    queryKey: memoryKeys.list(params || {}),
    queryFn: () => memoryAPI.listMemories(params),
    staleTime: 30 * 1000,
    enabled: options?.enabled ?? true,
  });
}

/**
 * Hook to fetch a single memory by ID
 */
export function useMemory(memoryId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: memoryKeys.detail(memoryId),
    queryFn: () => memoryAPI.getMemoryById(memoryId),
    enabled: !!memoryId && (options?.enabled ?? true),
  });
}

/**
 * Hook to search memories
 */
export function useMemorySearch(
  query: string,
  options?: {
    limit?: number;
    minConfidence?: number;
    enabled?: boolean;
  },
) {
  const { limit = 20, minConfidence = 0, enabled = true } = options || {};

  return useQuery({
    queryKey: memoryKeys.search(query),
    queryFn: () => memoryAPI.searchMemories(query, limit, minConfidence),
    enabled: enabled && query.length >= 2,
    staleTime: 30 * 1000,
  });
}

/**
 * Hook to fetch memories related to a given entity (via relationship provenance).
 */
export function useEntityRelatedMemories(
  entityId: string,
  options?: { enabled?: boolean; limit?: number },
) {
  const limit = options?.limit ?? 20;
  return useQuery({
    queryKey: memoryKeys.entityMemories(entityId, limit),
    queryFn: () => memoryAPI.getEntityRelatedMemories(entityId, limit),
    enabled: Boolean(entityId) && (options?.enabled ?? true),
    staleTime: 30 * 1000,
  });
}

/**
 * Hook to fetch duplicate candidates
 */
export function useDuplicateCandidates(
  status: "pending" | "all" = "pending",
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: memoryKeys.duplicates(status),
    queryFn: () => memoryAPI.getDuplicateCandidates(status),
    staleTime: 30 * 1000,
    refetchOnWindowFocus: true,
    enabled: options?.enabled ?? true,
  });
}

// =============================================================================
// Mutation Hooks
// =============================================================================

/**
 * Hook to add a new memory
 */
export function useAddMemory() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: AddMemoryRequest) => memoryAPI.addMemory(request),
    onSuccess: () => {
      // Invalidate related queries (use base keys for partial matching)
      queryClient.invalidateQueries({ queryKey: memoryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.searches() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.stats() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.graphBase() });
    },
  });
}

/**
 * Hook to update a memory
 */
export function useUpdateMemory() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      memoryId,
      request,
    }: {
      memoryId: string;
      request: UpdateMemoryRequest;
    }) => memoryAPI.updateMemory(memoryId, request),
    onSuccess: (_, { memoryId }) => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.detail(memoryId) });
      queryClient.invalidateQueries({ queryKey: memoryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.searches() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.stats() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.graphBase() });
    },
  });
}

/**
 * Hook to delete a memory
 */
export function useDeleteMemory() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (memoryId: string) => memoryAPI.deleteMemory(memoryId),
    onSuccess: (_, memoryId) => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.detail(memoryId) });
      queryClient.invalidateQueries({ queryKey: memoryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.searches() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.stats() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.graphBase() });
    },
  });
}

/**
 * Hook to merge explicit memory IDs into one (admin only)
 */
export function useMergeMemoriesArbitrary() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (
      request: MergeMemoriesArbitraryRequest,
    ): Promise<MergeMemoriesArbitraryResponse> =>
      memoryAPI.mergeMemoriesArbitrary(request),
    onSuccess: (_, request) => {
      queryClient.invalidateQueries({
        queryKey: memoryKeys.detail(request.keep_memory_id),
      });
      queryClient.invalidateQueries({ queryKey: memoryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.searches() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.stats() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.graphBase() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.duplicatesBase() });
    },
  });
}

/**
 * Hook to submit feedback for a memory
 */
export function useSubmitFeedback() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      memoryId,
      request,
    }: {
      memoryId: string;
      request: SubmitFeedbackRequest;
    }) => memoryAPI.submitFeedback(memoryId, request),
    onSuccess: (response, { memoryId, request }) => {
      const applyFeedback = (memory: Memory): Memory => {
        const next = { ...memory };
        const type = request.feedback_type;
        if (type === "thumbs_up") next.feedback_positive += 1;
        if (type === "thumbs_down") next.feedback_negative += 1;
        if (type === "resolution_success") next.resolution_success_count += 1;
        if (type === "resolution_failure") next.resolution_failure_count += 1;
        if (typeof response.new_confidence_score === "number") {
          next.confidence_score = response.new_confidence_score;
        }
        return next;
      };

      // Detail cache
      queryClient.setQueryData(
        memoryKeys.detail(memoryId),
        (prev: Memory | undefined | null) =>
          prev ? applyFeedback(prev) : prev,
      );

      // Lists (paginated)
      queryClient.setQueriesData(
        { queryKey: memoryKeys.lists(), type: "all" },
        (prev: ListMemoriesResponse | undefined) => {
          if (!prev) return prev;
          const items = prev.items.map((m) =>
            m.id === memoryId ? applyFeedback(m) : m,
          );
          return { ...prev, items };
        },
      );

      // Searches
      queryClient.setQueriesData(
        { queryKey: memoryKeys.searches(), type: "all" },
        (prev: Memory[] | undefined) => {
          if (!prev) return prev;
          return prev.map((m) => (m.id === memoryId ? applyFeedback(m) : m));
        },
      );

      queryClient.invalidateQueries({ queryKey: memoryKeys.detail(memoryId) });
      queryClient.invalidateQueries({ queryKey: memoryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.searches() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.stats() });
    },
  });
}

/**
 * Hook to merge duplicate memories
 */
export function useMergeMemories() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: MergeMemoriesRequest) =>
      memoryAPI.mergeMemories(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.searches() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.duplicatesBase() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.stats() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.graphBase() });
    },
  });
}

/**
 * Hook to dismiss a duplicate candidate
 */
export function useDismissDuplicate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      candidateId,
      notes,
    }: {
      candidateId: string;
      notes?: string;
    }) => memoryAPI.dismissDuplicate(candidateId, { notes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.duplicatesBase() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.stats() });
    },
  });
}

/**
 * Hook to export memories
 */
export function useExportMemories() {
  return useMutation({
    mutationFn: memoryAPI.exportMemories,
  });
}

/**
 * Hook to import existing knowledge sources into Memory UI (admin only)
 */
export function useImportMemorySources() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: ImportMemorySourcesRequest) =>
      memoryAPI.importMemorySources(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.searches() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.stats() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.graphBase() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.duplicatesBase() });
    },
  });
}

/**
 * Hook to import solved Zendesk tickets tagged for MB_playbook learning (admin only)
 */
export function useImportZendeskTagged() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: ImportZendeskTaggedRequest) =>
      memoryAPI.importZendeskTagged(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.searches() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.stats() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.graphBase() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.duplicatesBase() });
    },
  });
}

/**
 * Hook to update relationship metadata (admin only)
 */
export function useUpdateRelationship() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      relationshipId,
      request,
    }: {
      relationshipId: string;
      request: UpdateRelationshipRequest;
    }) => memoryAPI.updateRelationship(relationshipId, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.graphBase() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.stats() });
    },
  });
}

/**
 * Hook to delete a relationship (admin only)
 */
export function useDeleteRelationship() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (relationshipId: string) =>
      memoryAPI.deleteRelationship(relationshipId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.graphBase() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.stats() });
    },
  });
}

/**
 * Hook to merge relationships (admin only)
 */
export function useMergeRelationships() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: MergeRelationshipsRequest) =>
      memoryAPI.mergeRelationships(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.graphBase() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.stats() });
    },
  });
}

/**
 * Hook to preview an AI-assisted relationship split (admin only)
 */
export function useSplitRelationshipPreview(
  options?: UseMutationOptions<
    SplitRelationshipPreviewResponse,
    Error,
    {
      relationshipId: string;
      request: SplitRelationshipPreviewRequest;
    }
  >,
) {
  return useMutation({
    mutationFn: ({
      relationshipId,
      request,
    }: {
      relationshipId: string;
      request: SplitRelationshipPreviewRequest;
    }): Promise<SplitRelationshipPreviewResponse> =>
      memoryAPI.splitRelationshipPreview(relationshipId, request),
    ...options,
  });
}

/**
 * Hook to commit an AI-assisted relationship split (admin only)
 */
export function useSplitRelationshipCommit() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      relationshipId,
      request,
    }: {
      relationshipId: string;
      request: SplitRelationshipCommitRequest;
    }): Promise<SplitRelationshipCommitResponse> =>
      memoryAPI.splitRelationshipCommit(relationshipId, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.graphBase() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.stats() });
    },
  });
}

/**
 * Hook to analyze a relationship edge (admin only)
 */
export function useRelationshipAnalysis() {
  return useMutation({
    mutationFn: ({
      relationshipId,
      request,
    }: {
      relationshipId: string;
      request: RelationshipAnalysisRequest;
    }): Promise<RelationshipAnalysisResponse> =>
      memoryAPI.analyzeRelationship(relationshipId, request),
  });
}

/**
 * Hook to acknowledge (mark reviewed) a memory entity.
 */
export function useAcknowledgeEntity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (entityId: string) => memoryAPI.acknowledgeEntity(entityId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.graphBase() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.stats() });
    },
  });
}

/**
 * Hook to acknowledge (mark reviewed) a memory relationship.
 */
export function useAcknowledgeRelationship() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (relationshipId: string) =>
      memoryAPI.acknowledgeRelationship(relationshipId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.graphBase() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.stats() });
    },
  });
}
