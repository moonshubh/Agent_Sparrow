'use client'

import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from 'react'
import { User } from '@supabase/supabase-js'
import { supabase } from '@/lib/supabase'
import { authAPI } from '@/lib/api-client'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

interface AuthContextType {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  loginWithOAuth: (provider: 'google' | 'github') => Promise<void>
  logout: () => Promise<void>
  refreshToken: () => Promise<void>
  updateProfile: (data: { full_name?: string; avatar_url?: string; metadata?: any }) => Promise<void>
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
  const router = useRouter()

  // Check if auth bypass is enabled
  const bypassAuth = process.env.NEXT_PUBLIC_BYPASS_AUTH === 'true'
  const devMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true'

  // Initialize auth state
  useEffect(() => {
    const initializeAuth = async () => {
      console.log('AuthContext: Starting initialization...')
      console.log('Supabase URL:', process.env.NEXT_PUBLIC_SUPABASE_URL)
      console.log('Has Anon Key:', !!process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY)
      try {
        // Bypass authentication in development mode
        if (bypassAuth && devMode) {
          console.log('🚀 Auth bypass enabled - creating mock user')
          const mockUser = {
            id: 'dev-user-12345',
            email: 'developer@mailbird.com',
            user_metadata: {
              full_name: 'Test Developer',
              avatar_url: '/agent-sparrow.png'
            },
            app_metadata: {
              provider: 'bypass',
              providers: ['bypass']
            },
            created_at: new Date().toISOString(),
            last_sign_in_at: new Date().toISOString()
          } as User
          
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

    // Listen for auth changes
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
  }, [bypassAuth, devMode])


  const loginWithOAuth = useCallback(async (provider: 'google' | 'github') => {
    try {
      // Store return URL in session storage before OAuth redirect
      const currentPath = window.location.pathname
      if (currentPath !== '/login') {
        sessionStorage.setItem('authReturnUrl', currentPath)
      }
      
      const { data, error } = await supabase.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo: process.env.NEXT_PUBLIC_AUTH_REDIRECT_URL || `${window.location.origin}/auth/callback`
        }
      })

      if (error) throw error

      // The user will be redirected to the OAuth provider
      // Don't set isLoading to false here as the page will redirect
    } catch (error: any) {
      console.error('OAuth login error:', error)
      toast.error(error.message || `Failed to log in with ${provider}`)
      throw error
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
      router.push('/login')
    } catch (error: any) {
      console.error('Logout error:', error)
      toast.error(error.message || 'Failed to log out')
      throw error
    } finally {
      setIsLoading(false)
    }
  }, [router])


  const refreshToken = useCallback(async () => {
    try {
      const { data, error } = await supabase.auth.refreshSession()
      if (error) throw error
      
      if (data.session) {
        setUser(data.user)
      }
    } catch (error: any) {
      console.error('Token refresh error:', error)
      // If refresh fails, log out the user
      await logout()
    }
  }, [logout])

  const updateProfile = useCallback(async (data: { full_name?: string; avatar_url?: string; metadata?: any }) => {
    try {
      setIsLoading(true)
      
      // Update in Supabase
      const { data: userData, error } = await supabase.auth.updateUser({
        data
      })

      if (error) throw error

      // Sync with backend
      try {
        await authAPI.updateProfile(data)
      } catch (backendError) {
        console.error('Backend sync failed:', backendError)
      }

      if (userData.user) {
        setUser(userData.user)
      }

      toast.success('Profile updated successfully')
    } catch (error: any) {
      console.error('Profile update error:', error)
      toast.error(error.message || 'Failed to update profile')
      throw error
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
