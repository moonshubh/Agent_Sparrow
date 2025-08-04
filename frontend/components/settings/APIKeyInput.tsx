"use client"

import React, { useState, useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Eye, EyeOff, Save, Trash2, CheckCircle, AlertCircle, Info } from 'lucide-react'
import { 
  APIKeyType, 
  APIKeyInfo, 
  getAPIKeyDisplayName, 
  getAPIKeyDescription,
  getAPIKeyFormatRequirements,
  isAPIKeyRequired,
  apiKeyService 
} from '@/lib/api-keys'

interface APIKeyInputProps {
  type: APIKeyType
  existingKey?: APIKeyInfo
  onSave: (type: APIKeyType, keyName?: string) => void
  onDelete: (type: APIKeyType) => void
  className?: string
}

export function APIKeyInput({ 
  type, 
  existingKey, 
  onSave, 
  onDelete, 
  className = "" 
}: APIKeyInputProps) {
  const [apiKey, setAPIKey] = useState("")
  const [keyName, setKeyName] = useState(existingKey?.key_name || "")
  const [showKey, setShowKey] = useState(false)
  const [isValidating, setIsValidating] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [validationResult, setValidationResult] = useState<{
    isValid: boolean
    message: string
  } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const displayName = getAPIKeyDisplayName(type)
  const description = getAPIKeyDescription(type)
  const formatRequirements = getAPIKeyFormatRequirements(type)
  const isRequired = isAPIKeyRequired(type)
  
  // Ref to store timeout ID for cleanup
  const validationTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  // Clear state when existingKey changes
  useEffect(() => {
    setAPIKey("")
    setKeyName(existingKey?.key_name || "")
    setValidationResult(null)
    setError(null)
  }, [existingKey])
  
  // Cleanup timeout on component unmount
  useEffect(() => {
    return () => {
      if (validationTimeoutRef.current) {
        clearTimeout(validationTimeoutRef.current)
      }
    }
  }, [])

  const validateAPIKey = async (key: string) => {
    if (!key.trim()) {
      setValidationResult(null)
      return
    }

    setIsValidating(true)
    setError(null)

    try {
      const result = await apiKeyService.validateAPIKey({
        api_key_type: type,
        api_key: key.trim()
      })
      setValidationResult(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Validation failed')
      setValidationResult(null)
    } finally {
      setIsValidating(false)
    }
  }

  const handleAPIKeyChange = (value: string) => {
    setAPIKey(value)
    setError(null)
    setSuccessMessage(null) // Clear success message when user starts editing
    
    // Clear previous timeout if it exists
    if (validationTimeoutRef.current) {
      clearTimeout(validationTimeoutRef.current)
    }
    
    // Debounce validation
    validationTimeoutRef.current = setTimeout(() => {
      validateAPIKey(value)
    }, 500)
  }

  const handleSave = async () => {
    if (!apiKey.trim()) {
      setError('API key cannot be empty')
      return
    }

    if (validationResult && !validationResult.isValid) {
      setError('Please enter a valid API key')
      return
    }

    setIsSaving(true)
    setError(null)

    try {
      const result = await apiKeyService.createOrUpdateAPIKey({
        api_key_type: type,
        api_key: apiKey.trim(),
        key_name: keyName.trim() || undefined
      })

      if (result.success) {
        setAPIKey("") // Clear the input for security
        setSuccessMessage("API key saved successfully! The key has been cleared from this form for security reasons. You can re-enter it if you need to make changes.")
        setError(null)
        onSave(type, keyName.trim() || undefined)
        
        // Clear success message after 8 seconds
        setTimeout(() => setSuccessMessage(null), 8000)
      } else {
        setError(result.message)
        setSuccessMessage(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save API key')
      setSuccessMessage(null)
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!existingKey) return

    setIsDeleting(true)
    setError(null)

    try {
      const result = await apiKeyService.deleteAPIKey(type)
      
      if (result.success) {
        onDelete(type)
      } else {
        setError(result.message)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete API key')
    } finally {
      setIsDeleting(false)
    }
  }

  const canSave = apiKey.trim() && (!validationResult || validationResult.isValid) && !isValidating
  const canDelete = existingKey && !isRequired

  return (
    <form 
      onSubmit={(e) => {
        e.preventDefault()
        if (apiKey && validationResult?.isValid) {
          handleSave()
        }
      }}
      className={`space-y-4 p-6 border border-border rounded-lg bg-card/30 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Label className="text-lg font-medium">{displayName}</Label>
            {existingKey && (
              <Badge variant="default" className="text-xs bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                <CheckCircle className="w-3 h-3 mr-1" />
                Active
              </Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
      </div>

      {/* Current Key Status - Responsive with proper truncation */}
      {existingKey && (
        <div className="bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 rounded-md p-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex-1 min-w-0 space-y-1">
              <p className="text-sm font-medium text-green-800 dark:text-green-200">
                API Key Configured
              </p>
              
              {/* Responsive key info layout */}
              <div className="space-y-1 sm:space-y-0">
                {/* Mobile: Stacked layout, Desktop: Horizontal with bullets */}
                <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4 text-xs text-green-700 dark:text-green-300">
                  <span className="font-mono truncate max-w-[200px] sm:max-w-[150px]" title={existingKey.masked_key}>
                    {existingKey.masked_key}
                  </span>
                  
                  {existingKey.key_name && (
                    <div className="flex items-center gap-1">
                      <span className="hidden sm:inline">•</span>
                      <span className="truncate max-w-[200px] sm:max-w-[120px]" title={existingKey.key_name}>
                        {existingKey.key_name}
                      </span>
                    </div>
                  )}
                  
                  {existingKey.last_used_at && (
                    <div className="flex items-center gap-1">
                      <span className="hidden sm:inline">•</span>
                      <span className="whitespace-nowrap">
                        Used {new Date(existingKey.last_used_at).toLocaleDateString()}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </div>
            
            {canDelete && (
              <div className="flex-shrink-0">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleDelete}
                  disabled={isDeleting}
                  className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950/30"
                  aria-label="Delete API key"
                >
                  {isDeleting ? (
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                </Button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* API Key Input */}
      <div className="space-y-2">
        <Label htmlFor={`${type}-key`}>
          {existingKey ? 'Update API Key' : 'Enter API Key'}
        </Label>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Input
              id={`${type}-key`}
              type={showKey ? "text" : "password"}
              value={apiKey}
              onChange={(e) => handleAPIKeyChange(e.target.value)}
              placeholder={`Enter your ${displayName} API key`}
              className="pr-10"
              autoComplete="new-password"
              inputMode="text"
              disabled={isSaving}
            />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
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
            disabled={!canSave || isSaving}
            className="min-w-[80px]"
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
        </div>
      </div>

      {/* Key Name Input */}
      <div className="space-y-2">
        <Label htmlFor={`${type}-name`} className="text-sm">
          Key Name (Optional)
        </Label>
        <Input
          id={`${type}-name`}
          type="text"
          value={keyName}
          onChange={(e) => setKeyName(e.target.value)}
          placeholder="e.g., Production Key, Development Key"
          disabled={isSaving}
        />
      </div>

      {/* Validation Result */}
      {isValidating && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          Validating API key format...
        </div>
      )}

      {validationResult && (
        <Alert variant={validationResult.isValid ? "default" : "destructive"}>
          {validationResult.isValid ? (
            <CheckCircle className="h-4 w-4" />
          ) : (
            <AlertCircle className="h-4 w-4" />
          )}
          <AlertDescription>{validationResult.message}</AlertDescription>
        </Alert>
      )}

      {/* Error Display */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Success Display */}
      {successMessage && (
        <Alert variant="default" className="border-green-200 bg-green-50 text-green-800">
          <CheckCircle className="h-4 w-4 text-green-600" />
          <AlertDescription className="text-green-800">
            {successMessage}
          </AlertDescription>
        </Alert>
      )}

      {/* Format Requirements - More subtle */}
      <div className="text-xs text-muted-foreground p-3 bg-muted/20 rounded-md border-l-2 border-accent/30">
        <div className="flex items-center gap-2">
          <Info className="h-3 w-3" />
          <span className="font-medium">Format:</span>
          <span>{formatRequirements}</span>
        </div>
      </div>
    </form>
  )
}