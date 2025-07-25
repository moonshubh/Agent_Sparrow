'use client'

import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { UserProfile } from '@/components/auth/UserProfile'
import { useAuth } from '@/hooks/useAuth'
import { Header } from '@/components/layout/Header'
import { UserPanel } from '@/components/layout/UserPanel'

export default function ProfilePage() {
  const { user, updateProfile, logout, isLoading } = useAuth()

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-background">
        <Header />
        
        <div className="container mx-auto px-4 py-8">
          <div className="max-w-2xl mx-auto">
            <div className="mb-8">
              <h1 className="text-3xl font-bold">Profile</h1>
              <p className="text-muted-foreground mt-2">
                Manage your account information and preferences
              </p>
            </div>

            {/* Loading state */}
            {isLoading && (
              <div className="flex items-center justify-center py-12">
                <div className="flex items-center gap-3">
                  <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
                  <span className="text-lg">Loading profile...</span>
                </div>
              </div>
            )}

            {/* User profile content */}
            {!isLoading && user && (
              <UserProfile
                user={user}
                onUpdate={updateProfile}
              />
            )}

            {/* No user state (shouldn't happen in ProtectedRoute, but good fallback) */}
            {!isLoading && !user && (
              <div className="text-center py-12">
                <p className="text-muted-foreground">
                  Unable to load user profile. Please try refreshing the page.
                </p>
              </div>
            )}
          </div>
        </div>

        <UserPanel
          user={user}
          onLogout={logout}
        />
      </div>
    </ProtectedRoute>
  )
}