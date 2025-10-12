import { Fragment } from 'react'
import { Badge } from '@/shared/ui/badge'
import { Separator } from '@/shared/ui/separator'
import { APIKeyInput } from '@/features/settings/components/APIKeyInput'
import { APIKeyType, APIKeyInfo } from '@/services/api/api-keys'

export interface APIKeyConfig {
  type: APIKeyType
  name: string
  required: boolean
  description?: string
}

export interface APIKeyConfigSectionProps {
  configs: APIKeyConfig[]
  getExistingKey: (type: APIKeyType) => APIKeyInfo | undefined
  onSave: (type: APIKeyType, keyName?: string) => Promise<void>
  onDelete: (type: APIKeyType) => Promise<void>
}

export function APIKeyConfigSection({ 
  configs, 
  getExistingKey, 
  onSave, 
  onDelete 
}: APIKeyConfigSectionProps) {
  return (
    <div className="space-y-6">
      {configs.map((config, index) => (
        <Fragment key={config.type}>
          <div>
            <h3 className="text-lg font-medium mb-4 flex items-center gap-2">
              {config.name}
              <Badge 
                variant={config.required ? "destructive" : "outline"} 
                className="text-xs"
              >
                {config.required ? "Required" : "Optional"}
              </Badge>
            </h3>
            {config.description && (
              <p className="text-sm text-muted-foreground mb-4">{config.description}</p>
            )}
            <APIKeyInput
              type={config.type}
              existingKey={getExistingKey(config.type)}
              onSave={onSave}
              onDelete={onDelete}
            />
          </div>
          {index < configs.length - 1 && <Separator />}
        </Fragment>
      ))}
    </div>
  )
}