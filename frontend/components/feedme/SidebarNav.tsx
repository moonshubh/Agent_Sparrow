/**
 * SidebarNav Component - Single Column Layout with Apple/Google-level Polish
 * 
 * Features:
 * - Single column layout with FeedMe branding header
 * - 3 navigation tabs: Conversations | Folders | Analytics
 * - Collapsible sidebar (64px collapsed) with chevron toggle
 * - Persistent state via localStorage
 * - Apple/Google-level micro-interactions
 * - Perfect accessibility with ARIA labels
 */

'use client'

import React, { useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { 
  Home, 
  FolderOpen, 
  BarChart3,
  MessageCircle,
  ChevronLeft,
  ChevronRight
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUISidebar, useUIActions } from '@/lib/stores/ui-store'

interface SidebarNavProps {
  activeTab: 'conversations' | 'folders' | 'analytics'
  onTabChange: (tab: 'conversations' | 'folders' | 'analytics') => void
  conversationCount?: number
  folderCount?: number
  className?: string
}

export function SidebarNav({ 
  activeTab, 
  onTabChange, 
  conversationCount = 0,
  folderCount = 0,
  className 
}: SidebarNavProps) {
  const { isCollapsed, showFolderPanel } = useUISidebar()
  const { toggleSidebar, openFolderPanel, closeFolderPanel, openFolderPanelHover, closeFolderPanelHover } = useUIActions()
  const mouseLeaveTimerRef = useRef<NodeJS.Timeout | null>(null)

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (mouseLeaveTimerRef.current) {
        clearTimeout(mouseLeaveTimerRef.current)
      }
    }
  }, [])

  const tabs = [
    {
      id: 'conversations' as const,
      label: 'Conversations',
      icon: MessageCircle,
      count: conversationCount,
      description: 'Manage customer support transcripts'
    },
    {
      id: 'folders' as const,
      label: 'Folders',
      icon: FolderOpen,
      count: folderCount,
      description: 'Organize conversations by topic'
    },
    {
      id: 'analytics' as const,
      label: 'Analytics',
      icon: BarChart3,
      count: undefined,
      description: 'View usage statistics and insights'
    }
  ]

  return (
    <nav 
      className={cn(
        "h-screen bg-background border-r border-border flex flex-col transition-all duration-300 ease-in-out",
        isCollapsed ? "w-16" : "w-64",
        className
      )}
      data-testid="sidebar-nav"
      data-collapsed={isCollapsed}
    >
      {/* Branding Row with Chevron Toggle */}
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between">
          {/* Logo and Branding */}
          <div className="flex items-center space-x-2 min-w-0 flex-1">
            <div className="w-8 h-8 bg-accent/10 rounded-lg flex items-center justify-center shrink-0">
              <Home className="h-4 w-4 text-accent" />
            </div>
            {!isCollapsed && (
              <div className="min-w-0 flex-1">
                <h1 className="text-lg font-bold text-foreground truncate">
                  Feed<span className="text-accent">Me</span>
                </h1>
                <p className="text-xs text-muted-foreground truncate">
                  AI Transcript Manager
                </p>
              </div>
            )}
          </div>
          
          {/* Chevron Toggle Button */}
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleSidebar}
            className="h-8 w-8 p-0 hover:bg-mb-blue-300/10 transition-colors duration-200 shrink-0"
            aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            data-testid="sidebar-toggle"
          >
            {isCollapsed ? (
              <ChevronRight className="h-4 w-4 transition-transform duration-200" />
            ) : (
              <ChevronLeft className="h-4 w-4 transition-transform duration-200" />
            )}
          </Button>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex-1 p-4 space-y-2">
        {tabs.map((tab) => {
          const Icon = tab.icon
          const isActive = activeTab === tab.id
          
          return (
            <Button
              key={tab.id}
              variant={isActive ? "default" : "ghost"}
              className={cn(
                "w-full transition-all duration-200 relative",
                isCollapsed 
                  ? "h-10 w-10 p-0 mx-auto" 
                  : "justify-start h-9 px-3",
                isActive && "bg-accent text-accent-foreground shadow-sm",
                !isActive && "hover:bg-mb-blue-300/10"
              )}
              onClick={() => {
                onTabChange(tab.id)
                // Handle folder panel visibility
                if (tab.id === 'folders') {
                  if (showFolderPanel) {
                    closeFolderPanel()
                  } else {
                    openFolderPanel()
                  }
                } else {
                  closeFolderPanel()
                }
              }}
              onMouseEnter={() => {
                if (tab.id === 'folders') {
                  openFolderPanelHover()
                }
              }}
              onMouseLeave={(e) => {
                if (tab.id === 'folders') {
                  // Clear any existing timer
                  if (mouseLeaveTimerRef.current) {
                    clearTimeout(mouseLeaveTimerRef.current)
                  }
                  
                  // Check if mouse is moving towards the panel (right side)
                  const rect = e.currentTarget.getBoundingClientRect()
                  const mouseX = e.clientX
                  const tabRightEdge = rect.right
                  
                  // If mouse is moving towards panel area, delay close slightly
                  if (mouseX > tabRightEdge - 10) {
                    mouseLeaveTimerRef.current = setTimeout(() => closeFolderPanelHover(), 50)
                  } else {
                    closeFolderPanelHover()
                  }
                }
              }}
              onFocus={() => {
                if (tab.id === 'folders') {
                  openFolderPanel()
                }
              }}
              title={isCollapsed ? `${tab.label} - ${tab.description}` : tab.description}
              data-testid={`${tab.id}-tab`}
            >
              <Icon className={cn(
                "h-4 w-4 transition-all duration-200", 
                isCollapsed ? "mx-auto" : "mr-3 shrink-0"
              )} />
              {!isCollapsed && (
                <>
                  <span className="flex-1 text-left font-medium">{tab.label}</span>
                  {tab.count !== undefined && tab.count > 0 && (
                    <Badge 
                      variant="secondary" 
                      className="h-5 px-1.5 text-xs bg-accent/20 text-accent border-accent/30 ml-2"
                    >
                      {tab.count}
                    </Badge>
                  )}
                </>
              )}
              {/* Active indicator for collapsed mode */}
              {isCollapsed && isActive && (
                <div className="absolute -right-1 top-1/2 -translate-y-1/2 w-1 h-6 bg-accent rounded-l-full" />
              )}
            </Button>
          )
        })}
      </div>

    </nav>
  )
}
