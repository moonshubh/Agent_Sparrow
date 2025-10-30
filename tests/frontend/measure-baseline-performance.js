#!/usr/bin/env node

/**
 * Baseline Performance Measurement Script
 *
 * Measures first-token latency and streaming throughput for Agent Sparrow
 * CopilotKit integration baseline (Phase 0).
 *
 * Usage:
 *   node tests/frontend/measure-baseline-performance.js [options]
 *
 * Options:
 *   --url <url>           API URL (default: http://localhost:8000)
 *   --endpoint <path>     Endpoint path (default: /api/v1/copilotkit)
 *   --iterations <n>      Number of test iterations (default: 10)
 *   --session-id <id>     Session ID to use (default: generated)
 *   --output <file>       Output results to JSON file
 *   --verbose             Show detailed output
 *
 * Metrics Captured:
 *   - First-token latency (time to first streaming response)
 *   - Streaming throughput (tokens/second)
 *   - Total response time
 *   - Response completeness
 *
 * Example:
 *   node tests/frontend/measure-baseline-performance.js --iterations 5 --verbose
 */

const https = require('https');
const http = require('http');
const { performance } = require('perf_hooks');
const fs = require('fs');
const path = require('path');

// Parse command-line arguments
function parseArgs() {
  const args = {
    url: 'http://localhost:8000',
    endpoint: '/api/v1/copilotkit',
    iterations: 10,
    sessionId: `perf-test-${Date.now()}`,
    output: null,
    verbose: false,
  };

  for (let i = 2; i < process.argv.length; i++) {
    const arg = process.argv[i];
    if (arg === '--url' && i + 1 < process.argv.length) {
      args.url = process.argv[++i];
    } else if (arg === '--endpoint' && i + 1 < process.argv.length) {
      args.endpoint = process.argv[++i];
    } else if (arg === '--iterations' && i + 1 < process.argv.length) {
      args.iterations = parseInt(process.argv[++i], 10);
    } else if (arg === '--session-id' && i + 1 < process.argv.length) {
      args.sessionId = process.argv[++i];
    } else if (arg === '--output' && i + 1 < process.argv.length) {
      args.output = process.argv[++i];
    } else if (arg === '--verbose') {
      args.verbose = true;
    }
  }

  return args;
}

// Make HTTP/HTTPS request with streaming support
function makeRequest(url, options, data) {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);
    const isHttps = urlObj.protocol === 'https:';
    const client = isHttps ? https : http;

    const requestOptions = {
      ...options,
      hostname: urlObj.hostname,
      port: urlObj.port || (isHttps ? 443 : 80),
      path: urlObj.pathname + urlObj.search,
    };

    const req = client.request(requestOptions, (res) => {
      const chunks = [];
      const timings = {
        start: performance.now(),
        firstChunk: null,
        lastChunk: null,
        chunkCount: 0,
        totalBytes: 0,
      };

      res.on('data', (chunk) => {
        if (timings.firstChunk === null) {
          timings.firstChunk = performance.now();
        }
        timings.lastChunk = performance.now();
        timings.chunkCount++;
        timings.totalBytes += chunk.length;
        chunks.push(chunk);
      });

      res.on('end', () => {
        const body = Buffer.concat(chunks).toString();
        resolve({
          statusCode: res.statusCode,
          headers: res.headers,
          body,
          timings,
        });
      });

      res.on('error', reject);
    });

    req.on('error', reject);

    if (data) {
      req.write(data);
    }

    req.end();
  });
}

