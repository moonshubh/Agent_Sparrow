"use client"

import React, { useEffect, useState } from 'react'
import { cn } from '@/shared/lib/utils'
import { Check, Cloud, CloudOff, Loader2, AlertTriangle } from 'lucide-react'
import { Badge } from '@/shared/ui/badge'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/shared/ui/tooltip'

interface AutoSaveIndicatorProps {
  status: 'idle' | 'saving' | 'saved' | 'error' | 'offline'
  lastSaved?: Date
  className?: string
  showTooltip?: boolean
  message?: string
}

export function AutoSaveIndicator({ 
  status, 
  lastSaved, 
  className,
  showTooltip = true,
  message
}: AutoSaveIndicatorProps) {
  const [isVisible, setIsVisible] = useState(false)
  const [displayStatus, setDisplayStatus] = useState(status)

  useEffect(() => {
    // Show indicator when saving starts
    if (status === 'saving' || status === 'error' || status === 'offline') {
      setIsVisible(true)
      setDisplayStatus(status)
    }
    // Show saved state briefly then fade out
    else if (status === 'saved') {
      setIsVisible(true)
      setDisplayStatus('saved')
      const timer = setTimeout(() => {
        setIsVisible(false)
      }, 2000)
      return () => clearTimeout(timer)
    }
    // Hide when idle
    else if (status === 'idle') {
      setIsVisible(false)
    }
  }, [status])

  const getIcon = () => {
    switch (displayStatus) {
      case 'saving':
        return <Loader2 className="w-3 h-3 animate-spin" />
      case 'saved':
        return <Check className="w-3 h-3" />
      case 'error':
        return <AlertTriangle className="w-3 h-3" />
      case 'offline':
        return <CloudOff className="w-3 h-3" />
      default:
        return <Cloud className="w-3 h-3" />
    }
  }

  const getColor = () => {
    switch (displayStatus) {
      case 'saving':
        return 'text-blue-500 bg-blue-500/10 border-blue-500/30'
      case 'saved':
        return 'text-green-500 bg-green-500/10 border-green-500/30'
      case 'error':
        return 'text-red-500 bg-red-500/10 border-red-500/30'
      case 'offline':
        return 'text-yellow-500 bg-yellow-500/10 border-yellow-500/30'
      default:
        return 'text-zinc-500 bg-zinc-500/10 border-zinc-500/30'
    }
  }

  const getText = () => {
    if (message) return message
    
    switch (displayStatus) {
      case 'saving':
        return 'Saving...'
      case 'saved':
        return 'Saved'
      case 'error':
        return 'Save failed'
      case 'offline':
        return 'Offline'
      default:
        return 'Auto-save'
    }
  }

  const getTooltipContent = () => {
    if (displayStatus === 'saved' && lastSaved) {
      const time = lastSaved.toLocaleTimeString([], { 
        hour: '2-digit', 
        minute: '2-digit' 
      })
      return `Last saved at ${time}`
    }
    if (displayStatus === 'error') {
      return 'Failed to save. Will retry automatically.'
    }
    if (displayStatus === 'offline') {
      return 'You are offline. Changes will sync when connection is restored.'
    }
    if (displayStatus === 'saving') {
      return 'Saving your changes...'
    }
    return 'Auto-save is enabled'
  }

  const indicator = (
    <Badge
      variant="outline"
      className={cn(
        "flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium",
        "border backdrop-blur-sm transition-all duration-300",
        "animate-in fade-in slide-in-from-top-1",
        !isVisible && "opacity-0 pointer-events-none",
        getColor(),
        className
      )}
    >
      {getIcon()}
      <span>{getText()}</span>
      {displayStatus === 'saving' && (
        <span className="ml-1 flex gap-0.5">
          <span className="w-1 h-1 bg-current rounded-full animate-pulse" />
          <span className="w-1 h-1 bg-current rounded-full animate-pulse delay-100" />
          <span className="w-1 h-1 bg-current rounded-full animate-pulse delay-200" />
        </span>
      )}
    </Badge>
  )

  if (!showTooltip) return indicator

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          {indicator}
        </TooltipTrigger>
        <TooltipContent side="bottom" className="glass-effect">
          <p className="text-xs">{getTooltipContent()}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

// Hook for auto-save functionality
export function useAutoSave(
  saveFunction: () => Promise<void>,
  debounceMs: number = 1000
) {
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error' | 'offline'>('idle')
  const [lastSaved, setLastSaved] = useState<Date>()
  const [isOnline, setIsOnline] = useState(true)

  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true)
      setSaveStatus('idle')
    }
    const handleOffline = () => {
      setIsOnline(false)
      setSaveStatus('offline')
    }

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  useEffect(() => {
    if (!isOnline) {
      setSaveStatus('offline')
      return undefined
    }

    const timer = setTimeout(async () => {
      try {
        setSaveStatus('saving')
        await saveFunction()
        setSaveStatus('saved')
        setLastSaved(new Date())
      } catch (error) {
        console.error('Auto-save failed:', error)
        setSaveStatus('error')
      }
    }, debounceMs)

    return () => clearTimeout(timer)
  }, [isOnline, saveFunction, debounceMs])

  return { saveStatus, lastSaved }
}
