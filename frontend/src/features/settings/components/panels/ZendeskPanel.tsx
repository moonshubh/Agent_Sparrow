"use client"

import { useEffect, useState } from "react"
import { ZendeskStats, type ZendeskHealth } from "@/features/zendesk/components/ZendeskStats"
import { FeatureToggles } from "@/app/settings/zendesk/FeatureToggles"

export function ZendeskPanel() {
  const [health, setHealth] = useState<ZendeskHealth | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch("/api/admin/zendesk/health", { cache: "no-store" })
        if (!res.ok) {
          const j = await res.json().catch(() => ({} as any))
          throw new Error(j?.error || `upstream_${res.status}`)
        }
        const data = await res.json()
        if (!cancelled) setHealth(data)
      } catch (e: any) {
        if (!cancelled) setError(e?.message || "failed")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-6 w-40 bg-muted animate-pulse rounded" />
        <div className="h-24 w-full bg-muted animate-pulse rounded" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-2">
        <div className="text-sm text-red-500">Failed to load Zendesk health ({error}).</div>
        <div className="text-xs text-muted-foreground">Ensure INTERNAL_API_TOKEN and API_BASE are configured on the server and you have admin access.</div>
      </div>
    )
  }

  if (!health) return null

  return (
    <div className="space-y-4">
      <ZendeskStats health={health} />
      <FeatureToggles initialEnabled={!!health.enabled} initialDryRun={!!health.dry_run} />
    </div>
  )
}
