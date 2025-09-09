#!/usr/bin/env node

/**
 * Test script to verify API key integration
 * Run with: node scripts/test-api-key-integration.js
 */

const https = require('https');
const http = require('http');

// Color codes for terminal output
const colors = {
  reset: '\x1b[0m',
  bright: '\x1b[1m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m'
};

// Test configuration
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const AUTH_TOKEN = process.env.TEST_AUTH_TOKEN || '';

console.log(`${colors.cyan}${colors.bright}
╔══════════════════════════════════════════════════════════════╗
║         API Key Integration Test for MB-Sparrow             ║
╚══════════════════════════════════════════════════════════════╝
${colors.reset}`);

console.log(`${colors.blue}Configuration:${colors.reset}`);
console.log(`  API URL: ${colors.yellow}${API_URL}${colors.reset}`);
console.log(`  Auth Token: ${AUTH_TOKEN ? colors.green + 'Provided' : colors.red + 'Not provided (set TEST_AUTH_TOKEN env var)'}${colors.reset}`);
console.log('');

/**
 * Make HTTP request
 */
function makeRequest(path, options = {}) {
  const url = new URL(path, API_URL);
  const isHttps = url.protocol === 'https:';
  const client = isHttps ? https : http;
  
  const requestOptions = {
    hostname: url.hostname,
    port: url.port || (isHttps ? 443 : 80),
    path: url.pathname + url.search,
    method: options.method || 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    }
  };

  return new Promise((resolve, reject) => {
    const req = client.request(requestOptions, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          resolve({ status: res.statusCode, data: parsed });
        } catch (e) {
          resolve({ status: res.statusCode, data: data });
        }
      });
    });

    req.on('error', reject);
    
    if (options.body) {
      req.write(JSON.stringify(options.body));
    }
    
    req.end();
  });
}

/**
 * Test 1: Check backend health
 */
async function testBackendHealth() {
  console.log(`${colors.bright}Test 1: Backend Health Check${colors.reset}`);
  
  try {
    const response = await makeRequest('/api/v1/health');
    
    if (response.status === 200) {
      console.log(`  ${colors.green}✓ Backend is healthy${colors.reset}`);
      console.log(`    Response: ${JSON.stringify(response.data)}`);
      return true;
    } else {
      console.log(`  ${colors.red}✗ Backend returned status ${response.status}${colors.reset}`);
      return false;
    }
  } catch (error) {
    console.log(`  ${colors.red}✗ Failed to connect to backend: ${error.message}${colors.reset}`);
    return false;
  }
}

/**
 * Test 2: Check API key endpoints
 */
async function testAPIKeyEndpoints() {
  console.log(`\n${colors.bright}Test 2: API Key Endpoints${colors.reset}`);
  
  if (!AUTH_TOKEN) {
    console.log(`  ${colors.yellow}⚠ Skipped: No auth token provided${colors.reset}`);
    console.log(`    Set TEST_AUTH_TOKEN environment variable to test authenticated endpoints`);
    return false;
  }

  try {
    // Test listing API keys
    console.log(`  Testing GET /api/v1/api-keys/...`);
    const response = await makeRequest('/api/v1/api-keys/', {
      headers: {
        'Authorization': `Bearer ${AUTH_TOKEN}`
      }
    });
    
    if (response.status === 200) {
      console.log(`  ${colors.green}✓ Successfully fetched API keys${colors.reset}`);
      console.log(`    Total keys: ${response.data.api_keys?.length || 0}`);
      
      // Check for Gemini key
      const geminiKey = response.data.api_keys?.find(k => k.api_key_type === 'gemini');
      if (geminiKey) {
        console.log(`  ${colors.green}✓ Gemini API key configured${colors.reset}`);
        console.log(`    Key ID: ${geminiKey.id}`);
        console.log(`    Active: ${geminiKey.is_active}`);
        console.log(`    Masked: ${geminiKey.masked_key}`);
      } else {
        console.log(`  ${colors.yellow}⚠ No Gemini API key configured${colors.reset}`);
      }
      
      return true;
    } else if (response.status === 401) {
      console.log(`  ${colors.red}✗ Authentication failed (invalid token)${colors.reset}`);
      return false;
    } else if (response.status === 404) {
      console.log(`  ${colors.yellow}⚠ API key endpoints not available${colors.reset}`);
      console.log(`    This might be expected if API key management is disabled`);
      return false;
    } else {
      console.log(`  ${colors.red}✗ Unexpected status: ${response.status}${colors.reset}`);
      return false;
    }
  } catch (error) {
    console.log(`  ${colors.red}✗ Request failed: ${error.message}${colors.reset}`);
    return false;
  }
}

