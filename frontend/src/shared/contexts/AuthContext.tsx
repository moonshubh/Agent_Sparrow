"use client"

import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from 'react'
import { User } from '@supabase/supabase-js'
import { supabase } from '@/services/supabase'
import { authAPI } from '@/services/api/api-client'
// Avoid useRouter in providers mounted at RootLayout to prevent
// "expected app router to be mounted" during server render.
import { toast } from 'sonner'

export type ProfileUpdatePayload = {
  full_name?: string
  avatar_url?: string
  metadata?: Record<string, unknown>
}

const toError = (error: unknown, fallbackMessage: string): Error => (
  error instanceof Error ? error : new Error(fallbackMessage)
)

interface AuthContextType {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  loginWithOAuth: (provider: 'google' | 'github') => Promise<void>
  logout: () => Promise<void>
  refreshToken: () => Promise<void>
  updateProfile: (data: ProfileUpdatePayload) => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // Check if auth bypass is enabled
  const bypassAuth = process.env.NEXT_PUBLIC_BYPASS_AUTH === 'true'
  const devMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true'
  const localAuthBypass = process.env.NEXT_PUBLIC_LOCAL_AUTH_BYPASS === 'true'

  // Initialize auth state
  useEffect(() => {
    if (typeof window === 'undefined') return; // ensure router is mounted on client
    const initializeAuth = async () => {
      console.log('AuthContext: Starting initialization...')
      console.log('Local Auth Bypass:', localAuthBypass)
      console.log('Supabase URL:', process.env.NEXT_PUBLIC_SUPABASE_URL)
      console.log('Has Anon Key:', !!process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY)
      try {
        // Bypass authentication in local development mode
        if (localAuthBypass || (bypassAuth && devMode)) {
          console.log('🚀 Local auth bypass enabled - creating mock user')
          
          // Check if we have a local token
          const localUser = localStorage.getItem('user')
          if (localUser) {
            try {
              const parsedUser = JSON.parse(localUser)
              const mockUser: User = {
                id: parsedUser.id || 'dev-user-123',
                email: parsedUser.email || 'dev@localhost.com',
                app_metadata: {
                  provider: 'local',
                  providers: ['local'],
                },
                user_metadata: {
                  full_name: parsedUser.full_name || 'Local Dev User',
                  avatar_url: '/agent-sparrow.png',
                },
                aud: 'authenticated',
                role: 'authenticated',
                created_at: parsedUser.created_at || new Date().toISOString(),
                last_sign_in_at: parsedUser.last_sign_in_at || new Date().toISOString(),
                updated_at: parsedUser.updated_at || new Date().toISOString(),
                identities: [],
                factors: [],
              }
              
              setUser(mockUser)
              setIsLoading(false)
              return
            } catch (e) {
              console.error('Failed to parse local user:', e)
            }
          }
          
          // Fallback mock user
          const mockUser: User = {
            id: 'dev-user-123',
            email: 'dev@localhost.com',
            app_metadata: {
              provider: 'local',
              providers: ['local'],
            },
            user_metadata: {
              full_name: 'Local Dev User',
              avatar_url: '/agent-sparrow.png',
            },
            aud: 'authenticated',
            role: 'authenticated',
            created_at: new Date().toISOString(),
            last_sign_in_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            identities: [],
            factors: [],
          }
          
          setUser(mockUser)
          setIsLoading(false)
          return
        }

        console.log('AuthContext: Checking for existing session...')
        // Check if we have a session
        try {
          const { data: { session }, error } = await supabase.auth.getSession()
          
          if (error) {
            console.error('AuthContext: Error getting session:', error)
            // Don't throw, just continue without a session
          } else if (session) {
            console.log('AuthContext: Found session, setting user:', session.user.email)
            setUser(session.user)
            
            // Skip backend sync for now since backend auth endpoints are not configured
            // TODO: Enable this when backend auth is implemented
            /*
            try {
              await authAPI.getMe()
            } catch (error) {
              console.error('Failed to sync with backend:', error)
            }
            */
          } else {
            console.log('AuthContext: No session found')
          }
        } catch (sessionError) {
          console.error('AuthContext: Failed to check session:', sessionError)
        }
      } catch (error) {
        console.error('AuthContext: Error during initialization:', error)
        // Even if there's an error, we should stop loading to allow the user to try OAuth
      } finally {
        console.log('AuthContext: Initialization complete, setting isLoading to false')
        setIsLoading(false)
      }
    }

    initializeAuth()

    // Only listen for auth changes if not in local bypass mode
    if (!localAuthBypass) {
      const { data: { subscription } } = supabase.auth.onAuthStateChange(async (event, session) => {
        if (event === 'SIGNED_IN' && session) {
          setUser(session.user)
        } else if (event === 'SIGNED_OUT') {
          setUser(null)
        } else if (event === 'TOKEN_REFRESHED' && session) {
          setUser(session.user)
        }
      })

      return () => subscription.unsubscribe()
    }
  }, [bypassAuth, devMode, localAuthBypass])


