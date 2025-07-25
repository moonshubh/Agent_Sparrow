"use client"

import React, { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Key, Shield, CheckCircle, AlertCircle, Info, HelpCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { StatusGrid, StatusItem } from '@/components/api-keys/StatusGrid'
import { APIKeyConfigSection, APIKeyConfig } from '@/components/api-keys/APIKeyConfigSection'
import { SecurityFeatureGrid, SecurityFeature } from '@/components/api-keys/SecurityFeatureGrid'
import { 
  APIKeyType, 
  APIKeyInfo, 
  APIKeyStatus,
  apiKeyService 
} from '@/lib/api-keys'

// Define specific error types for better type safety
interface APIError {
  code?: string
  status?: number
  message: string
}

// Constants to eliminate code duplication
const ERROR_MESSAGES = {
  NETWORK_ERROR: 'Cannot connect to server. Please check your connection.',
  UNAUTHORIZED: 'Authentication required. Please log in.',
  GENERIC_LOAD_ERROR: 'Failed to load API keys',
  DEVELOPMENT_MODE: 'API Keys page: API loading disabled during development'
} as const

const DEFAULT_API_STATUS: APIKeyStatus = {
  user_id: 'unknown',
  gemini_configured: false,
  tavily_configured: false,
  firecrawl_configured: false,
  all_required_configured: false,
  last_validation_check: undefined
}

const DEVELOPMENT_API_STATUS: APIKeyStatus = {
  user_id: 'development',
  gemini_configured: false,
  tavily_configured: false,
  firecrawl_configured: false,
  all_required_configured: false,
  last_validation_check: 'Development mode'
}

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

  // Helper function to handle and format errors
  const handleError = (err: unknown): string => {
    // Type guard for APIError
    const isAPIError = (error: unknown): error is APIError => {
      return typeof error === 'object' && error !== null && 'message' in error
    }

    if (isAPIError(err)) {
      if (err.code === 'NETWORK_ERROR') {
        return ERROR_MESSAGES.NETWORK_ERROR
      }
      if (err.status === 401) {
        return ERROR_MESSAGES.UNAUTHORIZED
      }
      return err.message
    }
    
    if (err instanceof Error) {
      return err.message
    }
    
    return ERROR_MESSAGES.GENERIC_LOAD_ERROR
  }

  const loadData = async () => {
    setIsLoading(true)
    setError(null)

    // Skip API loading during development until auth system is integrated
    // Use Next.js specific environment detection for reliability
    if (process.env.NODE_ENV === 'development' || !process.env.NEXT_PUBLIC_SUPABASE_URL) {
      if (process.env.NODE_ENV === 'development') {
        console.log(ERROR_MESSAGES.DEVELOPMENT_MODE)
      }
      setAPIKeyStatus(DEVELOPMENT_API_STATUS)
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
    } catch (err: unknown) {
      const errorMessage = handleError(err)
      setError(errorMessage)
      console.error('API Keys loading error:', err)

      // Set default status on error
      setAPIKeyStatus(DEFAULT_API_STATUS)
    } finally {
      setIsLoading(false)
    }
  }

  const handleAPIKeySave = async (_type: APIKeyType, _keyName?: string) => {
    setIsLoading(true)
    try {
      await loadData()
    } finally {
      setIsLoading(false)
    }
  }

  const handleAPIKeyDelete = async (_type: APIKeyType) => {
    setIsLoading(true)
    try {
      await loadData()
    } finally {
      setIsLoading(false)
    }
  }

  const getExistingKey = (type: APIKeyType): APIKeyInfo | undefined => {
    return apiKeys.find(key => key.api_key_type === type)
  }

  // Data-driven configuration for status items
  const statusItems: StatusItem[] = [
    {
      id: 'gemini',
      name: 'Google Gemini',
      description: 'AI Models & Chat',
      configured: apiKeyStatus?.gemini_configured || false,
      required: true
    },
    {
      id: 'tavily',
      name: 'Tavily Search',
      description: 'Web Search',
      configured: apiKeyStatus?.tavily_configured || false,
      required: false
    },
    {
      id: 'firecrawl',
      name: 'Firecrawl',
      description: 'Web Scraping',
      configured: apiKeyStatus?.firecrawl_configured || false,
      required: false
    }
  ]

  // Data-driven configuration for API key sections
  const apiKeyConfigs: APIKeyConfig[] = [
    {
      type: APIKeyType.GEMINI,
      name: 'Google Gemini API',
      required: true
    },
    {
      type: APIKeyType.TAVILY,
      name: 'Tavily Search API',
      required: false
    },
    {
      type: APIKeyType.FIRECRAWL,
      name: 'Firecrawl API',
      required: false
    }
  ]

  // Data-driven configuration for security features
  const securityFeatures: SecurityFeature[] = [
    {
      id: 'encryption',
      icon: Shield,
      iconColor: 'text-green-600',
      title: 'AES-256 Encryption',
      description: 'All API keys are encrypted with user-specific keys before storage'
    },
    {
      id: 'isolation',
      icon: Key,
      iconColor: 'text-blue-600',
      title: 'User Isolation',
      description: 'Your keys are completely isolated from other users'
    },
    {
      id: 'transmission',
      icon: CheckCircle,
      iconColor: 'text-green-600',
      title: 'Secure Transmission',
      description: 'All operations use HTTPS encryption'
    },
    {
      id: 'storage',
      icon: HelpCircle,
      iconColor: 'text-purple-600',
      title: 'No Client Storage',
      description: 'Keys are never stored in your browser'
    }
  ]

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
                <StatusGrid items={statusItems} />

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
              <CardContent>
                <APIKeyConfigSection
                  configs={apiKeyConfigs}
                  getExistingKey={getExistingKey}
                  onSave={handleAPIKeySave}
                  onDelete={handleAPIKeyDelete}
                />
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
                <SecurityFeatureGrid features={securityFeatures} />
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}