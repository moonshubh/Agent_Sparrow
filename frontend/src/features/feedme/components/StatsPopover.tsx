import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog';
import { ScrollArea } from '@/shared/ui/scroll-area';
import { Separator } from '@/shared/ui/separator';
import { Button } from '@/shared/ui/button';
import { Badge } from '@/shared/ui/badge';
import { Alert, AlertDescription } from '@/shared/ui/alert';
import { Input } from '@/shared/ui/input';
import { Label } from '@/shared/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/ui/select';
import { BarChart3, RefreshCw, Settings2, ShieldAlert, X } from 'lucide-react';
import { cn } from '@/shared/lib/utils';
import { useUIStore } from '@/state/stores/ui-store';
import {
  useStatsData,
  formatTimeAgo,
  type StatsFilters,
} from '@/features/feedme/hooks/use-stats-data';
import { OverviewCards, StatsCardSkeleton } from './stats/StatsCards';
import type { OSCategory } from '@/features/feedme/services/feedme-api';

interface StatsPopoverProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}

const RANGE_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 1, label: 'Last 1 day' },
  { value: 7, label: 'Last 7 days' },
  { value: 14, label: 'Last 14 days' },
  { value: 30, label: 'Last 30 days' },
];

const OS_OPTIONS: Array<{ value: OSCategory | 'all'; label: string }> = [
  { value: 'all', label: 'All OS' },
  { value: 'windows', label: 'Windows' },
  { value: 'macos', label: 'macOS' },
  { value: 'both', label: 'Both' },
  { value: 'uncategorized', label: 'Uncategorized' },
];

