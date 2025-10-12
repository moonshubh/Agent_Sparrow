'use client'

import React, { useMemo, useCallback } from 'react'
import { Avatar, AvatarFallback, AvatarImage } from '@/shared/ui/avatar'
import { cn } from '@/shared/lib/utils'
import { User } from '@supabase/supabase-js'

type StatusType = 'online' | 'offline' | 'away' | 'busy'

interface UserAvatarProps {
  user: User | null
  size?: 'sm' | 'md' | 'lg' | 'xl'
  showStatus?: boolean
  statusType?: StatusType
  statusColor?: string
  showName?: boolean
  className?: string
}

const sizeMap = {
  sm: 'h-6 w-6 text-xs',
  md: 'h-8 w-8 text-sm',
  lg: 'h-10 w-10 text-base',
  xl: 'h-12 w-12 text-lg'
}

const statusSizeMap = {
  sm: 'h-2 w-2',
  md: 'h-2.5 w-2.5',
  lg: 'h-3 w-3',
  xl: 'h-3.5 w-3.5'
}

export const UserAvatar: React.FC<UserAvatarProps> = ({
  user,
  size = 'md',
  showStatus = false,
  statusType = 'online',
  statusColor,
  showName = false,
  className
}) => {
  const getInitials = useCallback((name?: string | null, email?: string | null) => {
    if (name) {
      return name
        .trim()
        .split(/\s+/) // Split by one or more whitespace characters
        .filter(word => word.length > 0) // Filter out empty strings
        .map(word => word[0])
        .join('')
        .toUpperCase()
        .slice(0, 2)
    }
    if (email) {
      return email[0].toUpperCase()
    }
    return 'U'
  }, [])

  const getUserImage = useCallback(() => {
    // Check for avatar URL from OAuth providers
    const avatarUrl = user?.user_metadata?.avatar_url || 
                     user?.user_metadata?.picture ||
                     user?.user_metadata?.avatar

    return avatarUrl
  }, [user?.user_metadata])

  const getUserName = useMemo(() => {
    return user?.user_metadata?.full_name || 
           user?.user_metadata?.name ||
           user?.email?.split('@')[0] || 
           'User'
  }, [user?.user_metadata, user?.email])

  const getStatusColor = useCallback(() => {
    if (statusColor) return statusColor
    
    switch (statusType) {
      case 'online':
        return 'bg-green-500'
      case 'away':
        return 'bg-yellow-500'
      case 'busy':
        return 'bg-red-500'
      case 'offline':
      default:
        return 'bg-gray-400'
    }
  }, [statusColor, statusType])

  if (!user) {
    return null
  }

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div className="relative">
        <Avatar className={cn(sizeMap[size], 'ring-2 ring-accent/20')}>
          <AvatarImage 
            src={getUserImage()} 
            alt={getUserName}
            className="object-cover"
          />
          <AvatarFallback className="bg-accent/10 text-accent font-semibold">
            {getInitials(getUserName, user?.email)}
          </AvatarFallback>
        </Avatar>
        
        {showStatus && (
          <span
            className={cn(
              'absolute bottom-0 right-0 block rounded-full ring-2 ring-background',
              getStatusColor(),
              statusSizeMap[size]
            )}
            aria-label={`User status: ${statusType}`}
          />
        )}
      </div>

      {showName && (
        <div className="flex flex-col">
          <span className="text-sm font-medium">{getUserName}</span>
          {user?.email && (
            <span className="text-xs text-muted-foreground">{user.email}</span>
          )}
        </div>
      )}
    </div>
  )
}