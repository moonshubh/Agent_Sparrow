import { createBrowserClient } from '@supabase/ssr'

// Check if we're in development bypass mode
const bypassAuth = process.env.NEXT_PUBLIC_BYPASS_AUTH === 'true'
const devMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true'

// In bypass mode, use dummy values if Supabase credentials are not provided
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || (bypassAuth && devMode ? 'https://placeholder.supabase.co' : '')
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || (bypassAuth && devMode ? 'placeholder-key' : '')

// Validate environment variables only if not in bypass mode
if (!bypassAuth && (!SUPABASE_URL || !SUPABASE_ANON_KEY)) {
  throw new Error('Missing required Supabase environment variables. Either configure Supabase or enable auth bypass for development.')
}

// Create a Supabase client for use in the browser
export const supabase = createBrowserClient(
  SUPABASE_URL,
  SUPABASE_ANON_KEY,
  {
    auth: {
      flowType: 'pkce',
      autoRefreshToken: !bypassAuth, // Disable auto-refresh in bypass mode
      detectSessionInUrl: !bypassAuth, // Disable URL detection in bypass mode
      persistSession: !bypassAuth // Disable persistence in bypass mode
    }
  }
)