/**
 * FeedMe API Client
 *
 * Canonical frontend contract for FeedMe endpoints.
 * - Uses backend source-of-truth contracts
 * - Sends auth headers on mutation/admin routes
 * - Provides compatibility exports for existing store usage
 */

import { getApiBaseUrl } from '@/shared/lib/utils/environment';
import { apiMonitor } from '@/services/api/api-monitor';
import backendHealthMonitor from '@/services/monitoring/backend-health-check';
import { supabase } from '@/services/supabase';
import { getAuthToken as getLocalAuthToken } from '@/services/auth/local-auth';

// Re-export platform type from shared types.
export type { PlatformType } from '@/shared/types/feedme';
import type { PlatformType } from '@/shared/types/feedme';

export class ApiUnreachableError extends Error {
  public readonly errorType?: 'timeout' | 'network' | 'server' | 'unknown';
  public readonly timestamp: Date;
  public readonly url?: string;

  constructor(
    message: string,
    public readonly originalError?: Error,
    errorType?: 'timeout' | 'network' | 'server' | 'unknown',
    url?: string,
  ) {
    super(message);
    this.name = 'ApiUnreachableError';
    this.errorType = errorType;
    this.timestamp = new Date();
    this.url = url;
  }
}

const SUPERSEDED_REQUEST_MESSAGE = 'Request superseded by a newer action';

export const isSupersededRequestError = (error: unknown): boolean =>
  error instanceof ApiUnreachableError &&
  error.message === SUPERSEDED_REQUEST_MESSAGE;

const TIMEOUT_CONFIGS = {
  quick: { timeout: 10000, retries: 2 },
  standard: { timeout: 30000, retries: 3 },
  heavy: { timeout: 60000, retries: 2 },
  database: { timeout: 45000, retries: 2 },
} as const;

const activeRequests = new Map<string, AbortController>();
const supersededRequests = new WeakSet<AbortController>();

const getRetryDelay = (attempt: number, maxRetries: number): number => {
  const attemptNumber = maxRetries - attempt;
  const baseDelay = Math.min(Math.pow(2, attemptNumber) * 1000, 8000);
  const jitter = Math.random() * 1000;
  return baseDelay + jitter;
};

const resolvedBaseFromEnv = process.env.NEXT_PUBLIC_API_BASE;
const resolvedBaseFromUtils = getApiBaseUrl();
const API_BASE =
  resolvedBaseFromEnv ||
  resolvedBaseFromUtils ||
  (process.env.NODE_ENV === 'development'
    ? 'http://localhost:8000/api/v1'
    : '/api/v1');
const FEEDME_API_BASE = `${API_BASE}/feedme`;

export type ProcessingStatusValue =
  | 'pending'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type ProcessingStageValue =
  | 'queued'
  | 'parsing'
  | 'ai_extraction'
  | 'embedding_generation'
  | 'quality_assessment'
  | 'completed'
  | 'failed';

export type OSCategory = 'windows' | 'macos' | 'both' | 'uncategorized';

export const PLATFORM_LABELS: Record<PlatformType, string> = {
  windows: 'Windows',
  macos: 'macOS',
  both: 'Both Windows and macOS',
};

export const PLATFORM_OPTIONS: { value: PlatformType; label: string }[] = [
  { value: 'windows', label: 'Windows' },
  { value: 'macos', label: 'macOS' },
  { value: 'both', label: 'Both Windows and macOS' },
];

export interface UploadTranscriptRequest {
  title: string;
  uploaded_by?: string;
  auto_process?: boolean;
}

export interface UploadTranscriptResponse {
  conversation_id: number;
  id?: number;
  title?: string;
  processing_status: ProcessingStatusValue;
  total_examples?: number;
  created_at?: string;
  updated_at?: string;
  metadata?: Record<string, unknown>;
  approval_status?: 'pending' | 'approved' | 'rejected' | 'awaiting_review';
  folder_id?: number | null;
  processing_method?: string;
  extracted_text?: string;
  os_category?: OSCategory;
  message?: string;
  duplicate?: boolean;
  duplicate_conversation_id?: number;
  upload_sha256?: string;
}

export interface ProcessingStatusResponse {
  conversation_id: number;
  status: ProcessingStatusValue;
  stage: ProcessingStageValue;
  progress_percentage: number;
  message?: string;
  error_message?: string;
  processing_started_at?: string;
  processing_completed_at?: string;
  processing_time_ms?: number;
  metadata?: Record<string, unknown>;
  examples_extracted?: number;
  estimated_completion?: string;
}

