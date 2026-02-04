/**
 * StatsPopover Component
 *
 * Main popover component that displays comprehensive FeedMe statistics
 * when the Stats button is clicked in the Dock.
 *
 * Features dot-matrix style cards with smooth animations.
 */

import React, { useState, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogClose,
} from "@/shared/ui/dialog";
import { ScrollArea } from "@/shared/ui/scroll-area";
import { Separator } from "@/shared/ui/separator";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { BarChart3, RefreshCw, X, AlertCircle } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import {
  useStatsData,
  formatTimeAgo,
} from "@/features/feedme/hooks/use-stats-data";
import {
  ConversationStatsCard,
  ProcessingMetricsCard,
  GeminiUsageCard,
  EmbeddingUsageCard,
  SystemHealthCard,
  StatsCardSkeleton,
} from "./stats/StatsCards";
import { Alert, AlertDescription } from "@/shared/ui/alert";
import { motion } from "motion/react";

interface StatsPopoverProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}

export function StatsPopover({
  open = false,
  onOpenChange,
  className,
}: StatsPopoverProps) {
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Fetch stats data with auto-refresh
  const { data, isLoading, error, refetch, lastFetchTime } = useStatsData({
    autoRefresh: open, // Only auto-refresh when dialog is open
    refreshInterval: 30000, // 30 seconds
    onError: (error) => {
      // Error is already being handled by the error state in the UI
      // No need to log to console in production
    },
  });

  // Manual refresh handler without memory leak
  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      await refetch();
    } finally {
      // Use requestAnimationFrame instead of setTimeout to avoid memory leak
      // and ensure the animation is visible for at least one frame
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setIsRefreshing(false);
        });
      });
    }
  }, [refetch]);

  // Format last updated time
  const lastUpdatedText = lastFetchTime
    ? formatTimeAgo(lastFetchTime.toISOString())
    : "Never";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        hideClose
        className={cn(
          "max-w-[1000px] p-0 h-[700px] overflow-hidden",
          "bg-[hsl(40_10%_96%)] dark:bg-[hsl(0_0%_10%)]",
          className,
        )}
      >
        <DialogHeader className="sr-only">
          <DialogTitle>FeedMe Statistics</DialogTitle>
        </DialogHeader>

        <div className="flex h-full min-h-0 flex-col">
          {/* Header */}
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="flex items-center justify-between px-6 py-4 border-b border-[hsl(0_0%_90%)] dark:border-[hsl(0_0%_20%)] bg-white/50 dark:bg-black/20 backdrop-blur-sm"
          >
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-[hsl(200.4_98%_38%)] text-white">
                <BarChart3 className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-[hsl(0_0%_15%)] dark:text-[hsl(40_15%_92%)]">
                  FeedMe Statistics
                </h3>
                <p className="text-xs text-[hsl(0_0%_50%)] dark:text-[hsl(0_0%_55%)]">
                  Real-time system metrics and insights
                </p>
              </div>
              <Badge
                variant="outline"
                className="ml-2 bg-[hsl(135_45%_45%)] text-white border-0 text-xs animate-pulse"
              >
                LIVE
              </Badge>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-[hsl(0_0%_50%)] dark:text-[hsl(0_0%_55%)]">
                Updated {lastUpdatedText}
              </span>
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9 rounded-lg hover:bg-[hsl(0_0%_90%)] dark:hover:bg-[hsl(0_0%_20%)]"
                onClick={handleRefresh}
                aria-label="Refresh stats"
                disabled={isRefreshing || isLoading}
              >
                <RefreshCw
                  className={cn("h-4 w-4", isRefreshing && "animate-spin")}
                />
              </Button>
              <DialogClose asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9 rounded-lg hover:bg-[hsl(0_0%_90%)] dark:hover:bg-[hsl(0_0%_20%)]"
                  aria-label="Close"
                >
                  <X className="h-4 w-4" />
                </Button>
              </DialogClose>
            </div>
          </motion.div>

          <Separator className="my-0 bg-transparent" />

          <div className="flex-1 overflow-hidden min-h-0">
            <ScrollArea className="h-full">
              <div className="p-6">
                {error && !data && (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                  >
                    <Alert variant="destructive" className="mb-6">
                      <AlertCircle className="h-4 w-4" />
                      <AlertDescription>
                        Failed to load statistics. Please try again later.
                      </AlertDescription>
                    </Alert>
                  </motion.div>
                )}

                {isLoading && !data ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <StatsCardSkeleton key={i} />
                    ))}
                  </div>
                ) : data ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                    {/* Row 1: Overview */}
                    <ConversationStatsCard
                      data={data.conversations}
                      animationDelay={0}
                    />
                    <ProcessingMetricsCard
                      data={data.processing}
                      animationDelay={0.1}
                    />
                    <SystemHealthCard
                      data={data.systemHealth}
                      animationDelay={0.2}
                    />

                    {/* Row 2: API Usage */}
                    <GeminiUsageCard
                      data={data.apiUsage}
                      animationDelay={0.3}
                    />
                    <EmbeddingUsageCard
                      data={data.apiUsage}
                      animationDelay={0.4}
                    />
                  </div>
                ) : null}
              </div>
            </ScrollArea>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
