"use client"

import React, { useRef } from 'react'
import { Plus, Mic } from 'lucide-react'
import { VoiceButton } from './VoiceButton'
import { SendIcon } from './SendIcon'

type Props = {
  value: string
  interimText?: string
  onInterim?: (t: string) => void
  onChange: (v: string) => void
  onSubmit: () => void
  onPickFiles: (files: FileList | null) => void | Promise<void>
  disabled?: boolean
  placeholder?: string
  provider: 'google' | 'openai'
  model: string
  onChangeProvider: (p: 'google' | 'openai') => void
  onChangeModel: (m: string) => void
  // Web search pill state
  searchMode?: 'auto' | 'web'
  onChangeSearchMode?: (mode: 'auto' | 'web') => void
}

export function CommandBar({ 
  value, 
  interimText, 
  onInterim, 
  onChange, 
  onSubmit, 
  onPickFiles, 
  disabled, 
  placeholder,
  provider,
  model,
  onChangeProvider,
  onChangeModel,
  searchMode = 'auto',
  onChangeSearchMode,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const submit = (e: React.FormEvent) => { 
    e.preventDefault()
    if (!disabled && (value.trim() || interimText?.trim())) {
      onSubmit()
    }
  }
  
  return (
    <form onSubmit={submit} className="w-full max-w-3xl mx-auto px-4">
      <div className="relative group">
        {/* Modern glass morphism input container */}
        <div className="relative rounded-[28px] bg-[hsl(var(--brand-surface)/0.90)] backdrop-blur-xl border border-border/50 px-4 py-5 md:py-6 shadow-lg hover:shadow-xl transition-all duration-300 focus-within:border-primary/50 min-h-[64px] md:min-h-[72px]">

          {/* Main input field */}
          <div className="flex-1 relative pr-16">
            <input
              type="text"
              className="w-full bg-transparent outline-none text-[15px] placeholder:text-muted-foreground/60 pr-2 pt-1 pb-9 md:pb-10"
              placeholder={placeholder || 'Ask anything...'}
              value={value}
              onChange={(e) => onChange(e.target.value)}
              disabled={disabled}
            />
            {!!interimText && (
              <div 
                aria-live="polite" 
                className="absolute inset-y-0 right-0 flex items-center text-xs text-muted-foreground/60 pointer-events-none"
              >
                {interimText}
              </div>
            )}
          </div>

          {/* Unified bottom controls row to guarantee alignment */}
          <div className="absolute inset-x-2 bottom-2 flex items-center justify-between">
            {/* Left cluster */}
            <div className="pointer-events-auto flex items-center gap-2 whitespace-nowrap">
              <button
                type="button"
                title="Add files"
                aria-label="Add files"
                className="w-8 h-8 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors rounded-full hover:bg-secondary/50"
                onClick={() => fileRef.current?.click()}
              >
                <Plus className="w-5 h-5 stroke-2" />
              </button>
              <button
                type="button"
                aria-label="Search mode"
                onClick={(e) => {
                  e.preventDefault()
                  if (!onChangeSearchMode) return
                  onChangeSearchMode(searchMode === 'web' ? 'auto' : 'web')
                }}
                className="px-3 h-8 rounded-full border border-border/40 text-xs flex items-center gap-1 hover:bg-secondary/50 text-foreground/90 bg-background/60 backdrop-blur-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-background leading-none"
                title={searchMode === 'web' ? 'Web search enabled' : 'Auto mode'}
              >
                <span
                  className="inline-block w-1.5 h-1.5 rounded-full"
                  style={{ background: searchMode === 'web' ? 'hsl(var(--primary))' : 'hsl(var(--muted-foreground))' }}
                />
                {searchMode === 'web' ? 'Web search' : 'Auto'}
              </button>
            </div>
            {/* Right cluster */}
            <div className="pointer-events-auto flex items-center gap-2">
              <VoiceButton
                onFinalText={(t) => onChange(value ? value + ' ' + t : t)}
                onInterimText={onInterim}
              />
              <button
                type="submit"
                disabled={disabled || (!value.trim() && !interimText?.trim())}
                aria-label="Send message"
                className="w-8 h-8 flex items-center justify-center rounded-full bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-200 hover:scale-105 active:scale-95"
              >
                <SendIcon className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Hidden file input */}
        <input
          ref={fileRef}
          type="file"
          className="hidden"
          multiple
          accept="image/*,audio/*,.txt,.log,.csv,.html,.htm"
          onChange={(e) => onPickFiles(e.target.files)}
        />
        
        {/* Subtle hint text */}
        {!value && !interimText && (
          <div className="absolute -bottom-6 left-0 right-0 text-center">
            <span className="text-[11px] text-muted-foreground/50">
              Press Enter to send • Attach files with the paperclip
            </span>
          </div>
        )}
      </div>
    </form>
  )
}
