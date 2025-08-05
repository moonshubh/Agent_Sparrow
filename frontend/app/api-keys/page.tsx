"use client"

import React, { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Key, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { APIKeyInput } from '@/components/settings/APIKeyInput'
import { 
  APIKeyType, 
  APIKeyInfo, 
  APIKeyStatus,
  apiKeyService,
  getAPIKeyDescription
} from '@/lib/api-keys'

export default function APIKeysPage() {
  const router = useRouter()
  const [apiKeys, setAPIKeys] = useState<APIKeyInfo[]>([])
  const [apiKeyStatus, setAPIKeyStatus] = useState<APIKeyStatus | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const [keysResult, statusResult] = await Promise.all([
        apiKeyService.listAPIKeys(),
        apiKeyService.getAPIKeyStatus()
      ])
      
      setAPIKeys(keysResult.api_keys)
      setAPIKeyStatus(statusResult)
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load API keys'
      setError(errorMessage)
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
          <Alert variant="destructive" className="mb-6">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Main Content */}
        {!isLoading && !error && (
          <Card>
            <CardHeader>
              <CardTitle>Configure API Keys</CardTitle>
              <CardDescription>
                Add your API keys to enable MB-Sparrow's AI features
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