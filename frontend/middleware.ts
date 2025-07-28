import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { createClient } from '@supabase/supabase-js'

// Helper function to safely extract project reference
function getProjectReference(): string {
  try {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
    if (!supabaseUrl) return 'default'
    
    const url = new URL(supabaseUrl)
    const hostname = url.hostname
    const projectRef = hostname.split('.')[0]
    
    // Validate project reference format (alphanumeric + hyphens)
    if (!/^[a-zA-Z0-9-]+$/.test(projectRef)) {
      console.warn('Invalid project reference format, using default')
      return 'default'
    }
    
    return projectRef
  } catch (error) {
    console.warn('Failed to parse Supabase URL, using default project reference:', error)
    return 'default'
  }
}

// Security configuration
const SECURITY_CONFIG = {
  // Rate limiting configuration - adjusted for better production patterns
  RATE_LIMIT_WINDOW_MS: 5 * 60 * 1000, // 5 minutes (shorter window)
  MAX_REQUESTS_PER_WINDOW: 50, // Reduced from 100
  BRUTE_FORCE_WINDOW_MS: 30 * 60 * 1000, // 30 minutes (longer for brute force)
  MAX_FAILED_ATTEMPTS: 3, // Reduced from 5
  
  // Cleanup configuration
  CLEANUP_INTERVAL_MS: 60 * 1000, // 1 minute
  MAX_ENTRIES_BEFORE_CLEANUP: 1000, // Trigger cleanup when entries exceed this
  
  // Cookie configuration
  COOKIE_CONFIG: {
    ACCESS_TOKEN: process.env.SUPABASE_ACCESS_TOKEN_COOKIE || 'sb-access-token',
    REFRESH_TOKEN: process.env.SUPABASE_REFRESH_TOKEN_COOKIE || 'sb-refresh-token',
    PROJECT_REF: getProjectReference()
  },
  
  // Security headers - strengthened CSP
  SECURITY_HEADERS: {
    'X-Frame-Options': 'DENY',
    'X-Content-Type-Options': 'nosniff',
    'X-XSS-Protection': '1; mode=block',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
    // Development-friendly CSP - allow inline scripts and eval for dev tools
    'Content-Security-Policy': process.env.NODE_ENV === 'development' 
      ? "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data: blob: https:; connect-src 'self' wss: ws: https: http://localhost:*; font-src 'self' data: https://fonts.gstatic.com; object-src 'none'; base-uri 'self';"
      : "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self' wss:; font-src 'self'; object-src 'none'; base-uri 'self';"
  },
  
  // Cache control headers for error responses
  NO_CACHE_HEADERS: {
    'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
    'Pragma': 'no-cache',
    'Expires': '0'
  }
}

// List of public routes that don't require authentication
const publicRoutes = [
  '/login',
  '/auth/callback',
  '/api/health'
]

// List of auth routes that should redirect to home if already authenticated
const authRoutes = ['/login']

// API routes that require CSRF protection
const csrfProtectedRoutes = [
  '/api/v1/feedme',
  '/api/v1/chat',
  '/api/v1/upload'
]

// Enhanced in-memory stores with periodic cleanup
// TODO: Replace with Redis in production for multi-instance deployments
interface RateLimitEntry {
  count: number
  windowStart: number
  lastAccess: number
}

const requestCounts = new Map<string, RateLimitEntry>()
const failedAttempts = new Map<string, RateLimitEntry>()
let lastCleanup = Date.now()

