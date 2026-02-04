/**
 * useStatsData Hook
 *
 * Custom hook for fetching and managing FeedMe statistics data.
 * Provides auto-refresh, error handling, and data transformation.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import {
  getApprovalWorkflowStats,
  type ApprovalWorkflowStats,
  feedMeApi,
  type GeminiUsage,
  type EmbeddingUsage,
  listConversations,
} from "@/features/feedme/services/feedme-api";
import { useAnalyticsStore } from "@/state/stores/analytics-store";

// Types for stats data
export interface ConversationStats {
  total: number;
  byPlatform: {
    windows: number;
    macos: number;
  };
  byStatus: {
    pending: number;
    processing: number;
    awaitingReview: number; // Conversations processed and ready for review
    completed: number;
    failed: number;
    approved: number;
    rejected: number;
  };
}

export interface ProcessingMetrics {
  averageTime: number; // in seconds
  successRate: number; // percentage
  failureRate: number; // percentage
  currentlyProcessing: number;
  queueSize: number;
}

export interface ApiUsage {
  gemini: {
    dailyUsed: number;
    dailyLimit: number;
    dailyUtilization: number; // percentage
    rpmLimit: number;
    callsInWindow: number;
    tpmLimit: number;
    tokensInWindow: number;
    windowSecondsRemaining: number;
    tokenWindowSecondsRemaining: number;
    status: "healthy" | "warning" | "critical";
  };
  embedding: {
    dailyUsed: number;
    dailyLimit: number;
    dailyUtilization: number; // percentage
    rpmLimit: number;
    tpmLimit: number;
    callsInWindow: number;
    tokensInWindow: number;
    windowSecondsRemaining: number;
    tokenWindowSecondsRemaining: number;
    status: "healthy" | "warning" | "critical";
  };
}

export interface RecentActivity {
  todayUploads: number;
  todaySearches: number;
  todayApprovals: number;
  lastUploadTime?: string;
  lastSearchTime?: string;
  lastApprovalTime?: string;
}

export interface SystemHealth {
  score: number; // 0-100
  status: "excellent" | "good" | "fair" | "poor";
  issues: string[];
  uptime: number; // in hours
}

export interface StatsData {
  conversations: ConversationStats;
  processing: ProcessingMetrics;
  apiUsage: ApiUsage;
  recentActivity: RecentActivity;
  systemHealth: SystemHealth;
  lastUpdated: string;
}

interface UseStatsDataOptions {
  autoRefresh?: boolean;
  refreshInterval?: number; // in milliseconds
  onError?: (error: Error) => void;
}

interface UseStatsDataReturn {
  data: StatsData | null;
  isLoading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
  lastFetchTime: Date | null;
}

/**
 * Custom hook for fetching and managing stats data
 */
