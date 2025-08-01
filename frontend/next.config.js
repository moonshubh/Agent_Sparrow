/** @type {import('next').NextConfig} */
const nextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  // Security headers configuration
  // Note: Runtime header toggling should be handled in middleware.ts for dynamic control
  async headers() {
    const isProduction = process.env.NODE_ENV === 'production'
    
    return [
      {
        // Apply security headers to all routes
        source: '/(.*)',
        headers: [
          {
            key: 'X-DNS-Prefetch-Control',
            value: 'on'
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY'
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff'
          },
          // Removed X-XSS-Protection as it's obsolete in modern browsers
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin'
          },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=(), payment=(), usb=()'
          },
          // Content Security Policy: Prevents XSS attacks by restricting resource sources
          // Production: Strict policy with minimal external sources
          // Development: Relaxed policy to support hot reload and dev tools
          {
            key: 'Content-Security-Policy',
            value: isProduction 
              ? "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; connect-src 'self' wss: ws: https:; font-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; upgrade-insecure-requests; report-uri /api/csp-report;"
              : "default-src 'self' 'unsafe-eval'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https: http:; connect-src 'self' ws: wss: http: https:; font-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self';"
          },
          // Only add HSTS in production
          ...(isProduction ? [{
            key: 'Strict-Transport-Security',
            value: 'max-age=31536000; includeSubDomains; preload'
          }] : []),
        ],
      },
    ]
  },
  // API rewrites to proxy backend requests
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'
    return [
      {
        source: '/api/v1/:path*',
        destination: `${backendUrl}/api/v1/:path*`,
      },
      {
        source: '/health',
        destination: `${backendUrl}/health`,
      },
    ]
  },
  // Additional security configuration
  // Note: crypto is a Node.js built-in and doesn't need external package config
  // Disable x-powered-by header for security
  poweredByHeader: false,
}

module.exports = nextConfig;