"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { motion, useInView } from "motion/react"
import { Button } from "@/shared/ui/button"
import { Separator } from "@/shared/ui/separator"
import { Badge } from "@/shared/ui/badge"
import { rateLimitApi, type UsageStats } from "@/services/api/endpoints/rateLimitApi"
import { apiKeyService, APIKeyType, type APIKeyListResponse } from "@/services/api/api-keys"
import { Loader2, RefreshCw, Activity, AlertCircle, Shield } from "lucide-react"

export function RateLimitsPanel() {
  const [stats, setStats] = useState<UsageStats | null>(null)
  const [keys, setKeys] = useState<APIKeyListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const ref = useRef(null)
  const isInView = useInView(ref, { once: true })

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [s, k] = await Promise.all([
        rateLimitApi.getUsageStats(),
        apiKeyService.listAPIKeys(),
      ])
      setStats(s)
      setKeys(k)
    } catch (e: any) {
      setError(e?.message || "failed")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Provider configuration flags are fetched above if needed later; limits shown below are static defaults

  const gridStats = useMemo(() => {
    const s = stats
    const f = s?.flash_stats
    const p = s?.pro_stats
    const flashRpdLimit = f?.rpd_limit ? Math.min(f.rpd_limit, 250) : 250
    return [
      { value: f ? `${f.rpm_used}/${f.rpm_limit}` : '—', label: 'Gemini Flash RPM' },
      { value: f ? `${f.rpd_used}/${flashRpdLimit}` : '—', label: 'Gemini Flash RPD' },
      { value: p ? `${p.rpm_used}/${p.rpm_limit}` : '—', label: 'Gemini Pro RPM' },
      { value: p ? `${p.rpd_used}/${p.rpd_limit}` : '—', label: 'Gemini Pro RPD' },
      { value: '1000 /month', label: 'Tavily Wb/search' },
      { value: '200 RPD', label: 'GPT‑5 mini RPD' },
    ]
  }, [stats])

  return (
    <section className="py-4">
      <div className="mx-auto max-w-7xl px-0">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-foreground mb-1 text-xl font-bold lg:text-2xl">Rate Limits</h2>
            <p className="text-foreground/70 max-w-2xl text-sm">Live usage and provider limits (Gemini, OpenAI, Tavily)</p>
          </div>
          <Button size="sm" variant="outline" disabled={loading || refreshing} onClick={async () => { setRefreshing(true); await refresh(); setRefreshing(false) }}>
            {loading || refreshing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
            Refresh
          </Button>
        </div>

        {error ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            Failed to load rate limits ({error}).
          </div>
        ) : null}

        <div ref={ref} className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {loading
            ? Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-24 animate-pulse rounded-xl border border-border/40 bg-muted/20" />
              ))
            : gridStats.map((stat, index) => (
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

        {/* Details */}
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border p-4">
            <h3 className="text-sm font-medium mb-2 flex items-center gap-2"><Activity className="h-4 w-4"/> Utilization</h3>
            {stats ? (
              <ul className="text-sm text-muted-foreground space-y-1">
                <li>Requests this minute: <span className="font-medium text-foreground">{stats.total_requests_this_minute}</span></li>
                <li>Requests today: <span className="font-medium text-foreground">{stats.total_requests_today}</span></li>
                <li>Uptime: <span className="font-medium text-foreground">{stats.uptime_percentage.toFixed(1)}%</span></li>
              </ul>
            ) : (
              <div className="text-sm text-muted-foreground">No data</div>
            )}
          </div>
          <div className="rounded-lg border p-4">
            <h3 className="text-sm font-medium mb-2 flex items-center gap-2"><Shield className="h-4 w-4"/> Circuit Breakers</h3>
            {stats ? (
              <ul className="text-sm text-muted-foreground space-y-1">
                <li>
                  Flash: <Badge variant={stats.flash_circuit.state === 'open' ? 'destructive' : 'secondary'} className="mx-1">{stats.flash_circuit.state}</Badge>
                  failures={stats.flash_circuit.failure_count}
                </li>
                <li>
                  Pro: <Badge variant={stats.pro_circuit.state === 'open' ? 'destructive' : 'secondary'} className="mx-1">{stats.pro_circuit.state}</Badge>
                  failures={stats.pro_circuit.failure_count}
                </li>
              </ul>
            ) : (
              <div className="text-sm text-muted-foreground">No data</div>
            )}
          </div>
        </div>

        <Separator className="my-6" />

        <div className="text-xs text-muted-foreground space-y-1">
          <p>Google Gemini free-tier limits vary; see docs: https://ai.google.dev/gemini-api/docs/rate-limits</p>
          <p>Tavily free-tier: 1000 requests/month.</p>
        </div>
      </div>
    </section>
  )
}