// Periodic cleanup function to prevent memory leaks
function performPeriodicCleanup(): void {
  const now = Date.now()
  
  // Only run cleanup if enough time has passed or if we have too many entries
  const shouldCleanup = 
    (now - lastCleanup > SECURITY_CONFIG.CLEANUP_INTERVAL_MS) ||
    (requestCounts.size > SECURITY_CONFIG.MAX_ENTRIES_BEFORE_CLEANUP) ||
    (failedAttempts.size > SECURITY_CONFIG.MAX_ENTRIES_BEFORE_CLEANUP)
  
  if (!shouldCleanup) return
  
  const rateLimitThreshold = now - SECURITY_CONFIG.RATE_LIMIT_WINDOW_MS
  const bruteForceThreshold = now - SECURITY_CONFIG.BRUTE_FORCE_WINDOW_MS
  
  // Clean up expired rate limit entries
  let cleanedCount = 0
  for (const [key, value] of requestCounts.entries()) {
    if (value.windowStart < rateLimitThreshold) {
      requestCounts.delete(key)
      cleanedCount++
    }
  }
  
  // Clean up expired brute force entries
  for (const [key, value] of failedAttempts.entries()) {
    if (value.windowStart < bruteForceThreshold) {
      failedAttempts.delete(key)
      cleanedCount++
    }
  }
  
  lastCleanup = now
  
  if (cleanedCount > 0) {
    console.log(`Cleaned up ${cleanedCount} expired security entries`)
  }
}

// Utility functions for security
function isValidIPv4(ip: string): boolean {
  const ipv4Regex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/
  return ipv4Regex.test(ip)
}

function isValidIPv6(ip: string): boolean {
  const ipv6Regex = /^(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$|^::1$|^::$/
  return ipv6Regex.test(ip)
}

function sanitizeIP(ip: string): string | null {
  if (!ip || typeof ip !== 'string') return null
  
  const trimmed = ip.trim()
  if (isValidIPv4(trimmed) || isValidIPv6(trimmed)) {
    return trimmed
  }
  
  return null
}

function getClientIP(request: NextRequest): string {
  // Priority order for IP extraction (most trusted first)
  const ipSources = [
    // 1. Direct connection IP (most trusted)
    request.ip,
    
    // 2. Trusted proxy headers (validate these in production)
    request.headers.get('CF-Connecting-IP'), // Cloudflare
    request.headers.get('X-Real-IP'),
    
    // 3. Standard forwarded headers (least trusted, can be spoofed)
    request.headers.get('X-Forwarded-For')?.split(',')[0]?.trim(),
  ]
  
  // Find the first valid IP
  for (const ip of ipSources) {
    if (ip) {
      const sanitized = sanitizeIP(ip)
      if (sanitized) {
        return sanitized
      }
    }
  }
  
  // Fallback for development or when IP cannot be determined
  return process.env.NODE_ENV === 'development' ? '127.0.0.1' : 'unknown'
}

function generateCSRFToken(): string {
  // Use Web Crypto API for Edge Runtime compatibility
  const array = new Uint8Array(32)
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    crypto.getRandomValues(array)
  } else {
    // Fallback for environments without Web Crypto API
    for (let i = 0; i < array.length; i++) {
      array[i] = Math.floor(Math.random() * 256)
    }
  }
  return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('')
}

function isRateLimited(ip: string, windowMs: number, maxRequests: number): boolean {
  const now = Date.now()
  const windowStart = now - windowMs
  
  // Perform periodic cleanup instead of per-request cleanup
  performPeriodicCleanup()
  
  const current = requestCounts.get(ip)
  if (!current || current.windowStart < windowStart) {
    requestCounts.set(ip, { count: 1, windowStart: now, lastAccess: now })
    return false
  }
  
  current.count++
  current.lastAccess = now
  return current.count > maxRequests
}

function isBruteForceBlocked(ip: string): boolean {
  const now = Date.now()
  const windowStart = now - SECURITY_CONFIG.BRUTE_FORCE_WINDOW_MS
  
  const attempts = failedAttempts.get(ip)
  if (!attempts || attempts.windowStart < windowStart) {
    return false
  }
  
  return attempts.count >= SECURITY_CONFIG.MAX_FAILED_ATTEMPTS
}

