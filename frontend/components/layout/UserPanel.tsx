'use client'

import React, { useState } from 'react'
import { User } from '@supabase/supabase-js'
import { UserAvatar } from '@/components/ui/UserAvatar'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { LogOut, Settings, Key, User as UserIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { motion, AnimatePresence } from 'framer-motion'
import { useRouter } from 'next/navigation'

interface UserPanelProps {
  user: User | null
  isAuthenticated: boolean
  onLogout: () => void
}

export const UserPanel: React.FC<UserPanelProps> = ({ 
  user, 
  isAuthenticated, 
  onLogout 
}) => {
  const [isExpanded, setIsExpanded] = useState(false)
  const router = useRouter()

  const handleNavigation = (path: string) => {
    router.push(path)
    setIsExpanded(false)
  }

  const getUserName = () => {
    if (!user) return 'Guest'
    return user?.user_metadata?.full_name || 
           user?.user_metadata?.name ||
           user?.email?.split('@')[0] || 
           'User'
  }

  if (!isAuthenticated || !user) {
    return null
  }

  return (
    <div className="fixed bottom-6 right-6 z-50">
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            transition={{ duration: 0.2 }}
            className="mb-3"
          >
            <Card className="w-64 border-border/50 bg-card/95 backdrop-blur-sm shadow-lg">
              <CardContent className="p-4">
                <div className="flex items-center gap-3 mb-4">
                  <UserAvatar user={user} size="lg" showStatus />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{getUserName()}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {user.email}
                    </p>
                  </div>
                </div>

                <div className="space-y-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full justify-start gap-2"
                    onClick={() => handleNavigation('/profile')}
                  >
                    <UserIcon className="h-4 w-4" />
                    Profile
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full justify-start gap-2"
                    onClick={() => handleNavigation('/api-keys')}
                  >
                    <Key className="h-4 w-4" />
                    API Keys
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full justify-start gap-2"
                    onClick={() => handleNavigation('/settings')}
                  >
                    <Settings className="h-4 w-4" />
                    Settings
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full justify-start gap-2 text-destructive hover:text-destructive"
                    onClick={() => {
                      onLogout()
                      setIsExpanded(false)
                    }}
                  >
                    <LogOut className="h-4 w-4" />
                    Sign Out
                  </Button>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.div
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        className="relative"
      >
        <Button
          variant="outline"
          size="icon"
          className={cn(
            'h-12 w-12 rounded-full border-2 border-accent/30 bg-background/80 backdrop-blur-sm shadow-lg hover:border-accent/50 hover:bg-background/90',
            isExpanded && 'border-accent/50 bg-background/90'
          )}
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <UserAvatar user={user} size="md" />
        </Button>

        {/* Online status indicator */}
        <div className="absolute -bottom-1 -right-1 h-4 w-4 rounded-full border-2 border-background bg-green-500" />
      </motion.div>
    </div>
  )
}