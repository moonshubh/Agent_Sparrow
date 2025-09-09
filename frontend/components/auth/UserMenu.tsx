'use client'

import React from 'react'
import { User } from '@supabase/supabase-js'
import { UserAvatar } from '@/components/ui/UserAvatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { 
  LogOut, 
  Settings, 
  User as UserIcon,
  Key
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useRouter } from 'next/navigation'

interface UserMenuProps {
  user: User
  onLogout: () => void
  className?: string
}

export const UserMenu: React.FC<UserMenuProps> = ({ user, onLogout, className }) => {
  const router = useRouter()

  const getUserName = () => {
    // Check user metadata first
    if (user?.user_metadata?.full_name) {
      return user.user_metadata.full_name
    }
    
    if (user?.user_metadata?.name) {
      return user.user_metadata.name
    }
    
    // Extract username from email with validation
    if (user?.email) {
      const emailUsername = user.email.split('@')[0]
      if (emailUsername && emailUsername.trim().length > 0) {
        return emailUsername.trim()
      }
    }
    
    // Final fallback
    return 'User'
  }

  const handleNavigation = (path: string) => {
    router.push(path)
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className={cn('relative h-10 w-10 rounded-full', className)}
        >
          <UserAvatar user={user} size="md" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-56" align="end" forceMount>
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col space-y-1">
            <p className="text-sm font-medium leading-none">{getUserName()}</p>
            <p className="text-xs leading-none text-muted-foreground">
              {user.email}
            </p>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuItem onClick={() => handleNavigation('/profile')}>
            <UserIcon className="mr-2 h-4 w-4" />
            <span>Profile</span>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => handleNavigation('/settings')}>
            <Settings className="mr-2 h-4 w-4" />
            <span>Settings</span>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => handleNavigation('/api-keys')}>
            <Key className="mr-2 h-4 w-4" />
            <span>API Keys</span>
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onLogout} className="text-destructive">
          <LogOut className="mr-2 h-4 w-4" />
          <span>Log out</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}