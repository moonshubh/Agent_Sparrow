#!/usr/bin/env node

/**
 * Test script to verify API timeout improvements
 * Run with: node test-api-improvements.js
 */

// Using native fetch (available in Node 18+)

console.log('🧪 Testing API Timeout Improvements\n');

async function testEndpoint(name, url, expectedTimeout) {
  console.log(`Testing ${name}...`);
  const startTime = Date.now();

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), expectedTimeout);

    const response = await fetch(url, {
      signal: controller.signal
    });

    clearTimeout(timeoutId);
    const duration = Date.now() - startTime;

    console.log(`  ✅ Success: ${response.status} in ${duration}ms`);
    return { success: true, duration, status: response.status };
  } catch (error) {
    const duration = Date.now() - startTime;
    const isTimeout = error.name === 'AbortError';

    if (isTimeout) {
      console.log(`  ⏱️ Timeout after ${duration}ms (expected: ${expectedTimeout}ms)`);
    } else {
      console.log(`  ❌ Error: ${error.message} after ${duration}ms`);
    }

    return { success: false, duration, error: error.message, isTimeout };
  }
}

async function runTests() {
  const baseUrl = 'http://localhost:8000/api/v1/feedme';

  // Test different endpoints with different timeout configurations
  const tests = [
    {
      name: 'List Conversations (Database query)',
      url: `${baseUrl}/conversations?page=1&page_size=20`,
      expectedTimeout: 45000 // Database operations get 45s
    },
    {
      name: 'Health Check (Quick operation)',
      url: `${baseUrl}/analytics`,
      expectedTimeout: 10000 // Quick operations get 10s
    },
    {
      name: 'Approval Stats (Database aggregation)',
      url: `${baseUrl}/approval/stats`,
      expectedTimeout: 45000 // Database operations get 45s
    },
    {
      name: 'List Folders (Database aggregation)',
      url: `${baseUrl}/folders`,
      expectedTimeout: 45000 // Database operations get 45s
    }
  ];

  const results = [];

  for (const test of tests) {
    const result = await testEndpoint(test.name, test.url, test.expectedTimeout);
    results.push({ ...test, ...result });
    console.log('');
  }

  // Summary
  console.log('📊 Summary:');
  console.log('─'.repeat(50));

  const successful = results.filter(r => r.success).length;
  const failed = results.filter(r => !r.success).length;
  const timeouts = results.filter(r => r.isTimeout).length;

  console.log(`Total tests: ${results.length}`);
  console.log(`Successful: ${successful}`);
  console.log(`Failed: ${failed}`);
  console.log(`Timeouts: ${timeouts}`);

  const avgDuration = results
    .filter(r => r.success)
    .reduce((sum, r) => sum + r.duration, 0) / successful || 0;

  if (successful > 0) {
    console.log(`Average response time: ${Math.round(avgDuration)}ms`);
  }

  // Performance insights
  console.log('\n💡 Performance Insights:');
  console.log('─'.repeat(50));

  results.forEach(result => {
    if (result.success && result.duration > result.expectedTimeout * 0.8) {
      console.log(`⚠️ ${result.name}: Approaching timeout threshold (${result.duration}ms / ${result.expectedTimeout}ms)`);
    }
  });

  console.log('\n✨ Features Being Tested:');
  console.log('─'.repeat(50));
  console.log('• Timeout behavior for different operation types');
  console.log('• Response time measurement');
  console.log('• Error handling and timeout detection');
  console.log('• Performance threshold warnings');
}

// Run tests
runTests().catch(console.error);