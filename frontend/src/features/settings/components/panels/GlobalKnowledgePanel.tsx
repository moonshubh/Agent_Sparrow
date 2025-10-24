"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { motion, useInView } from "motion/react"
import { globalKnowledgeApi, type GlobalKnowledgeSummary } from "@/features/global-knowledge/services/global-knowledge-api"
import { Button } from "@/shared/ui/button"
import { Loader2, RefreshCw, PlugZap, Plug } from "lucide-react"
import { Separator } from "@/shared/ui/separator"
import { ScrollArea } from "@/shared/ui/scroll-area"
import { Badge } from "@/shared/ui/badge"
import { cn } from "@/shared/lib/utils"
import { useGlobalKnowledgeObservability } from "@/features/global-knowledge/hooks/useGlobalKnowledgeObservability"

function pct(n?: number | null): string {
  if (n == null || Number.isNaN(n)) return "—"
  return `${Math.round(n * 100)}%`
}

function ms(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "—"
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`
  return `${Math.round(value)}ms`
}

export function GlobalKnowledgePanel() {
  const [summary, setSummary] = useState<GlobalKnowledgeSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const ref = useRef(null)
  const isInView = useInView(ref, { once: true })

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await globalKnowledgeApi.getSummary()
      setSummary(res)
    } catch (e: any) {
      setError(e?.message || "failed")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const stats = useMemo(() => {
    const s = summary
    return [
      { value: String(s?.total_submissions ?? 0), label: "Submissions (24h)" },
      { value: pct(s?.enhancer_success_rate), label: "Enhancer success" },
      { value: pct(s?.store_write_success_rate), label: "Store writes OK" },
      { value: pct(s?.fallback_rate), label: "Fallback rate" },
      { value: ms(s?.stage_p95_ms?.classification ?? null), label: "Classification p95" },
      { value: ms(s?.stage_p95_ms?.store_upserted ?? null), label: "Store write p95" },
    ]
  }, [summary])

  return (
    <section className="py-4">
      <div className="mx-auto max-w-7xl px-0">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-foreground mb-1 text-xl font-bold lg:text-2xl">Global Knowledge — Observability</h2>
            <p className="text-foreground/70 max-w-2xl text-sm">Live metrics for enhancer and knowledge store performance</p>
          </div>
          <Button size="sm" variant="outline" disabled={loading || refreshing} onClick={async () => { setRefreshing(true); await load(); setRefreshing(false) }}>
            {loading || refreshing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
            Refresh
          </Button>
        </div>

        {error ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            Failed to load metrics ({error}). Ensure backend endpoints are reachable.
          </div>
        ) : null}

        <div ref={ref} className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {loading
            ? Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-24 animate-pulse rounded-xl border border-border/40 bg-muted/20" />
              ))
            : stats.map((stat, index) => (
                <motion.div
                  key={stat.label}
                  initial={{ opacity: 0, y: 30 }}
                  animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 30 }}
                  transition={{ duration: 0.6, delay: index * 0.06 }}
                  className="group border-border bg-background hover:border-brand relative overflow-hidden rounded-xl border p-5 text-left transition-all hover:shadow-lg"
                >
                  <motion.div
                    className="text-brand mb-1 text-3xl font-bold lg:text-4xl"
                    initial={{ scale: 0.5 }}
                    animate={isInView ? { scale: 1 } : { scale: 0.5 }}
                    transition={{ duration: 0.8, delay: index * 0.06 + 0.2, type: "spring", stiffness: 200 }}
                  >
                    {stat.value}
                  </motion.div>
                  <h3 className="text-foreground text-sm font-medium">{stat.label}</h3>

                  <motion.div
                    className="from-brand/5 absolute inset-0 bg-gradient-to-br to-transparent opacity-0 group-hover:opacity-100"
                    initial={{ opacity: 0 }}
                    whileHover={{ opacity: 1 }}
                    transition={{ duration: 0.3 }}
                  />
                </motion.div>
              ))}
        </div>

        <Separator className="my-6" />

        {/* Timeline */}
        <TimelineSection />
      </div>
    </section>
  )
}

function TimelineSection() {
  const {
    events,
    isEventsLoading,
    eventsError,
    isStreamConnected,
    refreshEvents,
  } = useGlobalKnowledgeObservability()

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold">Timeline Stream</h3>
          <p className="text-xs text-muted-foreground">Real-time enhancer and persistence events</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={isStreamConnected ? 'default' : 'secondary'} className="flex items-center gap-1 text-xs">
            {isStreamConnected ? <PlugZap className="h-3 w-3" /> : <Plug className="h-3 w-3" />}
            {isStreamConnected ? 'Live' : 'Reconnecting'}
          </Badge>
          <Button variant="ghost" size="icon" onClick={() => void refreshEvents()}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {eventsError && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          Timeline error: {eventsError}
        </div>
      )}

      <div className="rounded-lg border">
        <ScrollArea className="h-[320px] p-0">
          {isEventsLoading ? (
            <div className="flex h-[320px] items-center justify-center text-sm text-muted-foreground">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading timeline…
            </div>
          ) : events.length === 0 ? (
            <div className="flex h-[200px] items-center justify-center text-sm text-muted-foreground">
              No timeline events yet.
            </div>
          ) : (
            <ul className="space-y-2 p-4">
              {events.map(event => (
                <li key={event.event_id} className="rounded-lg border border-border/60 bg-background/80 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-xs capitalize">{event.kind}</Badge>
                      <span className="font-medium">{event.stage}</span>
                      <span>•</span>
                      <span
                        className={cn(
                          'font-medium',
                          event.status === 'complete'
                            ? 'text-emerald-500'
                            : event.status === 'error'
                              ? 'text-destructive'
                              : 'text-muted-foreground',
                        )}
                      >
                        {event.status}
                      </span>
                    </div>
                    <span>{new Date(event.created_at).toLocaleString()}</span>
                  </div>
                  <div className="mt-2 text-sm">
                    {typeof (event as any)?.metadata?.reason !== 'undefined' && (event as any)?.metadata?.reason !== null && (
                      <div className="text-muted-foreground">Reason: {String((event as any).metadata.reason)}</div>
                    )}
                    {typeof (event as any)?.metadata?.action !== 'undefined' && (event as any)?.metadata?.action !== null && (
                      <div className="text-muted-foreground">Action: {String((event as any).metadata.action)}</div>
                    )}
                    {event.duration_ms != null && (
                      <div className="text-xs text-muted-foreground">Δ {formatDuration(event.duration_ms)}</div>
                    )}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                    {event.submission_id != null && (
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
              ))}
            </ul>
          )}
        </ScrollArea>
      </div>
    </div>
  )
}

function formatDuration(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '—'
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`
  return `${Math.round(value)}ms`
}
