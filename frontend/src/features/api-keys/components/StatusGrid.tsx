import React from 'react'
import { CheckCircle, AlertCircle } from 'lucide-react'
import { Badge } from '@/shared/ui/badge'

export interface StatusItem {
  id: string
  name: string
  description: string
  configured: boolean
  required: boolean
}

interface StatusGridProps {
  items: StatusItem[]
  getStatusIcon?: (configured: boolean) => React.ReactNode
}

const defaultGetStatusIcon = (configured: boolean) => {
  return configured ? (
    <CheckCircle className="h-5 w-5 text-green-600" />
  ) : (
    <AlertCircle className="h-5 w-5 text-amber-600" />
  )
}

// Helper function to determine badge properties based on item status
const getBadgeProperties = (item: StatusItem) => {
  if (item.configured) {
    return {
      variant: 'default' as const,
      label: 'Ready'
    }
  }
  
  if (item.required) {
    return {
      variant: 'destructive' as const,
      label: 'Required'
    }
  }
  
  return {
    variant: 'outline' as const,
    label: 'Optional'
  }
}

export function StatusGrid({ items, getStatusIcon = defaultGetStatusIcon }: StatusGridProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {items.map((item) => {
        const badgeProps = getBadgeProperties(item)
        
        return (
          <div key={item.id} className="flex items-center justify-between p-4 bg-muted/30 rounded-lg border">
            <div className="space-y-1">
              <p className="font-medium">{item.name}</p>
              <p className="text-sm text-muted-foreground">{item.description}</p>
            </div>
            <div className="flex items-center gap-2">
              {getStatusIcon(item.configured)}
              <Badge variant={badgeProps.variant}>
                {badgeProps.label}
              </Badge>
            </div>
          </div>
        )
      })}
    </div>
  )
}