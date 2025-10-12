'use client'

import { useMemo, useState } from 'react'

import { formatDistanceToNowStrict } from 'date-fns'
import { Loader2, RefreshCw, Activity, Database, AlertCircle, CheckCircle2, PlugZap, Plug } from 'lucide-react'
import { toast } from 'sonner'

import { useGlobalKnowledgeObservability, type QueueKind } from '@/features/global-knowledge/hooks/useGlobalKnowledgeObservability'
import { formatTimeAgo } from '@/features/feedme/hooks/use-stats-data'
import {
  GLOBAL_KNOWLEDGE_QUEUE_STATUSES,
  type GlobalKnowledgeQueueStatus,
} from '@/features/global-knowledge/services/global-knowledge-api'
import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/shared/ui/card'
import { Badge } from '@/shared/ui/badge'
import { ScrollArea } from '@/shared/ui/scroll-area'
import { Separator } from '@/shared/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/ui/select'
import { cn } from '@/shared/lib/utils'

const QUEUE_STATUS_OPTIONS = GLOBAL_KNOWLEDGE_QUEUE_STATUSES
const QUEUE_KIND_OPTIONS: readonly QueueKind[] = ['all', 'feedback', 'correction']

const isQueueKind = (value: string): value is QueueKind =>
  QUEUE_KIND_OPTIONS.includes(value as QueueKind)

const isQueueStatus = (value: string): value is GlobalKnowledgeQueueStatus =>
  QUEUE_STATUS_OPTIONS.includes(value as GlobalKnowledgeQueueStatus)

type EnhancedMetadata = {
  tags?: unknown
  key_facts?: unknown
}

const formatPercent = (value?: number | null): string => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—'
  }
  return `${Math.round(value * 100)}%`
}