// Measure performance for a single request
async function measureSingleRequest(args, iterationNum) {
  const testMessage = `Performance test message ${iterationNum}: Analyze this simple query.`;

  // GraphQL mutation for CopilotKit
  const graphqlQuery = {
    query: `
      mutation GenerateCopilotResponse(
        $data: GenerateCopilotResponseInput!
      ) {
        generateCopilotResponse(data: $data) {
          threadId
        }
      }
    `,
    variables: {
      data: {
        messages: [
          {
            role: 'user',
            content: testMessage,
          },
        ],
        properties: {
          session_id: args.sessionId,
          agent_type: 'primary',
          provider: 'google',
          model: 'gemini-2.5-flash-preview-09-2025',
        },
      },
    },
  };

  const requestBody = JSON.stringify(graphqlQuery);
  const fullUrl = `${args.url}${args.endpoint}`;

  const startTime = performance.now();

  try {
    const response = await makeRequest(fullUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(requestBody),
      },
    }, requestBody);

    const endTime = performance.now();
    const totalDuration = endTime - startTime;

    const firstTokenLatency = response.timings.firstChunk
      ? response.timings.firstChunk - response.timings.start
      : null;

    const streamingDuration = response.timings.lastChunk && response.timings.firstChunk
      ? response.timings.lastChunk - response.timings.firstChunk
      : 0;

    const streamingThroughput = streamingDuration > 0
      ? (response.timings.totalBytes / (streamingDuration / 1000))
      : 0;

    // Estimate tokens (rough approximation: 1 token ≈ 4 characters)
    const estimatedTokens = Math.ceil(response.timings.totalBytes / 4);
    const tokensPerSecond = streamingDuration > 0
      ? (estimatedTokens / (streamingDuration / 1000))
      : 0;

    return {
      iteration: iterationNum,
      success: response.statusCode === 200,
      statusCode: response.statusCode,
      totalDuration: Math.round(totalDuration),
      firstTokenLatency: firstTokenLatency ? Math.round(firstTokenLatency) : null,
      streamingDuration: Math.round(streamingDuration),
      chunkCount: response.timings.chunkCount,
      totalBytes: response.timings.totalBytes,
      streamingThroughput: Math.round(streamingThroughput),
      estimatedTokens,
      tokensPerSecond: Math.round(tokensPerSecond),
      timestamp: new Date().toISOString(),
    };
  } catch (error) {
    return {
      iteration: iterationNum,
      success: false,
      error: error.message,
      timestamp: new Date().toISOString(),
    };
  }
}

// Calculate statistics from measurements
function calculateStats(measurements) {
  const successful = measurements.filter(m => m.success);

  if (successful.length === 0) {
    return {
      totalIterations: measurements.length,
      successful: 0,
      failed: measurements.length,
      stats: null,
    };
  }

  const sortedByMetric = (metric) =>
    successful.map(m => m[metric]).filter(v => v !== null).sort((a, b) => a - b);

  const percentile = (arr, p) => {
    if (arr.length === 0) return null;
    const index = Math.ceil((p / 100) * arr.length) - 1;
    return arr[Math.max(0, index)];
  };

  const average = (arr) => arr.length > 0 ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;

  const firstTokens = sortedByMetric('firstTokenLatency');
  const totalDurations = sortedByMetric('totalDuration');
  const streamingDurations = sortedByMetric('streamingDuration');
  const tokensPerSecondArr = sortedByMetric('tokensPerSecond');

  return {
    totalIterations: measurements.length,
    successful: successful.length,
    failed: measurements.length - successful.length,
    stats: {
      firstTokenLatency: {
        p50: percentile(firstTokens, 50),
        p95: percentile(firstTokens, 95),
        p99: percentile(firstTokens, 99),
        avg: Math.round(average(firstTokens)),
        min: firstTokens[0] || null,
        max: firstTokens[firstTokens.length - 1] || null,
      },
      totalDuration: {
        p50: percentile(totalDurations, 50),
        p95: percentile(totalDurations, 95),
        p99: percentile(totalDurations, 99),
        avg: Math.round(average(totalDurations)),
        min: totalDurations[0] || null,
        max: totalDurations[totalDurations.length - 1] || null,
      },
      streamingDuration: {
        p50: percentile(streamingDurations, 50),
        p95: percentile(streamingDurations, 95),
        avg: Math.round(average(streamingDurations)),
      },
      tokensPerSecond: {
        p50: percentile(tokensPerSecondArr, 50),
        p95: percentile(tokensPerSecondArr, 95),
        avg: Math.round(average(tokensPerSecondArr)),
      },
    },
  };
}

