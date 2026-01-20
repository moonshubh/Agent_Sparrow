/**
 * Memory UI Type Definitions
 *
 * Comprehensive TypeScript types for the Memory UI system including
 * memories, entities, relationships, duplicates, and statistics.
 */

// =============================================================================
// Enums
// =============================================================================

export type SourceType = 'auto_extracted' | 'manual';

export type FeedbackType =
  | 'thumbs_up'
  | 'thumbs_down'
  | 'resolution_success'
  | 'resolution_failure';

export type EntityType =
  | 'product'
  | 'feature'
  | 'issue'
  | 'solution'
  | 'platform'
  | 'version'
  | 'customer'
  | 'error';

export type RelationshipType =
  | 'RESOLVED_BY'
  | 'AFFECTS'
  | 'REQUIRES'
  | 'CAUSED_BY'
  | 'REPORTED_BY'
  | 'WORKS_ON'
  | 'RELATED_TO'
  | 'SUPERSEDES';

export type DuplicateStatus = 'pending' | 'merged' | 'dismissed' | 'superseded';

// =============================================================================
// Core Models
// =============================================================================

export interface Memory {
  id: string;
  content: string;
  metadata: Record<string, unknown>;
  source_type: SourceType;
  confidence_score: number;
  retrieval_count: number;
  last_retrieved_at: string | null;
  feedback_positive: number;
  feedback_negative: number;
  resolution_success_count: number;
  resolution_failure_count: number;
  agent_id: string;
  tenant_id: string;
  created_at: string;
  updated_at: string;
}