export interface ConversationListResponse {
  conversations: UploadTranscriptResponse[];
  total_count: number;
  page: number;
  page_size: number;
  has_next: boolean;
  total_conversations?: number;
  total_pages?: number;
}

export interface ApprovalRequest {
  approved_by?: string;
  approval_notes?: string;
  reviewer_notes?: string;
  tags?: string[];
}

export interface RejectionRequest {
  rejected_by?: string;
  rejection_reason?: string;
  rejection_notes?: string;
  reviewer_notes?: string;
}

export interface ApprovalResponse {
  conversation: UploadTranscriptResponse;
  approval_status?: string;
  action?: string;
  timestamp?: string;
  message: string;
}

export interface DeleteConversationResponse {
  conversation_id: number;
  title: string;
  examples_deleted: number;
  message: string;
}

export interface ApprovalWorkflowStats {
  total_conversations: number;
  pending_approval: number;
  awaiting_review: number;
  approved: number;
  rejected: number;
  published: number;
  currently_processing: number;
  processing_failed: number;
  avg_quality_score?: number;
  avg_processing_time_ms?: number;
  windows_count?: number;
  macos_count?: number;
}

export interface FeedMeExample {
  id: number;
  conversation_id: number;
  question?: string;
  answer?: string;
  question_text?: string;
  answer_text?: string;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
  metadata?: Record<string, unknown>;
  approval_status?: 'pending' | 'approved' | 'rejected' | 'awaiting_review';
}

export interface ExampleListResponse {
  examples: FeedMeExample[];
  total_examples: number;
  page: number;
  page_size: number;
  has_next?: boolean;
  total_pages?: number;
}

export interface SearchExamplesFilters {
  date_from?: string;
  date_to?: string;
  folder_ids?: number[];
  tags?: string[];
  min_confidence?: number;
  max_confidence?: number;
  platforms?: string[];
  status?: string[];
  min_quality_score?: number;
  max_quality_score?: number;
  issue_types?: string[];
  resolution_types?: string[];
}

export interface SearchExamplesRequest {
  query: string;
  page?: number;
  page_size?: number;
  filters?: SearchExamplesFilters;
  include_snippets?: boolean;
  highlight_matches?: boolean;
  sort_by?: string;
}

export interface SearchExampleResult {
  id: number;
  type: 'conversation' | 'example';
  title: string;
  snippet?: string | null;
  score: number;
  conversation_id: number;
  example_id?: number;
  folder_id?: number;
  folder_name?: string;
  tags?: string[];
  confidence_score: number;
  quality_score: number;
  issue_type?: string;
  resolution_type?: string;
  created_at: string;
  updated_at: string;
}

export interface SearchExamplesResponse {
  results: SearchExampleResult[];
  total_count: number;
  page: number;
  page_size: number;
  has_more: boolean;
  facets?: Record<string, unknown>;
}

export interface FeedMeFolder {
  id: number;
  name: string;
  description?: string;
  color?: string;
  parent_id?: number | null;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
  conversation_count?: number;
}

export interface FolderListResponse {
  folders: FeedMeFolder[];
  total_count: number;
}

export interface CreateFolderRequest {
  name: string;
  description?: string;
  color?: string;
  parent_id?: number | null;
  created_by?: string;
}

export interface UpdateFolderRequest {
  name?: string;
  description?: string;
  color?: string;
  parent_id?: number | null;
}

export interface FolderAssignmentFailure {
  conversation_id: number;
  reason: string;
}

export interface FolderAssignmentResponse {
  folder_id: number | null;
  folder_name: string;
  conversation_ids: number[];
  assigned_count: number;
  requested_count: number;
  failed: FolderAssignmentFailure[];
  partial_success: boolean;
  action: string;
  message: string;
}

export interface GeminiUsage {
  daily_used: number;
  daily_limit: number;
  rpm_limit: number;
  calls_in_window: number;
  window_seconds_remaining: number;
  utilization: {
    daily: number;
    rpm: number;
  };
  status: 'healthy' | 'warning';
  day: string;
}

export interface EmbeddingUsage {
  daily_used: number;
  daily_limit: number;
  rpm_limit: number;
  tpm_limit: number;
  calls_in_window: number;
  tokens_in_window: number;
  window_seconds_remaining: number;
  token_window_seconds_remaining: number;
  utilization: {
    daily: number;
    rpm: number;
    tpm: number;
  };
  status: 'healthy' | 'warning';
  day: string;
}

