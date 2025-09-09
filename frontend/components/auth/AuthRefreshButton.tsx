"use client"

import React, { useState } from 'react'
import { Button } from '@/components/ui/button'
import { RefreshCw, Check, AlertCircle } from 'lucide-react'
import { supabase } from '@/lib/supabase-browser'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

interface AuthRefreshButtonProps {
  onSuccess?: () => void
  onError?: (error: Error) => void
  showTooltip?: boolean
  variant?: 'default' | 'outline' | 'ghost' | 'secondary'
  size?: 'default' | 'sm' | 'lg' | 'icon'
  className?: string
}

export function AuthRefreshButton({
  onSuccess,
  onError,
  showTooltip = true,
  variant = 'outline',
  size = 'sm',
  className
}: AuthRefreshButtonProps) {
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [status, setStatus] = useState<'idle' | 'success' | 'error'>('idle')

  const handleRefresh = async () => {
    try {
      setIsRefreshing(true)
      setStatus('idle')

      const { data, error } = await supabase.auth.refreshSession()

      if (error) throw error

      if (data.session) {
        setStatus('success')
        toast.success('Session refreshed successfully')
        onSuccess?.()

        // Reset status after animation
        setTimeout(() => setStatus('idle'), 2000)
      } else {
        throw new Error('No session returned from refresh')
      }
    } catch (error) {
      console.error('Failed to refresh session:', error)
      setStatus('error')
      
      const errorMessage = error instanceof Error ? error.message : 'Failed to refresh session'
      toast.error(errorMessage)
      onError?.(error instanceof Error ? error : new Error(errorMessage))

      // Reset status after animation
      setTimeout(() => setStatus('idle'), 3000)
    } finally {
      setIsRefreshing(false)
    }
  }

  const getIcon = () => {
    switch (status) {
      case 'success':
        return <Check className="h-4 w-4" />
      case 'error':
        return <AlertCircle className="h-4 w-4" />
      default:
        return <RefreshCw className={cn("h-4 w-4", isRefreshing && "animate-spin")} />
    }
  }

  const getButtonColor = () => {
    switch (status) {
      case 'success':
        return 'text-green-500 border-green-500/30 hover:bg-green-500/10'
      case 'error':
        return 'text-red-500 border-red-500/30 hover:bg-red-500/10'
      default:
        return ''
    }
  }

  const button = (
    <Button
      variant={variant}
      size={size}
      onClick={handleRefresh}
      disabled={isRefreshing}
      className={cn(
        "glass-effect transition-all duration-200",
        getButtonColor(),
        className
      )}
    >
      {getIcon()}
      {size !== 'icon' && (
        <span className="ml-2">
          {isRefreshing ? 'Refreshing...' : 'Refresh Token'}
        </span>
      )}
    </Button>
  )

  if (!showTooltip || size === 'icon') {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            {button}
          </TooltipTrigger>
          <TooltipContent className="glass-effect">
            <p className="text-xs">Refresh your authentication token</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }

  return button
}