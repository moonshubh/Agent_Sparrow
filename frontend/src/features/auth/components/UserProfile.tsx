'use client'

import React, { useState } from 'react'
import { User } from '@supabase/supabase-js'
import { toast } from 'sonner'
import { Loader2, Save } from 'lucide-react'

import { type ProfileUpdatePayload } from '@/shared/contexts/AuthContext'
import { UserAvatar } from '@/shared/ui/UserAvatar'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'

interface UserProfileProps {
  user: User
  onUpdate: (data: ProfileUpdatePayload) => Promise<void>
}

// Helper function to format dates consistently
const formatDate = (dateString: string): string => {
  const date = new Date(dateString)
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// Helper function to report errors (can be replaced with monitoring service)
const reportError = (error: unknown, context: string) => {
  if (process.env.NODE_ENV === 'development') {
    console.error(`${context}:`, error)
  } else {
    // In production, this could send errors to a monitoring service
    // Example: errorReportingService.captureException(error, { context })
    console.error(`${context}: An error occurred`)
  }
}

export const UserProfile: React.FC<UserProfileProps> = ({ user, onUpdate }) => {
  const [isLoading, setIsLoading] = useState(false)
  const [fullName, setFullName] = useState(
    user?.user_metadata?.full_name || user?.user_metadata?.name || ''
  )
  
  // Store initial name for change detection
  const initialFullName = user?.user_metadata?.full_name || user?.user_metadata?.name || ''

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    // Check if fullName has actually changed
    if (fullName === initialFullName) {
      toast.info('No changes to save')
      return
    }
    
    try {
      setIsLoading(true)
      await onUpdate({ full_name: fullName })
      toast.success('Profile updated successfully')
    } catch (error) {
      // Enhanced error reporting and user feedback
      reportError(error, 'Profile update error')
      
      // Extract specific error details for better user feedback
      let errorMessage = 'Failed to update profile'
      if (error instanceof Error) {
        if (error.message.includes('network')) {
          errorMessage = 'Network error. Please check your connection and try again.'
        } else if (error.message.includes('unauthorized')) {
          errorMessage = 'You are not authorized to update this profile.'
        } else if (error.message.includes('validation')) {
          errorMessage = 'Invalid profile data. Please check your input.'
        } else if (error.message) {
          errorMessage = `Update failed: ${error.message}`
        }
      }
      
      toast.error(errorMessage)
    } finally {
      setIsLoading(false)
    }
  }

  const getProvider = () => {
    const provider = user?.app_metadata?.provider
    
    // Check if provider is a valid non-empty string
    if (provider && typeof provider === 'string' && provider.trim().length > 0) {
      return provider.charAt(0).toUpperCase() + provider.slice(1)
    }
    
    return 'OAuth'
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Profile Information</CardTitle>
          <CardDescription>
            Update your profile information and manage your account
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex items-center space-x-4">
            <UserAvatar user={user} size="xl" />
            <div>
              <p className="text-sm font-medium">Profile Picture</p>
              <p className="text-sm text-muted-foreground">
                Your profile picture is provided by {getProvider()}
              </p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={user.email || ''}
                disabled
                className="bg-muted"
              />
              <p className="text-sm text-muted-foreground">
                Your email is managed by {getProvider()} and cannot be changed here
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="fullName">Full Name</Label>
              <Input
                id="fullName"
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Enter your full name"
              />
            </div>

            <Button type="submit" disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="mr-2 h-4 w-4" />
                  Save Changes
                </>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Account Information</CardTitle>
          <CardDescription>
            Details about your account and authentication
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2">
            <div className="flex justify-between">
              <span className="text-sm font-medium">User ID</span>
              <span className="text-sm text-muted-foreground font-mono">{user.id}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm font-medium">Provider</span>
              <span className="text-sm text-muted-foreground">{getProvider()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm font-medium">Created</span>
              <span className="text-sm text-muted-foreground">
                {formatDate(user.created_at)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm font-medium">Last Sign In</span>
              <span className="text-sm text-muted-foreground">
                {user.last_sign_in_at 
                  ? formatDate(user.last_sign_in_at)
                  : 'Never'
                }
              </span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
