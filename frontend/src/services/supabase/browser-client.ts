import { createBrowserClient } from '@supabase/ssr'

// Check if we're in local auth bypass mode
const isLocalAuthBypass = process.env.NEXT_PUBLIC_LOCAL_AUTH_BYPASS === 'true'

// In local auth bypass mode, use dummy values
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || (isLocalAuthBypass ? 'http://localhost:54321' : '')
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || (isLocalAuthBypass ? 'dummy-key-for-local-dev' : '')

// Only validate in non-local mode
if (!isLocalAuthBypass && (!supabaseUrl || !supabaseAnonKey)) {
  throw new Error('Missing required Supabase environment variables')
}

// Create a Supabase client for use in the browser
// In local mode, this will be a dummy client that won't be used
export const supabase = createBrowserClient(
  supabaseUrl,
  supabaseAnonKey,
  {
    auth: {
      flowType: 'pkce',
      autoRefreshToken: !isLocalAuthBypass,
      detectSessionInUrl: !isLocalAuthBypass,
      persistSession: !isLocalAuthBypass
    }
  }
)