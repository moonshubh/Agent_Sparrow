// Re-export the browser client from the new file
import { supabase } from './supabase-browser'
export { supabase }

// Helper to get the current session
export const getSession = async () => {
  const { data: { session }, error } = await supabase.auth.getSession()
  if (error) {
    console.error('Error getting session:', error)
    return null
  }
  return session
}

// Helper to get the current user
export const getCurrentUser = async () => {
  const { data: { user }, error } = await supabase.auth.getUser()
  if (error) {
    console.error('Error getting user:', error)
    return null
  }
  return user
}

// Type definitions for Supabase
export type SupabaseUser = Awaited<ReturnType<typeof getCurrentUser>>
export type SupabaseSession = Awaited<ReturnType<typeof getSession>>