export interface FeedMeStatsOverviewResponse {
  time_range: {
    start_at: string;
    end_at: string;
    range_days: number;
  };
  filters: {
    folder_id: number | null;
    os_category: OSCategory | null;
  };
  cards: {
    queue_depth: number;
    failure_rate: number;
    p50_latency_ms: number;
    p95_latency_ms: number;
    assign_throughput: number;
    kb_ready_throughput: number;
    sla_warning_count: number;
    sla_breach_count: number;
  };
  os_distribution: Record<OSCategory, number>;
  sla_thresholds: {
    warning_minutes: number;
    breach_minutes: number;
  };
  total_conversations: number;
  generated_at: string;
}

export interface FeedMeSettings {
  tenant_id: string;
  kb_ready_folder_id: number | null;
  sla_warning_minutes: number;
  sla_breach_minutes: number;
  updated_at?: string | null;
}

export interface FeedMeSettingsUpdateRequest {
  kb_ready_folder_id?: number | null;
  sla_warning_minutes?: number;
  sla_breach_minutes?: number;
}

export interface MarkReadyRequest {
  confirm_move?: boolean;
  reason?: string;
}

export interface MarkReadyResponse {
  conversation_id: number;
  kb_ready_folder_id: number;
  folder_id: number;
  os_category: OSCategory;
  approval_status: string;
  message: string;
}

export interface RegenerateAiNoteResponse {
  conversation_id: number;
  generation_status: 'completed' | 'failed';
  metadata: Record<string, unknown>;
  message: string;
}

export interface ConversationVersion {
  id: number;
  conversation_id: number;
  version_number: number;
  transcript_content: string;
  created_at: string;
  created_by?: string;
  change_description?: string;
  is_active: boolean;
}

export interface VersionListResponse {
  versions: ConversationVersion[];
  total_count: number;
  active_version: number;
}

export interface ModifiedLine {
  line_number: number;
  original: string;
  modified: string;
}

export interface VersionDiff {
  diff_html: string;
  additions: number;
  deletions: number;
  version_1_id: number;
  version_2_id: number;
  from_version?: number;
  to_version?: number;
  added_lines?: string[];
  removed_lines?: string[];
  modified_lines?: ModifiedLine[];
  unchanged_lines?: string[];
  stats?: Record<string, number>;
}

export interface ConversationEditRequest {
  transcript_content: string;
  edit_reason: string;
  user_id: string;
  title?: string;
}

export interface ConversationRevertRequest {
  target_version: number;
  user_id?: string;
  reverted_by?: string;
  reason?: string;
  revert_reason?: string;
  reprocess?: boolean;
}

export interface EditResponse {
  conversation: UploadTranscriptResponse;
  new_version: number;
  conversation_id: number;
  message: string;
  task_id?: string;
  reprocessing?: boolean;
  new_version_uuid?: string;
}

export interface RevertResponse {
  conversation: UploadTranscriptResponse;
  conversation_id: number;
  reverted_to_version: number;
  new_version: number;
  message: string;
  task_id?: string;
  reprocessing?: boolean;
  new_version_uuid?: string;
}

const getAuthToken = async (): Promise<string | null> => {
  try {
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (token) {
      return token;
    }
  } catch {
    // fall through
  }

  try {
    const localToken = getLocalAuthToken();
    if (localToken) {
      return localToken;
    }
  } catch {
    // fall through
  }

  if (typeof window !== 'undefined') {
    return (
      localStorage.getItem('access_token') ||
      localStorage.getItem('authToken') ||
      null
    );
  }

  return null;
};

