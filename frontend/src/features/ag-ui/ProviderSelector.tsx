'use client'

import { ChevronDown } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/shared/ui/tooltip'
import { Provider, PROVIDER_LABELS, ProviderAvailability } from '@/services/api/endpoints/models'

interface ProviderSelectorProps {
  provider: Provider
  onChangeProvider: (provider: Provider) => void
  availableProviders: ProviderAvailability
  align?: 'left' | 'right'
}

const PROVIDER_DESCRIPTIONS: Record<Provider, string> = {
  google: 'Google Gemini - Fast and reliable AI models',
  xai: 'xAI Grok - Advanced reasoning with 2M context',
}

// Provider icons (simple text-based for now)
const PROVIDER_ICONS: Record<Provider, string> = {
  google: '✨',
  xai: '🚀',
}

export function ProviderSelector({
  provider,
  onChangeProvider,
  availableProviders,
  align = 'right',
}: ProviderSelectorProps) {
  // Get list of available providers
  const enabledProviders = (Object.keys(availableProviders) as Provider[]).filter(
    (p) => availableProviders[p]
  )

  const hasMultipleProviders = enabledProviders.length > 1
  const tooltipText = PROVIDER_DESCRIPTIONS[provider] || 'Select AI provider'

  // If only one provider is available, just show a static badge
  if (!hasMultipleProviders) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <div
              className={`flex items-center gap-1.5 h-9 px-3 rounded-organic border border-border bg-secondary text-sm text-foreground ${align === 'right' ? 'ml-auto' : ''}`}
            >
              <span>{PROVIDER_ICONS[provider]}</span>
              <span>{PROVIDER_LABELS[provider]}</span>
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

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className={`relative ${align === 'right' ? 'ml-auto' : ''}`}>
            <select
              value={provider}
              onChange={(e) => onChangeProvider(e.target.value as Provider)}
              aria-label="Select AI provider"
              className="w-full h-9 appearance-none rounded-organic border border-border bg-secondary pl-3 pr-8 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-terracotta-400/40 cursor-pointer"
            >
              {enabledProviders.map((p) => (
                <option key={p} value={p}>
                  {PROVIDER_ICONS[p]} {PROVIDER_LABELS[p]}
                </option>
              ))}
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
