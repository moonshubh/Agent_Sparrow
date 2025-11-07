#!/usr/bin/env node

/**
 * Test Script for CopilotKit Infinite Loop Fixes
 *
 * This script helps verify that the infinite loop fixes are working correctly
 * by checking for common patterns that cause issues.
 */

const fs = require('fs');
const path = require('path');

const COPILOT_DIR = path.join(__dirname, 'src', 'app', 'chat', 'copilot');

const files = [
  'CopilotSidebarClient.tsx',
  'CopilotKnowledgeBridge.tsx',
  'CopilotSuggestionsBridge.tsx'
];

const PROBLEMATIC_PATTERNS = [
  {
    name: 'Callback in useEffect dependencies',
    pattern: /useEffect\([^)]*\[[^\]]*\b(on[A-Z]\w+|handle[A-Z]\w+|callback)\b[^\]]*\]/g,
    severity: 'error',
    fix: 'Store callback in useRef and remove from dependencies'
  },
  {
    name: 'setState in render phase',
    pattern: /^(?!.*useEffect).*set[A-Z]\w+\([^)]*\)/gm,
    severity: 'warning',
    fix: 'Move state updates into useEffect or event handlers'
  },
  {
    name: 'Missing dependency array',
    pattern: /useEffect\s*\([^)]+\)\s*(?![,\s]*\[)/g,
    severity: 'error',
    fix: 'Add dependency array to useEffect'
  },
  {
    name: 'Circular dependency pattern',
    pattern: /useEffect.*onDocumentsRegistered.*setDocumentPointers/gs,
    severity: 'error',
    fix: 'Use ref pattern to break circular dependency'
  }
];

const REQUIRED_PATTERNS = [
  {
    name: 'Callback ref pattern',
    pattern: /const\s+\w+Ref\s*=\s*useRef\s*\(\s*on[A-Z]\w+\s*\)/,
    description: 'Should use refs for callbacks to prevent recreating them'
  },
  {
    name: 'Stable bridge callbacks',
    pattern: /bridgeCallbacksRef\.current/,
    description: 'Should use stable callback references in bridge components'
  }
];

console.log('🔍 Checking for infinite loop patterns...\n');

let hasErrors = false;
let hasWarnings = false;

files.forEach(file => {
  const filePath = path.join(COPILOT_DIR, file);

  // Check if fixed version exists
  const fixedPath = filePath.replace('.tsx', 'Fixed.tsx');
  const hasFixed = fs.existsSync(fixedPath);

  if (!fs.existsSync(filePath)) {
    console.log(`⚠️  ${file}: File not found`);
    return;
  }

  const content = fs.readFileSync(filePath, 'utf8');

  console.log(`\n📄 ${file}${hasFixed ? ' (fixed version available)' : ''}`);
  console.log('─'.repeat(50));

  // Check for problematic patterns
  let fileHasIssues = false;

  PROBLEMATIC_PATTERNS.forEach(({ name, pattern, severity, fix }) => {
    const matches = content.match(pattern);
    if (matches) {
      fileHasIssues = true;
      const icon = severity === 'error' ? '❌' : '⚠️';
      console.log(`${icon} ${name}: Found ${matches.length} occurrence(s)`);
      console.log(`   Fix: ${fix}`);

      if (severity === 'error') hasErrors = true;
      if (severity === 'warning') hasWarnings = true;

      // Show first match for context
      if (matches[0].length < 100) {
        console.log(`   Example: ${matches[0].trim()}`);
      }
    }
  });

  // Check for required patterns (in fixed versions)
  if (hasFixed) {
    const fixedContent = fs.readFileSync(fixedPath, 'utf8');

    REQUIRED_PATTERNS.forEach(({ name, pattern, description }) => {
      if (!fixedContent.match(pattern)) {
        console.log(`⚠️  Fixed version missing: ${name}`);
        console.log(`   ${description}`);
      }
    });
  }

  if (!fileHasIssues) {
    console.log('✅ No problematic patterns detected');
  }
});

console.log('\n' + '='.repeat(50));
console.log('📊 Summary:');

if (hasErrors) {
  console.log('❌ Critical issues found that will cause infinite loops');
  console.log('\n🔧 To fix:');
  console.log('1. Apply the fixed versions:');
  files.forEach(file => {
    const fixedName = file.replace('.tsx', 'Fixed.tsx');
    console.log(`   cp ${fixedName} ${file}`);
  });
  process.exit(1);
} else if (hasWarnings) {
  console.log('⚠️  Potential issues found that might cause problems');
  console.log('   Review and apply fixes as needed');
} else {
  console.log('✅ No infinite loop patterns detected!');
  console.log('   Your components should work correctly');
}

console.log('\n💡 Next steps:');
console.log('1. Test in browser: npm run dev');
console.log('2. Check console for errors');
console.log('3. Monitor React DevTools for excessive re-renders');
console.log('4. Use Performance tab to check for memory leaks');