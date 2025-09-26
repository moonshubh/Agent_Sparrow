import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { createEdgeClient, getUserFromToken, hasAuthCookies } from '@/lib/supabase-edge'

// Check if local auth bypass is enabled
const isLocalAuthBypass = process.env.NEXT_PUBLIC_LOCAL_AUTH_BYPASS === 'true'

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

  // Skip middleware for static files and health check
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/static') ||
    pathname.includes('.') ||
    pathname === '/api/health'
  ) {
    return NextResponse.next()
  }

  // In local auth bypass mode, check for local token
  if (isLocalAuthBypass) {
    if (!pathname.startsWith('/api')) {
      if (process.env.NODE_ENV === 'development') {
        console.log('Middleware - Local auth bypass mode, skipping auth checks for:', pathname)
      }
      return NextResponse.next()
    }
  }

  // Skip middleware for other API routes that don't need frontend middleware
  if (pathname.startsWith('/api') && !pathname.startsWith('/api/v1')) {
    return NextResponse.next()
  }

  // Check if route is public
  const isPublicRoute = publicRoutes.some(route => pathname.startsWith(route))
  const isAuthRoute = authRoutes.some(route => pathname.startsWith(route))

  // Create response object first
  let response = NextResponse.next({
    request: {
      headers: request.headers,
    },
  })

  // Create Edge Runtime compatible Supabase client
  const supabase = createEdgeClient(request, response)

  // Get the user session
  const { data: { user }, error } = await supabase.auth.getUser()

  const isAuthenticated = !!user && !error

  if (process.env.NODE_ENV === 'development') {
    console.log('Middleware - Path:', pathname, 'Auth:', isAuthenticated ? 'yes' : 'no')
  }

  // Handle authentication logic
  if (!isAuthenticated && !isPublicRoute) {
    const returnUrl = encodeURIComponent(pathname + request.nextUrl.search)
    const loginUrl = new URL('/login', request.url)
    loginUrl.searchParams.set('returnUrl', returnUrl)
    
    return NextResponse.redirect(loginUrl)
  }

  if (isAuthenticated && isAuthRoute) {
    // User is authenticated and trying to access auth routes
    return NextResponse.redirect(new URL('/', request.url))
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
