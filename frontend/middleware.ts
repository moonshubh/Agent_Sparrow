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

  // Skip middleware for static files and certain API routes
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/static') ||
    pathname.includes('.') ||
    pathname === '/api/health' ||
    (pathname.startsWith('/api') && !pathname.startsWith('/api/v1'))
  ) {
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

  console.log('Middleware - Path:', pathname, 'User:', user?.email || 'none', 'Error:', error?.message)

  const isAuthenticated = !!user && !error

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