"use client"

import React, { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'
import { Settings, Key, Shield, AlertCircle, CheckCircle, Info } from 'lucide-react'
import { APIKeyInput } from './APIKeyInput'
import { 
  APIKeyType, 
  APIKeyInfo, 
  APIKeyStatus,
  apiKeyService 
} from '@/lib/api-keys'

interface SettingsModalProps {
  isOpen: boolean
  onClose: () => void
}

export function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  const [apiKeys, setAPIKeys] = useState<APIKeyInfo[]>([])
  const [apiKeyStatus, setAPIKeyStatus] = useState<APIKeyStatus | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Load API keys when modal opens (only in production or when auth is ready)
  useEffect(() => {
    if (isOpen) {
      // Skip API loading during development until auth system is integrated
      if (process.env.NODE_ENV === 'development') {
        console.log('Settings modal: API loading disabled during development')
        setAPIKeyStatus({
          user_id: 'development',
          gemini_configured: false,
          tavily_configured: false,
          firecrawl_configured: false,
          all_required_configured: false,
          last_validation_check: 'Development mode'
        })
        return
      }
      
      loadAPIKeys()
      loadAPIKeyStatus()
    }
  }, [isOpen])

  const loadAPIKeys = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const result = await apiKeyService.listAPIKeys()
      setAPIKeys(result.api_keys)
    } catch (err: any) {
      let errorMessage = 'Failed to load API keys'
      
      // Handle different error types gracefully
      if (err?.code === 'NETWORK_ERROR') {
        errorMessage = 'Cannot connect to server. Please check your connection.'
      } else if (err?.code === 'TIMEOUT') {
        errorMessage = 'Request timed out. Please try again.'
      } else if (err?.status === 401) {
        errorMessage = 'Authentication required. Please log in.'
      } else if (err instanceof Error) {
        errorMessage = err.message
      }
      
      setError(errorMessage)
      console.error('API Keys loading error:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const loadAPIKeyStatus = async () => {
    try {
      const status = await apiKeyService.getAPIKeyStatus()
      setAPIKeyStatus(status)
    } catch (err: any) {
      console.warn('Failed to load API key status (non-critical):', err)
      
      // Set a default status when API is unavailable
      setAPIKeyStatus({
        user_id: 'unknown',
        gemini_configured: false,
        tavily_configured: false,
        firecrawl_configured: false,
        all_required_configured: false,
        last_validation_check: undefined
      })
    }
  }

  const handleAPIKeySave = (type: APIKeyType, keyName?: string) => {
    // Reload the API keys after save
    loadAPIKeys()
    loadAPIKeyStatus()
  }

  const handleAPIKeyDelete = (type: APIKeyType) => {
    // Reload the API keys after delete
    loadAPIKeys()
    loadAPIKeyStatus()
  }

  const getExistingKey = (type: APIKeyType): APIKeyInfo | undefined => {
    return apiKeys.find(key => key.api_key_type === type)
  }

  const getStatusIcon = (configured: boolean) => {
    return configured ? (
      <CheckCircle className="h-4 w-4 text-green-600" />
    ) : (
      <AlertCircle className="h-4 w-4 text-yellow-600" />
    )
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5 text-accent" />
            MB-Sparrow Settings
          </DialogTitle>
          <DialogDescription>
            Configure your API keys and system settings for the MB-Sparrow multi-agent system.
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="api-keys" className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="api-keys" className="flex items-center gap-2">
              <Key className="h-4 w-4" />
              API Keys
            </TabsTrigger>
            <TabsTrigger value="security" className="flex items-center gap-2">
              <Shield className="h-4 w-4" />
              Security
            </TabsTrigger>
          </TabsList>

          <TabsContent value="api-keys" className="space-y-6">
            {/* API Key Status Overview */}
            {apiKeyStatus && (
              <div className="bg-muted/30 border border-border rounded-lg p-4">
                <h3 className="text-lg font-medium mb-3 flex items-center gap-2">
                  <Info className="h-5 w-5 text-accent" />
                  Configuration Status
                </h3>
                
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="flex items-center justify-between p-3 bg-background rounded-md border">
                    <div>
                      <p className="font-medium">Google Gemini</p>
                      <p className="text-sm text-muted-foreground">AI Models</p>
                    </div>
                    <div className="flex items-center gap-2">
                      {getStatusIcon(apiKeyStatus.gemini_configured)}
                      <Badge variant={apiKeyStatus.gemini_configured ? "default" : "secondary"}>
                        {apiKeyStatus.gemini_configured ? "Ready" : "Required"}
                      </Badge>
                    </div>
                  </div>

                  <div className="flex items-center justify-between p-3 bg-background rounded-md border">
                    <div>
                      <p className="font-medium">Tavily Search</p>
                      <p className="text-sm text-muted-foreground">Web Search</p>
                    </div>
                    <div className="flex items-center gap-2">
                      {getStatusIcon(apiKeyStatus.tavily_configured)}
                      <Badge variant={apiKeyStatus.tavily_configured ? "default" : "outline"}>
                        {apiKeyStatus.tavily_configured ? "Ready" : "Optional"}
                      </Badge>
                    </div>
                  </div>

                  <div className="flex items-center justify-between p-3 bg-background rounded-md border">
                    <div>
                      <p className="font-medium">Firecrawl</p>
                      <p className="text-sm text-muted-foreground">Web Scraping</p>
                    </div>
                    <div className="flex items-center gap-2">
                      {getStatusIcon(apiKeyStatus.firecrawl_configured)}
                      <Badge variant={apiKeyStatus.firecrawl_configured ? "default" : "outline"}>
                        {apiKeyStatus.firecrawl_configured ? "Ready" : "Optional"}
                      </Badge>
                    </div>
                  </div>
                </div>

                {!apiKeyStatus.all_required_configured && (
                  <Alert className="mt-4">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>
                      <strong>Google Gemini API key is required</strong> for the system to function properly. 
                      Please configure it below to enable AI-powered responses.
                    </AlertDescription>
                  </Alert>
                )}

                {apiKeyStatus.all_required_configured && (
                  <Alert className="mt-4 border-green-200 bg-green-50 text-green-800">
                    <CheckCircle className="h-4 w-4" />
                    <AlertDescription>
                      All required API keys are configured. Your MB-Sparrow system is ready to use!
                    </AlertDescription>
                  </Alert>
                )}
              </div>
            )}

            {/* Error Display */}
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {/* Loading State */}
            {isLoading && (
              <div className="flex items-center justify-center p-8">
                <div className="flex items-center gap-2">
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
                  <span>Loading API keys...</span>
                </div>
              </div>
            )}

            {/* API Key Configuration */}
            {!isLoading && (
              <div className="space-y-6">
                <div>
                  <h3 className="text-lg font-medium mb-2">API Key Configuration</h3>
                  <p className="text-sm text-muted-foreground mb-4">
                    Configure your API keys for different services. Keys are encrypted and stored securely.
                  </p>
                  <Separator />
                </div>

                {/* Gemini API Key */}
                <APIKeyInput
                  type={APIKeyType.GEMINI}
                  existingKey={getExistingKey(APIKeyType.GEMINI)}
                  onSave={handleAPIKeySave}
                  onDelete={handleAPIKeyDelete}
                />

                {/* Tavily API Key */}
                <APIKeyInput
                  type={APIKeyType.TAVILY}
                  existingKey={getExistingKey(APIKeyType.TAVILY)}
                  onSave={handleAPIKeySave}
                  onDelete={handleAPIKeyDelete}
                />

                {/* Firecrawl API Key */}
                <APIKeyInput
                  type={APIKeyType.FIRECRAWL}
                  existingKey={getExistingKey(APIKeyType.FIRECRAWL)}
                  onSave={handleAPIKeySave}
                  onDelete={handleAPIKeyDelete}
                />
              </div>
            )}
          </TabsContent>

          <TabsContent value="security" className="space-y-6">
            <div className="space-y-4">
              <div>
                <h3 className="text-lg font-medium mb-2">Security Information</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  Learn about how your API keys and data are protected.
                </p>
                <Separator />
              </div>

              <div className="grid gap-4">
                <Alert>
                  <Shield className="h-4 w-4" />
                  <AlertDescription>
                    <strong>Encryption:</strong> All API keys are encrypted using AES-256 encryption 
                    with user-specific keys before being stored in the database.
                  </AlertDescription>
                </Alert>

                <Alert>
                  <Key className="h-4 w-4" />
                  <AlertDescription>
                    <strong>User Isolation:</strong> Your API keys are completely isolated from other users 
                    and can only be accessed by your authenticated session.
                  </AlertDescription>
                </Alert>

                <Alert>
                  <Info className="h-4 w-4" />
                  <AlertDescription>
                    <strong>No Client Storage:</strong> API keys are never stored in your browser's 
                    localStorage, sessionStorage, or cookies for maximum security.
                  </AlertDescription>
                </Alert>

                <Alert>
                  <CheckCircle className="h-4 w-4" />
                  <AlertDescription>
                    <strong>Secure Transmission:</strong> All API key operations use HTTPS encryption 
                    and are protected against man-in-the-middle attacks.
                  </AlertDescription>
                </Alert>

                <Alert>
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    <strong>No Logging:</strong> API keys never appear in server logs, error messages, 
                    or debug output to prevent accidental exposure.
                  </AlertDescription>
                </Alert>
              </div>

              <div className="bg-muted/30 border border-border rounded-lg p-4">
                <h4 className="font-medium mb-2">Best Practices</h4>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  <li>• Use unique, strong API keys from each provider</li>
                  <li>• Regularly rotate your API keys for enhanced security</li>
                  <li>• Monitor your API usage through provider dashboards</li>
                  <li>• Never share your API keys with others</li>
                  <li>• Revoke access immediately if a key is compromised</li>
                </ul>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}