  const loginWithOAuth = useCallback(async (provider: 'google' | 'github') => {
    try {
      // Store return URL in session storage before OAuth redirect
      const currentPath = window.location.pathname
      if (currentPath !== '/login') {
        sessionStorage.setItem('authReturnUrl', currentPath)
      }
      
      const { error } = await supabase.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo: process.env.NEXT_PUBLIC_AUTH_REDIRECT_URL || `${window.location.origin}/auth/callback`
        }
      })

      if (error) throw error

      // The user will be redirected to the OAuth provider
      // Don't set isLoading to false here as the page will redirect
    } catch (error) {
      const err = toError(error, `Failed to log in with ${provider}`)
      console.error('OAuth login error:', err)
      toast.error(err.message || `Failed to log in with ${provider}`)
      throw err
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      setIsLoading(true)
      
      // Sign out from Supabase
      const { error } = await supabase.auth.signOut()
      if (error) throw error

      // Skip backend sync for now since backend auth endpoints are not configured
      // TODO: Enable this when backend auth is implemented
      /*
      try {
        await authAPI.signOut()
      } catch (backendError) {
        console.error('Backend logout sync failed:', backendError)
      }
      */

      setUser(null)
      toast.success('Logged out successfully')
      if (typeof window !== 'undefined') {
        window.location.href = '/login'
      }
    } catch (error) {
      const err = toError(error, 'Failed to log out')
      console.error('Logout error:', err)
      toast.error(err.message || 'Failed to log out')
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [])


  const refreshToken = useCallback(async () => {
    try {
      const { data, error } = await supabase.auth.refreshSession()
      if (error) throw error
      
      if (data.session) {
        setUser(data.user)
      }
    } catch (error) {
      const err = toError(error, 'Token refresh failed')
      console.error('Token refresh error:', err)
      // If refresh fails, log out the user
      await logout()
    }
  }, [logout])

  const updateProfile = useCallback(async (profile: ProfileUpdatePayload) => {
    try {
      setIsLoading(true)
      
      // Update in Supabase
      const { data: userData, error } = await supabase.auth.updateUser({
        data: profile
      })

      if (error) throw error

      // Sync with backend
      try {
        await authAPI.updateProfile(profile)
      } catch (backendError) {
        console.error('Backend sync failed:', backendError)
      }

      if (userData.user) {
        setUser(userData.user)
      }

      toast.success('Profile updated successfully')
    } catch (error) {
      const err = toError(error, 'Failed to update profile')
      console.error('Profile update error:', err)
      toast.error(err.message || 'Failed to update profile')
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [])


  const value: AuthContextType = useMemo(() => ({
    user,
    isLoading,
    isAuthenticated: !!user,
    loginWithOAuth,
    logout,
    refreshToken,
    updateProfile
  }), [user, isLoading, loginWithOAuth, logout, refreshToken, updateProfile])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
