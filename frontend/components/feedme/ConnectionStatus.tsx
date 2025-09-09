/**
 * Connection Status Component
 * Displays the current connection status to the FeedMe backend API
 */

'use client'

import React, { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, Loader2, WifiOff } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

interface ConnectionStatusProps {
  onRetry?: () => void
  className?: string
}

export function ConnectionStatus({ onRetry, className }: ConnectionStatusProps) {
  const [status, setStatus] = useState<'checking' | 'connected' | 'error'>('checking')
  const [errorMessage, setErrorMessage] = useState<string>('')
  const [apiUrl, setApiUrl] = useState<string>('')

  const checkConnection = async () => {
    setStatus('checking')
    setErrorMessage('')
    
    const baseUrl = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000/api/v1'
    setApiUrl(baseUrl)
    
    try {
      // Try to fetch the health endpoint - adjusting path based on API_BASE structure
      const healthUrl = baseUrl.includes('/api/v1') 
        ? baseUrl.replace('/api/v1', '/health')
        : `${baseUrl}/health`
      
      const response = await fetch(healthUrl, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
        // Don't use fetch with retry here - we want to see the raw error
        signal: AbortSignal.timeout(5000), // 5 second timeout
      })

      if (response.ok) {
        setStatus('connected')
      } else {
        setStatus('error')
        setErrorMessage(`API returned status ${response.status}`)
      }
    } catch (error) {
      setStatus('error')
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          setErrorMessage('Connection timeout - is the backend running?')
        } else if (error.message.includes('fetch')) {
          setErrorMessage('Cannot connect to backend - please ensure the API server is running on port 8000')
        } else {
          setErrorMessage(error.message)
        }
      } else {
        setErrorMessage('Unknown connection error')
      }
    }
  }

  useEffect(() => {
    checkConnection()
  }, [])

  const handleRetry = () => {
    checkConnection()
    onRetry?.()
  }

  if (status === 'checking') {
    return (
      <Alert className={className}>
        <Loader2 className="h-4 w-4 animate-spin" />
        <AlertTitle>Checking connection...</AlertTitle>
        <AlertDescription>
          Connecting to FeedMe API at {apiUrl}
        </AlertDescription>
      </Alert>
    )
  }

  if (status === 'error') {
    return (
      <Alert variant="destructive" className={className}>
        <WifiOff className="h-4 w-4" />
        <AlertTitle>Connection Error</AlertTitle>
        <AlertDescription className="space-y-2">
          <p>{errorMessage}</p>
          <p className="text-sm">
            API URL: <code className="bg-muted px-1 py-0.5 rounded">{apiUrl}</code>
          </p>
          <div className="flex items-center gap-2 mt-2">
            <Button size="sm" variant="outline" onClick={handleRetry}>
              Retry Connection
            </Button>
            <p className="text-xs text-muted-foreground">
              Make sure the backend is running with: <code>uvicorn app.main:app --reload --port 8000</code>
            </p>
          </div>
        </AlertDescription>
      </Alert>
    )
  }

  return (
    <Alert className={className}>
      <CheckCircle2 className="h-4 w-4 text-green-600" />
      <AlertTitle>Connected</AlertTitle>
      <AlertDescription>
        Successfully connected to FeedMe API at {apiUrl}
      </AlertDescription>
    </Alert>
  )
}

export default ConnectionStatus