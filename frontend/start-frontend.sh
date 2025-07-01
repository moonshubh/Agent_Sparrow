#!/bin/bash

echo "🚀 Starting MB-Sparrow Frontend..."
echo "================================="
echo ""

# Check Node.js version
echo "📦 Environment:"
echo "  Node.js: $(node --version)"
echo "  npm: $(npm --version)"
echo "  Directory: $(pwd)"
echo ""

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "❌ node_modules not found. Installing dependencies..."
    npm install --legacy-peer-deps
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install dependencies"
        exit 1
    fi
    echo "✅ Dependencies installed successfully"
    echo ""
fi

# Kill any existing process on port 3000
echo "🔍 Checking port 3000..."
lsof -ti:3000 2>/dev/null | xargs kill -9 2>/dev/null && echo "✅ Cleared existing process on port 3000" || echo "✅ Port 3000 is available"
echo ""

# Set environment
export NODE_ENV=development

# Start the development server
echo "🎯 Starting Next.js development server..."
echo "▶️  Server will be available at:"
echo "   - Local:   http://localhost:3000"
echo "   - Network: http://$(ipconfig getifaddr en0 2>/dev/null || echo 'your-ip'):3000"
echo ""
echo "📝 Logs:"
echo "--------------------------------"
npm run dev