const buildHeaders = async (
  options: {
    auth?: boolean;
    json?: boolean;
    extra?: HeadersInit;
  } = {},
): Promise<HeadersInit> => {
  const { auth = false, json = true, extra } = options;
  const headers = new Headers(extra || {});

  if (json && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  if (auth) {
    const token = await getAuthToken();
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
  }

  return headers;
};

const extractErrorMessage = async (response: Response): Promise<string> => {
  const fallback = `${response.status} ${response.statusText}`.trim();
  try {
    const data = (await response.json()) as {
      detail?: string;
      message?: string;
      error?: string;
    };
    return data.detail || data.message || data.error || fallback;
  } catch {
    return fallback;
  }
};

const fetchWithRetry = async (
  url: string,
  options: RequestInit = {},
  retries = 3,
  timeout = 30000,
  skipRetryOn503 = false,
  requestKey?: string,
): Promise<Response> => {
  if (typeof window !== 'undefined' && navigator.onLine === false) {
    throw new ApiUnreachableError('You are offline - unable to reach FeedMe service');
  }

  if (retries === 3) {
    const healthStatus = backendHealthMonitor.getLastHealthStatus();
    if (healthStatus && !healthStatus.healthy) {
      console.warn('[FeedMe API] Backend unhealthy, request will continue', healthStatus);
    }
  }

  if (requestKey && activeRequests.has(requestKey)) {
    const previousController = activeRequests.get(requestKey);
    if (previousController) {
      supersededRequests.add(previousController);
      previousController.abort();
    }
    activeRequests.delete(requestKey);
  }

  const controller = new AbortController();
  if (requestKey) {
    activeRequests.set(requestKey, controller);
  }

  const startTime = Date.now();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    apiMonitor.track({
      url,
      method: options.method || 'GET',
      duration: Date.now() - startTime,
      status: response.status,
      timestamp: new Date(),
      size: parseInt(response.headers.get('content-length') || '0', 10),
    });

    if (requestKey) {
      activeRequests.delete(requestKey);
    }

    if (response.status === 503) {
      if (skipRetryOn503) {
        return response;
      }
      throw new Error('Service temporarily unavailable (503)');
    }

    if (response.status >= 500 && retries > 0) {
      throw new Error(`Server error (${response.status})`);
    }

    return response;
  } catch (error) {
    clearTimeout(timeoutId);

    apiMonitor.track({
      url,
      method: options.method || 'GET',
      duration: Date.now() - startTime,
      status: error instanceof Error && error.name === 'AbortError' ? 'timeout' : 'error',
      timestamp: new Date(),
    });

    if (requestKey) {
      activeRequests.delete(requestKey);
    }

    const isTimeout = error instanceof Error && error.name === 'AbortError';
    const wasSuperseded = supersededRequests.has(controller);
    if (wasSuperseded) {
      supersededRequests.delete(controller);
    }
    const isNetworkError =
      error instanceof Error &&
      (error.message.includes('NetworkError') ||
        error.message.includes('fetch') ||
        error.message.includes('ECONNREFUSED'));
    const isServerError =
      error instanceof Error &&
      (error.message.includes('Server error') ||
        error.message.includes('Service temporarily unavailable'));

    const shouldRetry =
      retries > 0 &&
      !wasSuperseded &&
      (isNetworkError || isServerError || (isTimeout && retries > 1));

    if (shouldRetry) {
      const delay = getRetryDelay(retries, 3);
      await new Promise((resolve) => setTimeout(resolve, delay));
      return fetchWithRetry(
        url,
        options,
        retries - 1,
        isTimeout ? Math.round(timeout * 1.5) : timeout,
        skipRetryOn503,
        requestKey,
      );
    }

    let message = 'Unexpected error connecting to FeedMe service';
    let errorType: 'timeout' | 'network' | 'server' | 'unknown' = 'unknown';

    if (error instanceof Error) {
      if (wasSuperseded) {
        message = SUPERSEDED_REQUEST_MESSAGE;
      } else if (isTimeout) {
        errorType = 'timeout';
        message = `Request timed out after ${Math.round(timeout / 1000)} seconds`;
      } else if (isNetworkError) {
        errorType = 'network';
        message = 'Network connection failed';
      } else if (error.message.includes('Service temporarily unavailable')) {
        errorType = 'server';
        message = 'FeedMe service is temporarily unavailable';
      } else if (isServerError) {
        errorType = 'server';
        message = 'FeedMe service encountered an error';
      } else {
        message = error.message;
      }
    }

    const wrapped = new ApiUnreachableError(
      message,
      error instanceof Error ? error : new Error(String(error)),
      errorType,
      url,
    );

    throw backendHealthMonitor.handleApiError(wrapped);
  }
};

const requestJson = async <T>(
  path: string,
  options: {
    method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
    auth?: boolean;
    body?: unknown;
    timeoutConfig?: keyof typeof TIMEOUT_CONFIGS;
    skipRetryOn503?: boolean;
    requestKey?: string;
    headers?: HeadersInit;
  } = {},
): Promise<T> => {
  const {
    method = 'GET',
    auth = false,
    body,
    timeoutConfig = 'standard',
    skipRetryOn503 = false,
    requestKey,
    headers,
  } = options;

  const timeout = TIMEOUT_CONFIGS[timeoutConfig].timeout;
  const retries = TIMEOUT_CONFIGS[timeoutConfig].retries;

  const hasJsonBody = body !== undefined;
  const builtHeaders = await buildHeaders({
    auth,
    json: hasJsonBody,
    extra: headers,
  });

  const response = await fetchWithRetry(
    `${FEEDME_API_BASE}${path}`,
    {
      method,
      headers: builtHeaders,
      body: hasJsonBody ? JSON.stringify(body) : undefined,
    },
    retries,
    timeout,
    skipRetryOn503,
    requestKey,
  );

  if (!response.ok) {
    throw new Error(await extractErrorMessage(response));
  }

  return response.json() as Promise<T>;
};

