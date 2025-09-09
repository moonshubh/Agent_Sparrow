"use client"

import React, { useState, useEffect } from 'react'
import { APIKeyConfigModal } from '@/components/api-keys/APIKeyConfigModal'
import { APIKeyStatusBadge } from '@/components/api-keys/APIKeyStatusBadge'
import { StatusGrid } from '@/components/api-keys/StatusGrid'
import { SecurityFeatureGrid } from '@/components/api-keys/SecurityFeatureGrid'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
  Key,
  Plus,
  Shield,
  AlertTriangle,
  CheckCircle,
  Settings,
  RefreshCw,
  Info,
  Lock,
  Unlock,
  Eye,
  EyeOff
} from 'lucide-react'
import { apiKeyAPI } from '@/lib/api-client'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

interface ApiKeyInfo {
  id: string
  api_key_type: string
  key_name?: string
  is_active: boolean
  created_at: string
  masked_key?: string
}

export default function APIKeysSettingsPage() {
  const [keys, setKeys] = useState<ApiKeyInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [keyStatus, setKeyStatus] = useState<any>(null)

  useEffect(() => {
    fetchAPIKeys()
    fetchKeyStatus()
  }, [])

  const fetchAPIKeys = async () => {
    try {
      setLoading(true)
      const response = await apiKeyAPI.list()
      // The backend returns an object with api_keys array
      setKeys(response.api_keys || [])
    } catch (error) {
      console.error('Failed to fetch API keys:', error)
      toast.error('Failed to load API keys')
      setKeys([]) // Ensure keys is always an array
    } finally {
      setLoading(false)
    }
  }

  const fetchKeyStatus = async () => {
    try {
      const status = await apiKeyAPI.getStatus()
      setKeyStatus(status)
    } catch (error) {
      console.error('Failed to fetch key status:', error)
    }
  }

  const handleDeleteKey = async (keyType: string) => {
    const confirmed = window.confirm(`Are you sure you want to delete the ${keyType} API key?`)
    if (!confirmed) return

    try {
      await apiKeyAPI.delete(keyType)
      toast.success(`${keyType} API key deleted successfully`)
      fetchAPIKeys()
      fetchKeyStatus()
    } catch (error) {
      toast.error(`Failed to delete ${keyType} API key`)
    }
  }

  const getKeyTypeInfo = (type: string) => {
    const typeMap: Record<string, { label: string; color: string; description: string }> = {
      gemini: {
        label: 'Gemini AI',
        color: 'blue',
        description: 'Powers the primary AI agent capabilities'
      },
      tavily: {
        label: 'Tavily Search',
        color: 'green',
        description: 'Enables web search and research features'
      },
      firecrawl: {
        label: 'Firecrawl',
        color: 'orange',
        description: 'Web scraping and content extraction'
      }
    }
    return typeMap[type.toLowerCase()] || { 
      label: type, 
      color: 'gray', 
      description: 'Third-party API integration' 
    }
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
      {keyStatus && (
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
                  <p className="text-sm font-medium">{keyStatus.total_keys}</p>
                  <p className="text-xs text-muted-foreground">Total Keys</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg bg-green-500/10">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                </div>
                <div>
                  <p className="text-sm font-medium">{keyStatus.active_keys}</p>
                  <p className="text-xs text-muted-foreground">Active Keys</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg bg-yellow-500/10">
                  <AlertTriangle className="h-4 w-4 text-yellow-500" />
                </div>
                <div>
                  <p className="text-sm font-medium">{keyStatus.inactive_keys}</p>
                  <p className="text-xs text-muted-foreground">Inactive Keys</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg bg-purple-500/10">
                  <Settings className="h-4 w-4 text-purple-500" />
                </div>
                <div>
                  <p className="text-sm font-medium">{keyStatus.key_types?.length || 0}</p>
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
          fetchKeyStatus()
        }} 
      />
    </div>
  )
}