// Main execution
async function main() {
  const args = parseArgs();

  console.log('='.repeat(70));
  console.log('Agent Sparrow - Baseline Performance Measurement (Phase 0)');
  console.log('='.repeat(70));
  console.log(`\nConfiguration:`);
  console.log(`  API URL:      ${args.url}`);
  console.log(`  Endpoint:     ${args.endpoint}`);
  console.log(`  Iterations:   ${args.iterations}`);
  console.log(`  Session ID:   ${args.sessionId}`);
  console.log(`  Output File:  ${args.output || 'None (console only)'}`);
  console.log();

  const measurements = [];

  for (let i = 1; i <= args.iterations; i++) {
    process.stdout.write(`Running iteration ${i}/${args.iterations}... `);

    const result = await measureSingleRequest(args, i);
    measurements.push(result);

    if (result.success) {
      process.stdout.write(`✓ (${result.firstTokenLatency}ms first token)\n`);
      if (args.verbose) {
        console.log(`  Details: ${result.totalDuration}ms total, ${result.estimatedTokens} tokens, ${result.tokensPerSecond} tokens/sec`);
      }
    } else {
      process.stdout.write(`✗ (${result.error})\n`);
    }

    // Small delay between iterations
    if (i < args.iterations) {
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }

  console.log();
  console.log('='.repeat(70));
  console.log('Results Summary');
  console.log('='.repeat(70));

  const stats = calculateStats(measurements);

  console.log(`\nTest Iterations: ${stats.totalIterations}`);
  console.log(`  Successful: ${stats.successful}`);
  console.log(`  Failed:     ${stats.failed}`);

  if (stats.stats) {
    console.log(`\nFirst-Token Latency (ms):`);
    console.log(`  p50 (median):  ${stats.stats.firstTokenLatency.p50}ms`);
    console.log(`  p95:           ${stats.stats.firstTokenLatency.p95}ms`);
    console.log(`  p99:           ${stats.stats.firstTokenLatency.p99}ms`);
    console.log(`  Average:       ${stats.stats.firstTokenLatency.avg}ms`);
    console.log(`  Range:         ${stats.stats.firstTokenLatency.min}ms - ${stats.stats.firstTokenLatency.max}ms`);

    console.log(`\nTotal Response Duration (ms):`);
    console.log(`  p50 (median):  ${stats.stats.totalDuration.p50}ms`);
    console.log(`  p95:           ${stats.stats.totalDuration.p95}ms`);
    console.log(`  Average:       ${stats.stats.totalDuration.avg}ms`);

    console.log(`\nStreaming Throughput:`);
    console.log(`  Tokens/sec (p50):  ${stats.stats.tokensPerSecond.p50}`);
    console.log(`  Tokens/sec (p95):  ${stats.stats.tokensPerSecond.p95}`);
    console.log(`  Tokens/sec (avg):  ${stats.stats.tokensPerSecond.avg}`);

    console.log(`\n${'='.repeat(70)}`);
    console.log('Baseline Thresholds (±10% regression acceptable)');
    console.log('='.repeat(70));
    console.log(`\nFirst-Token Latency Target:   < 1500ms (p95)`);
    console.log(`  Current p95: ${stats.stats.firstTokenLatency.p95}ms ${stats.stats.firstTokenLatency.p95 < 1500 ? '✓' : '✗'}`);
    console.log(`\nStreaming Delta Target:        < 100ms (p95)`);
    console.log(`  Current p95: ${stats.stats.streamingDuration.p95}ms ${stats.stats.streamingDuration.p95 < 100 ? '✓' : '✗'}`);
  } else {
    console.log('\n⚠️  No successful measurements. Check API connectivity.');
  }

  // Save to file if specified
  if (args.output) {
    const outputData = {
      metadata: {
        timestamp: new Date().toISOString(),
        config: args,
        phase: 'Phase 0 - Baseline',
      },
      measurements,
      stats,
    };

    const outputPath = path.resolve(args.output);
    fs.writeFileSync(outputPath, JSON.stringify(outputData, null, 2));
    console.log(`\n✓ Results saved to: ${outputPath}`);
  }

  console.log();
}

// Run if executed directly
if (require.main === module) {
  main().catch((error) => {
    console.error('\n❌ Error:', error.message);
    process.exit(1);
  });
}

module.exports = { measureSingleRequest, calculateStats };