export const cancelAllActiveRequests = (): void => {
  activeRequests.forEach((controller) => controller.abort());
  activeRequests.clear();
};

export class FeedMeApiClient {
  private readonly baseUrl: string;

  constructor(baseUrl: string = FEEDME_API_BASE) {
    this.baseUrl = baseUrl;
  }

  async uploadTranscriptFile(
    title: string,
    file: File,
    uploadedBy?: string,
    autoProcess = true,
  ): Promise<UploadTranscriptResponse> {
    const formData = new FormData();
    formData.append('title', title);
    formData.append('transcript_file', file);
    formData.append('auto_process', String(autoProcess));
    if (uploadedBy) {
      formData.append('uploaded_by', uploadedBy);
    }

    const headers = await buildHeaders({ auth: true, json: false });
    const response = await fetchWithRetry(
      `${this.baseUrl}/conversations/upload`,
      {
        method: 'POST',
        headers,
        body: formData,
      },
      TIMEOUT_CONFIGS.heavy.retries,
      TIMEOUT_CONFIGS.heavy.timeout,
    );

    if (!response.ok) {
      throw new Error(await extractErrorMessage(response));
    }

    return response.json() as Promise<UploadTranscriptResponse>;
  }

  async getProcessingStatus(conversationId: number): Promise<ProcessingStatusResponse> {
    return requestJson<ProcessingStatusResponse>(`/conversations/${conversationId}/status`, {
      timeoutConfig: 'quick',
    });
  }

  async getConversationById(conversationId: number): Promise<UploadTranscriptResponse> {
    return requestJson<UploadTranscriptResponse>(`/conversations/${conversationId}`);
  }

  async getConversation(conversationId: number): Promise<UploadTranscriptResponse> {
    return this.getConversationById(conversationId);
  }

  async updateConversation(
    conversationId: number,
    updates: {
      title?: string;
      extracted_text?: string;
      metadata?: Record<string, unknown>;
      approval_status?: 'pending' | 'approved' | 'rejected' | 'awaiting_review';
      os_category?: OSCategory;
    },
  ): Promise<UploadTranscriptResponse> {
    return requestJson<UploadTranscriptResponse>(`/conversations/${conversationId}`, {
      method: 'PUT',
      auth: true,
      body: updates,
    });
  }

