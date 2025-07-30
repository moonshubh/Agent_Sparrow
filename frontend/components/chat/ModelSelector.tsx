import React from 'react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

export interface ModelOption {
  label: string
  value: string
  description?: string
  rpmLimit?: number
  rpdLimit?: number  // Requests per day
  badge?: string
}

const MODEL_OPTIONS: ModelOption[] = [
  {
    label: 'Gemini 2.5 Flash',
    value: 'google/gemini-2.5-flash',
    description: 'Fast and efficient (default)',
    rpmLimit: 10,   // Actual Google API free tier limit
    rpdLimit: 250,  // Requests per day limit
    badge: 'Default'
  },
  {
    label: 'Gemini 2.5 Pro',
    value: 'google/gemini-2.5-pro',
    description: 'Advanced reasoning capabilities',
    rpmLimit: 5,    // Actual Google API free tier limit
    rpdLimit: 100,  // Requests per day limit
  },
  {
    label: 'Kimi K2',
    value: 'moonshotai/kimi-k2',
    description: '1T parameter MoE model (open-source)',
    rpmLimit: 20,   // OpenRouter free tier limit
    badge: 'Free Tier'
  },
]

interface ModelSelectorProps {
  value?: string
  onChange: (value: string) => void
  disabled?: boolean
  className?: string
}

export function ModelSelector({ value, onChange, disabled, className }: ModelSelectorProps) {
  const currentValue = value || MODEL_OPTIONS[0].value

  return (
    <Select value={currentValue} onValueChange={onChange} disabled={disabled} className={className}>
      <SelectTrigger className="w-[220px] h-8 text-sm">
        <SelectValue placeholder="Select a model" />
      </SelectTrigger>
      <SelectContent className="text-sm">
        {MODEL_OPTIONS.map((option) => (
          <SelectItem key={option.value} value={option.value} className="text-sm">
            <div className="flex items-center gap-2">
              <span className="text-sm truncate">{option.label}</span>
              {option.badge && (
                <span className="text-xs bg-accent/20 text-accent px-1.5 py-0.5 rounded flex-shrink-0">
                  {option.badge}
                </span>
              )}
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}