import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { createServerClient } from '@supabase/ssr'

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

  // Special handling for /api/chat - requires authentication
  if (pathname === '/api/chat') {
    const authHeader = request.headers.get('authorization')
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      if (process.env.NODE_ENV === 'development') {
        console.log('Middleware - /api/chat: No authorization header')
      }
      return new Response('Unauthorized: Authentication required', { status: 401 })
    }

    // Create a Supabase client to verify the token
    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
        cookies: {
          get(name: string) {
            return request.cookies.get(name)?.value
          },
          set() {},
          remove() {},
        },
      }
    )

    const token = authHeader.replace('Bearer ', '')
    const { data: { user }, error } = await supabase.auth.getUser(token)

    if (error || !user) {
      if (process.env.NODE_ENV === 'development') {
        console.log('Middleware - /api/chat: Invalid token')
      }
      return new Response('Unauthorized: Invalid authentication token', { status: 401 })
    }

    if (process.env.NODE_ENV === 'development') {
      console.log('Middleware - /api/chat: User authenticated')
    }
    // Continue with the request
    return NextResponse.next()
  }

  // Skip middleware for other API routes that don't need frontend middleware
  if (pathname.startsWith('/api') && !pathname.startsWith('/api/v1')) {
    return NextResponse.next()
  }

  // Check if route is public
  const isPublicRoute = publicRoutes.some(route => pathname.startsWith(route))
  const isAuthRoute = authRoutes.some(route => pathname.startsWith(route))

  // Create a Supabase client configured for server-side use
  let response = NextResponse.next({
    request: {
      headers: request.headers,
    },
  })

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        get(name: string) {
          return request.cookies.get(name)?.value
        },
        set(name: string, value: string, options: any) {
          response.cookies.set({
            name,
            value,
            ...options,
          })
        },
        remove(name: string, options: any) {
          response.cookies.set({
            name,
            value: '',
            ...options,
          })
        },
      },
    }
  )

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