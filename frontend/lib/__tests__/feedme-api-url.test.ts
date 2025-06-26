/**
 * Regression tests for FeedMe API URL configuration
 * Ensures API base URL is properly configured without typeof window checks
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('FeedMe API URL Configuration', () => {
  const originalEnv = process.env.NEXT_PUBLIC_API_BASE

  beforeEach(() => {
    vi.clearAllMocks()
    // Clear module cache to get fresh imports
    vi.resetModules()
  })

  afterEach(() => {
    // Restore original env
    if (originalEnv !== undefined) {
      process.env.NEXT_PUBLIC_API_BASE = originalEnv
    } else {
      delete process.env.NEXT_PUBLIC_API_BASE
    }
  })

  it('should use environment variable when provided', async () => {
    process.env.NEXT_PUBLIC_API_BASE = 'https://api.example.com/v1'
    
    // Dynamic import to get fresh module with new env
    const { feedMeApi } = await import('../feedme-api')
    
    expect(feedMeApi).toBeDefined()
    // The client should be initialized with the env value + /feedme
    expect(feedMeApi['baseUrl']).toBe('https://api.example.com/v1/feedme')
  })

  it('should use default relative path when env variable not set', async () => {
    delete process.env.NEXT_PUBLIC_API_BASE
    
    // Dynamic import to get fresh module with no env var
    const { feedMeApi } = await import('../feedme-api')
    
    expect(feedMeApi).toBeDefined()
    // Should use default relative path + /feedme
    expect(feedMeApi['baseUrl']).toBe('/api/v1/feedme')
  })

  it('should not use typeof window checks for URL determination', async () => {
    // This test ensures we don't have SSR/CSR mismatches
    // Since we removed typeof window checks, the URL should be deterministic
    process.env.NEXT_PUBLIC_API_BASE = '/api/v1'
    
    const { feedMeApi } = await import('../feedme-api')
    
    // Should always use the same URL regardless of environment
    expect(feedMeApi['baseUrl']).toBe('/api/v1/feedme')
  })

  it('should have ApiUnreachableError available for import', async () => {
    const { ApiUnreachableError } = await import('../feedme-api')
    
    expect(ApiUnreachableError).toBeDefined()
    expect(typeof ApiUnreachableError).toBe('function')
    
    const error = new ApiUnreachableError('Test error')
    expect(error.name).toBe('ApiUnreachableError')
    expect(error.message).toBe('Test error')
  })
})