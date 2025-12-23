"use client"

import { useState, useCallback, useEffect } from 'react'
import { Switch } from '@/shared/ui/switch'
import { toast } from 'sonner'

interface ModelOption {
  id: string
  name: string
}

interface ModelsConfig {
  models: Record<string, ModelOption[]>
  available_providers: string[]
  default_provider: string
  default_model: string
}

interface FeatureTogglesProps {
  initialEnabled: boolean
  initialDryRun: boolean
  initialProvider?: string
  initialModel?: string
}

const PROVIDER_LABELS: Record<string, string> = {
  google: 'Google (Gemini)',
  xai: 'xAI (Grok)',
  openrouter: 'OpenRouter',
}

export function FeatureToggles({ initialEnabled, initialDryRun, initialProvider, initialModel }: FeatureTogglesProps) {
  const [enabled, setEnabled] = useState<boolean>(!!initialEnabled)
  const [dryRun, setDryRun] = useState<boolean>(!!initialDryRun)
  const [provider, setProvider] = useState<string>(initialProvider || 'google')
  const [model, setModel] = useState<string>(initialModel || 'gemini-3-flash-preview')
  const [loading, setLoading] = useState<boolean>(false)
  const [modelsConfig, setModelsConfig] = useState<ModelsConfig | null>(null)

  // Fetch available models on mount
  useEffect(() => {
    async function fetchModels() {
      try {
        const res = await fetch('/api/admin/zendesk/models')
        if (res.ok) {
          const data = await res.json()
          setModelsConfig(data)
        }
      } catch (e) {
        console.error('Failed to fetch models config:', e)
      }
    }
    fetchModels()
  }, [])

  const updateFlags = useCallback(async (next: { enabled?: boolean; dry_run?: boolean; provider?: string; model?: string }) => {
    if (loading) return
    setLoading(true)
    const prev = { enabled, dryRun, provider, model }
    if (typeof next.enabled === 'boolean') setEnabled(next.enabled)
    if (typeof next.dry_run === 'boolean') setDryRun(next.dry_run)
    if (typeof next.provider === 'string') setProvider(next.provider)
    if (typeof next.model === 'string') setModel(next.model)
    try {
      const res = await fetch('/api/admin/zendesk/feature', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled: typeof next.enabled === 'boolean' ? next.enabled : enabled,
          dry_run: typeof next.dry_run === 'boolean' ? next.dry_run : dryRun,
          provider: typeof next.provider === 'string' ? next.provider : provider,
          model: typeof next.model === 'string' ? next.model : model,
        }),
      })
      if (!res.ok) throw new Error('failed')
      toast.success('Zendesk settings updated')
    } catch (e) {
      setEnabled(prev.enabled)
      setDryRun(prev.dryRun)
      setProvider(prev.provider)
      setModel(prev.model)
      toast.error('Failed to update settings')
    } finally {
      setLoading(false)
    }
  }, [enabled, dryRun, provider, model, loading])

  // When provider changes, select first available model for that provider
  const handleProviderChange = (newProvider: string) => {
    const models = modelsConfig?.models?.[newProvider] || []
    const firstModel = models[0]?.id || ''
    updateFlags({ provider: newProvider, model: firstModel })
  }

  const availableModels = modelsConfig?.models?.[provider] || []
  const availableProviders = modelsConfig?.available_providers || ['google']

  return (
    <div className="rounded-md border p-4 space-y-6">
      <h2 className="font-medium">Controls</h2>

      {/* Toggle Switches */}
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

      {/* Model Selection */}
      <div className="border-t pt-4 space-y-4">
        <h3 className="text-sm font-medium">AI Model Configuration</h3>

        <div className="grid gap-4 md:grid-cols-2">
          {/* Provider Selector */}
          <div className="space-y-2">
            <label className="text-sm text-muted-foreground">Provider</label>
            <select
              value={provider}
              onChange={(e) => handleProviderChange(e.target.value)}
              disabled={loading}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
            >
              {availableProviders.map((p) => (
                <option key={p} value={p}>
                  {PROVIDER_LABELS[p] || p}
                </option>
              ))}
            </select>
          </div>

          {/* Model Selector */}
          <div className="space-y-2">
            <label className="text-sm text-muted-foreground">Model</label>
            <select
              value={model}
              onChange={(e) => updateFlags({ model: e.target.value })}
              disabled={loading || availableModels.length === 0}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
            >
              {availableModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <p className="text-xs text-muted-foreground">
          Default: Gemini 3 Flash. Enable dry run to test model changes without affecting live tickets.
        </p>
      </div>
    </div>
  )
}
