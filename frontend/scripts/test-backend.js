#!/usr/bin/env node

/**
 * Test Backend Connectivity
 * Run this to verify the backend URL is correct
 */

const https = require('https');
const http = require('http');

// Get the backend URL from command line or environment
const backendUrl = process.argv[2] || process.env.NEXT_PUBLIC_API_URL;

if (!backendUrl) {
  console.error('❌ Please provide a backend URL');
  console.log('Usage: node scripts/test-backend.js https://your-backend-url');
  process.exit(1);
}

console.log(`\n🔍 Testing backend connectivity to: ${backendUrl}\n`);

// Parse the URL
const url = new URL(backendUrl);
const protocol = url.protocol === 'https:' ? https : http;

// Test the health endpoint
const healthUrl = `${backendUrl}/health`;
console.log(`Testing: ${healthUrl}`);

protocol.get(healthUrl, (res) => {
  console.log(`Status: ${res.statusCode} ${res.statusMessage}`);
  
  let data = '';
  res.on('data', (chunk) => {
    data += chunk;
  });
  
  res.on('end', () => {
    if (res.statusCode === 200) {
      console.log('✅ Backend is healthy!');
      console.log('Response:', data);
      console.log('\n✨ Use this URL in Railway:');
      console.log(`NEXT_PUBLIC_API_URL=${backendUrl}`);
    } else {
      console.log('❌ Backend returned non-200 status');
      console.log('Response:', data);
    }
  });
}).on('error', (err) => {
  console.error('❌ Connection failed:', err.message);
  
  if (err.code === 'ECONNREFUSED') {
    console.log('\n💡 Possible issues:');
    console.log('1. Backend is not running');
    console.log('2. Wrong port (try adding :8080 or :8000)');
    console.log('3. Wrong domain');
  } else if (err.code === 'ENOTFOUND') {
    console.log('\n💡 Domain not found. Check the URL.');
  }
});

// Also test the API endpoint
setTimeout(() => {
  const apiUrl = `${backendUrl}/api/v1/rate-limits/status`;
  console.log(`\nTesting: ${apiUrl}`);
  
  protocol.get(apiUrl, (res) => {
    console.log(`Status: ${res.statusCode} ${res.statusMessage}`);
    if (res.statusCode === 200) {
      console.log('✅ API v1 endpoint is accessible');
    } else {
      console.log('⚠️  API v1 endpoint returned non-200 status');
    }
  }).on('error', (err) => {
    console.error('❌ API connection failed:', err.message);
  });
}, 1000);