export function useStatsData(
  options: UseStatsDataOptions = {},
): UseStatsDataReturn {
  const {
    autoRefresh = true,
    refreshInterval = 30000, // 30 seconds default
    onError,
  } = options;

  const [data, setData] = useState<StatsData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [lastFetchTime, setLastFetchTime] = useState<Date | null>(null);

  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const isMountedRef = useRef(true);

  // Get analytics store actions for supplementary data
  const analyticsActions = useAnalyticsStore((state) => state.actions);

  // Transform API data into structured stats
  const transformData = useCallback(
    (
      workflowStats: ApprovalWorkflowStats,
      geminiUsage: GeminiUsage | null,
      embeddingUsage: EmbeddingUsage | null,
      analyticsData: ReturnType<typeof useAnalyticsStore.getState>,
      extras?: {
        totalOverride?: number;
        platformCounts?: { windows: number; macos: number };
      },
    ): StatsData => {
      // Prefer totals/platform counts from extras when available
      const totalConversations =
        (extras?.totalOverride ?? workflowStats.total_conversations) || 0;
      const platformWindows = extras?.platformCounts?.windows ?? 0;
      const platformMac = extras?.platformCounts?.macos ?? 0;

      // Processing metrics
      const avgProcessingTime = workflowStats.avg_processing_time_ms
        ? workflowStats.avg_processing_time_ms / 1000 // Convert to seconds
        : 0; // No default, show actual data only

      // Success rate is based on processing completion (not approval status)
      // Completed = successfully processed (regardless of approval status)
      // Failed = processing failed
      // "Processed" approval_status means processing completed successfully
      const totalSuccessfullyProcessed =
        (workflowStats.approved || 0) +
        (workflowStats.rejected || 0) +
        (workflowStats.awaiting_review || 0); // 'processed' conversations
      const totalFailed = workflowStats.processing_failed || 0;
      const totalAttempted = totalSuccessfullyProcessed + totalFailed;
      const successRate =
        totalAttempted > 0
          ? (totalSuccessfullyProcessed / totalAttempted) * 100
          : 0; // Show 0% when there's no data, not 100%

      // System health calculation
      const calculateHealthScore = () => {
        let score = 100;
        const issues: string[] = [];

        const geminiDailyUtilization = geminiUsage?.utilization.daily ?? 0;
        if (geminiDailyUtilization > 80) {
          score -= 10;
          issues.push("High Gemini API usage");
        }
        const embeddingDailyUtilization =
          embeddingUsage?.utilization.daily ?? 0;
        if (embeddingDailyUtilization > 80) {
          score -= 10;
          issues.push("High embedding API usage");
        }

        // Check processing queue
        if ((workflowStats.currently_processing || 0) > 10) {
          score -= 5;
          issues.push("Large processing queue");
        }

        // Check failure rate
        const failureRate = 100 - successRate;
        if (failureRate > 10) {
          score -= 15;
          issues.push("High failure rate");
        }

        // Determine status
        let status: SystemHealth["status"] = "excellent";
        if (score < 70) status = "poor";
        else if (score < 80) status = "fair";
        else if (score < 90) status = "good";

        return { score, status, issues };
      };

      const { score, status, issues } = calculateHealthScore();

      // Get recent activity from analytics store
      const todayUploads = analyticsData?.usageStats?.uploads_today || 0;
      const todaySearches = analyticsData?.usageStats?.searches_today || 0;
      const todayApprovals = analyticsData?.usageStats?.approvals_today || 0;

      return {
        conversations: {
          total: totalConversations,
          byPlatform: {
            windows: platformWindows,
            macos: platformMac,
          },
          byStatus: {
            pending: workflowStats.pending_approval || 0,
            processing: workflowStats.currently_processing || 0,
            awaitingReview: workflowStats.awaiting_review || 0, // Processed, ready for review
            completed:
              (workflowStats.approved || 0) + (workflowStats.rejected || 0), // Terminal states
            failed: workflowStats.processing_failed || 0,
            approved: workflowStats.approved || 0,
            rejected: workflowStats.rejected || 0,
          },
        },
        processing: {
          averageTime: avgProcessingTime,
          successRate,
          failureRate: 100 - successRate,
          currentlyProcessing: workflowStats.currently_processing || 0,
          queueSize: workflowStats.awaiting_review || 0,
        },
        apiUsage: {
          gemini: {
            dailyUsed: geminiUsage?.daily_used || 0,
            // Free tier limits (Gemini 2.5 Flash-Lite Preview): RPD 1000, RPM 15, TPM 250k
            dailyLimit: Math.min(geminiUsage?.daily_limit ?? 1000, 1000),
            dailyUtilization: geminiUsage?.utilization?.daily || 0,
            rpmLimit: Math.min(geminiUsage?.rpm_limit ?? 15, 15),
            callsInWindow: geminiUsage?.calls_in_window || 0,
            tpmLimit: 250_000,
            tokensInWindow: 0,
            windowSecondsRemaining: geminiUsage?.window_seconds_remaining || 60,
            tokenWindowSecondsRemaining: 60,
            status: geminiUsage?.status || "healthy",
          },
          embedding: {
            dailyUsed: embeddingUsage?.daily_used || 0,
            // Free tier limits (Gemini Embeddings): RPD 1000, RPM 100, TPM 30k
            dailyLimit: Math.min(embeddingUsage?.daily_limit ?? 1000, 1000),
            dailyUtilization: embeddingUsage?.utilization?.daily || 0,
            rpmLimit: Math.min(embeddingUsage?.rpm_limit ?? 100, 100),
            tpmLimit: Math.min(embeddingUsage?.tpm_limit ?? 30_000, 30_000),
            callsInWindow: embeddingUsage?.calls_in_window || 0,
            tokensInWindow: embeddingUsage?.tokens_in_window || 0,
            windowSecondsRemaining:
              embeddingUsage?.window_seconds_remaining || 60,
            tokenWindowSecondsRemaining:
              embeddingUsage?.token_window_seconds_remaining || 60,
            status: embeddingUsage?.status || "healthy",
          },
        },
        recentActivity: {
          todayUploads,
          todaySearches,
          todayApprovals,
          // TODO: Get actual timestamps from API when available
          lastUploadTime: "", // Will be populated by backend
          lastSearchTime: "", // Will be populated by backend
          lastApprovalTime: "", // Will be populated by backend
        },
        systemHealth: {
          score,
          status,
          issues,
          uptime: 0, // Will be populated by backend with actual system uptime
        },
        lastUpdated: new Date().toISOString(),
      };
    },
    [],
  );

  // Fetch all stats data
  const fetchData = useCallback(async () => {
    if (!isMountedRef.current) return;

    try {
      setIsLoading(true);
      setError(null);

      // Fetch all data in parallel
      const [workflowStats, geminiUsage, embeddingUsage] =
        await Promise.allSettled([
          getApprovalWorkflowStats(),
          feedMeApi.getGeminiUsage(),
          feedMeApi.getEmbeddingUsage(),
        ]);

      // Load analytics data
      await analyticsActions.loadUsageStats();
      const analyticsData = useAnalyticsStore.getState();

      // Supplement totals using existing endpoints
      // Note: Platform-specific counts are no longer available (feedme_examples table removed)
      const [listRes] = await Promise.allSettled([
        listConversations(1, 1, undefined, undefined, null),
      ]);

      // Process results
      const workflow =
        workflowStats.status === "fulfilled"
          ? workflowStats.value
          : {
              total_conversations: 0,
              pending_approval: 0,
              awaiting_review: 0,
              approved: 0,
              rejected: 0,
              published: 0,
              currently_processing: 0,
              processing_failed: 0,
            };

      const gemini =
        geminiUsage.status === "fulfilled" ? geminiUsage.value : null;

      const embedding =
        embeddingUsage.status === "fulfilled" ? embeddingUsage.value : null;

      // Transform and set data
      const transformedData = transformData(
        workflow,
        gemini,
        embedding,
        analyticsData,
        {
          totalOverride:
            listRes.status === "fulfilled"
              ? (listRes.value.total_conversations ??
                listRes.value.total_count ??
                0)
              : undefined,
          platformCounts: {
            // Platform counts now available from metadata tags via RPC
            windows: workflow.windows_count ?? 0,
            macos: workflow.macos_count ?? 0,
          },
        },
      );

      if (isMountedRef.current) {
        setData(transformedData);
        setLastFetchTime(new Date());
      }
    } catch (err) {
      if (isMountedRef.current) {
        const error =
          err instanceof Error ? err : new Error("Failed to fetch stats data");
        setError(error);
        onError?.(error);
      }
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
      }
    }
  }, [transformData, analyticsActions, onError]);

  // Set up auto-refresh
  useEffect(() => {
    if (!autoRefresh) return;

    // Initial fetch
    fetchData();

    // Set up interval
    intervalRef.current = setInterval(() => {
      fetchData();
    }, refreshInterval);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [autoRefresh, refreshInterval, fetchData]);

  // Cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true;

    return () => {
      isMountedRef.current = false;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, []);

  return {
    data,
    isLoading,
    error,
    refetch: fetchData,
    lastFetchTime,
  };
}

// Utility function to format time ago
export function formatTimeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

// Utility function to get status color
export function getStatusColor(
  status:
    | "healthy"
    | "warning"
    | "critical"
    | "excellent"
    | "good"
    | "fair"
    | "poor",
): string {
  switch (status) {
    case "healthy":
    case "excellent":
      return "text-green-500";
    case "good":
      return "text-green-400";
    case "warning":
    case "fair":
      return "text-yellow-500";
    case "critical":
    case "poor":
      return "text-red-500";
    default:
      return "text-gray-500";
  }
}
