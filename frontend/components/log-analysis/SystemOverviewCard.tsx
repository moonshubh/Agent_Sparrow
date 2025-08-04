"use client"

import React from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { 
  Activity,
  Database,
  Mail,
  Folder,
  Monitor
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { type SystemStats, healthStatusClasses } from '@/lib/log-analysis-utils'

interface SystemOverviewCardProps {
  stats: SystemStats
}

interface OverviewItem {
  label: string
  value: string | number
  icon: React.ComponentType<{ className?: string }>
  variant?: 'default' | 'health'
  healthStatus?: string
}

export function SystemOverviewCard({ stats }: SystemOverviewCardProps) {
  const items: OverviewItem[] = [
    {
      label: 'Health',
      value: stats.health_status || 'Unknown',
      icon: Activity,
      variant: 'health',
      healthStatus: stats.health_status
    },
    {
      label: 'Accounts',
      value: stats.account_count ?? 0,
      icon: Mail
    },
    {
      label: 'Folders', 
      value: stats.folder_count ?? 0,
      icon: Folder
    },
    {
      label: 'DB Size',
      value: stats.database_size_mb ? `${stats.database_size_mb} MB` : '0 MB',
      icon: Database
    },
    {
      label: 'Mailbird',
      value: stats.mailbird_version ?? 'Unknown',
      icon: Monitor
    }
  ]

  return (
    <Card className="w-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-semibold flex items-center gap-2">
          <Activity className="h-4 w-4 text-primary" />
          System Overview
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
          {items.map((item, index) => {
            const Icon = item.icon
            const isHealthItem = item.variant === 'health'
            const healthClasses = isHealthItem && item.healthStatus 
              ? healthStatusClasses(item.healthStatus)
              : null

            return (
              <div
                key={index}
                className="flex flex-col items-center space-y-2 p-3 rounded-lg bg-muted/30 border border-border/50"
              >
                <div className="flex items-center gap-2">
                  <Icon className={cn(
                    "h-4 w-4",
                    isHealthItem && healthClasses?.icon || "text-muted-foreground"
                  )} />
                  <span className="text-xs font-medium text-muted-foreground">
                    {item.label}
                  </span>
                </div>
                
                {isHealthItem ? (
                  <Badge 
                    variant="outline" 
                    className={cn(
                      "text-xs font-semibold px-2 py-1",
                      healthClasses?.bg,
                      healthClasses?.text
                    )}
                  >
                    <span className="sr-only">System health status: </span>
                    {item.value}
                  </Badge>
                ) : (
                  <div className="text-sm font-semibold text-foreground text-center">
                    {item.value}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}