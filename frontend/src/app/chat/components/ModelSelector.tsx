'use client'

import { Label } from '@/shared/ui/label'

interface ModelSelectorProps {
  model: string
  onChangeModel: (model: string) => void
  align?: 'left' | 'right'
  models: string[]
}

export function ModelSelector({
  model,
  onChangeModel,
  align = 'right',
  models,
}: ModelSelectorProps) {
  return (
    <div className={`flex items-center gap-2 ${align === 'right' ? 'ml-auto' : ''}`}>
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
