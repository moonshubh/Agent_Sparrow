"use client"

import React, { useMemo, useState } from 'react'
import { SlidersHorizontal } from 'lucide-react'

type Provider = 'google' | 'openai'

type Props = {
  provider: Provider
  model: string
  onChangeProvider: (p: Provider) => void
  onChangeModel: (m: string) => void
  align?: 'right' | 'left'
}

export function ModelSelector({ provider, model, onChangeProvider, onChangeModel, align = 'right' }: Props) {
  const [open, setOpen] = useState(false)

  const models = useMemo(() => {
    return provider === 'openai'
      ? ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini']
      : ['gemini-2.5-flash', 'gemini-2.5-pro']
  }, [provider])

  return (
    <div className="relative">
      <button
        type="button"
        aria-label="Select model"
        className="p-2 rounded-full text-muted-foreground hover:bg-muted"
        onClick={() => setOpen((v) => !v)}
      >
        <SlidersHorizontal className="w-6 h-6" />
      </button>
      {open && (
        <div
          className={[
            'absolute z-50 mt-2 w-72 rounded-xl border border-border bg-background shadow-lg p-3',
            align === 'right' ? 'right-0' : 'left-0',
          ].join(' ')}
        >
          <div className="text-xs text-muted-foreground mb-2">Model Settings</div>
          <div className="flex items-center gap-2 mb-2">
            <label className="text-xs text-muted-foreground w-20">Provider</label>
            <select
              className="border rounded p-1 flex-1"
              value={provider}
              onChange={(e) => onChangeProvider(e.target.value as Provider)}
            >
              <option value="google">Google (Gemini)</option>
              <option value="openai">OpenAI</option>
            </select>
          </div>
          <div className="flex items-center gap-2 mb-2">
            <label className="text-xs text-muted-foreground w-20">Model</label>
            <input
              className="border rounded p-1 flex-1"
              value={model}
              onChange={(e) => onChangeModel(e.target.value)}
              list="model-options"
            />
            <datalist id="model-options">
              {models.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </div>
          <div className="flex justify-end">
            <button
              type="button"
              className="text-xs px-2 py-1 rounded border border-border hover:bg-muted"
              onClick={() => setOpen(false)}
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

