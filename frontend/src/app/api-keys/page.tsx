"use client"

import React, { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Key, Loader2 } from 'lucide-react'
import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'
import { Alert, AlertDescription } from '@/shared/ui/alert'
import { APIKeyInput } from '@/features/settings/components/APIKeyInput'
import { 
  APIKeyType, 
  APIKeyInfo, 
  apiKeyService,
  getAPIKeyDescription
} from '@/services/api/api-keys'

export default function APIKeysPage() {
  const router = useRouter()
  const [apiKeys, setAPIKeys] = useState<APIKeyInfo[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const keysResult = await apiKeyService.listAPIKeys()
      
      setAPIKeys(keysResult.api_keys)
    } catch (err: unknown) {
      // Check if it's a 404 error
      if (err instanceof Error && err.message.includes('404')) {
        setError('API key management is not available on this deployment. This feature may not be configured on the backend server.')
      } else {
        const errorMessage = err instanceof Error ? err.message : 'Failed to load API keys'
        setError(errorMessage)
      }
      console.error('API Keys loading error:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleAPIKeySave = async () => {
    await loadData()
  }

  const handleAPIKeyDelete = async () => {
    await loadData()
  }

  const getExistingKey = (type: APIKeyType): APIKeyInfo | undefined => {
    return apiKeys.find(key => key.api_key_type === type)
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Simple Header */}
      <div className="border-b">
        <div className="container max-w-3xl mx-auto px-6 py-4">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => router.back()}
              aria-label="Go back"
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div className="flex items-center gap-2">
              <Key className="h-5 w-5 text-muted-foreground" />
              <h1 className="text-xl font-semibold">API Keys</h1>
            </div>
          </div>
        </div>
      </div>

      <div className="container max-w-3xl mx-auto px-6 py-8">
        {/* Loading State */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        )}

        {/* Error State */}
        {error && !isLoading && (
          <>
            <Alert variant={error.includes('not available') ? 'default' : 'destructive'} className="mb-6">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
            
            {/* Show instructions when API is not available */}
            {error.includes('not available') && (
              <Card>
                <CardHeader>
                  <CardTitle>API Key Configuration</CardTitle>
                  <CardDescription>
                    Manual configuration required
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    The API key management endpoints are not available on this deployment. 
                    You may need to configure API keys through environment variables or contact your administrator.
                  </p>
                  <div className="space-y-3">
                    <div className="p-3 bg-muted/50 rounded-lg">
                      <h4 className="text-sm font-medium mb-1">Google Gemini API Key</h4>
                      <p className="text-xs text-muted-foreground">
                        Required for AI-powered responses. Set as GEMINI_API_KEY environment variable.
                      </p>
                    </div>
                    <div className="p-3 bg-muted/50 rounded-lg">
                      <h4 className="text-sm font-medium mb-1">Tavily Search API Key</h4>
                      <p className="text-xs text-muted-foreground">
                        Optional for web search. Set as TAVILY_API_KEY environment variable.
                      </p>
                    </div>
                    <div className="p-3 bg-muted/50 rounded-lg">
                      <h4 className="text-sm font-medium mb-1">Firecrawl API Key</h4>
                      <p className="text-xs text-muted-foreground">
                        Optional for web scraping. Set as FIRECRAWL_API_KEY environment variable.
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        )}

        {/* Main Content */}
        {!isLoading && !error && (
          <Card>
            <CardHeader>
              <CardTitle>Configure API Keys</CardTitle>
              <CardDescription>
                Add your API keys to enable MB-Sparrow&apos;s AI features
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Gemini API Key (Required) */}
              <div>
                <h3 className="text-sm font-medium mb-1">Google Gemini API</h3>
                <p className="text-xs text-muted-foreground mb-3">
                  {getAPIKeyDescription(APIKeyType.GEMINI)}
                </p>
                <APIKeyInput
                  type={APIKeyType.GEMINI}
                  existingKey={getExistingKey(APIKeyType.GEMINI)}
                  onSave={handleAPIKeySave}
                  onDelete={handleAPIKeyDelete}
                />
              </div>

              {/* Optional API Keys */}
              <div className="space-y-6 pt-4 border-t">
                <div>
                  <h3 className="text-sm font-medium mb-1">Tavily Search API (Optional)</h3>
                  <p className="text-xs text-muted-foreground mb-3">
                    {getAPIKeyDescription(APIKeyType.TAVILY)}
                  </p>
                  <APIKeyInput
                    type={APIKeyType.TAVILY}
                    existingKey={getExistingKey(APIKeyType.TAVILY)}
                    onSave={handleAPIKeySave}
                    onDelete={handleAPIKeyDelete}
                  />
                </div>

                <div>
                  <h3 className="text-sm font-medium mb-1">Firecrawl API (Optional)</h3>
                  <p className="text-xs text-muted-foreground mb-3">
                    {getAPIKeyDescription(APIKeyType.FIRECRAWL)}
                  </p>
                  <APIKeyInput
                    type={APIKeyType.FIRECRAWL}
                    existingKey={getExistingKey(APIKeyType.FIRECRAWL)}
                    onSave={handleAPIKeySave}
                    onDelete={handleAPIKeyDelete}
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
