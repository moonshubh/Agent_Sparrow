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
          {
            key: 'Content-Security-Policy',
            value: isProduction 
              ? "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://accounts.google.com https://apis.google.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data: blob: https:; connect-src 'self' wss: ws: https://*.supabase.co https://accounts.google.com https://api.github.com; font-src 'self' https://fonts.gstatic.com data:; frame-src https://accounts.google.com https://github.com https://*.supabase.co; object-src 'none'; base-uri 'self';"
              : "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://accounts.google.com https://apis.google.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data: blob: https:; connect-src 'self' wss: ws: http://localhost:8000 https://*.supabase.co https://accounts.google.com https://api.github.com; font-src 'self' https://fonts.gstatic.com data:; frame-src https://accounts.google.com https://github.com https://*.supabase.co; object-src 'none'; base-uri 'self';"
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
  // Additional security configuration
  // Note: crypto is a Node.js built-in and doesn't need external package config
  // Disable x-powered-by header for security
  poweredByHeader: false,
}

module.exports = nextConfig;