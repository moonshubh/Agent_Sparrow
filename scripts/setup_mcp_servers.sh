#!/bin/bash
# Setup Script for MCP Servers
# Required for NLWeb Integration - Step 1.2: Content Extraction & Transformation

set -e

echo "🚀 Setting up MCP Servers for MB-Sparrow Agent..."

# Check if npm/npx is available
if ! command -v npx &> /dev/null; then
    echo "❌ Error: npx is not installed. Please install Node.js and npm first."
    echo "   Visit: https://nodejs.org/"
    exit 1
fi

echo "✅ Found npx, proceeding with MCP server installation..."

# Install Firecrawl MCP Server (Primary server for Step 1.2)
echo "📦 Installing Firecrawl MCP Server..."
npx -y @modelcontextprotocol/server-firecrawl --help > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Firecrawl MCP Server is ready"
else
    echo "⚠️  Firecrawl MCP Server installation may need API key"
fi

# Install Brave Search MCP Server (Optional - for enhanced web search)
echo "📦 Installing Brave Search MCP Server..."
npx -y @modelcontextprotocol/server-brave-search --help > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Brave Search MCP Server is ready"
else
    echo "⚠️  Brave Search MCP Server installation may need API key"
fi

# Install Filesystem MCP Server (Utility server)
echo "📦 Installing Filesystem MCP Server..."
npx -y @modelcontextprotocol/server-filesystem --help > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Filesystem MCP Server is ready"
else
    echo "⚠️  Filesystem MCP Server installation may have issues"
fi

echo ""
echo "🎉 MCP Server setup completed!"
echo ""
echo "📋 Next Steps:"
echo "1. Set up your API keys in the environment:"
echo "   export FIRECRAWL_API_KEY='your_firecrawl_api_key'"
echo "   export BRAVE_SEARCH_API_KEY='your_brave_search_api_key'"
echo ""
echo "2. To get API keys:"
echo "   - Firecrawl: https://firecrawl.dev/"
echo "   - Brave Search: https://brave.com/search/api/"
echo ""
echo "3. Test the content extractor:"
echo "   python backend/tools/mailbird_content_extractor.py"
echo ""
echo "🔗 MCP Servers Documentation:"
echo "   https://github.com/modelcontextprotocol/servers" 