  async listConversations(
    page = 1,
    pageSize = 20,
    status?: string,
    uploadedBy?: string,
    searchQuery?: string,
    folderId?: number | null,
  ): Promise<ConversationListResponse> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });

    if (status) params.append('status', status);
    if (uploadedBy) params.append('uploaded_by', uploadedBy);
    if (searchQuery) params.append('search', searchQuery);

    // Default backend behavior is "all conversations" when no folder_id is supplied.
    if (folderId !== undefined && folderId !== null) {
      params.append('folder_id', String(folderId));
    }

    const response = await fetchWithRetry(
      `${this.baseUrl}/conversations?${params.toString()}`,
      {},
      TIMEOUT_CONFIGS.database.retries,
      TIMEOUT_CONFIGS.database.timeout,
      true,
      `feedme-list-${page}-${pageSize}-${status || ''}-${uploadedBy || ''}-${folderId ?? 'all'}-${searchQuery || ''}`,
    );

    if (!response.ok) {
      if (response.status === 503) {
        return {
          conversations: [],
          total_count: 0,
          page,
          page_size: pageSize,
          has_next: false,
          total_conversations: 0,
          total_pages: 0,
        };
      }
      throw new Error(await extractErrorMessage(response));
    }

    return response.json() as Promise<ConversationListResponse>;
  }

  async deleteConversation(conversationId: number): Promise<DeleteConversationResponse> {
    return requestJson<DeleteConversationResponse>(`/conversations/${conversationId}`, {
      method: 'DELETE',
      auth: true,
    });
  }

  async reprocessConversation(conversationId: number): Promise<{ task_id: string; status: string; message: string }> {
    return requestJson<{ task_id: string; status: string; message: string }>(
      `/conversations/${conversationId}/reprocess`,
      {
        method: 'POST',
        auth: true,
      },
    );
  }

  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetchWithRetry(`${this.baseUrl}/health`, {}, 1, TIMEOUT_CONFIGS.quick.timeout);
      return response.ok;
    } catch {
      return false;
    }
  }

  async getConversationExamples(
    conversationId: number,
    page = 1,
    pageSize = 20,
    isActive?: boolean,
  ): Promise<ExampleListResponse> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (isActive !== undefined) {
      params.append('is_active', String(isActive));
    }

    // Example endpoints were deprecated in this release. Keep compatibility contract.
    try {
      return await requestJson<ExampleListResponse>(
        `/conversations/${conversationId}/examples?${params.toString()}`,
      );
    } catch {
      return {
        examples: [],
        total_examples: 0,
        page,
        page_size: pageSize,
        has_next: false,
      };
    }
  }

  async updateExample(
    _exampleId: number,
    _updates: Partial<FeedMeExample>,
  ): Promise<FeedMeExample> {
    throw new Error('Example editing endpoints were removed from FeedMe in this release.');
  }

  async createFolderSupabase(folderData: CreateFolderRequest): Promise<FeedMeFolder> {
    return requestJson<FeedMeFolder>('/folders', {
      method: 'POST',
      auth: true,
      body: folderData,
    });
  }

  async updateFolderSupabase(
    folderId: number,
    folderData: UpdateFolderRequest,
  ): Promise<FeedMeFolder> {
    return requestJson<FeedMeFolder>(`/folders/${folderId}`, {
      method: 'PUT',
      auth: true,
      body: folderData,
    });
  }

  async deleteFolderSupabase(
    folderId: number,
    moveConversationsTo?: number,
  ): Promise<{ message: string }> {
    const params = new URLSearchParams();
    if (moveConversationsTo !== undefined) {
      params.append('move_conversations_to', String(moveConversationsTo));
    }
    const suffix = params.toString() ? `?${params.toString()}` : '';

    return requestJson<{ message: string }>(`/folders/${folderId}${suffix}`, {
      method: 'DELETE',
      auth: true,
    });
  }

  async assignConversationsToFolderSupabase(
    folderId: number | null,
    conversationIds: number[],
  ): Promise<FolderAssignmentResponse> {
    return requestJson<FolderAssignmentResponse>('/folders/assign', {
      method: 'POST',
      auth: true,
      body: {
        folder_id: folderId,
        conversation_ids: conversationIds,
      },
    });
  }

  async listFolders(): Promise<FolderListResponse> {
    return requestJson<FolderListResponse>('/folders', {
      timeoutConfig: 'database',
      skipRetryOn503: true,
      requestKey: 'feedme-list-folders',
    });
  }

  async getGeminiUsage(): Promise<GeminiUsage> {
    return requestJson<GeminiUsage>('/gemini-usage');
  }

  async getEmbeddingUsage(): Promise<EmbeddingUsage> {
    return requestJson<EmbeddingUsage>('/embedding-usage');
  }

  async searchExamples(request: SearchExamplesRequest): Promise<SearchExamplesResponse> {
    return requestJson<SearchExamplesResponse>('/search/examples', {
      method: 'POST',
      body: request,
    });
  }

  async getApprovalWorkflowStats(): Promise<ApprovalWorkflowStats> {
    return requestJson<ApprovalWorkflowStats>('/approval/stats', {
      timeoutConfig: 'database',
      skipRetryOn503: true,
      requestKey: 'feedme-approval-stats',
    });
  }

  async getStatsOverview(params?: {
    rangeDays?: number;
    folderId?: number | null;
    osCategory?: OSCategory | null;
  }): Promise<FeedMeStatsOverviewResponse> {
    const search = new URLSearchParams();
    search.set('range_days', String(params?.rangeDays ?? 7));
    if (params?.folderId !== undefined && params.folderId !== null) {
      search.set('folder_id', String(params.folderId));
    }
    if (params?.osCategory) {
      search.set('os_category', params.osCategory);
    }

    return requestJson<FeedMeStatsOverviewResponse>(`/stats/overview?${search.toString()}`, {
      timeoutConfig: 'database',
    });
  }

  async markConversationReady(
    conversationId: number,
    request: MarkReadyRequest = {},
  ): Promise<MarkReadyResponse> {
    return requestJson<MarkReadyResponse>(`/conversations/${conversationId}/mark-ready`, {
      method: 'POST',
      auth: true,
      body: request,
    });
  }

  async regenerateAiNote(conversationId: number): Promise<RegenerateAiNoteResponse> {
    return requestJson<RegenerateAiNoteResponse>(`/conversations/${conversationId}/ai-note/regenerate`, {
      method: 'POST',
      auth: true,
    });
  }

  async getFeedMeSettings(): Promise<FeedMeSettings> {
    return requestJson<FeedMeSettings>('/settings', {
      auth: true,
      timeoutConfig: 'database',
    });
  }

  async updateFeedMeSettings(
    updates: FeedMeSettingsUpdateRequest,
  ): Promise<FeedMeSettings> {
    return requestJson<FeedMeSettings>('/settings', {
      method: 'PUT',
      auth: true,
      body: updates,
      timeoutConfig: 'database',
    });
  }
}