export interface MemoryEntity {
  id: string;
  entity_type: EntityType;
  entity_name: string;
  normalized_name: string;
  display_label: string | null;
  first_seen_at: string;
  last_seen_at: string;
  last_modified_at?: string | null;
  acknowledged_at?: string | null;
  occurrence_count: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface MemoryRelationship {
  id: string;
  source_entity_id: string;
  target_entity_id: string;
  relationship_type: RelationshipType;
  weight: number;
  occurrence_count: number;
  source_memory_id: string | null;
  first_seen_at: string;
  last_seen_at: string;
  last_modified_at?: string | null;
  acknowledged_at?: string | null;
  created_at: string;
}

export interface DuplicateCandidate {
  id: string;
  memory_id_1: string;
  memory_id_2: string;
  similarity_score: number;
  status: DuplicateStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  merge_target_id: string | null;
  detected_at: string;
  detection_method: string;
  // Expanded memories for UI display
  memory1?: Memory;
  memory2?: Memory;
}

export interface MemoryFeedback {
  id: string;
  memory_id: string;
  user_id: string | null;
  feedback_type: FeedbackType;
  session_id: string | null;
  ticket_id: string | null;
  notes: string | null;
  created_at: string;
}

// =============================================================================
// Graph Data Types
// =============================================================================

export interface GraphNode {
  id: string;
  entityType: EntityType;
  entityName: string;
  displayLabel: string;
  occurrenceCount: number;
  metadata?: Record<string, unknown>;
  firstSeenAt?: string;
  lastSeenAt?: string;
  acknowledgedAt?: string | null;
  lastModifiedAt?: string | null;
  createdAt?: string;
  updatedAt?: string;
  // Positioning for 3D graph
  x?: number;
  y?: number;
  z?: number;
  // Visual properties
  color?: string;
  size?: number;
}

export interface GraphLink {
  id: string;
  source: string;
  target: string;
  relationshipType: RelationshipType;
  weight: number;
  occurrenceCount: number;
  acknowledgedAt?: string | null;
  lastModifiedAt?: string | null;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

// =============================================================================
// Radial Tree Types (Memory Visualization)
// =============================================================================

export type TreeViewMode = 'celebrate_strengths' | 'surface_gaps';

export interface TreeEdge {
  sourceId: string;
  targetId: string;
  occurrenceCount: number;
  weight: number;
  relationshipTypes: RelationshipType[];
  relationships: Array<{
    id: string;
    relationshipType: RelationshipType;
    weight: number;
    occurrenceCount: number;
    sourceId: string;
    targetId: string;
    acknowledgedAt?: string | null;
    lastModifiedAt?: string | null;
  }>;
}

export interface TreeNodeData {
  id: string;
  node: GraphNode;
  children: TreeNodeData[];
  parentId: string | null;
  depth: number;
  parentEdge?: TreeEdge;
}

export interface CycleEdge {
  sourceId: string;
  targetId: string;
  occurrenceCount: number;
  weight: number;
}

export interface OrphanEntity {
  id: string;
  node: GraphNode;
}

export interface TreeTransformResult {
  root: TreeNodeData;
  rootId: string;
  byId: Map<string, TreeNodeData>;
  treeEdges: TreeEdge[];
  cycleEdges: CycleEdge[];
  orphans: OrphanEntity[];
}

// =============================================================================
// API Request Types
// =============================================================================

export interface AddMemoryRequest {
  content: string;
  metadata?: Record<string, unknown>;
  source_type?: SourceType;
  agent_id?: string;
  tenant_id?: string;
}

export interface UpdateMemoryRequest {
  content?: string;
  metadata?: Record<string, unknown>;
}

export interface MergeMemoriesRequest {
  duplicate_candidate_id: string;
  keep_memory_id: string;
  merge_content?: string;
}

export interface MergeMemoriesArbitraryRequest {
  keep_memory_id: string;
  merge_memory_ids: string[];
  merge_content?: string;
}

export interface SubmitFeedbackRequest {
  feedback_type: FeedbackType;
  session_id?: string;
  ticket_id?: string;
  notes?: string;
}

export interface ExportFilters {
  entity_types?: EntityType[];
  min_confidence?: number;
  created_after?: string;
}

export interface ExportMemoriesRequest {
  format: 'json';
  filters?: ExportFilters;
}

export interface DismissDuplicateRequest {
  notes?: string;
}

export interface SearchMemoriesRequest {
  query: string;
  limit?: number;
  min_confidence?: number;
  agent_id?: string;
  tenant_id?: string;
}

export interface ListMemoriesRequest {
  limit?: number;
  offset?: number;
  agent_id?: string;
  tenant_id?: string;
  source_type?: SourceType;
  sort_order?: 'asc' | 'desc';
}

export interface ImportMemorySourcesRequest {
  include_issue_resolutions?: boolean;
  include_playbook_entries?: boolean;
  include_playbook_files?: boolean;
  playbook_statuses?: string[];
  limit?: number;
  include_playbook_embeddings?: boolean;
  include_mem0_primary?: boolean;
}

export interface UpdateRelationshipRequest {
  source_entity_id: string;
  target_entity_id: string;
  relationship_type: RelationshipType;
  weight: number;
}

export interface MergeRelationshipsRequest {
  relationship_ids: string[];
  source_entity_id: string;
  target_entity_id: string;
  relationship_type: RelationshipType;
  weight: number;
}

export interface SplitRelationshipPreviewRequest {
  max_memories?: number;
  max_clusters?: number;
  cluster_count?: number | null;
  samples_per_cluster?: number;
  use_ai?: boolean;
}

export interface SplitRelationshipCommitCluster {
  name?: string | null;
  source_entity_id: string;
  target_entity_id: string;
  relationship_type: RelationshipType;
  weight: number;
  memory_ids: string[];
}

export interface SplitRelationshipCommitRequest {
  clusters: SplitRelationshipCommitCluster[];
}

// =============================================================================
// API Response Types
// =============================================================================

export interface ListMemoriesResponse {
  items: Memory[];
  total: number;
  limit: number;
  offset: number;
}

export interface AddMemoryResponse {
  id: string;
  content: string;
  confidence_score: number;
  source_type: SourceType;
  entities_extracted: number;
  relationships_created: number;
  created_at: string;
}

export interface UpdateMemoryResponse {
  id: string;
  content: string;
  updated_at: string;
}

export interface DeleteMemoryResponse {
  deleted: boolean;
  entities_orphaned: number;
  relationships_removed: number;
}

export interface DeleteRelationshipResponse {
  deleted: boolean;
  relationship_id: string;
}

export interface MergeMemoriesResponse {
  merged_memory_id: string;
  deleted_memory_id: string;
  confidence_score: number;
  entities_transferred: number;
}

export interface MergeMemoriesArbitraryResponse {
  merged_memory_id: string;
  deleted_memory_ids: string[];
  duplicate_candidate_ids: string[];
  confidence_score: number;
  entities_transferred: number;
}

export interface SubmitFeedbackResponse {
  feedback_id: string;
  new_confidence_score: number;
}

export interface ExportMemoriesResponse {
  export_id: string;
  download_url: string;
  memory_count: number;
  entity_count: number;
  relationship_count: number;
}

export interface DismissDuplicateResponse {
  candidate_id: string;
  status: string;
}

export interface ImportMemorySourcesResponse {
  issue_resolutions_imported: number;
  issue_resolutions_skipped: number;
  issue_resolutions_failed: number;
  playbook_entries_imported: number;
  playbook_entries_skipped: number;
  playbook_entries_failed: number;
  playbook_files_imported: number;
  playbook_files_skipped: number;
  playbook_files_failed: number;
  mem0_primary_imported: number;
  mem0_primary_skipped: number;
  mem0_primary_failed: number;
}

export interface MergeRelationshipsResponse {
  merged_relationship: MemoryRelationship;
  deleted_relationship_ids: string[];
}

export interface SplitRelationshipClusterSample {
  id: string;
  content_preview: string;
  confidence_score?: number | null;
  created_at?: string | null;
}

export interface SplitRelationshipClusterSuggestion {
  cluster_id: number;
  name: string;
  source_entity_id: string;
  target_entity_id: string;
  relationship_type: RelationshipType;
  weight: number;
  occurrence_count: number;
  memory_ids: string[];
  samples: SplitRelationshipClusterSample[];
}

export interface SplitRelationshipPreviewResponse {
  relationship_id: string;
  source_entity_id: string;
  target_entity_id: string;
  existing_relationship_ids: string[];
  clusters: SplitRelationshipClusterSuggestion[];
  used_ai: boolean;
  ai_model_id?: string | null;
  ai_error?: string | null;
}

export interface SplitRelationshipCommitResponse {
  source_entity_id: string;
  target_entity_id: string;
  deleted_relationship_ids: string[];
  created_relationships: MemoryRelationship[];
}

export interface RelationshipAnalysisRequest {
  max_direct_memories?: number;
  max_neighbor_edges?: number;
  max_neighbor_memories?: number;
  use_ai?: boolean;
}

export interface RelationshipAnalysisResponse {
  relationship_id: string;
  source_entity_id: string;
  target_entity_id: string;
  checklist: RelationshipChecklistItem[];
  actions: RelationshipSuggestedAction[];
  analysis_markdown: string;
  used_ai: boolean;
  ai_model_id?: string | null;
  ai_error?: string | null;
  direct_memory_count: number;
  neighbor_edge_count: number;
  neighbor_memory_count: number;
}

export interface RelationshipChecklistItem {
  id: string;
  title: string;
  category: string;
  why?: string | null;
  memory_ids?: string[];
  entity_ids?: string[];
}

export type RelationshipSuggestedActionKind =
  | 'update_relationship'
  | 'merge_relationships'
  | 'split_relationship_commit'
  | 'update_memory'
  | 'delete_memory'
  | 'merge_memories_arbitrary'
  | 'delete_relationship';

export interface RelationshipSuggestedAction {
  id: string;
  title: string;
  kind: RelationshipSuggestedActionKind;
  confidence: number;
  destructive: boolean;
  payload: Record<string, unknown>;
  memory_ids: string[];
  entity_ids: string[];
  relationship_ids: string[];
}

export interface MemoryMeResponse {
  sub?: string | null;
  roles: string[];
  is_admin: boolean;
}

export interface MemoryStats {
  total_memories: number;
  total_entities: number;
  total_relationships: number;
  pending_duplicates: number;
  high_confidence: number;
  medium_confidence: number;
  low_confidence: number;
  entity_types: Record<string, number>;
  relationship_types: Record<string, number>;
}

// =============================================================================
// UI State Types
// =============================================================================

export interface MemoryFilters {
  searchQuery: string;
  entityTypes: EntityType[];
  minConfidence: number;
  sourceType: SourceType | null;
  sortBy: 'confidence' | 'created_at' | 'retrieval_count';
  sortOrder: 'asc' | 'desc';
}

export interface MemoryViewMode {
  mode: 'graph' | 'table' | 'duplicates';
}

export interface SelectedMemory {
  memory: Memory;
  entities: MemoryEntity[];
  relationships: MemoryRelationship[];
}

// =============================================================================
// Shared Constants
// =============================================================================

export const ALL_ENTITY_TYPES: readonly EntityType[] = [
  'product',
  'feature',
  'issue',
  'solution',
  'platform',
  'version',
  'customer',
  'error',
] as const;

// =============================================================================
// Entity Type Colors for Graph (Mailbird Brand Scheme)
// =============================================================================

export const ENTITY_COLORS: Record<EntityType, string> = {
  product: '#0078D4',       // Mailbird Blue (Primary)
  feature: '#10B981',       // Emerald
  issue: '#EF4444',         // Red
  solution: '#22C55E',      // Green
  platform: '#F59E0B',      // Amber
  version: '#38BDF8',       // Sky Blue
  customer: '#14B8A6',      // Teal
  error: '#F43F5E',         // Rose
};

export const ENTITY_LABELS: Record<EntityType, string> = {
  product: 'Product',
  feature: 'Feature',
  issue: 'Issue',
  solution: 'Solution',
  platform: 'Platform',
  version: 'Version',
  customer: 'Customer',
  error: 'Error',
};

export const RELATIONSHIP_LABELS: Record<RelationshipType, string> = {
  RESOLVED_BY: 'Resolved By',
  AFFECTS: 'Affects',
  REQUIRES: 'Requires',
  CAUSED_BY: 'Caused By',
  REPORTED_BY: 'Reported By',
  WORKS_ON: 'Works On',
  RELATED_TO: 'Related To',
  SUPERSEDES: 'Supersedes',
};
