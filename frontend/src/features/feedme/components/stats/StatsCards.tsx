'use client';

import React from 'react';
import { motion } from 'motion/react';
import { Skeleton } from '@/shared/ui/skeleton';
import { Badge } from '@/shared/ui/badge';
import { GlowingEffect } from '@/shared/ui/glowing-effect';
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Gauge,
  Layers3,
  ListChecks,
  Timer,
} from 'lucide-react';
import type { FeedMeStatsOverviewResponse } from '@/features/feedme/services/feedme-api';

interface CardProps {
  title: string;
  value: string;
  subtitle?: string;
  icon: React.ReactNode;
  delay?: number;
  children?: React.ReactNode;
}

function StatCard({ title, value, subtitle, icon, delay = 0, children }: CardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay }}
      className="group relative min-h-[12.5rem] rounded-2xl p-1.5 transition-all duration-300 hover:-translate-y-1"
    >
      <GlowingEffect
        blur={0}
        borderWidth={3}
        spread={80}
        glow={true}
        disabled={false}
        proximity={64}
        inactiveZone={0.01}
      />
      <div className="relative flex h-full flex-col justify-between gap-3 overflow-hidden rounded-2xl bg-card/95 p-4 shadow-none">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</p>
          <span className="text-muted-foreground">{icon}</span>
        </div>
        <p className="text-2xl font-semibold tabular-nums">{value}</p>
        {subtitle ? <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p> : null}
        {children ? <div className="mt-3">{children}</div> : null}
      </div>
    </motion.div>
  );
}

export function StatsCardSkeleton() {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <Skeleton className="mb-3 h-3 w-24" />
      <Skeleton className="mb-2 h-8 w-20" />
      <Skeleton className="h-3 w-28" />
    </div>
  );
}

interface OverviewCardsProps {
  overview: FeedMeStatsOverviewResponse;
}

export function OverviewCards({ overview }: OverviewCardsProps) {
  const cards = overview.cards;

  const warningCount = cards.sla_warning_count;
  const breachCount = cards.sla_breach_count;
  const slaStatus = breachCount > 0 ? 'breach' : warningCount > 0 ? 'warning' : 'healthy';

  return (
    <>
      <StatCard
        title="Queue Depth"
        value={String(cards.queue_depth)}
        subtitle="Pending or processing"
        icon={<Layers3 className="h-4 w-4" />}
      />

      <StatCard
        title="Failure Rate"
        value={`${cards.failure_rate.toFixed(2)}%`}
        subtitle="Within selected window"
        icon={<Gauge className="h-4 w-4" />}
        delay={0.04}
      />

      <StatCard
        title="Latency"
        value={`${Math.round(cards.p95_latency_ms)} ms`}
        subtitle={`p50 ${Math.round(cards.p50_latency_ms)} ms`}
        icon={<Timer className="h-4 w-4" />}
        delay={0.08}
      />

      <StatCard
        title="Assign Throughput"
        value={String(cards.assign_throughput)}
        subtitle="Folder assignment actions"
        icon={<ListChecks className="h-4 w-4" />}
        delay={0.12}
      />

      <StatCard
        title="KB Ready Throughput"
        value={String(cards.kb_ready_throughput)}
        subtitle="Marked ready for KB"
        icon={<CheckCircle2 className="h-4 w-4" />}
        delay={0.16}
      />

      <StatCard
        title="SLA Alerts"
        value={`${warningCount}/${breachCount}`}
        subtitle={`Warnings/Breaches (${overview.sla_thresholds.warning_minutes}/${overview.sla_thresholds.breach_minutes} min)`}
        icon={
          slaStatus === 'healthy' ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          ) : (
            <AlertTriangle className="h-4 w-4 text-amber-600" />
          )
        }
        delay={0.2}
      >
        <div className="flex items-center gap-2 text-xs">
          <Badge variant="secondary" className="bg-amber-100 text-amber-900">
            Warnings {warningCount}
          </Badge>
          <Badge
            variant="secondary"
            className={breachCount > 0 ? 'bg-rose-100 text-rose-900' : 'bg-muted text-muted-foreground'}
          >
            Breaches {breachCount}
          </Badge>
        </div>
      </StatCard>

      <StatCard
        title="OS Distribution"
        value={String(overview.total_conversations)}
        subtitle="Total conversations in range"
        icon={<Clock3 className="h-4 w-4" />}
        delay={0.24}
      >
        <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
          <span>Windows: {overview.os_distribution.windows}</span>
          <span>macOS: {overview.os_distribution.macos}</span>
          <span>Both: {overview.os_distribution.both}</span>
          <span>Uncategorized: {overview.os_distribution.uncategorized}</span>
        </div>
      </StatCard>
    </>
  );
}
