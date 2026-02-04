#!/usr/bin/env node

/**
 * Environment Variable Verification Script
 * Run this to check if environment variables are properly configured
 */

const chalk = require("chalk") || {
  red: (s) => s,
  green: (s) => s,
  yellow: (s) => s,
  blue: (s) => s,
};

console.log("\n🔍 Verifying Environment Variables...\n");

const requiredVars = {
  production: [
    "NEXT_PUBLIC_API_URL",
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    "NODE_ENV",
  ],
  development: [
    "NEXT_PUBLIC_API_URL",
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
  ],
};

const env = process.env.NODE_ENV || "development";
const isProduction = env === "production";

console.log(`📦 Environment: ${chalk.blue(env)}\n`);

// Check required variables
const required = requiredVars[isProduction ? "production" : "development"];
const missing = [];
const configured = [];

required.forEach((varName) => {
  if (process.env[varName]) {
    configured.push(varName);
    const value =
      varName.includes("KEY") || varName.includes("SECRET")
        ? "***" + process.env[varName].slice(-4)
        : process.env[varName];
    console.log(`✅ ${chalk.green(varName)}: ${value}`);
  } else {
    missing.push(varName);
    console.log(`❌ ${chalk.red(varName)}: NOT SET`);
  }
});

// Check API URL specifically
if (process.env.NEXT_PUBLIC_API_URL) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (isProduction && apiUrl.includes("localhost")) {
    console.log(
      `\n⚠️  ${chalk.yellow("WARNING")}: Production environment is using localhost API URL!`,
    );
    console.log(`   Current: ${apiUrl}`);
    console.log(`   Expected: https://your-backend-domain.com`);
  }
}

// Summary
console.log("\n📊 Summary:");
console.log(`   Configured: ${chalk.green(configured.length)} variables`);
console.log(`   Missing: ${chalk.red(missing.length)} variables`);

if (missing.length > 0) {
  console.log(`\n❗ Missing required environment variables:`);
  missing.forEach((v) => console.log(`   - ${v}`));

  if (isProduction) {
    console.log(
      `\n💡 For Railway deployment, set these in your service's Variables tab.`,
    );
  } else {
    console.log(
      `\n💡 For local development, copy .env.local.example to .env.local and update the values.`,
    );
  }

  process.exit(1);
} else {
  console.log(`\n✨ All required environment variables are configured!`);
  process.exit(0);
}