export const feedMeApi = new FeedMeApiClient();

export const uploadTranscriptFile = (
  title: string,
  file: File,
  uploadedBy?: string,
  autoProcess?: boolean,
) => feedMeApi.uploadTranscriptFile(title, file, uploadedBy, autoProcess);

export const uploadTranscriptText = () => {
  throw new Error('Text-based uploads are disabled. Please upload a PDF file.');
};

export const getProcessingStatus = (conversationId: number) =>
  feedMeApi.getProcessingStatus(conversationId);

export function listConversations(
  page?: number,
  pageSize?: number,
  searchQuery?: string,
  _sortBy?: string,
  folderId?: number | null,
) {
  return feedMeApi.listConversations(
    page,
    pageSize,
    undefined,
    undefined,
    searchQuery,
    folderId,
  );
}

export const searchExamples = (request: SearchExamplesRequest) =>
  feedMeApi.searchExamples(request);

export async function updateConversation(
  conversationId: number,
  updateData: {
    title?: string;
    metadata?: Record<string, unknown>;
    extracted_text?: string;
    os_category?: OSCategory;
  },
): Promise<UploadTranscriptResponse> {
  return feedMeApi.updateConversation(conversationId, updateData);
}

export async function editConversation(
  conversationId: number,
  editRequest: ConversationEditRequest,
): Promise<EditResponse> {
  const result = await requestJson<{
    conversation_id: number;
    new_version: number;
    message: string;
    new_version_uuid?: string;
  }>(`/conversations/${conversationId}/edit`, {
    method: 'PUT',
    auth: true,
    body: editRequest,
  });

  const conversation = await feedMeApi.getConversationById(conversationId);

  return {
    conversation,
    conversation_id: result.conversation_id,
    new_version: result.new_version,
    message: result.message,
    new_version_uuid: result.new_version_uuid,
    reprocessing: true,
  };
}

export async function getConversationVersions(
  conversationId: number,
): Promise<VersionListResponse> {
  return requestJson<VersionListResponse>(`/conversations/${conversationId}/versions`);
}

export async function getConversationVersion(
  conversationId: number,
  versionNumber: number,
): Promise<ConversationVersion> {
  return requestJson<ConversationVersion>(
    `/conversations/${conversationId}/versions/${versionNumber}`,
  );
}

export async function getVersionDiff(
  conversationId: number,
  version1: number,
  version2: number,
): Promise<VersionDiff> {
  return requestJson<VersionDiff>(
    `/conversations/${conversationId}/versions/${version1}/diff/${version2}`,
  );
}

export async function revertConversation(
  conversationId: number,
  targetVersion: number,
  revertRequest: ConversationRevertRequest,
): Promise<RevertResponse> {
  const requestBody = {
    ...revertRequest,
    target_version: revertRequest.target_version ?? targetVersion,
    user_id: revertRequest.user_id || revertRequest.reverted_by || 'system',
    revert_reason:
      revertRequest.revert_reason ||
      revertRequest.reason ||
      'Reverted from FeedMe UI',
  };

  const result = await requestJson<{
    conversation_id: number;
    reverted_to_version: number;
    new_version: number;
    message: string;
    new_version_uuid?: string;
  }>(`/conversations/${conversationId}/revert/${targetVersion}`, {
    method: 'POST',
    auth: true,
    body: requestBody,
  });

  const conversation = await feedMeApi.getConversationById(conversationId);

  return {
    conversation,
    conversation_id: result.conversation_id,
    reverted_to_version: result.reverted_to_version,
    new_version: result.new_version,
    message: result.message,
    new_version_uuid: result.new_version_uuid,
    reprocessing: true,
  };
}

export async function deleteConversation(
  conversationId: number,
): Promise<DeleteConversationResponse> {
  return feedMeApi.deleteConversation(conversationId);
}

export async function approveConversation(
  conversationId: number,
  approvalRequest: ApprovalRequest,
): Promise<ApprovalResponse> {
  return requestJson<ApprovalResponse>(`/conversations/${conversationId}/approve`, {
    method: 'POST',
    auth: true,
    body: approvalRequest,
  });
}

