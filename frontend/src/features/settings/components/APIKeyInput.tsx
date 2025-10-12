"use client"

import React, { useState, useEffect } from 'react'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'
import { Alert, AlertDescription } from '@/shared/ui/alert'
import { Eye, EyeOff, Save, Trash2, CheckCircle, AlertCircle } from 'lucide-react'
import { 
  APIKeyType, 
  APIKeyInfo, 
  apiKeyService 
} from '@/services/api/api-keys'

interface APIKeyInputProps {
  type: APIKeyType
  existingKey?: APIKeyInfo
  onSave: (type: APIKeyType) => void
  onDelete: (type: APIKeyType) => void
}

export function APIKeyInput({ 
  type, 
  existingKey, 
  onSave, 
  onDelete
}: APIKeyInputProps) {
  const [apiKey, setAPIKey] = useState("")
  const [showKey, setShowKey] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    setAPIKey("")
    setError(null)
    setSuccess(false)
  }, [existingKey])

  const handleSave = async () => {
    if (!apiKey.trim()) {
      setError('Please enter an API key')
      return
    }

    setIsSaving(true)
    setError(null)
    setSuccess(false)

    try {
      await apiKeyService.createOrUpdateAPIKey({
        api_key_type: type,
        api_key: apiKey.trim()
      })

      setAPIKey("")
      setSuccess(true)
      onSave(type)
      
      // Clear success message after 3 seconds
      setTimeout(() => setSuccess(false), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save API key')
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!existingKey) return

    setIsDeleting(true)
    setError(null)

    try {
      await apiKeyService.deleteAPIKey(type)
      onDelete(type)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete API key')
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <div className="space-y-3">
      {/* Current Key Status */}
      {existingKey && (
        <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
          <div className="flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-green-600" />
            <span className="text-sm">API key configured</span>
            <span className="text-xs text-muted-foreground font-mono">
              ({existingKey.masked_key})
            </span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleDelete}
            disabled={isDeleting}
            className="text-destructive hover:text-destructive"
          >
            {isDeleting ? (
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
          </Button>
        </div>
      )}

      {/* API Key Input - Wrapped in form to prevent browser warnings */}
      <form 
        onSubmit={(e) => {
          e.preventDefault()
          if (apiKey.trim()) {
            handleSave()
          }
        }}
        className="flex gap-2"
      >
        <div className="relative flex-1">
          <Input
            type={showKey ? "text" : "password"}
            value={apiKey}
            onChange={(e) => setAPIKey(e.target.value)}
            placeholder={existingKey ? "Enter new API key" : "Enter API key"}
            disabled={isSaving}
            autoComplete="off"
            name={`api-key-${type}`}
            aria-label={`API key for ${type}`}
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="absolute right-0 top-0 h-full px-3"
            onClick={() => setShowKey(!showKey)}
            tabIndex={-1}
          >
            {showKey ? (
              <EyeOff className="h-4 w-4 text-muted-foreground" />
            ) : (
              <Eye className="h-4 w-4 text-muted-foreground" />
            )}
          </Button>
        </div>
        <Button
          type="submit"
          disabled={!apiKey.trim() || isSaving}
        >
          {isSaving ? (
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          ) : (
            <>
              <Save className="h-4 w-4 mr-1" />
              Save
            </>
          )}
        </Button>
      </form>

      {/* Error Message */}
      {error && (
        <Alert variant="destructive" className="py-2">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="text-sm">{error}</AlertDescription>
        </Alert>
      )}

      {/* Success Message */}
      {success && (
        <Alert className="py-2 border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-200">
          <CheckCircle className="h-4 w-4" />
          <AlertDescription className="text-sm">API key saved successfully</AlertDescription>
        </Alert>
      )}
    </div>
  )
}
