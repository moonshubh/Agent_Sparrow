"use client"

import React from 'react'
import { cn } from '@/lib/utils'
import { 
  BarChart3, 
  AlertTriangle, 
  Eye, 
  Shield 
} from 'lucide-react'

interface ActionBarProps {
  activeTab?: string
  onTabChange?: (tabId: string) => void
  issueCount?: number
  hasInsights?: boolean
  className?: string
  onSystemOverviewClick?: () => void
  criticalIssuesCount?: number
}

const tabs = [
  {
    id: 'system',
    label: 'System Overview',
    icon: BarChart3,
    isSystemTab: true
  },
  {
    id: 'issues',
    label: 'Issues',
    icon: AlertTriangle,
    showCount: true
  },
  {
    id: 'insights',
    label: 'Insights',
    icon: Eye,
    canDisable: true
  },
  {
    id: 'actions',
    label: 'Actions',
    icon: Shield
  }
]

export function ActionBar({ 
  activeTab = 'system',
  onTabChange,
  issueCount = 0,
  hasInsights = false,
  className,
  onSystemOverviewClick,
  criticalIssuesCount = 0
}: ActionBarProps) {
  const handleTabClick = (tabId: string) => {
    if (tabId === 'system' && onSystemOverviewClick) {
      onSystemOverviewClick()
    } else if (onTabChange) {
      onTabChange(tabId)
    }
    
    // Smooth scroll to panel after tab change
    requestAnimationFrame(() => {
      const panel = document.getElementById(`panel-${tabId}`)
      if (panel) {
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    })
  }

  return (
    <div className={cn(
      "flex items-center space-x-3 lg:space-x-6 overflow-x-auto no-scrollbar",
      className
    )}>
      {tabs.map((tab) => {
        const Icon = tab.icon
        const isActive = activeTab === tab.id
        const isDisabled = tab.canDisable && !hasInsights
        const showCount = tab.showCount && issueCount > 0

        return (
          <button
            key={tab.id}
            onClick={() => !isDisabled && handleTabClick(tab.id)}
            disabled={isDisabled}
            className={cn(
              "flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap",
              "focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2",
              isActive
                ? "bg-accent/10 text-accent border border-accent/20"
                : isDisabled
                ? "text-muted-foreground/50 cursor-not-allowed"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
            )}
            aria-selected={isActive}
            aria-controls={`panel-${tab.id}`}
            role="tab"
          >
            <Icon className="h-4 w-4" />
            <span className="flex items-center gap-1">
              {tab.label}
              {showCount && (
                <div className="flex items-center gap-1">
                  <span className="px-1.5 py-0.5 text-xs bg-muted-foreground/20 rounded-full">
                    {issueCount}
                  </span>
                  {criticalIssuesCount > 0 && (
                    <span className="px-1.5 py-0.5 text-xs bg-red-500/20 text-red-600 dark:text-red-400 rounded-full font-semibold">
                      {criticalIssuesCount} critical
                    </span>
                  )}
                </div>
              )}
            </span>
          </button>
        )
      })}
    </div>
  )
}