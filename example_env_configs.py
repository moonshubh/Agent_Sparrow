#!/usr/bin/env python3
"""
Example script showing how to configure different security modes
for MB-Sparrow applications.
"""

import os
from pathlib import Path

def show_configuration_examples():
    """Show examples of different environment configurations."""
    
    print("=== MB-Sparrow Security Configuration Examples ===\n")
    
    print("1. PRODUCTION CONFIGURATION (Recommended for production):")
    print("""
# Production environment variables (.env or system environment)
FORCE_PRODUCTION_SECURITY=true          # Force production security mode
ENABLE_AUTH_ENDPOINTS=true              # Enable authentication endpoints
ENABLE_API_KEY_ENDPOINTS=true           # Enable API key management
SKIP_AUTH=false                         # Require authentication
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key
INTERNAL_API_TOKEN=your-secure-token    # For internal service communication

# Result: All security features enabled, authentication required
""")
    
    print("2. DEVELOPMENT CONFIGURATION (For local development):")
    print("""
# Development environment variables
FORCE_PRODUCTION_SECURITY=false         # Allow development mode
ENABLE_AUTH_ENDPOINTS=false             # Disable auth endpoints for testing
ENABLE_API_KEY_ENDPOINTS=false          # Disable API key endpoints for testing
SKIP_AUTH=true                          # Bypass authentication
DEVELOPMENT_USER_ID=dev-user-12345      # Fallback user ID for development

# Result: Security endpoints disabled, authentication bypassed
""")
    
    print("3. TESTING CONFIGURATION (For automated tests):")
    print("""
# Testing environment variables
FORCE_PRODUCTION_SECURITY=false
ENABLE_AUTH_ENDPOINTS=false
ENABLE_API_KEY_ENDPOINTS=false
SKIP_AUTH=true
DEVELOPMENT_USER_ID=test-user-id

# Result: Minimal security for fast test execution
""")
    
    print("4. STAGING CONFIGURATION (Pre-production testing):")
    print("""
# Staging environment variables
ENVIRONMENT=production                   # Trigger production mode detection
ENABLE_AUTH_ENDPOINTS=true              # Test auth endpoints
ENABLE_API_KEY_ENDPOINTS=true           # Test API key management
SKIP_AUTH=false                         # Test authentication flows
SUPABASE_URL=https://staging-project.supabase.co

# Result: Production-like security with staging database
""")
    
    print("=== Environment Variable Reference ===\n")
    print("Security Control Variables:")
    print("- FORCE_PRODUCTION_SECURITY: Force production security mode (default: true)")
    print("- ENABLE_AUTH_ENDPOINTS: Enable authentication endpoints (default: true)")
    print("- ENABLE_API_KEY_ENDPOINTS: Enable API key management (default: true)")
    print("- SKIP_AUTH: Bypass authentication checks (default: false)")
    print()
    
    print("Production Mode Detection:")
    print("- ENVIRONMENT=production|prod")
    print("- DEPLOY_ENV=production|prod")
    print("- NODE_ENV=production")
    print("- STAGE=production|prod")
    print("- SUPABASE_URL containing 'supabase.co'")
    print()
    
    print("Security Behavior:")
    print("- Production mode ALWAYS enables auth and API key endpoints")
    print("- Development mode respects individual endpoint configuration")
    print("- Authentication can be bypassed in development with SKIP_AUTH=true")
    print("- Endpoint imports fail gracefully if dependencies are missing")
    print()
    
    print("=== Testing Your Configuration ===")
    print("1. Check security status: GET /security-status")
    print("2. Run: python test_security_config.py")
    print("3. Check application logs on startup for security configuration")
    print()

if __name__ == "__main__":
    show_configuration_examples()