export function StatsPopover({
  open = false,
  onOpenChange,
  className,
}: StatsPopoverProps) {
  const showToast = useUIStore((state) => state.actions.showToast);

  const [isRefreshing, setIsRefreshing] = useState(false);
  const [rangeDays, setRangeDays] = useState(7);
  const [folderId, setFolderId] = useState<number | null>(null);
  const [osCategory, setOsCategory] = useState<OSCategory | null>(null);

  const filters: StatsFilters = useMemo(
    () => ({ rangeDays, folderId, osCategory }),
    [rangeDays, folderId, osCategory],
  );

  const {
    overview,
    folders,
    settings,
    isAdmin,
    isLoading,
    isSavingSettings,
    error,
    refetch,
    saveSettings,
    lastFetchTime,
  } = useStatsData({
    autoRefresh: open,
    refreshInterval: 30000,
    filters,
    onError: (err) => {
      console.error('Failed to load FeedMe stats', err);
    },
  });

  const [kbFolderSetting, setKbFolderSetting] = useState<string>('none');
  const [warningSetting, setWarningSetting] = useState<string>('60');
  const [breachSetting, setBreachSetting] = useState<string>('180');

  useEffect(() => {
    if (!settings) return;
    setKbFolderSetting(
      typeof settings.kb_ready_folder_id === 'number'
        ? String(settings.kb_ready_folder_id)
        : 'none',
    );
    setWarningSetting(String(settings.sla_warning_minutes));
    setBreachSetting(String(settings.sla_breach_minutes));
  }, [settings]);

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      await refetch();
    } finally {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => setIsRefreshing(false));
      });
    }
  }, [refetch]);

  const handleSaveSettings = useCallback(async () => {
    const warning = Number(warningSetting);
    const breach = Number(breachSetting);

    if (!Number.isFinite(warning) || warning <= 0) {
      showToast({
        type: 'error',
        title: 'Invalid warning threshold',
        message: 'SLA warning threshold must be greater than 0.',
        duration: 4000,
      });
      return;
    }

    if (!Number.isFinite(breach) || breach <= warning) {
      showToast({
        type: 'error',
        title: 'Invalid breach threshold',
        message: 'SLA breach threshold must be greater than warning threshold.',
        duration: 4000,
      });
      return;
    }

    try {
      await saveSettings({
        kb_ready_folder_id: kbFolderSetting === 'none' ? null : Number(kbFolderSetting),
        sla_warning_minutes: warning,
        sla_breach_minutes: breach,
      });
      showToast({
        type: 'success',
        title: 'FeedMe settings updated',
        message: 'KB folder and SLA thresholds were saved.',
        duration: 3000,
      });
    } catch (err) {
      showToast({
        type: 'error',
        title: 'Failed to save settings',
        message: err instanceof Error ? err.message : 'Please try again.',
        duration: 5000,
      });
    }
  }, [breachSetting, kbFolderSetting, saveSettings, showToast, warningSetting]);

  const lastUpdatedText = lastFetchTime
    ? formatTimeAgo(lastFetchTime.toISOString())
    : 'Never';

  const slaAlertBadge =
    overview && overview.cards.sla_breach_count > 0
      ? 'BREACH'
      : overview && overview.cards.sla_warning_count > 0
        ? 'WARNING'
        : 'HEALTHY';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        hideClose
        className={cn('max-w-[1080px] p-0 h-[760px] overflow-hidden', className)}
      >
        <DialogHeader className="sr-only">
          <DialogTitle>FeedMe Statistics</DialogTitle>
        </DialogHeader>

        <div className="flex h-full min-h-0 flex-col">
          <div className="flex items-center justify-between border-b bg-background/80 px-6 py-4 backdrop-blur-sm">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-[hsl(200.4_98%_38%)] p-2 text-white">
                <BarChart3 className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-lg font-semibold">FeedMe Statistics</h3>
                <p className="text-xs text-muted-foreground">DB-backed metrics with SLA alerting</p>
              </div>
              <Badge
                variant="outline"
                className={cn(
                  'ml-2 border-0 text-xs text-white',
                  slaAlertBadge === 'BREACH'
                    ? 'bg-rose-600'
                    : slaAlertBadge === 'WARNING'
                      ? 'bg-amber-500'
                      : 'bg-emerald-600',
                )}
              >
                {slaAlertBadge}
              </Badge>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Updated {lastUpdatedText}</span>
              <Button
                variant="ghost"
                size="icon"
                onClick={handleRefresh}
                disabled={isRefreshing || isLoading}
                aria-label="Refresh stats"
              >
                <RefreshCw className={cn('h-4 w-4', (isRefreshing || isLoading) && 'animate-spin')} />
              </Button>
              <DialogClose asChild>
                <Button variant="ghost" size="icon" aria-label="Close">
                  <X className="h-4 w-4" />
                </Button>
              </DialogClose>
            </div>
          </div>

          <div className="border-b bg-muted/20 px-6 py-3">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Time Range</Label>
                <Select
                  value={String(rangeDays)}
                  onValueChange={(value) => setRangeDays(Number(value))}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue placeholder="Select range" />
                  </SelectTrigger>
                  <SelectContent>
                    {RANGE_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={String(opt.value)}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Folder Filter</Label>
                <Select
                  value={folderId === null ? 'all' : String(folderId)}
                  onValueChange={(value) =>
                    setFolderId(value === 'all' ? null : Number(value))
                  }
                >
                  <SelectTrigger className="h-9">
                    <SelectValue placeholder="All folders" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All folders</SelectItem>
                    <SelectItem value="0">Unassigned</SelectItem>
                    {folders.map((folder) => (
                      <SelectItem key={folder.id} value={String(folder.id)}>
                        {folder.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">OS Filter</Label>
                <Select
                  value={osCategory ?? 'all'}
                  onValueChange={(value) =>
                    setOsCategory(value === 'all' ? null : (value as OSCategory))
                  }
                >
                  <SelectTrigger className="h-9">
                    <SelectValue placeholder="All OS" />
                  </SelectTrigger>
                  <SelectContent>
                    {OS_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          <div className="flex min-h-0 flex-1 overflow-hidden">
            <ScrollArea className="h-full flex-1">
              <div className="p-6">
                {error && !overview ? (
                  <Alert variant="destructive" className="mb-6">
                    <ShieldAlert className="h-4 w-4" />
                    <AlertDescription>
                      Failed to load stats overview. {error.message}
                    </AlertDescription>
                  </Alert>
                ) : null}

                {isLoading && !overview ? (
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {Array.from({ length: 6 }).map((_, idx) => (
                      <StatsCardSkeleton key={idx} />
                    ))}
                  </div>
                ) : null}

                {overview ? (
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                    <OverviewCards overview={overview} />
                  </div>
                ) : null}
              </div>
            </ScrollArea>

            <aside className="hidden w-[320px] border-l bg-muted/10 p-4 lg:block">
              <div className="mb-3 flex items-center gap-2">
                <Settings2 className="h-4 w-4 text-muted-foreground" />
                <h4 className="text-sm font-semibold">FeedMe Settings</h4>
              </div>

              {!isAdmin ? (
                <Alert>
                  <ShieldAlert className="h-4 w-4" />
                  <AlertDescription>
                    Admin-only settings. Your account can view stats but cannot edit KB/SLA configuration.
                  </AlertDescription>
                </Alert>
              ) : (
                <div className="space-y-4">
                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground">KB Ready Folder</Label>
                    <Select value={kbFolderSetting} onValueChange={setKbFolderSetting}>
                      <SelectTrigger className="h-9">
                        <SelectValue placeholder="Select folder" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">Not configured</SelectItem>
                        {folders.map((folder) => (
                          <SelectItem key={folder.id} value={String(folder.id)}>
                            {folder.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground">SLA Warning (minutes)</Label>
                    <Input
                      type="number"
                      min={1}
                      value={warningSetting}
                      onChange={(event) => setWarningSetting(event.target.value)}
                    />
                  </div>

                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground">SLA Breach (minutes)</Label>
                    <Input
                      type="number"
                      min={1}
                      value={breachSetting}
                      onChange={(event) => setBreachSetting(event.target.value)}
                    />
                  </div>

                  <Button
                    className="w-full"
                    onClick={() => {
                      void handleSaveSettings();
                    }}
                    disabled={isSavingSettings}
                  >
                    {isSavingSettings ? 'Saving…' : 'Save Settings'}
                  </Button>

                  <p className="text-xs text-muted-foreground">
                    SLA alerts are computed in-app from these thresholds and shown in the overview cards.
                  </p>
                </div>
              )}
            </aside>
          </div>

          <Separator className="my-0" />
        </div>
      </DialogContent>
    </Dialog>
  );
}
