'use client'

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { useEffect } from 'react'

type Provider = 'google' | 'openai'

interface ModelSelectorProps {
  provider: Provider
  model: string
  onChangeProvider: (provider: Provider) => void
  onChangeModel: (model: string) => void
  align?: 'left' | 'right'
}

const MODELS_BY_PROVIDER: Record<Provider, string[]> = {
  google: ['gemini-2.5-flash-preview-09-2025', 'gemini-2.5-flash'],
  openai: ['gpt-5-mini', 'gpt5-mini'],
}

const DEFAULT_MODELS: Record<Provider, string> = {
  google: 'gemini-2.5-flash-preview-09-2025',
  openai: 'gpt-5-mini',
}

export function ModelSelector({
  provider,
  model,
  onChangeProvider,
  onChangeModel,
  align = 'right',
}: ModelSelectorProps) {
  const models = MODELS_BY_PROVIDER[provider] || []

  // Validate and reset model when provider changes
  useEffect(() => {
    if (!models.includes(model)) {
      // Model is invalid for current provider, reset to default
      onChangeModel(DEFAULT_MODELS[provider])
    }
  }, [provider, model, models, onChangeModel])

  const handleProviderChange = (newProvider: Provider) => {
    onChangeProvider(newProvider)
    // Also set the default model for the new provider
    onChangeModel(DEFAULT_MODELS[newProvider])
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