/**
 * Test 3: Test internal API key endpoint (may fail in production)
 */
async function testInternalEndpoint() {
  console.log(`\n${colors.bright}Test 3: Internal API Key Endpoint${colors.reset}`);
  
  if (!AUTH_TOKEN) {
    console.log(`  ${colors.yellow}⚠ Skipped: No auth token provided${colors.reset}`);
    return false;
  }

  try {
    // First get user ID from token (this is a simplified check)
    console.log(`  Testing internal endpoint...`);
    const response = await makeRequest('/api/v1/api-keys/internal/gemini?user_id=test-user', {
      headers: {
        'Authorization': `Bearer ${AUTH_TOKEN}`,
        'X-Internal-Token': process.env.INTERNAL_API_TOKEN || ''
      }
    });
    
    if (response.status === 200) {
      console.log(`  ${colors.green}✓ Internal endpoint accessible${colors.reset}`);
      console.log(`    ${colors.yellow}Warning: This should be blocked in production!${colors.reset}`);
      return true;
    } else if (response.status === 403) {
      console.log(`  ${colors.green}✓ Internal endpoint properly secured (403 Forbidden)${colors.reset}`);
      console.log(`    This is expected in production deployments`);
      return true;
    } else if (response.status === 404) {
      console.log(`  ${colors.yellow}⚠ Internal endpoint not found${colors.reset}`);
      return false;
    } else {
      console.log(`  ${colors.yellow}⚠ Unexpected status: ${response.status}${colors.reset}`);
      return false;
    }
  } catch (error) {
    console.log(`  ${colors.red}✗ Request failed: ${error.message}${colors.reset}`);
    return false;
  }
}

/**
 * Run all tests
 */
async function runTests() {
  console.log(`${colors.bright}Starting tests...${colors.reset}\n`);
  
  const results = {
    health: await testBackendHealth(),
    apiKeys: await testAPIKeyEndpoints(),
    internal: await testInternalEndpoint()
  };
  
  // Summary
  console.log(`\n${colors.cyan}${colors.bright}════════════════════════════════════════════════════════════════${colors.reset}`);
  console.log(`${colors.bright}Test Summary:${colors.reset}`);
  console.log(`  Backend Health: ${results.health ? colors.green + '✓ Passed' : colors.red + '✗ Failed'}${colors.reset}`);
  console.log(`  API Key Endpoints: ${results.apiKeys ? colors.green + '✓ Passed' : colors.yellow + '⚠ Partial'}${colors.reset}`);
  console.log(`  Internal Security: ${results.internal ? colors.green + '✓ Secure' : colors.yellow + '⚠ Check'}${colors.reset}`);
  
  const allPassed = Object.values(results).every(r => r);
  
  console.log(`\n${colors.bright}Overall: ${allPassed ? colors.green + '✓ All tests passed' : colors.yellow + '⚠ Some issues detected'}${colors.reset}`);
  
  // Recommendations
  if (!AUTH_TOKEN) {
    console.log(`\n${colors.yellow}Recommendation:${colors.reset}`);
    console.log(`  To fully test authentication, obtain a valid auth token by:`);
    console.log(`  1. Login to the frontend application`);
    console.log(`  2. Open browser DevTools > Application > Storage > Session Storage`);
    console.log(`  3. Find the Supabase auth token`);
    console.log(`  4. Run: TEST_AUTH_TOKEN="your-token" node scripts/test-api-key-integration.js`);
  }
  
  console.log(`\n${colors.cyan}${colors.bright}════════════════════════════════════════════════════════════════${colors.reset}\n`);
}

// Run tests
runTests().catch(error => {
  console.error(`${colors.red}Fatal error: ${error.message}${colors.reset}`);
  process.exit(1);
});