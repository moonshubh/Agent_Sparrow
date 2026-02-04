"use client";

import { useRef } from "react";
import { motion, useInView } from "motion/react";
import { cn } from "@/shared/lib/utils";
import { Activity, Clock, AlertTriangle, CheckCircle2 } from "lucide-react";

export type ZendeskHealth = {
  enabled?: boolean;
  dry_run?: boolean;
  provider?: string;
  model?: string;
  usage?: { calls_used?: number; budget?: number } | null;
  daily?: { gemini_calls_used?: number; gemini_daily_limit?: number } | null;
  queue?: {
    pending?: number;
    retry?: number;
    processing?: number;
    failed?: number;
  } | null;
};

interface StatsGridProps {
  title?: string;
  description?: string;
  health: ZendeskHealth;
}

// Simple stat card component
interface StatItemProps {
  label: string;
  value: string | number;
  subtitle?: string;
  status?: "healthy" | "warning" | "critical";
  delay?: number;
}

function StatItem({
  label,
  value,
  subtitle,
  status = "healthy",
  delay = 0,
}: StatItemProps) {
  const statusColors = {
    healthy: "hsl(135 45% 45%)",
    warning: "hsl(40 90% 50%)",
    critical: "hsl(0 70% 50%)",
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay }}
      className="p-4 rounded-lg bg-card border border-border"
    >
      <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">
        {label}
      </div>
      <div className="text-2xl font-bold text-foreground tabular-nums">
        {value}
      </div>
      {subtitle && (
        <div className="flex items-center gap-1 mt-1 text-xs text-muted-foreground">
          {status === "healthy" && (
            <CheckCircle2
              className="w-3 h-3"
              style={{ color: statusColors[status] }}
            />
          )}
          {status === "warning" && (
            <AlertTriangle
              className="w-3 h-3"
              style={{ color: statusColors[status] }}
            />
          )}
          {status === "critical" && (
            <AlertTriangle
              className="w-3 h-3"
              style={{ color: statusColors[status] }}
            />
          )}
          <span>{subtitle}</span>
        </div>
      )}
    </motion.div>
  );
}

// Progress bar component
function ProgressBar({
  value,
  max,
  label,
}: {
  value: number;
  max: number;
  label: string;
}) {
  const percentage = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  const color =
    percentage > 80
      ? "hsl(0 70% 50%)"
      : percentage > 60
        ? "hsl(40 90% 50%)"
        : "hsl(135 45% 45%)";

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium">{percentage.toFixed(1)}%</span>
      </div>
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="h-full rounded-full"
          style={{ backgroundColor: color }}
        />
      </div>
    </div>
  );
}

export function ZendeskStats({
  title = "Zendesk — Integration Health",
  description = "Feature status, usage, and queue metrics",
  health,
}: StatsGridProps) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });

  // Feature toggle values
  const enabled = health?.enabled ?? false;
  const dryRun = health?.dry_run ?? false;

  // API usage values
  const dailyUsed = health?.daily?.gemini_calls_used ?? 0;
  const dailyLimit = health?.daily?.gemini_daily_limit ?? 1000;

  const monthlyUsed = health?.usage?.calls_used ?? 0;
  const monthlyBudget = health?.usage?.budget ?? 10000;

  // Queue values
  const qPending = health?.queue?.pending ?? 0;
  const qFailed = health?.queue?.failed ?? 0;
  const qProcessing = health?.queue?.processing ?? 0;
  const qRetry = health?.queue?.retry ?? 0;

  return (
    <section className="py-4" ref={ref}>
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
          transition={{ duration: 0.6 }}
          className="mb-5"
        >
          <h2 className="text-foreground text-lg font-semibold">{title}</h2>
          <p className="text-muted-foreground text-sm">{description}</p>
        </motion.div>

        {/* Feature Toggle Status */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}
          transition={{ duration: 0.4, delay: 0.1 }}
          className="flex flex-wrap gap-3 mb-5"
        >
          <div
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium",
              enabled
                ? "bg-green-500/10 text-green-600 dark:text-green-400"
                : "bg-red-500/10 text-red-600 dark:text-red-400",
            )}
          >
            <div
              className={cn(
                "w-1.5 h-1.5 rounded-full",
                enabled ? "bg-green-500" : "bg-red-500",
              )}
            />
            Feature {enabled ? "Enabled" : "Disabled"}
          </div>
          <div
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium",
              dryRun
                ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                : "bg-muted text-muted-foreground",
            )}
          >
            <div
              className={cn(
                "w-1.5 h-1.5 rounded-full",
                dryRun ? "bg-amber-500" : "bg-muted-foreground",
              )}
            />
            Dry Run {dryRun ? "On" : "Off"}
          </div>
        </motion.div>

        {/* Stats Grid - 2 columns */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
          {/* API Usage Section */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}
            transition={{ duration: 0.4, delay: 0.2 }}
            className="p-4 rounded-lg bg-card border border-border space-y-4"
          >
            <div className="flex items-center gap-2 text-sm font-medium">
              <Activity className="w-4 h-4 text-primary" />
              <span>API Usage</span>
            </div>
            <ProgressBar
              value={dailyUsed}
              max={dailyLimit}
              label={`Daily: ${dailyUsed.toLocaleString()} / ${dailyLimit.toLocaleString()}`}
            />
            <ProgressBar
              value={monthlyUsed}
              max={monthlyBudget}
              label={`Monthly: ${monthlyUsed.toLocaleString()} / ${monthlyBudget.toLocaleString()}`}
            />
          </motion.div>

          {/* Queue Section */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}
            transition={{ duration: 0.4, delay: 0.3 }}
            className="p-4 rounded-lg bg-card border border-border"
          >
            <div className="flex items-center gap-2 text-sm font-medium mb-3">
              <Clock className="w-4 h-4 text-primary" />
              <span>Queue Status</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="text-center p-2 rounded bg-amber-500/10">
                <div className="text-xl font-bold text-amber-600 dark:text-amber-400">
                  {qPending}
                </div>
                <div className="text-xs text-muted-foreground">Pending</div>
              </div>
              <div className="text-center p-2 rounded bg-blue-500/10">
                <div className="text-xl font-bold text-blue-600 dark:text-blue-400">
                  {qProcessing}
                </div>
                <div className="text-xs text-muted-foreground">Processing</div>
              </div>
              <div className="text-center p-2 rounded bg-purple-500/10">
                <div className="text-xl font-bold text-purple-600 dark:text-purple-400">
                  {qRetry}
                </div>
                <div className="text-xs text-muted-foreground">Retry</div>
              </div>
              <div className="text-center p-2 rounded bg-red-500/10">
                <div className="text-xl font-bold text-red-600 dark:text-red-400">
                  {qFailed}
                </div>
                <div className="text-xs text-muted-foreground">Failed</div>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
