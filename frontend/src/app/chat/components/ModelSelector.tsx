'use client'

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/ui/select'
import { Label } from '@/shared/ui/label'
import { useEffect, useMemo } from 'react'

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
  const models = modelsByProvider?.[provider] || []
  const defaultModel = useMemo(() => (models.length ? models[0] : model), [models, model])

  // Validate and reset model when provider changes
  useEffect(() => {
    if (!models.includes(model)) {
      // Model is invalid for current provider, reset to default
      onChangeModel(defaultModel)
    }
  }, [provider, model, models, onChangeModel, defaultModel])

  const handleProviderChange = (newProvider: Provider) => {
    onChangeProvider(newProvider)
    // Also set the default model for the new provider
    const next = (modelsByProvider?.[newProvider] || [])[0]
    if (next) onChangeModel(next)
  }

  return (
    <div className={`flex items-center gap-2 ${align === 'right' ? 'ml-auto' : ''}`}>
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Provider</Label>
        <Select value={provider} onValueChange={(v) => handleProviderChange(v as Provider)}>
          <SelectTrigger className="w-32 h-8">
            <SelectValue placeholder="Provider" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="google">Google</SelectItem>
            <SelectItem value="openai">OpenAI</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Model</Label>
        <Select value={model} onValueChange={(v) => onChangeModel(v)}>
          <SelectTrigger className="w-40 h-8">
            <SelectValue placeholder="Model" />
          </SelectTrigger>
          <SelectContent>
            {models.map((m) => (
              <SelectItem key={m} value={m}>
                {m}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}