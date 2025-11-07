'use client'

import { Label } from '@/shared/ui/label'

type Provider = 'google' | 'openai'

interface ModelSelectorProps {
  provider: Provider
  model: string
  onChangeProvider: (provider: Provider) => void
  onChangeModel: (model: string) => void
  align?: 'left' | 'right'
  modelsByProvider: Record<Provider, string[]>
}

export function ModelSelector({
  provider,
  model,
  onChangeProvider,
  onChangeModel,
  align = 'right',
  modelsByProvider,
}: ModelSelectorProps) {
  const models = modelsByProvider?.[provider] ?? []

  // TEMPORARILY SIMPLIFIED: Using regular select elements to avoid infinite loop issues
  return (
    <div className={`flex items-center gap-2 ${align === 'right' ? 'ml-auto' : ''}`}>
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Provider</Label>
        <select
          value={provider}
          onChange={(e) => onChangeProvider(e.target.value as Provider)}
          className="w-32 h-8 px-2 rounded-md border border-input bg-background text-sm"
        >
          <option value="google">Google</option>
          <option value="openai">OpenAI</option>
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Model</Label>
        <select
          value={model}
          onChange={(e) => onChangeModel(e.target.value)}
          disabled={models.length === 0}
          className="w-40 h-8 px-2 rounded-md border border-input bg-background text-sm disabled:opacity-50"
        >
          {models.length === 0 ? (
            <option>No models available</option>
          ) : (
            models.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))
          )}
        </select>
      </div>
    </div>
  )
}
