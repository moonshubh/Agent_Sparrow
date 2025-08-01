import { createClient } from '@supabase/supabase-js'

// Ensure required environment variables are set
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

// Validate environment variables
if (!supabaseUrl || !supabaseAnonKey) {
  const errorMessage = 'Missing required Supabase environment variables. Please set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in your .env.local file.'
  
  if (process.env.NODE_ENV === 'development') {
    // In development, throw an error to make configuration issues immediately obvious
    throw new Error(errorMessage)
  } else {
    // In production, log a warning to avoid breaking the app
    console.warn('Supabase credentials not configured. Authentication will not work.')
  }
}

// Create a single supabase client for interacting with the database
export const supabase = createClient(
  supabaseUrl || 'https://placeholder.supabase.co',
  supabaseAnonKey || 'placeholder-key',
  {
    auth: {
      autoRefreshToken: true,
      persistSession: true,
      detectSessionInUrl: true,
      flowType: 'pkce'
    },
    // Additional security options
    db: {
      schema: 'public'
    },
    global: {
      headers: {
        'X-Client-Info': 'mb-sparrow-frontend'
      }
    }
  }
)

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