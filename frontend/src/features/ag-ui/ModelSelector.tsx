'use client'

import { ChevronDown } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/shared/ui/tooltip'

interface ModelSelectorProps {
  model: string
  onChangeModel: (model: string) => void
  align?: 'left' | 'right'
  models: string[]
  helperText?: string
  recommended?: string
}

const MODEL_DESCRIPTIONS: Record<string, string> = {
  'gemini-2.5-flash': 'Flash balances speed and cost for orchestrating subagents.',
  'gemini-2.5-pro': 'Pro provides deeper reasoning and analysis for complex tasks.',
}

export function ModelSelector({
  model,
  onChangeModel,
  align = 'right',
  models,
  helperText,
  recommended,
}: ModelSelectorProps) {
  const supportedModels = new Set(['gemini-2.5-flash', 'gemini-2.5-pro']);
  const vettedModels = models.filter((m) => supportedModels.has(m));
  const displayModels = vettedModels.length > 0 ? vettedModels : models;
  const tooltipText =
    MODEL_DESCRIPTIONS[model] ||
    (recommended && model === recommended ? `${model} (recommended)` : helperText) ||
    'Select a model';
  const hasModels = displayModels.length > 0;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className={`relative ${align === 'right' ? 'ml-auto' : ''}`}>
            <select
              value={model}
              onChange={(e) => onChangeModel(e.target.value)}
              disabled={!hasModels}
              aria-label="Select model"
              className="w-full h-9 appearance-none rounded-organic border border-border bg-secondary pl-3 pr-8 text-sm text-foreground placeholder:text-muted-foreground disabled:opacity-60 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-terracotta-400/40 cursor-pointer"
            >
              {!hasModels ? (
                <option>No models available</option>
              ) : (
                displayModels.map((m) => (
                  <option key={m} value={m}>
                    {recommended && recommended === m ? `${m} (recommended)` : m}
                  </option>
                ))
              )}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          </div>
        </TooltipTrigger>
        <TooltipContent
          side="bottom"
          className="max-w-[200px] text-xs bg-card border-border text-foreground shadow-academia-md"
        >
          <p>{tooltipText}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
