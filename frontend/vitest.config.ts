/**
 * Vitest Configuration for FeedMe v2.0 Phase 3 Testing
 * 
 * Comprehensive test configuration supporting React components, TypeScript, 
 * and enterprise-grade testing requirements with 95%+ coverage targets.
 */

import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    css: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      reportsDirectory: './coverage',
      exclude: [
        'node_modules/',
        'vitest.setup.ts',
        '**/*.d.ts',
        '**/*.config.*',
        'dist/',
        '.next/',
        'coverage/',
        '**/__tests__/**',
        '**/*.test.*',
        '**/*.spec.*',
      ],
      thresholds: {
        global: {
          branches: 95,
          functions: 95,
          lines: 95,
          statements: 95,
        },
        // Specific thresholds for critical components
        'components/feedme/': {
          branches: 98,
          functions: 98,
          lines: 98,
          statements: 98,
        },
      },
      include: [
        'components/**/*.{ts,tsx}',
        'lib/**/*.{ts,tsx}',
        'hooks/**/*.{ts,tsx}',
        'utils/**/*.{ts,tsx}',
      ],
    },
    // Performance settings for large test suites
    testTimeout: 10000,
    hookTimeout: 10000,
    teardownTimeout: 5000,
    // Parallel execution for faster test runs
    pool: 'threads',
    poolOptions: {
      threads: {
        singleThread: false,
        maxThreads: 4,
        minThreads: 1,
      },
    },
    // Test file patterns
    include: [
      '**/__tests__/**/*.{test,spec}.{js,ts,jsx,tsx}',
      '**/*.{test,spec}.{js,ts,jsx,tsx}',
    ],
    exclude: [
      'node_modules/',
      'dist/',
      '.next/',
      'coverage/',
      'e2e/',
    ],
    // Watch mode settings
    watch: false,
    // Reporter configuration
    reporter: ['verbose', 'junit'],
    outputFile: {
      junit: './test-results/junit.xml',
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './'),
      '@/components': path.resolve(__dirname, './components'),
      '@/lib': path.resolve(__dirname, './lib'),
      '@/hooks': path.resolve(__dirname, './hooks'),
      '@/utils': path.resolve(__dirname, './utils'),
    },
  },
  esbuild: {
    target: 'es2020',
  },
})
