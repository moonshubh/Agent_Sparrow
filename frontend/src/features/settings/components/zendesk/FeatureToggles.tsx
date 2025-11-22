"use client"

import { useState, useCallback } from 'react'
import { Switch } from '@/shared/ui/switch'
import { toast } from 'sonner'

interface FeatureTogglesProps {
  initialEnabled: boolean
  initialDryRun: boolean
}

export function FeatureToggles({ initialEnabled, initialDryRun }: FeatureTogglesProps) {
  const [enabled, setEnabled] = useState<boolean>(!!initialEnabled)
  const [dryRun, setDryRun] = useState<boolean>(!!initialDryRun)
  const [loading, setLoading] = useState<boolean>(false)

  const updateFlags = useCallback(async (next: { enabled?: boolean; dry_run?: boolean }) => {
    if (loading) return
    setLoading(true)
    const prev = { enabled, dryRun }
    if (typeof next.enabled === 'boolean') setEnabled(next.enabled)
    if (typeof next.dry_run === 'boolean') setDryRun(next.dry_run)
    try {
      const res = await fetch('/api/admin/zendesk/feature', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: typeof next.enabled === 'boolean' ? next.enabled : enabled, dry_run: typeof next.dry_run === 'boolean' ? next.dry_run : dryRun }),
      })
      if (!res.ok) throw new Error('failed')
      toast.success('Zendesk feature updated')
    } catch (e) {
      setEnabled(prev.enabled)
      setDryRun(prev.dryRun)
      toast.error('Failed to update feature flags')
    } finally {
      setLoading(false)
    }
  }, [enabled, dryRun, loading])

  return (
    <div className="rounded-md border p-4 space-y-4">
      <h2 className="font-medium">Controls</h2>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-sm font-medium">Zendesk Enabled</div>
            <div className="text-xs text-muted-foreground">Master on/off flag</div>
          </div>
          <Switch
            checked={enabled}
            disabled={loading}
            onCheckedChange={(v) => updateFlags({ enabled: Boolean(v) })}
            aria-label="Toggle Zendesk enabled"
          />
        </div>
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-sm font-medium">Dry run</div>
            <div className="text-xs text-muted-foreground">Process without external side effects</div>
          </div>
          <Switch
            checked={dryRun}
            disabled={loading}
            onCheckedChange={(v) => updateFlags({ dry_run: Boolean(v) })}
            aria-label="Toggle Zendesk dry run"
          />
        </div>
      </div>
    </div>
  )
}
