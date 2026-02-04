const path = require("path");

const katexCssStub = path.join(__dirname, "src/styles/katex-stub.css");

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Note: eslint config moved to eslint.config.js (Next.js 16+ requirement)
  typescript: {
    ignoreBuildErrors: true,
  },
  // Empty turbopack config to acknowledge Turbopack is the default bundler in Next.js 16
  // The webpack config below is used for the katex CSS alias (Turbopack doesn't support false aliases)
  turbopack: {},
  // Webpack config for katex CSS alias - prevents bundling since we load via CDN
  webpack(config) {
    config.resolve = config.resolve || {};
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      "katex/dist/katex.min.css": katexCssStub,
    };
    return config;
  },
  env: {
    GEMINI_API_KEY: process.env.GEMINI_API_KEY,
    GOOGLE_GENERATIVE_AI_API_KEY: process.env.GOOGLE_GENERATIVE_AI_API_KEY,
    OPENAI_API_KEY: process.env.OPENAI_API_KEY,
  },
  // Security headers configuration
  // Note: Runtime header toggling should be handled in middleware.ts for dynamic control
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
      // Proxy WebSocket connections
      {
        source: "/ws/:path*",
        destination: `${apiUrl}/ws/:path*`,
      },
    ];
  },
  async headers() {
    const isProduction = process.env.NODE_ENV === "production";
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const connectSrcBase = [
      "'self'",
      "wss:",
      "ws:",
      apiUrl,
      "http://127.0.0.1:8000",
      "https://*.supabase.co",
      "https://accounts.google.com",
      "https://api.github.com",
    ];
    const connectSrcProdExtra = [
      "https://agentsparrow-production.up.railway.app",
      "https://*.railway.app",
    ];

    const connectSrcDev = connectSrcBase.join(" ");
    const connectSrcProd = connectSrcBase.concat(connectSrcProdExtra).join(" ");

    return [
      {
        // Apply security headers to all routes
        source: "/(.*)",
        headers: [
          {
            key: "X-DNS-Prefetch-Control",
            value: "on",
          },
          {
            key: "X-Frame-Options",
            value: "DENY",
          },
          {
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
          {
            key: "X-XSS-Protection",
            value: "1; mode=block",
          },
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
          {
            key: "Permissions-Policy",
            value:
              "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
          },
          {
            key: "Content-Security-Policy",
            value: `default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://accounts.google.com https://apis.google.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; img-src 'self' data: blob: https:; connect-src ${isProduction ? connectSrcProd : connectSrcDev}; font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net data:; frame-src https://accounts.google.com https://github.com https://*.supabase.co; worker-src 'self' blob:; object-src 'none'; base-uri 'self';`,
          },
          // Only add HSTS in production
          ...(isProduction
            ? [
                {
                  key: "Strict-Transport-Security",
                  value: "max-age=31536000; includeSubDomains; preload",
                },
              ]
            : []),
        ],
      },
    ];
  },
  // Additional security configuration
  // Note: crypto is a Node.js built-in and doesn't need external package config
  // Disable x-powered-by header for security
  poweredByHeader: false,
};

module.exports = nextConfig;
