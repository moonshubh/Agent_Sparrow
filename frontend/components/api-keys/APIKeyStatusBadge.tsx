"use client"

import React, { useEffect, useState } from 'react'
import { Key, AlertCircle, CheckCircle, Loader2 } from 'lucide-react'
import { checkUserAPIKeyStatus } from '@/lib/api/api-key-service-secure'
import { supabase } from '@/lib/supabase-browser'
import { APIKeyType } from '@/lib/api-keys'
import { cn } from '@/lib/utils'

interface APIKeyStatusBadgeProps {
  className?: string
  onClick?: () => void
}

type KeyStatus = 'active' | 'fallback' | 'missing' | 'loading' | 'error'

export function APIKeyStatusBadge({ className, onClick }: APIKeyStatusBadgeProps) {
  const [status, setStatus] = useState<KeyStatus>('loading')
  const [provider, setProvider] = useState<string>('')
  
  useEffect(() => {
    checkAPIKeyStatus()
    const interval = setInterval(checkAPIKeyStatus, 60000) // Check every minute
    return () => clearInterval(interval)
  }, [])

  const checkAPIKeyStatus = async () => {
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        setStatus('fallback')
        setProvider('Server')
        return
      }

      // For now, since the backend endpoint doesn't exist yet, 
      // we'll default to showing server key status
      // TODO: Implement backend endpoint /api/v1/api-keys/status/{keyType}
      setStatus('fallback')
      setProvider('Server Key')
      
      // Uncomment when backend endpoint is ready:
      // const keyStatus = await checkUserAPIKeyStatus(session.access_token, APIKeyType.GEMINI)
      // if (keyStatus?.is_configured && keyStatus?.is_active) {
      //   setStatus('active')
      //   setProvider('Gemini')
      // } else if (keyStatus?.is_configured) {
      //   setStatus('error')
      //   setProvider('Invalid Key')
      // } else {
      //   setStatus('fallback')
      //   setProvider('Server')
      // }
    } catch (error) {
      console.error('Failed to check API key status:', error)
      setStatus('fallback')
      setProvider('Server')
    }
  }

  const getStatusColor = () => {
    switch (status) {
      case 'active': return 'bg-green-500/20 text-green-500 border-green-500/30'
      case 'fallback': return 'bg-yellow-500/20 text-yellow-500 border-yellow-500/30'
      case 'missing': return 'bg-red-500/20 text-red-500 border-red-500/30'
      case 'error': return 'bg-red-500/20 text-red-500 border-red-500/30'
      default: return 'bg-zinc-500/20 text-zinc-500 border-zinc-500/30'
    }
  }

  const getStatusIcon = () => {
    switch (status) {
      case 'active': return <CheckCircle className="w-3.5 h-3.5" />
      case 'fallback': return <AlertCircle className="w-3.5 h-3.5" />
      case 'missing': return <AlertCircle className="w-3.5 h-3.5" />
      case 'error': return <AlertCircle className="w-3.5 h-3.5" />
      case 'loading': return <Loader2 className="w-3.5 h-3.5 animate-spin" />
      default: return <Key className="w-3.5 h-3.5" />
    }
  }

  const getStatusText = () => {
    switch (status) {
      case 'active': return `${provider} Key Active`
      case 'fallback': return 'Using Server Key'
      case 'missing': return 'No API Key'
      case 'error': return 'Key Check Failed'
      case 'loading': return 'Checking...'
      default: return 'Unknown'
    }
  }

  return (
    <button
      onClick={onClick}
      className={cn(
        'flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium',
        'border backdrop-blur-sm transition-all duration-200',
        'hover:scale-105 active:scale-95 cursor-pointer',
        getStatusColor(),
        className
      )}
      title={`API Key Status: ${getStatusText()}`}
    >
      {getStatusIcon()}
      <span>{getStatusText()}</span>
      <div className={cn(
        'w-1.5 h-1.5 rounded-full',
        status === 'active' ? 'bg-green-500' : 
        status === 'fallback' ? 'bg-yellow-500' : 
        status === 'missing' || status === 'error' ? 'bg-red-500' : 
        'bg-zinc-500',
        status === 'loading' && 'animate-pulse'
      )} />
    </button>
  )
}