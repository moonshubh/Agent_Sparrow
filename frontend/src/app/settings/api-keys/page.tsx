"use client"

import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { APIKeyConfigModal } from '@/features/api-keys/components/APIKeyConfigModal'
import { APIKeyStatusBadge } from '@/features/api-keys/components/APIKeyStatusBadge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'
import { Button } from '@/shared/ui/button'
import { Alert, AlertDescription } from '@/shared/ui/alert'
import { Badge } from '@/shared/ui/badge'
import { Separator } from '@/shared/ui/separator'
import {
  Key,
  Plus,
  Shield,
  AlertTriangle,
  CheckCircle,
  Settings,
  Info,
  Lock,
  Unlock
} from 'lucide-react'
import { apiKeyService, APIKeyType } from '@/services/api/api-keys'
import { toast } from 'sonner'

type ApiKeyListResponse = Awaited<ReturnType<typeof apiKeyService.listAPIKeys>>
type ApiKeyItem = ApiKeyListResponse['api_keys'][number]

export default function APIKeysSettingsPage() {
  const [keys, setKeys] = useState<ApiKeyItem[]>([])
  const [loading, setLoading] = useState(true)
  const [isModalOpen, setIsModalOpen] = useState(false)

  const fetchAPIKeys = useCallback(async () => {
    try {
      setLoading(true)
      const response = await apiKeyService.listAPIKeys()
      setKeys(response.api_keys)
    } catch (error) {
      console.error('Failed to fetch API keys:', error)
      toast.error('Failed to load API keys')
      setKeys([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAPIKeys()
  }, [fetchAPIKeys])

  const handleDeleteKey = async (keyType: APIKeyType) => {
    const confirmed = window.confirm(`Are you sure you want to delete the ${keyType} API key?`)
    if (!confirmed) return

    try {
      await apiKeyService.deleteAPIKey(keyType)
      toast.success(`${keyType} API key deleted successfully`)
      fetchAPIKeys()
    } catch (error) {
      console.error('Failed to delete API key:', error)
      toast.error(`Failed to delete ${keyType} API key`)
    }
  }

  const typeInfoLookup = useMemo(() => ({
    [APIKeyType.GEMINI]: {
      label: 'Gemini AI',
      color: 'blue',
      description: 'Powers the primary AI agent capabilities'
    },
    [APIKeyType.TAVILY]: {
      label: 'Tavily Search',
      color: 'green',
      description: 'Enables web search and research features'
    },
    [APIKeyType.FIRECRAWL]: {
      label: 'Firecrawl',
      color: 'orange',
      description: 'Web scraping and content extraction'
    },
    [APIKeyType.OPENAI]: {
      label: 'OpenAI',
      color: 'purple',
      description: 'Optional key for OpenAI integration'
    }
  }), [])

  const summary = useMemo(() => {
    const total = keys.length
    const active = keys.filter(key => key.is_active).length
    const inactive = total - active
    const typeCount = new Set(keys.map(key => key.api_key_type)).size

    return { total, active, inactive, typeCount }
  }, [keys])

  const getKeyTypeInfo = (type: APIKeyType) =>
    typeInfoLookup[type] ?? {
      label: type,
      color: 'gray',
      description: 'Third-party API integration'
    }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <Key className="h-5 w-5 text-accent" />
            API Key Management
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Configure and manage your API keys for external services
          </p>
        </div>
        <div className="flex items-center gap-2">
          <APIKeyStatusBadge onClick={() => setIsModalOpen(true)} />
          <Button
            onClick={() => setIsModalOpen(true)}
            className="glass-effect"
          >
            <Plus className="h-4 w-4 mr-2" />
            Add API Key
          </Button>
        </div>
      </div>

      <Separator />

      {/* Status Overview */}
      {summary.total > 0 && (
        <Card className="glass-effect">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Shield className="h-4 w-4" />
              API Key Status Overview
            </CardTitle>
            <CardDescription>Current status of all configured API keys</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg bg-blue-500/10">
                  <Key className="h-4 w-4 text-blue-500" />
                </div>
                <div>
                  <p className="text-sm font-medium">{summary.total}</p>
                  <p className="text-xs text-muted-foreground">Total Keys</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg bg-green-500/10">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                </div>
                <div>
                  <p className="text-sm font-medium">{summary.active}</p>
                  <p className="text-xs text-muted-foreground">Active Keys</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg bg-yellow-500/10">
                  <AlertTriangle className="h-4 w-4 text-yellow-500" />
                </div>
                <div>
                  <p className="text-sm font-medium">{summary.inactive}</p>
                  <p className="text-xs text-muted-foreground">Inactive Keys</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg bg-purple-500/10">
                  <Settings className="h-4 w-4 text-purple-500" />
                </div>
                <div>
                  <p className="text-sm font-medium">{summary.typeCount}</p>
                  <p className="text-xs text-muted-foreground">Key Types</p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Configured Keys */}
      <Card className="glass-effect">
        <CardHeader>
          <CardTitle className="text-base">Configured API Keys</CardTitle>
          <CardDescription>Manage your existing API key configurations</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-20 bg-secondary/20 rounded-lg animate-pulse" />
              ))}
            </div>
          ) : keys.length === 0 ? (
            <Alert>
              <Info className="h-4 w-4" />
              <AlertDescription>
                No API keys configured yet. Add your first API key to get started.
              </AlertDescription>
            </Alert>
          ) : (
            <div className="space-y-3">
              {keys.map(key => {
                const typeInfo = getKeyTypeInfo(key.api_key_type)
                return (
                  <div
                    key={key.id}
                    className="flex items-center justify-between p-4 rounded-lg border glass-effect hover:scale-[1.01] transition-transform"
                  >
                    <div className="flex items-center gap-3">
                      {key.is_active ? (
                        <Unlock className="h-5 w-5 text-green-500" />
                      ) : (
                        <Lock className="h-5 w-5 text-red-500" />
                      )}
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{typeInfo.label}</span>
                          <Badge
                            variant={key.is_active ? "default" : "secondary"}
                            className="text-xs"
                          >
                            {key.is_active ? 'Active' : 'Inactive'}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                          {typeInfo.description}
                        </p>
                        {key.masked_key && (
                          <code className="text-xs bg-secondary/50 px-2 py-0.5 rounded mt-1 inline-block">
                            {key.masked_key}
                          </code>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        Added {new Date(key.created_at).toLocaleDateString()}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeleteKey(key.api_key_type)}
                        className="text-destructive hover:text-destructive"
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Security Features */}
      <Card className="glass-effect">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Shield className="h-4 w-4" />
            Security Features
          </CardTitle>
          <CardDescription>API key security and best practices</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <Alert>
              <Shield className="h-4 w-4" />
              <AlertDescription>
                Your API keys are encrypted and stored securely. Never share your API keys publicly.
              </AlertDescription>
            </Alert>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-green-500 mt-0.5" />
                <div>
                  <p className="text-sm font-medium">End-to-end Encryption</p>
                  <p className="text-xs text-muted-foreground">
                    All API keys are encrypted at rest and in transit
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-green-500 mt-0.5" />
                <div>
                  <p className="text-sm font-medium">Secure Storage</p>
                  <p className="text-xs text-muted-foreground">
                    Keys are stored in encrypted database with access controls
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-green-500 mt-0.5" />
                <div>
                  <p className="text-sm font-medium">Masked Display</p>
                  <p className="text-xs text-muted-foreground">
                    API keys are partially masked for security
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-green-500 mt-0.5" />
                <div>
                  <p className="text-sm font-medium">Regular Rotation</p>
                  <p className="text-xs text-muted-foreground">
                    Rotate your API keys regularly for enhanced security
                  </p>
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Best Practices */}
      <Card className="glass-effect">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Info className="h-4 w-4" />
            Best Practices
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li className="flex items-start gap-2">
              <span className="text-accent">•</span>
              <span>Never commit API keys to version control or share them in plain text</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-accent">•</span>
              <span>Use environment-specific keys for development and production</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-accent">•</span>
              <span>Regularly rotate your API keys, especially if they may have been exposed</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-accent">•</span>
              <span>Monitor API key usage and set up alerts for unusual activity</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-accent">•</span>
              <span>Use the principle of least privilege - only grant necessary permissions</span>
            </li>
          </ul>
        </CardContent>
      </Card>

      {/* API Key Configuration Modal */}
      <APIKeyConfigModal 
        isOpen={isModalOpen} 
        onClose={() => {
          setIsModalOpen(false)
          fetchAPIKeys()
        }} 
      />
    </div>
  )
}
