#!/usr/bin/env node

/**
 * Environment Check Script for Build Time
 * This runs during build to ensure environment variables are set
 */

console.log('\n🔍 Build-Time Environment Check\n');

const requiredVars = [
  'NEXT_PUBLIC_API_URL',
  'NODE_ENV'
];

console.log('Environment Variables at Build Time:');
requiredVars.forEach(varName => {
  const value = process.env[varName];
  if (value) {
    console.log(`✅ ${varName}: ${value}`);
  } else {
    console.log(`❌ ${varName}: NOT SET`);
  }
});

// Check if API URL is localhost in production
if (process.env.NODE_ENV === 'production' && 
    process.env.NEXT_PUBLIC_API_URL && 
    process.env.NEXT_PUBLIC_API_URL.includes('localhost')) {
  console.error('\n⚠️  WARNING: Production build is using localhost API URL!');
  console.error('This will cause connection errors in production.');
  process.exit(1);
}

// Check if API URL is missing in production
if (process.env.NODE_ENV === 'production' && !process.env.NEXT_PUBLIC_API_URL) {
  console.error('\n❌ ERROR: NEXT_PUBLIC_API_URL is required for production builds!');
  console.error('Set this in your Railway service variables before building.');
  process.exit(1);
}

console.log('\n✅ Build environment check passed!\n');