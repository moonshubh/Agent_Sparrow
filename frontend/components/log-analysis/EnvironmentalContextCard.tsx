"use client"

import React from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { 
  Monitor,
  Globe,
  Shield,
  Network,
  Settings,
  Clock
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { type EnvironmentalContext } from '@/lib/log-analysis-utils'

interface EnvironmentalContextCardProps {
  context: EnvironmentalContext
  className?: string
}

interface ContextItem {
  label: string
  value: string | boolean | string[]
  icon: React.ComponentType<{ className?: string }>
  type?: 'text' | 'boolean' | 'array'
}

export function EnvironmentalContextCard({ context, className }: EnvironmentalContextCardProps) {
  const items: ContextItem[] = [
    {
      label: 'Operating System',
      value: context.os_version || 'Unknown',
      icon: Monitor,
      type: 'text'
    },
    {
      label: 'Platform',
      value: context.platform || 'Unknown',
      icon: Settings,
      type: 'text'
    },
    {
      label: 'Network Type',
      value: context.network_type || 'Unknown',
      icon: Network,
      type: 'text'
    },
    {
      label: 'Firewall Status',
      value: context.firewall_status || 'Unknown',
      icon: Shield,
      type: 'text'
    },
    {
      label: 'Proxy Configured',
      value: context.proxy_configured,
      icon: Globe,
      type: 'boolean'
    },
    {
      label: 'Timezone',
      value: context.timezone || 'Unknown',
      icon: Clock,
      type: 'text'
    }
  ]

  const renderValue = (item: ContextItem) => {
    if (item.type === 'boolean') {
      return (
        <Badge variant={item.value ? "default" : "secondary"} className="text-xs">
          {item.value ? 'Enabled' : 'Disabled'}
        </Badge>
      )
    }
    
    if (item.type === 'array' && Array.isArray(item.value)) {
      return item.value.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {item.value.slice(0, 3).map((val, idx) => (
            <Badge key={idx} variant="outline" className="text-xs">
              {val}
            </Badge>
          ))}
          {item.value.length > 3 && (
            <Badge variant="secondary" className="text-xs">
              +{item.value.length - 3} more
            </Badge>
          )}
        </div>
      ) : (
        <span className="text-xs text-muted-foreground">None detected</span>
      )
    }
    
    return (
      <span className="text-sm font-medium text-foreground">
        {item.value as string}
      </span>
    )
  }

  return (
    <Card className={cn("w-full", className)}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-semibold flex items-center gap-2">
          <Monitor className="h-4 w-4 text-primary" />
          Environmental Context
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map((item, index) => {
            const Icon = item.icon

            return (
              <div
                key={index}
                className="flex items-center justify-between p-3 rounded-lg bg-muted/30 border border-border/50"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <Icon className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                  <span className="text-xs font-medium text-muted-foreground truncate">
                    {item.label}
                  </span>
                </div>
                
                <div className="ml-2 flex-shrink-0">
                  {renderValue(item)}
                </div>
              </div>
            )
          })}
        </div>
        
        {/* Antivirus Software */}
        {context.antivirus_software && context.antivirus_software.length > 0 && (
          <div className="mt-4 p-3 rounded-lg bg-muted/30 border border-border/50">
            <div className="flex items-center gap-2 mb-2">
              <Shield className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground">
                Antivirus Software
              </span>
            </div>
            <div className="flex flex-wrap gap-1">
              {context.antivirus_software.map((av, idx) => (
                <Badge key={idx} variant="outline" className="text-xs">
                  {av}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}