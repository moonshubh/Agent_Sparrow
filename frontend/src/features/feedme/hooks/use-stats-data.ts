import { useState, useEffect, useCallback, useRef } from 'react';
import {
  getStatsOverview,
  listFolders,
  getFeedMeSettings,
  updateFeedMeSettings,
  type FeedMeStatsOverviewResponse,
  type FeedMeFolder,
  type FeedMeSettings,
  type FeedMeSettingsUpdateRequest,
  type OSCategory,
} from '@/features/feedme/services/feedme-api';

export interface StatsFilters {
  rangeDays: number;
  folderId: number | null;
  osCategory: OSCategory | null;
}

interface UseStatsDataOptions {
  autoRefresh?: boolean;
  refreshInterval?: number;
  filters?: StatsFilters;
  onError?: (error: Error) => void;
}

interface UseStatsDataReturn {
  overview: FeedMeStatsOverviewResponse | null;
  folders: FeedMeFolder[];
  settings: FeedMeSettings | null;
  isAdmin: boolean;
  isLoading: boolean;
  isSavingSettings: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
  saveSettings: (updates: FeedMeSettingsUpdateRequest) => Promise<void>;
  lastFetchTime: Date | null;
}

export function useStatsData(options: UseStatsDataOptions = {}): UseStatsDataReturn {
  const {
    autoRefresh = true,
    refreshInterval = 30000,
    filters = {
      rangeDays: 7,
      folderId: null,
      osCategory: null,
    },
    onError,
  } = options;

  const [overview, setOverview] = useState<FeedMeStatsOverviewResponse | null>(null);
  const [folders, setFolders] = useState<FeedMeFolder[]>([]);
  const [settings, setSettings] = useState<FeedMeSettings | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [lastFetchTime, setLastFetchTime] = useState<Date | null>(null);

  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const isMountedRef = useRef(true);
  const inFlightFetchRef = useRef<Map<string, Promise<void>>>(new Map());
  const latestFetchIdRef = useRef(0);

  const fetchData = useCallback(async () => {
    if (!isMountedRef.current) return;
    const fetchKey = JSON.stringify({
      rangeDays: filters.rangeDays,
      folderId: filters.folderId,
      osCategory: filters.osCategory,
    });
    const existingRequest = inFlightFetchRef.current.get(fetchKey);
    if (existingRequest) {
      return existingRequest;
    }

    const fetchId = latestFetchIdRef.current + 1;
    latestFetchIdRef.current = fetchId;

    const request = (async () => {
      try {
        setIsLoading(true);
        setError(null);

        const [overviewResult, foldersResult, settingsResult] = await Promise.allSettled([
          getStatsOverview({
            rangeDays: filters.rangeDays,
            folderId: filters.folderId,
            osCategory: filters.osCategory,
          }),
          listFolders(),
          getFeedMeSettings(),
        ]);

        if (overviewResult.status !== 'fulfilled') {
          throw overviewResult.reason instanceof Error
            ? overviewResult.reason
            : new Error('Failed to load FeedMe overview stats');
        }

        if (!isMountedRef.current || latestFetchIdRef.current !== fetchId) return;

        setOverview(overviewResult.value);

        if (foldersResult.status === 'fulfilled') {
          setFolders(foldersResult.value.folders);
        } else {
          setFolders([]);
        }

        if (settingsResult.status === 'fulfilled') {
          setSettings(settingsResult.value);
          setIsAdmin(true);
        } else {
          const message =
            settingsResult.reason instanceof Error
              ? settingsResult.reason.message.toLowerCase()
              : '';

          // Non-admin users are expected to get 403 on settings routes.
          if (message.includes('403') || message.includes('admin role')) {
            setIsAdmin(false);
            setSettings(null);
          } else {
            // Unknown settings failure: keep stats visible, surface warning state as non-admin.
            setIsAdmin(false);
            setSettings(null);
          }
        }

        setLastFetchTime(new Date());
      } catch (err) {
        if (!isMountedRef.current || latestFetchIdRef.current !== fetchId) return;
        const normalizedError =
          err instanceof Error ? err : new Error('Failed to load FeedMe stats');
        setError(normalizedError);
        onError?.(normalizedError);
      } finally {
        if (isMountedRef.current && latestFetchIdRef.current === fetchId) {
          setIsLoading(false);
        }
      }
    })();

    inFlightFetchRef.current.set(fetchKey, request);

    try {
      await request;
    } finally {
      if (inFlightFetchRef.current.get(fetchKey) === request) {
        inFlightFetchRef.current.delete(fetchKey);
      }
    }
  }, [filters.folderId, filters.osCategory, filters.rangeDays, onError]);

  const saveSettings = useCallback(
    async (updates: FeedMeSettingsUpdateRequest) => {
      setIsSavingSettings(true);
      try {
        const updated = await updateFeedMeSettings(updates);
        if (isMountedRef.current) {
          setSettings(updated);
        }
        await fetchData();
      } finally {
        if (isMountedRef.current) {
          setIsSavingSettings(false);
        }
      }
    },
    [fetchData],
  );

  useEffect(() => {
    if (!autoRefresh) {
      return;
    }

    fetchData();

    intervalRef.current = setInterval(() => {
      fetchData();
    }, refreshInterval);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [autoRefresh, fetchData, refreshInterval]);

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
    overview,
    folders,
    settings,
    isAdmin,
    isLoading,
    isSavingSettings,
    error,
    refetch: fetchData,
    saveSettings,
    lastFetchTime,
  };
}

export function formatTimeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}