const formatMilliseconds = (value?: number | null): string => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—'
  }

  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}s`
  }

  return `${Math.round(value)}ms`
}

const EmptyState = ({ message }: { message: string }) => (
  <div className="flex flex-col items-center justify-center py-8 text-sm text-muted-foreground">
    <AlertCircle className="mb-2 h-5 w-5" />
    <span>{message}</span>
  </div>
)

export const ObservabilityTab = () => {
  const {
    summary,
    queue,
    events,
    isSummaryLoading,
    isQueueLoading,
    isEventsLoading,
    summaryError,
    queueError,
    eventsError,
    streamError,
    isStreamConnected,
    queueFilter,
    refreshSummary,
    refreshQueue,
    refreshEvents,
    setQueueFilter,
    promoteCorrection,
    promoteFeedback,
  } = useGlobalKnowledgeObservability()

  const [activeQueueTab, setActiveQueueTab] = useState<QueueKind>(queueFilter.kind)
  const [summaryRefreshing, setSummaryRefreshing] = useState(false)
  const [queueRefreshing, setQueueRefreshing] = useState(false)
  const [eventsRefreshing, setEventsRefreshing] = useState(false)
  const [actionLoading, setActionLoading] = useState<{ kind: 'feedback' | 'correction'; id: number } | null>(null)

  const stageMetrics = useMemo(() => {
    const stageP95 = summary?.stage_p95_ms ?? {}
    return [
      { label: 'Classification', value: formatMilliseconds(stageP95.classification) },
      { label: 'Normalization', value: formatMilliseconds(stageP95.normalization) },
      { label: 'Moderation', value: formatMilliseconds(stageP95.moderation) },
      { label: 'Store Write', value: formatMilliseconds(stageP95.store_upserted) },
    ]
  }, [summary])

  const handleSummaryRefresh = async () => {
    setSummaryRefreshing(true)
    try {
      await refreshSummary()
      toast.success('Metrics refreshed')
    } catch (error) {
      toast.error('Failed to refresh metrics', { description: error instanceof Error ? error.message : String(error) })
    } finally {
      setSummaryRefreshing(false)
    }
  }

  const handleQueueRefresh = async () => {
    setQueueRefreshing(true)
    try {
      await refreshQueue()
      toast.success('Queue updated')
    } catch (error) {
      toast.error('Failed to refresh queue', { description: error instanceof Error ? error.message : String(error) })
    } finally {
      setQueueRefreshing(false)
    }
  }

  const handleEventsRefresh = async () => {
    setEventsRefreshing(true)
    try {
      await refreshEvents()
      toast.success('Timeline refreshed')
    } catch (error) {
      toast.error('Failed to refresh timeline', { description: error instanceof Error ? error.message : String(error) })
    } finally {
      setEventsRefreshing(false)
    }
  }

  const onPromote = async (kind: 'feedback' | 'correction', id: number) => {
    setActionLoading({ kind, id })
    try {
      const response = kind === 'correction'
        ? await promoteCorrection(id)
        : await promoteFeedback(id)

      if (response.success) {
        toast.success(kind === 'correction' ? 'Correction added to knowledge base' : 'Feedback flagged for review')
      } else {
        toast.error('Action failed', { description: response.message ?? 'Unknown failure' })
      }
    } catch (error) {
      toast.error('Action failed', { description: error instanceof Error ? error.message : String(error) })
    } finally {
      setActionLoading(null)
    }
  }

  const summaryCards = [
    {
      title: 'Total submissions (24h)',
      value: summary?.total_submissions ?? 0,
      icon: Activity,
    },
    {
      title: 'Enhancer success rate',
      value: formatPercent(summary?.enhancer_success_rate),
      icon: CheckCircle2,
    },
    {
      title: 'Store write success',
      value: formatPercent(summary?.store_write_success_rate),
      icon: Database,
    },
    {
      title: 'Fallback rate',
      value: formatPercent(summary?.fallback_rate),
      icon: AlertCircle,
    },
  ]

  return (
    <div className="space-y-4">
      {(summaryError || queueError || eventsError || streamError) && (
        <Card className="border-destructive/40 bg-destructive/10">
          <CardContent className="flex flex-wrap items-center gap-3 py-3 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" />
            <span className="font-medium">Issues detected:</span>
            <div className="flex flex-wrap gap-2">
              {summaryError && <Badge variant="destructive">Metrics: {summaryError}</Badge>}
              {queueError && <Badge variant="destructive">Queue: {queueError}</Badge>}
              {eventsError && <Badge variant="destructive">Timeline: {eventsError}</Badge>}
              {streamError && <Badge variant="destructive">Stream: {streamError}</Badge>}
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <div>
            <CardTitle className="text-lg">Global Knowledge Metrics</CardTitle>
            <p className="text-sm text-muted-foreground">Live enhancer and store performance overview</p>
          </div>
          <Button variant="outline" size="sm" onClick={handleSummaryRefresh} disabled={summaryRefreshing}>
            {summaryRefreshing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          {isSummaryLoading ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {summaryCards.map(card => (
                <div key={card.title} className="h-24 animate-pulse rounded-lg bg-muted/40" />
              ))}
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {summaryCards.map(card => (
                <div key={card.title} className="rounded-lg border border-border/60 bg-muted/20 p-4">
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>{card.title}</span>
                    <card.icon className="h-4 w-4" />
                  </div>
                  <div className="mt-2 text-2xl font-semibold">{card.value}</div>
                </div>
              ))}
            </div>
          )}

          <Separator className="my-4" />

          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
            {stageMetrics.map(metric => (
              <div key={metric.label} className="rounded-lg border border-border/50 bg-muted/10 p-3">
                <div className="text-xs text-muted-foreground">{metric.label} p95</div>
                <div className="mt-1 text-lg font-medium">{metric.value}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="flex h-full flex-col">
          <CardHeader className="flex flex-row items-center justify-between gap-4">
            <div>
              <CardTitle className="text-lg">Timeline stream</CardTitle>
              <p className="text-sm text-muted-foreground">Real-time enhancer and persistence events</p>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={isStreamConnected ? 'default' : 'secondary'} className="flex items-center gap-1 text-xs">
                {isStreamConnected ? <PlugZap className="h-3 w-3" /> : <Plug className="h-3 w-3" />}
                {isStreamConnected ? 'Live' : 'Reconnecting'}
              </Badge>
              <Button variant="ghost" size="icon" onClick={handleEventsRefresh} disabled={eventsRefreshing}>
                {eventsRefreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              </Button>
            </div>
          </CardHeader>
          <CardContent className="flex-1 overflow-hidden p-0">
            {isEventsLoading ? (
              <div className="flex h-[320px] items-center justify-center text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading timeline…
              </div>
            ) : events.length === 0 ? (
              <EmptyState message="No timeline events yet." />
            ) : (
              <ScrollArea className="h-[320px]">
                <ul className="space-y-2 p-4">
                  {events.map(event => {
                    const eventMetadata = event.metadata ?? {}
                    const reason = Object.prototype.hasOwnProperty.call(eventMetadata, 'reason')
                      ? eventMetadata.reason
                      : undefined
                    const action = Object.prototype.hasOwnProperty.call(eventMetadata, 'action')
                      ? eventMetadata.action
                      : undefined

                    return (
                      <li key={event.event_id} className="rounded-lg border border-border/60 bg-background/80 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="text-xs capitalize">{event.kind}</Badge>
                          <span className="font-medium">{event.stage}</span>
                          <span>•</span>
                          <span className={cn(
                            'font-medium',
                            event.status === 'complete' ? 'text-emerald-500' : event.status === 'error' ? 'text-destructive' : 'text-muted-foreground',
                          )}>
                            {event.status}
                          </span>
                        </div>
                        <span>{formatTimeAgo(event.created_at)}</span>
                      </div>
                      <div className="mt-2 text-sm">
                        {reason !== undefined && reason !== null && (
                          <div className="text-muted-foreground">Reason: {String(reason)}</div>
                        )}
                        {action !== undefined && action !== null && (
                          <div className="text-muted-foreground">Action: {String(action)}</div>
                        )}
                        {event.duration_ms !== null && event.duration_ms !== undefined && (
                          <div className="text-xs text-muted-foreground">Δ {formatMilliseconds(event.duration_ms)}</div>
                        )}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                        {event.submission_id !== null && event.submission_id !== undefined && (
                          <Badge variant="secondary">Submission #{event.submission_id}</Badge>
                        )}
                        {event.fallback_used && <Badge variant="destructive">Fallback</Badge>}
                        {event.store_written != null && (
                          <Badge variant={event.store_written ? 'default' : 'destructive'}>
                            Store {event.store_written ? 'written' : 'failed'}
                          </Badge>
                        )}
                      </div>
                      </li>
                    )
                  })}
                </ul>
              </ScrollArea>
            )}
          </CardContent>
        </Card>

        <Card className="flex h-full flex-col">
          <CardHeader className="flex flex-row items-center justify-between gap-4">
            <div>
              <CardTitle className="text-lg">Review queue</CardTitle>
              <p className="text-sm text-muted-foreground">Approve corrections and flag feedback in one view</p>
            </div>
            <Button variant="ghost" size="icon" onClick={handleQueueRefresh} disabled={queueRefreshing}>
              {queueRefreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            </Button>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Tabs
              value={activeQueueTab}
              onValueChange={value => {
                if (!isQueueKind(value)) {
                  return
                }
                setActiveQueueTab(value)
                setQueueFilter({ kind: value })
              }}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <TabsList className="grid w-full grid-cols-3 sm:w-auto">
                  {QUEUE_KIND_OPTIONS.map(kind => (
                    <TabsTrigger key={kind} value={kind} className="capitalize">
                      {kind === 'all' ? 'All' : kind}
                    </TabsTrigger>
                  ))}
                </TabsList>
                <Select
                  value={queueFilter.status}
                  onValueChange={value => {
                    if (!isQueueStatus(value)) {
                      return
                    }
                    setQueueFilter({ status: value })
                  }}
                >
                  <SelectTrigger className="w-[160px]">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    {QUEUE_STATUS_OPTIONS.map(status => (
                      <SelectItem key={status} value={status} className="capitalize">
                        {status}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <TabsContent value={activeQueueTab} className="mt-4 flex-1">
                {isQueueLoading ? (
                  <div className="flex h-[320px] items-center justify-center text-sm text-muted-foreground">
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading queue…
                  </div>
                ) : queue.length === 0 ? (
                  <EmptyState message="No submissions for this filter." />
                ) : (
                  <ScrollArea className="h-[320px] pr-2">
                    <div className="space-y-3">
                      {queue.map(item => {
                        const enhanced = ((item.metadata ?? {}) as { enhanced?: EnhancedMetadata }).enhanced ?? {}
                        const rawTags = Array.isArray(enhanced.tags) ? enhanced.tags : item.tags
                        const tags = rawTags.filter((tag): tag is string => typeof tag === 'string')
                        const rawKeyFacts = Array.isArray(enhanced.key_facts) ? enhanced.key_facts : item.key_facts
                        const keyFacts = rawKeyFacts.filter((fact): fact is string => typeof fact === 'string')

                        return (
                          <div key={`${item.kind}-${item.id}`} className="rounded-lg border border-border/70 bg-background/80 p-3">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                <Badge variant="outline" className="capitalize">{item.kind}</Badge>
                                <Badge variant="secondary" className="capitalize">{item.status}</Badge>
                                <span>#{item.id}</span>
                              </div>
                              <span className="text-xs text-muted-foreground">
                                {formatDistanceToNowStrict(new Date(item.created_at), { addSuffix: true })}
                              </span>
                            </div>
                            <div className="mt-2 text-sm font-medium">
                              {item.summary || item.raw_text || 'No summary available'}
                            </div>
                            {keyFacts.length > 0 && (
                              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
                                {keyFacts.map(fact => (
                                  <li key={fact}>{fact}</li>
                                ))}
                              </ul>
                            )}
                            {tags.length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-2">
                                {tags.map(tag => (
                                  <Badge key={tag} variant="outline" className="text-[11px] capitalize">
                                    {tag}
                                  </Badge>
                                ))}
                              </div>
                            )}
                            <CardFooter className="mt-3 flex items-center justify-between gap-3 p-0">
                              <div className="text-[11px] text-muted-foreground">
                                {item.user_id ? `Submitted by ${item.user_id}` : 'Anonymous submission'}
                              </div>
                              <div className="flex gap-2">
                                {item.kind === 'correction' && (
                                  <Button
                                    size="sm"
                                    onClick={() => onPromote('correction', item.id)}
                                    disabled={actionLoading?.kind === 'correction' && actionLoading.id === item.id}
                                  >
                                    {actionLoading?.kind === 'correction' && actionLoading.id === item.id ? (
                                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    ) : (
                                      <Database className="mr-2 h-4 w-4" />
                                    )}
                                    Add to Knowledge Base
                                  </Button>
                                )}
                                {item.kind === 'feedback' && (
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => onPromote('feedback', item.id)}
                                    disabled={actionLoading?.kind === 'feedback' && actionLoading.id === item.id}
                                  >
                                    {actionLoading?.kind === 'feedback' && actionLoading.id === item.id ? (
                                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    ) : (
                                      <CheckCircle2 className="mr-2 h-4 w-4" />
                                    )}
                                    Flag for Review
                                  </Button>
                                )}
                              </div>
                            </CardFooter>
                          </div>
                        )
                      })}
                    </div>
                  </ScrollArea>
                )}
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export default ObservabilityTab