export async function rejectConversation(
  conversationId: number,
  rejectionRequest: RejectionRequest,
): Promise<ApprovalResponse> {
  return requestJson<ApprovalResponse>(`/conversations/${conversationId}/reject`, {
    method: 'POST',
    auth: true,
    body: rejectionRequest,
  });
}

export async function getApprovalWorkflowStats(): Promise<ApprovalWorkflowStats> {
  return feedMeApi.getApprovalWorkflowStats();
}

export async function createFolderSupabase(
  folderData: CreateFolderRequest,
): Promise<FeedMeFolder> {
  return feedMeApi.createFolderSupabase(folderData);
}

export async function updateFolderSupabase(
  folderId: number,
  folderData: UpdateFolderRequest,
): Promise<FeedMeFolder> {
  return feedMeApi.updateFolderSupabase(folderId, folderData);
}

export async function deleteFolderSupabase(
  folderId: number,
  moveConversationsTo?: number,
): Promise<{ message: string }> {
  return feedMeApi.deleteFolderSupabase(folderId, moveConversationsTo);
}

export async function assignConversationsToFolderSupabase(
  folderId: number | null,
  conversationIds: number[],
): Promise<FolderAssignmentResponse> {
  return feedMeApi.assignConversationsToFolderSupabase(folderId, conversationIds);
}

export async function getConversationExamples(
  conversationId: number,
  page = 1,
  pageSize = 20,
  isActive?: boolean,
): Promise<ExampleListResponse> {
  return feedMeApi.getConversationExamples(conversationId, page, pageSize, isActive);
}

export async function updateExample(
  exampleId: number,
  updates: Partial<FeedMeExample>,
): Promise<FeedMeExample> {
  return feedMeApi.updateExample(exampleId, updates);
}

export async function deleteExample(_exampleId: number): Promise<{
  example_id: number;
  conversation_id: number;
  conversation_title: string;
  question_preview: string;
  message: string;
}> {
  throw new Error('Example delete endpoint was removed from FeedMe in this release.');
}

export async function listFolders(): Promise<FolderListResponse> {
  return feedMeApi.listFolders();
}

export async function createFolder(
  request: CreateFolderRequest,
): Promise<FeedMeFolder> {
  return feedMeApi.createFolderSupabase(request);
}

export async function updateFolder(
  folderId: number,
  request: UpdateFolderRequest,
): Promise<FeedMeFolder> {
  return feedMeApi.updateFolderSupabase(folderId, request);
}

export async function deleteFolder(
  folderId: number,
): Promise<{ message: string }> {
  return feedMeApi.deleteFolderSupabase(folderId);
}

export async function assignConversationsToFolder(
  folderId: number | null,
  conversationIds: number[],
): Promise<FolderAssignmentResponse> {
  return feedMeApi.assignConversationsToFolderSupabase(folderId, conversationIds);
}

export async function getAnalytics(): Promise<ApprovalWorkflowStats> {
  return getApprovalWorkflowStats();
}

export async function getStatsOverview(params?: {
  rangeDays?: number;
  folderId?: number | null;
  osCategory?: OSCategory | null;
}): Promise<FeedMeStatsOverviewResponse> {
  return feedMeApi.getStatsOverview(params);
}

export async function getFeedMeSettings(): Promise<FeedMeSettings> {
  return feedMeApi.getFeedMeSettings();
}

export async function updateFeedMeSettings(
  updates: FeedMeSettingsUpdateRequest,
): Promise<FeedMeSettings> {
  return feedMeApi.updateFeedMeSettings(updates);
}

export async function markConversationReady(
  conversationId: number,
  request: MarkReadyRequest = {},
): Promise<MarkReadyResponse> {
  return feedMeApi.markConversationReady(conversationId, request);
}

export async function regenerateAiNote(
  conversationId: number,
): Promise<RegenerateAiNoteResponse> {
  return feedMeApi.regenerateAiNote(conversationId);
}

export const simulateUploadProgress = (
  onProgress: (progress: number) => void,
  duration = 2000,
): Promise<void> => {
  return new Promise((resolve) => {
    const steps = 20;
    const stepDuration = duration / steps;
    let currentStep = 0;

    const interval = setInterval(() => {
      currentStep++;
      const progress = (currentStep / steps) * 100;
      onProgress(Math.min(100, progress));

      if (currentStep >= steps) {
        clearInterval(interval);
        resolve();
      }
    }, stepDuration);
  });
};
