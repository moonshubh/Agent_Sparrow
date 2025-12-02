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

// Official model display names and descriptions
const MODEL_INFO: Record<string, { name: string; description: string; provider: 'google' | 'xai' | 'openrouter' }> = {
  // Google Gemini (official names from ai.google.dev/gemini-api/docs/models)
  'gemini-3-pro-preview': {
    name: 'Gemini 3.0 Pro',
    description: 'Most intelligent model with advanced multimodal understanding and agentic capabilities.',
    provider: 'google',
  },
  'gemini-2.5-pro': {
    name: 'Gemini 2.5 Pro',
    description: 'Advanced thinking model for complex reasoning over code, math, and STEM.',
    provider: 'google',
  },
  'gemini-2.5-flash': {
    name: 'Gemini 2.5 Flash',
    description: 'Best price-performance for large scale processing and agentic tasks.',
    provider: 'google',
  },
  // xAI Grok (official from docs.x.ai)
  'grok-4-1-fast-reasoning': {
    name: 'Grok 4.1 Fast',
    description: 'Fast reasoning model with 2M token context window.',
    provider: 'xai',
  },
  // OpenRouter models
  'x-ai/grok-4.1-fast:free': {
    name: 'Grok 4.1 Fast',
    description: 'Grok 4.1 via OpenRouter (free tier).',
    provider: 'openrouter',
  },
  'minimax/minimax-m2': {
    name: 'MiniMax M2',
    description: 'MiniMax M2 via OpenRouter - fast and capable.',
    provider: 'openrouter',
  },
}

// Main coordinator models only (no preview variants or lite models)
const COORDINATOR_MODELS = new Set([
  // Google Gemini - main coordinator models
  'gemini-3-pro-preview',
  'gemini-2.5-pro',
  'gemini-2.5-flash',
  // xAI Grok
  'grok-4-1-fast-reasoning',
  // OpenRouter
  'x-ai/grok-4.1-fast:free',
  'minimax/minimax-m2',
])

// Provider logos as inline SVGs
const ProviderLogo = ({ provider }: { provider: 'google' | 'xai' | 'openrouter' }) => {
  switch (provider) {
    case 'google':
      return (
        <svg className="w-4 h-4 mr-1.5 flex-shrink-0" viewBox="0 0 24 24" fill="none">
          <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
          <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
          <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
          <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
        </svg>
      )
    case 'xai':
      return (
        <svg className="w-4 h-4 mr-1.5 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
          <path d="M13.982 10.622L20.54 3h-1.554l-5.693 6.618L8.244 3H3l6.878 10.007L3 21h1.554l6.014-6.989L15.756 21H21l-7.018-10.378zm-2.128 2.474l-.697-.997L5.084 4.104h2.387l4.474 6.4.697.996 5.815 8.318h-2.387l-4.745-6.79v-.032z"/>
        </svg>
      )
    case 'openrouter':
      return (
        <svg className="w-4 h-4 mr-1.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10"/>
          <path d="M12 6v12M6 12h12"/>
        </svg>
      )
  }
}

// Get display name for a model
const getDisplayName = (modelId: string, isRecommended?: boolean): string => {
  const info = MODEL_INFO[modelId]
  const name = info?.name || modelId
  return isRecommended ? `${name} (recommended)` : name
}

// Get provider from model ID
const getProvider = (modelId: string): 'google' | 'xai' | 'openrouter' => {
  return MODEL_INFO[modelId]?.provider || 'google'
}

export function ModelSelector({
  model,
  onChangeModel,
  align = 'right',
  models,
  helperText,
  recommended,
}: ModelSelectorProps) {
  // Filter to main coordinator models only
  const coordinatorModels = models.filter((m) => COORDINATOR_MODELS.has(m))
  const displayModels = coordinatorModels.length > 0 ? coordinatorModels : models

  const currentInfo = MODEL_INFO[model]
  const tooltipText = currentInfo?.description || helperText || 'Select a model'
  const hasModels = displayModels.length > 0
  const currentProvider = getProvider(model)

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className={`relative ${align === 'right' ? 'ml-auto' : ''}`}>
            {/* Custom display showing logo + name */}
            <div className="flex items-center h-9 rounded-organic border border-border bg-secondary pl-2.5 pr-8 text-sm text-foreground cursor-pointer hover:bg-secondary/80 transition-colors">
              <ProviderLogo provider={currentProvider} />
              <span className="truncate">{getDisplayName(model, model === recommended)}</span>
            </div>
            {/* Hidden native select for accessibility */}
            <select
              value={model}
              onChange={(e) => onChangeModel(e.target.value)}
              disabled={!hasModels}
              aria-label="Select model"
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
            >
              {!hasModels ? (
                <option>No models available</option>
              ) : (
                displayModels.map((m) => (
                  <option key={m} value={m}>
                    {getDisplayName(m, m === recommended)}
                  </option>
                ))
              )}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          </div>
        </TooltipTrigger>
        <TooltipContent
          side="bottom"
          className="max-w-[240px] text-xs bg-card border-border text-foreground shadow-academia-md"
        >
          <p>{tooltipText}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