function recordFailedAttempt(ip: string): void {
  const now = Date.now()
  const windowStart = now - SECURITY_CONFIG.BRUTE_FORCE_WINDOW_MS
  
  const current = failedAttempts.get(ip)
  if (!current || current.windowStart < windowStart) {
    failedAttempts.set(ip, { count: 1, windowStart: now, lastAccess: now })
  } else {
    current.count++
    current.lastAccess = now
  }
}

function clearFailedAttempts(ip: string): void {
  failedAttempts.delete(ip)
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl
  const clientIP = getClientIP(request)
  
  // Create response with security headers
  let response = NextResponse.next()
  
  // Apply security headers to all responses
  Object.entries(SECURITY_CONFIG.SECURITY_HEADERS).forEach(([key, value]) => {
    response.headers.set(key, value)
  })

  // Skip middleware for static files and certain API routes
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/static') ||
    pathname.includes('.') ||
    pathname === '/api/health' || // Explicitly allow health check
    (pathname.startsWith('/api') && !pathname.startsWith('/api/v1'))
  ) {
    return response
  }

  // Check if auth bypass is enabled for development (server-side only)
  const bypassAuth = process.env.BYPASS_AUTH === 'true'
  const devMode = process.env.NODE_ENV === 'development'
  
  if (bypassAuth && devMode) {
    console.log('🚀 Auth middleware bypassed for development')
    // Still apply security headers in development
    return response
  }
  
  // Rate limiting check
  if (isRateLimited(clientIP, SECURITY_CONFIG.RATE_LIMIT_WINDOW_MS, SECURITY_CONFIG.MAX_REQUESTS_PER_WINDOW)) {
    console.warn(`Rate limit exceeded for IP: ${clientIP}`)
    return new NextResponse('Too Many Requests', { 
      status: 429,
      headers: {
        'Retry-After': Math.ceil(SECURITY_CONFIG.RATE_LIMIT_WINDOW_MS / 1000).toString(),
        ...Object.fromEntries(Object.entries(SECURITY_CONFIG.SECURITY_HEADERS)),
        ...Object.fromEntries(Object.entries(SECURITY_CONFIG.NO_CACHE_HEADERS))
      }
    })
  }
  
  // Brute force protection check
  if (isBruteForceBlocked(clientIP)) {
    console.warn(`Brute force protection triggered for IP: ${clientIP}`)
    return new NextResponse('Temporarily Blocked', { 
      status: 429,
      headers: {
        'Retry-After': Math.ceil(SECURITY_CONFIG.BRUTE_FORCE_WINDOW_MS / 1000).toString(),
        ...Object.fromEntries(Object.entries(SECURITY_CONFIG.SECURITY_HEADERS)),
        ...Object.fromEntries(Object.entries(SECURITY_CONFIG.NO_CACHE_HEADERS))
      }
    })
  }

  // CSRF Protection for state-changing requests
  const requiresCSRF = csrfProtectedRoutes.some(route => pathname.startsWith(route))
  if (requiresCSRF && ['POST', 'PUT', 'DELETE', 'PATCH'].includes(request.method)) {
    const csrfToken = request.headers.get('X-CSRF-Token')
    const sessionCSRF = request.cookies.get('csrf-token')?.value
    
    if (!csrfToken || !sessionCSRF || csrfToken !== sessionCSRF) {
      console.warn(`CSRF token validation failed for ${pathname} from IP: ${clientIP}`)
      recordFailedAttempt(clientIP)
      return new NextResponse('CSRF Token Invalid', { 
        status: 403,
        headers: {
          ...Object.fromEntries(Object.entries(SECURITY_CONFIG.SECURITY_HEADERS)),
          ...Object.fromEntries(Object.entries(SECURITY_CONFIG.NO_CACHE_HEADERS))
        }
      })
    }
  }

  // Check if route is public
  const isPublicRoute = publicRoutes.some(route => pathname.startsWith(route))
  const isAuthRoute = authRoutes.some(route => pathname.startsWith(route))

  // Get Supabase client for server-side auth check
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

  // If Supabase is not configured, only allow in development mode
  if (!supabaseUrl || !supabaseAnonKey) {
    if (devMode) {
      console.warn('Supabase not configured, skipping auth middleware in development')
      return response
    } else {
      console.error('Supabase configuration missing in production')
      return new NextResponse('Service Unavailable', { 
        status: 503,
        headers: Object.fromEntries(Object.entries(SECURITY_CONFIG.SECURITY_HEADERS))
      })
    }
  }

  // Create a Supabase client with the request cookies
  const supabase = createClient(supabaseUrl, supabaseAnonKey, {
    auth: {
      persistSession: false,
      autoRefreshToken: false, // Handle refresh manually for security
    }
  })

  // Get the session from cookies using configurable names
  const cookieName = `${SECURITY_CONFIG.COOKIE_CONFIG.ACCESS_TOKEN}-${SECURITY_CONFIG.COOKIE_CONFIG.PROJECT_REF}`
  const refreshCookieName = `${SECURITY_CONFIG.COOKIE_CONFIG.REFRESH_TOKEN}-${SECURITY_CONFIG.COOKIE_CONFIG.PROJECT_REF}`
  
  const refreshToken = request.cookies.get(refreshCookieName)?.value || request.cookies.get('sb-refresh-token')?.value
  const accessToken = request.cookies.get(cookieName)?.value || request.cookies.get('sb-access-token')?.value

  let isAuthenticated = false
  let user = null
  let sessionError = null

  if (refreshToken && accessToken) {
    try {
      // Set the session from cookies
      const { data: { user: sessionUser }, error } = await supabase.auth.setSession({
        access_token: accessToken,
        refresh_token: refreshToken
      })
      
      if (error) {
        sessionError = error
        console.warn('Session validation error:', error.message)
        
        // If token is expired, try to refresh
        if (error.message.includes('expired') || error.message.includes('invalid')) {
          try {
            const { data: refreshData, error: refreshError } = await supabase.auth.refreshSession({
              refresh_token: refreshToken
            })
            
            if (refreshError) {
              // Handle different types of refresh errors with granular logging
              if (refreshError.message.includes('network') || refreshError.message.includes('fetch')) {
                console.warn(`Network error during token refresh for IP ${clientIP}:`, refreshError.message)
                // Don't record failed attempt for network errors
              } else if (refreshError.message.includes('invalid_grant') || refreshError.message.includes('refresh_token')) {
                console.warn(`Invalid refresh token for IP ${clientIP}:`, refreshError.message)
                recordFailedAttempt(clientIP)
                // Clear potentially corrupted tokens
                response.cookies.delete(cookieName)
                response.cookies.delete(refreshCookieName)
              } else if (refreshError.message.includes('unauthorized') || refreshError.message.includes('forbidden')) {
                console.warn(`Unauthorized refresh attempt for IP ${clientIP}:`, refreshError.message)
                recordFailedAttempt(clientIP)
              } else {
                console.warn(`Unknown token refresh error for IP ${clientIP}:`, refreshError.message)
                recordFailedAttempt(clientIP)
              }
            } else if (refreshData.user) {
              user = refreshData.user
              isAuthenticated = true
              clearFailedAttempts(clientIP)
              
              console.log(`Successful token refresh for IP ${clientIP}`)
              
              // Update response with new tokens
              response = NextResponse.next()
              Object.entries(SECURITY_CONFIG.SECURITY_HEADERS).forEach(([key, value]) => {
                response.headers.set(key, value)
              })
              
              if (refreshData.session) {
                response.cookies.set(cookieName, refreshData.session.access_token, {
                  httpOnly: true,
                  secure: process.env.NODE_ENV === 'production',
                  sameSite: 'lax',
                  maxAge: 60 * 60 // 1 hour
                })
                response.cookies.set(refreshCookieName, refreshData.session.refresh_token, {
                  httpOnly: true,
                  secure: process.env.NODE_ENV === 'production',
                  sameSite: 'lax',
                  maxAge: 60 * 60 * 24 * 7 // 1 week
                })
              }
            } else {
              console.warn(`Token refresh returned no user data for IP ${clientIP}`)
              recordFailedAttempt(clientIP)
            }
          } catch (refreshError) {
            // Enhanced error handling for different exception types
            if (refreshError instanceof TypeError && refreshError.message.includes('fetch')) {
              console.error(`Network connectivity error during token refresh for IP ${clientIP}:`, refreshError.message)
              // Don't record failed attempt for network issues
            } else if (refreshError instanceof Error) {
              if (refreshError.message.includes('timeout')) {
                console.error(`Timeout error during token refresh for IP ${clientIP}:`, refreshError.message)
                // Don't record failed attempt for timeouts
              } else if (refreshError.message.includes('abort')) {
                console.error(`Request aborted during token refresh for IP ${clientIP}:`, refreshError.message)
                // Don't record failed attempt for aborted requests
              } else {
                console.error(`Unexpected error during token refresh for IP ${clientIP}:`, refreshError.message)
                recordFailedAttempt(clientIP)
              }
            } else {
              console.error(`Unknown error type during token refresh for IP ${clientIP}:`, refreshError)
              recordFailedAttempt(clientIP)
            }
          }
        }
      } else {
        user = sessionUser
        isAuthenticated = !!sessionUser
        clearFailedAttempts(clientIP)
      }
    } catch (error) {
      console.error('Error validating session:', error)
      sessionError = error
      recordFailedAttempt(clientIP)
    }
  }

  // Handle authentication logic
  if (!isAuthenticated && !isPublicRoute) {
    // Clear potentially corrupted auth cookies
    const redirectResponse = NextResponse.redirect(new URL('/login', request.url))
    Object.entries(SECURITY_CONFIG.SECURITY_HEADERS).forEach(([key, value]) => {
      redirectResponse.headers.set(key, value)
    })
    
    // Clear auth cookies on failed authentication
    redirectResponse.cookies.delete(cookieName)
    redirectResponse.cookies.delete(refreshCookieName)
    redirectResponse.cookies.delete('sb-access-token')
    redirectResponse.cookies.delete('sb-refresh-token')
    
    const returnUrl = encodeURIComponent(pathname + request.nextUrl.search)
    const loginUrl = new URL('/login', request.url)
    loginUrl.searchParams.set('returnUrl', returnUrl)
    
    return NextResponse.redirect(loginUrl)
  }

  if (isAuthenticated && isAuthRoute) {
    // User is authenticated and trying to access auth routes
    const homeUrl = new URL('/', request.url)
    const redirectResponse = NextResponse.redirect(homeUrl)
    Object.entries(SECURITY_CONFIG.SECURITY_HEADERS).forEach(([key, value]) => {
      redirectResponse.headers.set(key, value)
    })
    return redirectResponse
  }

  // Generate CSRF token for new sessions
  if (isAuthenticated && !request.cookies.get('csrf-token')) {
    const csrfToken = generateCSRFToken()
    response.cookies.set('csrf-token', csrfToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'strict',
      maxAge: 60 * 60 * 24 // 24 hours
    })
    response.headers.set('X-CSRF-Token', csrfToken)
  }
  
  // Add user context headers for server components
  if (isAuthenticated && user) {
    response.headers.set('x-user-authenticated', 'true')
    response.headers.set('x-user-id', user.id)
    response.headers.set('x-user-email', user.email || '')
    
    // Add user role if available in user metadata
    if (user.user_metadata?.role) {
      response.headers.set('x-user-role', user.user_metadata.role)
    }
  }
  
  // Add security context headers
  response.headers.set('x-client-ip', clientIP)
  response.headers.set('x-request-id', 
    typeof crypto !== 'undefined' && crypto.randomUUID 
      ? crypto.randomUUID() 
      : generateCSRFToken().slice(0, 36) // Fallback UUID-like format
  )

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