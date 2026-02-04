/**
 * Edge Runtime compatible Supabase client for Next.js middleware
 *
 * This client is specifically designed to work in Edge Runtime environments
 * where Node.js APIs are not available.
 */

import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { createClient, SupabaseClient } from "@supabase/supabase-js";
import { NextRequest, NextResponse } from "next/server";

/**
 * Creates an Edge Runtime compatible Supabase client using @supabase/ssr
 * This properly handles cookie reading/writing for authentication
 */
export function createEdgeClient(
  request: NextRequest,
  response: NextResponse,
): SupabaseClient {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseAnonKey) {
    throw new Error("Missing Supabase environment variables");
  }

  // Use @supabase/ssr's createServerClient for proper cookie handling
  return createServerClient(supabaseUrl, supabaseAnonKey, {
    cookies: {
      get(name: string) {
        return request.cookies.get(name)?.value;
      },
      set(name: string, value: string, options: CookieOptions) {
        // Set cookie on the response
        response.cookies.set({
          name,
          value,
          ...options,
          // Ensure secure in production
          secure: options.secure ?? process.env.NODE_ENV === "production",
        });
      },
      remove(name: string, options: CookieOptions) {
        response.cookies.set({
          name,
          value: "",
          ...options,
          maxAge: 0,
        });
      },
    },
  });
}

/**
 * Helper function to get user from auth token in Edge Runtime
 * This is useful for API routes that receive Bearer tokens
 */
export async function getUserFromToken(
  token: string,
  supabaseUrl?: string,
  supabaseAnonKey?: string,
): Promise<{ user: any; error: any }> {
  const url = supabaseUrl || process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = supabaseAnonKey || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !key) {
    return { user: null, error: new Error("Missing Supabase configuration") };
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
  });

  // Get user from the token
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser(token);

  return { user, error };
}

/**
 * Helper to extract auth cookies from request in a Edge Runtime compatible way
 */
export function getAuthCookies(request: NextRequest): {
  accessToken?: string;
  refreshToken?: string;
} {
  const cookies = request.cookies;

  // Supabase stores tokens in cookies with specific names
  const accessToken =
    cookies.get("sb-access-token")?.value ||
    cookies.get("supabase-auth-token")?.value;
  const refreshToken = cookies.get("sb-refresh-token")?.value;

  return { accessToken, refreshToken };
}

/**
 * Simplified auth check for Edge Runtime
 * Returns true if user appears to be authenticated based on cookies
 */
export function hasAuthCookies(request: NextRequest): boolean {
  const { accessToken } = getAuthCookies(request);
  return !!accessToken;
}
