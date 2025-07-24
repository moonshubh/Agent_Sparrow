import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { createClient } from '@supabase/supabase-js'

// List of public routes that don't require authentication
const publicRoutes = [
  '/login',
  '/auth/callback',
  '/api/health'
]

// List of auth routes that should redirect to home if already authenticated
const authRoutes = ['/login']

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Skip middleware for static files and API routes (except our auth endpoints)
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/static') ||
    pathname.includes('.') ||
    (pathname.startsWith('/api') && !pathname.startsWith('/api/v1'))
  ) {
    return NextResponse.next()
  }

  // Check if auth bypass is enabled for development
  const bypassAuth = process.env.NEXT_PUBLIC_BYPASS_AUTH === 'true'
  const devMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true'
  
  if (bypassAuth && devMode) {
    console.log('🚀 Auth middleware bypassed for development')
    return NextResponse.next()
  }

  // Check if route is public
  const isPublicRoute = publicRoutes.some(route => pathname.startsWith(route))
  const isAuthRoute = authRoutes.some(route => pathname.startsWith(route))

  // Get Supabase client for server-side auth check
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

  // If Supabase is not configured, allow all routes (development mode)
  if (!supabaseUrl || !supabaseAnonKey) {
    console.warn('Supabase not configured, skipping auth middleware')
    return NextResponse.next()
  }

  // Create a Supabase client with the request cookies
  const supabase = createClient(supabaseUrl, supabaseAnonKey, {
    auth: {
      persistSession: false
    }
  })

  // Get the session from cookies
  const refreshToken = request.cookies.get('sb-refresh-token')?.value
  const accessToken = request.cookies.get('sb-access-token')?.value

  let isAuthenticated = false

  if (refreshToken && accessToken) {
    try {
      // Set the session from cookies
      const { data: { user } } = await supabase.auth.setSession({
        access_token: accessToken,
        refresh_token: refreshToken
      })
      isAuthenticated = !!user
    } catch (error) {
      console.error('Error validating session:', error)
    }
  }

  // Handle authentication logic
  if (!isAuthenticated && !isPublicRoute) {
    // User is not authenticated and trying to access a protected route
    const returnUrl = encodeURIComponent(pathname)
    const loginUrl = new URL('/login', request.url)
    loginUrl.searchParams.set('returnUrl', returnUrl)
    return NextResponse.redirect(loginUrl)
  }

  if (isAuthenticated && isAuthRoute) {
    // User is authenticated and trying to access auth routes
    const homeUrl = new URL('/', request.url)
    return NextResponse.redirect(homeUrl)
  }

  // For authenticated requests, we could add the user info to headers
  // This helps with server-side rendering
  const response = NextResponse.next()
  
  if (isAuthenticated && accessToken) {
    // Add auth headers for server components
    response.headers.set('x-user-authenticated', 'true')
  }

  return response
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public folder
     */
    '/((?!_next/static|_next/image|favicon.ico|.*\\..*|public).*)',
  ],
}