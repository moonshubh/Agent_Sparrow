"use client"

import React, { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Key, Shield, CheckCircle, AlertCircle, Info, HelpCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'
import { APIKeyInput } from '@/components/settings/APIKeyInput'
import { 
  APIKeyType, 
  APIKeyInfo, 
  APIKeyStatus,
  apiKeyService 
} from '@/lib/api-keys'

export default function APIKeysPage() {
  const router = useRouter()
  const [apiKeys, setAPIKeys] = useState<APIKeyInfo[]>([])
  const [apiKeyStatus, setAPIKeyStatus] = useState<APIKeyStatus | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Load API keys on component mount
  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setIsLoading(true)
    setError(null)

    // Skip API loading during development until auth system is integrated
    if (process.env.NODE_ENV === 'development') {
      console.log('API Keys page: API loading disabled during development')
      setAPIKeyStatus({
        user_id: 'development',
        gemini_configured: false,
        tavily_configured: false,
        firecrawl_configured: false,
        all_required_configured: false,
        last_validation_check: 'Development mode'
      })
      setIsLoading(false)
      return
    }

    try {
      const [keysResult, statusResult] = await Promise.all([
        apiKeyService.listAPIKeys(),
        apiKeyService.getAPIKeyStatus()
      ])
      
      setAPIKeys(keysResult.api_keys)
      setAPIKeyStatus(statusResult)
    } catch (err: any) {
      let errorMessage = 'Failed to load API keys'
      
      if (err?.code === 'NETWORK_ERROR') {
        errorMessage = 'Cannot connect to server. Please check your connection.'
      } else if (err?.status === 401) {
        errorMessage = 'Authentication required. Please log in.'
      } else if (err instanceof Error) {
        errorMessage = err.message
      }
      
      setError(errorMessage)
      console.error('API Keys loading error:', err)

      // Set default status on error
      setAPIKeyStatus({
        user_id: 'unknown',
        gemini_configured: false,
        tavily_configured: false,
        firecrawl_configured: false,
        all_required_configured: false,
        last_validation_check: undefined
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleAPIKeySave = (type: APIKeyType, keyName?: string) => {
    loadData()
  }

  const handleAPIKeyDelete = (type: APIKeyType) => {
    loadData()
  }

  const getExistingKey = (type: APIKeyType): APIKeyInfo | undefined => {
    return apiKeys.find(key => key.api_key_type === type)
  }

  const getStatusIcon = (configured: boolean) => {
    return configured ? (
      <CheckCircle className="h-5 w-5 text-green-600" />
    ) : (
      <AlertCircle className="h-5 w-5 text-amber-600" />
    )
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b bg-card/50 backdrop-blur">
        <div className="container max-w-4xl mx-auto px-6 py-4">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.back()}
              className="gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              Back
            </Button>
            <div className="flex items-center gap-3">
              <Key className="h-6 w-6 text-accent" />
              <div>
                <h1 className="text-2xl font-bold">API Keys</h1>
                <p className="text-sm text-muted-foreground">
                  Configure your API keys for MB-Sparrow services
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="container max-w-4xl mx-auto px-6 py-8">
        {/* Loading State */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="flex items-center gap-3">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
              <span className="text-lg">Loading API keys...</span>
            </div>
          </div>
        )}

        {/* Error State */}
        {error && !isLoading && (
          <Alert variant="destructive" className="mb-6">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Main Content */}
        {!isLoading && apiKeyStatus && (
          <div className="space-y-8">
            {/* Status Overview */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Info className="h-5 w-5 text-accent" />
                  Configuration Status
                </CardTitle>
                <CardDescription>
                  Overview of your API key configuration for MB-Sparrow services
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {/* Gemini Status */}
                  <div className="flex items-center justify-between p-4 bg-muted/30 rounded-lg border">
                    <div className="space-y-1">
                      <p className="font-medium">Google Gemini</p>
                      <p className="text-sm text-muted-foreground">AI Models & Chat</p>
                    </div>
                    <div className="flex items-center gap-2">
                      {getStatusIcon(apiKeyStatus.gemini_configured)}
                      <Badge variant={apiKeyStatus.gemini_configured ? "default" : "destructive"}>
                        {apiKeyStatus.gemini_configured ? "Ready" : "Required"}
                      </Badge>
                    </div>
                  </div>

                  {/* Tavily Status */}
                  <div className="flex items-center justify-between p-4 bg-muted/30 rounded-lg border">
                    <div className="space-y-1">
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

                  {/* Firecrawl Status */}
                  <div className="flex items-center justify-between p-4 bg-muted/30 rounded-lg border">
                    <div className="space-y-1">
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

                {/* Status Alerts */}
                <div className="mt-6 space-y-3">
                  {!apiKeyStatus.all_required_configured && (
                    <Alert>
                      <AlertCircle className="h-4 w-4" />
                      <AlertDescription>
                        <strong>Google Gemini API key is required</strong> for MB-Sparrow to function properly. 
                        Please configure it below to enable AI-powered responses.
                      </AlertDescription>
                    </Alert>
                  )}

                  {apiKeyStatus.all_required_configured && (
                    <Alert className="border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-200">
                      <CheckCircle className="h-4 w-4" />
                      <AlertDescription>
                        All required API keys are configured. Your MB-Sparrow system is ready to use!
                      </AlertDescription>
                    </Alert>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* API Key Configuration */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Key className="h-5 w-5 text-accent" />
                  Configure API Keys
                </CardTitle>
                <CardDescription>
                  Add or update your API keys for different services. All keys are encrypted and stored securely.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Google Gemini */}
                <div>
                  <h3 className="text-lg font-medium mb-4 flex items-center gap-2">
                    Google Gemini API
                    <Badge variant="destructive" className="text-xs">Required</Badge>
                  </h3>
                  <APIKeyInput
                    type={APIKeyType.GEMINI}
                    existingKey={getExistingKey(APIKeyType.GEMINI)}
                    onSave={handleAPIKeySave}
                    onDelete={handleAPIKeyDelete}
                  />
                </div>

                <Separator />

                {/* Tavily Search */}
                <div>
                  <h3 className="text-lg font-medium mb-4 flex items-center gap-2">
                    Tavily Search API
                    <Badge variant="outline" className="text-xs">Optional</Badge>
                  </h3>
                  <APIKeyInput
                    type={APIKeyType.TAVILY}
                    existingKey={getExistingKey(APIKeyType.TAVILY)}
                    onSave={handleAPIKeySave}
                    onDelete={handleAPIKeyDelete}
                  />
                </div>

                <Separator />

                {/* Firecrawl */}
                <div>
                  <h3 className="text-lg font-medium mb-4 flex items-center gap-2">
                    Firecrawl API
                    <Badge variant="outline" className="text-xs">Optional</Badge>
                  </h3>
                  <APIKeyInput
                    type={APIKeyType.FIRECRAWL}
                    existingKey={getExistingKey(APIKeyType.FIRECRAWL)}
                    onSave={handleAPIKeySave}
                    onDelete={handleAPIKeyDelete}
                  />
                </div>
              </CardContent>
            </Card>

            {/* Security Information */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Shield className="h-5 w-5 text-accent" />
                  Security & Privacy
                </CardTitle>
                <CardDescription>
                  Learn how your API keys are protected
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Shield className="h-4 w-4 text-green-600" />
                      <span className="font-medium">AES-256 Encryption</span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      All API keys are encrypted with user-specific keys before storage
                    </p>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Key className="h-4 w-4 text-blue-600" />
                      <span className="font-medium">User Isolation</span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Your keys are completely isolated from other users
                    </p>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <CheckCircle className="h-4 w-4 text-green-600" />
                      <span className="font-medium">Secure Transmission</span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      All operations use HTTPS encryption
                    </p>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <HelpCircle className="h-4 w-4 text-purple-600" />
                      <span className="font-medium">No Client Storage</span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Keys are never stored in your browser
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}