#!/bin/bash

# Enable Local Authentication Bypass for Already Running System
# Run this script to configure environment variables for local auth

echo "🔐 Enabling Local Authentication Bypass"
echo "⚠️  This is for development only - DO NOT USE IN PRODUCTION"
echo ""

# Create .env file for backend if it doesn't exist
cat > .env << EOF
# Local Development Authentication Bypass
SKIP_AUTH=true
DEVELOPMENT_USER_ID=dev-user-123
FORCE_PRODUCTION_SECURITY=false
ENABLE_LOCAL_AUTH_BYPASS=true
GEMINI_API_KEY=AIzaSyBHfa0Qkm3xohVtX6zhXEIrUSPxJYaxZm0
FEEDME_ENABLED=true
FEEDME_AI_PDF_ENABLED=true
JWT_SECRET_KEY=local-development-secret-key-for-testing-only
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440
API_KEY_ENCRYPTION_SECRET=local-dev-encryption-key-32chars
EOF

echo "✅ Created .env file with local auth configuration"

# Create/update frontend .env.local
cat > frontend/.env.local << EOF
# Frontend Local Development Configuration
NEXT_PUBLIC_LOCAL_AUTH_BYPASS=true
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
EOF

echo "✅ Created frontend/.env.local with local auth configuration"
echo ""
echo "🔄 Please restart your services for changes to take effect:"
echo ""
echo "1. Stop the backend server (Ctrl+C in the terminal running uvicorn)"
echo "2. Restart it with: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "3. Stop the frontend (Ctrl+C in the terminal running npm)"
echo "4. Restart it with: cd frontend && npm run dev"
echo ""
echo "Or use the provided commands below:"
echo ""
echo "Backend restart command:"
echo "  cd /Users/shubhpatel/Downloads/Agent_Sparrow-Frontend-2.0"
echo "  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "Frontend restart command:"
echo "  cd /Users/shubhpatel/Downloads/Agent_Sparrow-Frontend-2.0/frontend"
echo "  npm run dev"
echo ""
echo "📍 After restart, access the application at: http://localhost:3000"
echo "🔐 Local Auth Credentials:"
echo "   Email: dev@localhost.com"
echo "   Password: dev"