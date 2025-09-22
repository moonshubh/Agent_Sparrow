/**
 * Edge Runtime compatible Supabase client for Next.js middleware
 *
 * This client is specifically designed to work in Edge Runtime environments
 * where Node.js APIs are not available.
 */

import { createClient, SupabaseClient } from '@supabase/supabase-js'
import { NextRequest, NextResponse } from 'next/server'

/**
 * Creates an Edge Runtime compatible Supabase client
 * This avoids using Node.js specific APIs that aren't available in Edge Runtime
 */
export function createEdgeClient(
  request: NextRequest,
  response: NextResponse
): SupabaseClient {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

  if (!supabaseUrl || !supabaseAnonKey) {
    throw new Error('Missing Supabase environment variables')
  }

  // Create a Supabase client with custom cookie handling for Edge Runtime
  return createClient(supabaseUrl, supabaseAnonKey, {
    auth: {
      // Use cookies from the request/response for auth storage
      storage: {
        getItem: (key: string) => {
          const cookieName = key.split(':').pop() || key
          return request.cookies.get(cookieName)?.value || null
        },
        setItem: (key: string, value: string) => {
          const cookieName = key.split(':').pop() || key
          response.cookies.set({
            name: cookieName,
            value,
            httpOnly: true,
            secure: process.env.NODE_ENV === 'production',
            sameSite: 'lax',
            maxAge: 60 * 60 * 24 * 7, // 7 days
          })
        },
        removeItem: (key: string) => {
          const cookieName = key.split(':').pop() || key
          response.cookies.set({
            name: cookieName,
            value: '',
            httpOnly: true,
            secure: process.env.NODE_ENV === 'production',
            sameSite: 'lax',
            maxAge: 0,
          })
        },
      },
      // Disable auto-refresh in Edge Runtime to avoid timer issues
      autoRefreshToken: false,
      detectSessionInUrl: false,
      persistSession: false,
      // Use pkce flow for better security
      flowType: 'pkce',
    },
    // Disable real-time features in Edge Runtime
    realtime: {
      params: {
        eventsPerSecond: -1, // Disable real-time
      },
    },
    // Set global headers
    global: {
      headers: {
        'x-runtime': 'edge',
      },
    },
  })
}

/**
 * Helper function to get user from auth token in Edge Runtime
 * This is useful for API routes that receive Bearer tokens
 */
export async function getUserFromToken(
  token: string,
  supabaseUrl?: string,
  supabaseAnonKey?: string
): Promise<{ user: any; error: any }> {
  const url = supabaseUrl || process.env.NEXT_PUBLIC_SUPABASE_URL
  const key = supabaseAnonKey || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

  if (!url || !key) {
    return { user: null, error: new Error('Missing Supabase configuration') }
  }

  // Create a minimal client just for auth verification
  const supabase = createClient(url, key, {
    auth: {
      autoRefreshToken: false,
      detectSessionInUrl: false,
      persistSession: false,
    },
    // Disable real-time in Edge Runtime
    realtime: {
      params: {
        eventsPerSecond: -1,
      },
    },
  })

  // Get user from the token
  const { data: { user }, error } = await supabase.auth.getUser(token)

  return { user, error }
}

/**
 * Helper to extract auth cookies from request in a Edge Runtime compatible way
 */
export function getAuthCookies(request: NextRequest): {
  accessToken?: string
  refreshToken?: string
} {
  const cookies = request.cookies

  // Supabase stores tokens in cookies with specific names
  const accessToken = cookies.get('sb-access-token')?.value ||
                     cookies.get('supabase-auth-token')?.value
  const refreshToken = cookies.get('sb-refresh-token')?.value

  return { accessToken, refreshToken }
}

/**
 * Simplified auth check for Edge Runtime
 * Returns true if user appears to be authenticated based on cookies
 */
export function hasAuthCookies(request: NextRequest): boolean {
  const { accessToken } = getAuthCookies(request)
  return !!accessToken
}