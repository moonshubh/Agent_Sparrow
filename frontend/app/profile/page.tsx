'use client'

import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { UserProfile } from '@/components/auth/UserProfile'
import { useAuth } from '@/hooks/useAuth'
import { Header } from '@/components/layout/Header'
import { UserPanel } from '@/components/layout/UserPanel'

export default function ProfilePage() {
  const { user, updateProfile, logout } = useAuth()

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

            {user && (
              <UserProfile
                user={user}
                onUpdate={updateProfile}
              />
            )}
          </div>
        </div>

        <UserPanel
          user={user}
          isAuthenticated={!!user}
          onLogout={logout}
        />
      </div>
    </ProtectedRoute>
  )
}