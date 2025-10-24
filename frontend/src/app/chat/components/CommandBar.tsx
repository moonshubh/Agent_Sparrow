"use client"

import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Plus } from 'lucide-react'
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
  memoryEnabled?: boolean
  onToggleMemory?: (enabled: boolean) => void
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
  memoryEnabled = true,
  onToggleMemory,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [showSlashMenu, setShowSlashMenu] = useState(false)
  const [slashIndex, setSlashIndex] = useState(0)

  const slashCommands = useMemo(
    () => [
      {
        cmd: '/feedback',
        title: 'Feedback',
        description: 'Share corrections or improvements for global knowledge',
      },
      {
        cmd: '/correct',
        title: 'Correct',
        description: 'Prefill selected text as incorrect and provide the corrected version',
      },
    ],
    [],
  )

  const filtered = useMemo(() => {
    const trimmed = (value || '').trimStart()
    if (!trimmed.startsWith('/')) return []
    const term = trimmed.slice(1).split(/\s+/)[0]?.toLowerCase() || ''
    if (!term) return slashCommands
    return slashCommands.filter((s) => s.cmd.includes(term))
  }, [slashCommands, value])

  useEffect(() => {
    const active = !disabled && filtered.length > 0
    setShowSlashMenu(active)
    setSlashIndex(0)
  }, [filtered.length, disabled])
  const submit = (e: React.FormEvent) => { 
    e.preventDefault()
    if (!disabled && (value.trim() || interimText?.trim())) {
      onSubmit()
    }
  }
  
  const acceptSlash = (idx: number) => {
    const item = filtered[idx]
    if (!item) return
    const next = item.cmd + ' '
    onChange(next)
    setShowSlashMenu(false)
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
              onKeyDown={(e) => {
                if (!showSlashMenu) return
                if (e.key === 'ArrowDown') {
                  e.preventDefault()
                  setSlashIndex((i) => (i + 1) % filtered.length)
                } else if (e.key === 'ArrowUp') {
                  e.preventDefault()
                  setSlashIndex((i) => (i - 1 + filtered.length) % filtered.length)
                } else if (e.key === 'Enter' || e.key === 'Tab') {
                  e.preventDefault()
                  acceptSlash(slashIndex)
                } else if (e.key === 'Escape') {
                  setShowSlashMenu(false)
                }
              }}
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
              {process.env.NEXT_PUBLIC_ENABLE_MEMORY !== 'false' && (
                <button
                  type="button"
                  aria-label="Use server memory"
                  onClick={(e) => {
                    e.preventDefault()
                    onToggleMemory?.(!memoryEnabled)
                  }}
                  className="px-3 h-8 rounded-full border border-border/40 text-xs flex items-center gap-1 hover:bg-secondary/50 text-foreground/90 bg-background/60 backdrop-blur-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-background leading-none"
                  title={memoryEnabled ? 'Server memory enabled' : 'Server memory disabled'}
                >
                  <span
                    className="inline-block w-1.5 h-1.5 rounded-full"
                    style={{ background: memoryEnabled ? 'hsl(var(--primary))' : 'hsl(var(--muted-foreground))' }}
                  />
                  {memoryEnabled ? 'Memory on' : 'Memory off'}
                </button>
              )}
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

        {/* Slash command suggestions */}
        {showSlashMenu && (
          <div
            role="listbox"
            aria-label="Slash commands"
            className="absolute left-4 right-4 bottom-[76px] z-[60] overflow-hidden rounded-lg border border-border/50 bg-popover shadow-xl"
          >
            {filtered.map((item, idx) => (
              <button
                key={item.cmd}
                role="option"
                aria-selected={slashIndex === idx}
                className={
                  'flex w-full items-start gap-3 px-3 py-2 text-left text-sm hover:bg-muted/40 data-[selected=true]:bg-muted/50'
                }
                data-selected={slashIndex === idx}
                onMouseEnter={() => setSlashIndex(idx)}
                onClick={(e) => {
                  e.preventDefault()
                  acceptSlash(idx)
                }}
              >
                <span className="inline-flex h-6 min-w-20 items-center rounded-md bg-muted/50 px-2 font-mono text-xs text-foreground/80">
                  {item.cmd}
                </span>
                <span className="flex-1">
                  <span className="block text-foreground/90 font-medium">{item.title}</span>
                  <span className="block text-muted-foreground text-xs">{item.description}</span>
                </span>
              </button>
            ))}
          </div>
        )}

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

