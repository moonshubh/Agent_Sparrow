"use client"

import React, { useCallback, useEffect, useState } from 'react'
import { Badge } from '@/shared/ui/badge'
import { Circle, Cloud, CloudOff, Loader2 } from 'lucide-react'
import { sessionsAPI, ChatSession } from '@/services/api/endpoints/sessions'
import { cn } from '@/shared/lib/utils'

interface SessionStatusChipProps {
  sessionId?: string | null
  className?: string
  showDetails?: boolean
}

export function SessionStatusChip({ 
  sessionId, 
  className,
  showDetails = true 
}: SessionStatusChipProps) {
  const [session, setSession] = useState<ChatSession | null>(null)
  const [isOnline, setIsOnline] = useState(true)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    // Monitor online status
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  const fetchSessionDetails = useCallback(async () => {
    if (!sessionId) return

    try {
      setLoading(true)
      // Fetch session details from list (API doesn't have get by ID)
      const sessions = await sessionsAPI.list(100, 0)
      const currentSession = sessions.find(s => s.id === sessionId)
      if (currentSession) {
        setSession(currentSession)
      }
    } catch (error) {
      console.error('Failed to fetch session details:', error)
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => {
    if (sessionId) {
      void fetchSessionDetails()
    } else {
      setSession(null)
    }
  }, [sessionId, fetchSessionDetails])

  const getStatusIcon = () => {
    if (loading) return <Loader2 className="w-3 h-3 animate-spin" />
    if (!isOnline) return <CloudOff className="w-3 h-3" />
    if (session) return <Circle className="w-3 h-3 animate-pulse fill-current" />
    return <Cloud className="w-3 h-3" />
  }

  const getStatusColor = () => {
    if (!isOnline) return 'bg-red-500/20 text-red-500 border-red-500/30'
    if (session) return 'bg-green-500/20 text-green-500 border-green-500/30'
    return 'bg-zinc-500/20 text-zinc-500 border-zinc-500/30'
  }

  const getStatusText = () => {
    if (!isOnline) return 'Offline'
    if (loading) return 'Loading...'
    if (session) {
      if (!showDetails) return 'Active'
      const agentType = session.agent_type || 'primary'
      return `${agentType.charAt(0).toUpperCase() + agentType.slice(1)} Session`
    }
    return 'No Session'
  }

  const formatTime = (dateString?: string) => {
    if (!dateString) return ''
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    
    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    
    const diffHours = Math.floor(diffMins / 60)
    if (diffHours < 24) return `${diffHours}h ago`
    
    const diffDays = Math.floor(diffHours / 24)
    return `${diffDays}d ago`
  }

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <Badge 
        variant="outline" 
        className={cn(
          "flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium",
          "border backdrop-blur-sm transition-all duration-200",
          getStatusColor()
        )}
      >
        {getStatusIcon()}
        <span>{getStatusText()}</span>
      </Badge>
      
      {showDetails && session && session.updated_at && (
        <span className="text-xs text-muted-foreground">
          {formatTime(session.updated_at)}
        </span>
      )}
    </div>
  )
}
