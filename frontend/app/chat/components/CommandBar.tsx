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
  onPickFiles: (files: FileList | null) => void
  disabled?: boolean
  placeholder?: string
  provider: 'google' | 'openai'
  model: string
  onChangeProvider: (p: 'google' | 'openai') => void
  onChangeModel: (m: string) => void
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
  onChangeModel
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
        <div className="relative flex items-center gap-2 rounded-[28px] bg-background/60 dark:bg-zinc-900/60 backdrop-blur-xl border border-border/40 dark:border-zinc-800/60 px-4 py-3 shadow-lg hover:shadow-xl transition-all duration-300 focus-within:border-primary/50">
          
          {/* Attachment button - clean + icon */}
          <button
            type="button"
            title="Add files"
            aria-label="Add files"
            className="flex-shrink-0 w-8 h-8 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors rounded-full hover:bg-secondary/50"
            onClick={() => fileRef.current?.click()}
          >
            <Plus className="w-5 h-5 stroke-2" />
          </button>
          
          {/* Main input field */}
          <div className="flex-1 relative">
            <input
              type="text"
              className="w-full bg-transparent outline-none text-[15px] placeholder:text-muted-foreground/60 pr-2"
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

          {/* Voice button */}
          <VoiceButton 
            onFinalText={(t) => onChange((prev) => (prev ? prev + ' ' : '') + t)} 
            onInterimText={onInterim}
            className="flex-shrink-0"
          />
          
          {/* Submit button with custom arrow icon */}
          <button
            type="submit"
            disabled={disabled || (!value.trim() && !interimText?.trim())}
            aria-label="Send message"
            className="flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-full bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-200 hover:scale-105 active:scale-95"
          >
            <SendIcon className="w-4 h-4" />
          </button>
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