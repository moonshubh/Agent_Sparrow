import React from 'react'
import type { LucideIcon } from 'lucide-react'

export interface SecurityFeature {
  id: string
  icon: LucideIcon
  iconColor: string
  title: string
  description: string
}

interface SecurityFeatureGridProps {
  features: SecurityFeature[]
}

export function SecurityFeatureGrid({ features }: SecurityFeatureGridProps): React.JSX.Element {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {features.map((feature) => (
        <div key={feature.id} className="space-y-2">
          <div className="flex items-center gap-2">
            <feature.icon className={`h-4 w-4 ${feature.iconColor}`} aria-hidden="true" />
            <span className="font-medium">{feature.title}</span>
          </div>
          <p className="text-sm text-muted-foreground">
            {feature.description}
          </p>
        </div>
      ))}
    </div>
  )
}