/**
 * Secure Storage Utility
 * Provides encrypted storage for sensitive data with XSS protection
 */

import { STORAGE_CONFIG } from '@/shared/config/constants'
import { logger } from '@/shared/logging/logger'

// Storage types
export enum StorageType {
  LOCAL = 'local',
  SESSION = 'session',
  MEMORY = 'memory'
}

// Storage entry with metadata
interface StorageEntry<T = unknown> {
  data: T
  timestamp: number
  expiry?: number
  encrypted?: boolean
  checksum?: string
}

type MemoryStoreValue = StorageEntry<unknown> | { raw: string }

interface DOMPurifyModule {
  sanitize: (input: string, config?: Record<string, unknown>) => string
}

interface DOMPurifyWindow extends Window {
  DOMPurify?: DOMPurifyModule
}

const isRecord = (value: unknown): value is Record<string, unknown> => {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

// Encryption interface (can be implemented with Web Crypto API)
interface Encryptor {
  encrypt(data: string): Promise<string>
  decrypt(data: string): Promise<string>
}

// Web Crypto API based encryption (secure)
class WebCryptoEncryptor implements Encryptor {
  private key: CryptoKey | null = null
  private keyString: string

  constructor(keyString?: string) {
    this.keyString = keyString || this.generateKeyString()
    this.initializeKey()
  }

  private generateKeyString(): string {
    // Generate a secure random key
    if (typeof window !== 'undefined' && window.crypto) {
      const array = new Uint8Array(32)
      window.crypto.getRandomValues(array)
      return btoa(String.fromCharCode.apply(null, Array.from(array)))
    }
    // Fallback for SSR
    return btoa('fallback-key-' + Date.now())
  }

  private async initializeKey(): Promise<void> {
    if (typeof window === 'undefined' || !window.crypto || !window.crypto.subtle) {
      return
    }

    try {
      const encoder = new TextEncoder()
      const keyData = encoder.encode(this.keyString.substring(0, 32).padEnd(32, '0'))

      this.key = await crypto.subtle.importKey(
        'raw',
        keyData,
        { name: 'AES-GCM', length: 256 },
        false,
        ['encrypt', 'decrypt']
      )
    } catch (error) {
      logger.warn('Failed to initialize crypto key', { error })
    }
  }

  async encrypt(data: string): Promise<string> {
    // Wait for key initialization if needed
    if (!this.key && typeof window !== 'undefined') {
      await this.initializeKey()
    }

    if (this.key && typeof window !== 'undefined' && window.crypto && window.crypto.subtle) {
      try {
        const encoder = new TextEncoder()
        const dataBuffer = encoder.encode(data)

        // Generate a random IV for each encryption
        const iv = window.crypto.getRandomValues(new Uint8Array(12))

        const encryptedBuffer = await crypto.subtle.encrypt(
          { name: 'AES-GCM', iv },
          this.key,
          dataBuffer
        )

        // Combine IV and encrypted data
        const combined = new Uint8Array(iv.length + encryptedBuffer.byteLength)
        combined.set(iv)
        combined.set(new Uint8Array(encryptedBuffer), iv.length)

        return btoa(String.fromCharCode.apply(null, Array.from(combined)))
      } catch (error) {
        logger.warn('Encryption failed, using fallback', { error })
      }
    }

    // Fallback to base64 encoding only
    return btoa(encodeURIComponent(data))
  }

  async decrypt(data: string): Promise<string> {
    // Wait for key initialization if needed
    if (!this.key && typeof window !== 'undefined') {
      await this.initializeKey()
    }

    if (this.key && typeof window !== 'undefined' && window.crypto && window.crypto.subtle) {
      try {
        const combined = Uint8Array.from(atob(data), c => c.charCodeAt(0))

        // Extract IV and encrypted data
        const iv = combined.slice(0, 12)
        const encryptedData = combined.slice(12)

        const decryptedBuffer = await crypto.subtle.decrypt(
          { name: 'AES-GCM', iv },
          this.key,
          encryptedData
        )

        const decoder = new TextDecoder()
        return decoder.decode(decryptedBuffer)
      } catch (error) {
        logger.warn('Secure storage decrypt failed, attempting fallback', { error })
        // Try fallback decryption
        try {
          return decodeURIComponent(atob(data))
        } catch {
          throw new Error('Failed to decrypt data')
        }
      }
    }

    // Fallback to base64 decoding
    try {
      return decodeURIComponent(atob(data))
    } catch {
      throw new Error('Failed to decrypt data')
    }
  }
}

// Secure storage configuration
export interface SecureStorageConfig {
  type?: StorageType
  encrypt?: boolean
  encryptor?: Encryptor
  prefix?: string
  expiry?: number
  checkIntegrity?: boolean
  sanitize?: boolean
}

/**
 * Secure Storage Manager
 * Handles encrypted storage with XSS protection
 */
export class SecureStorage {
  private memoryStorage = new Map<string, MemoryStoreValue>()
  private encryptor: Encryptor
  private config: Required<SecureStorageConfig>

  constructor(config: SecureStorageConfig = {}) {
    this.config = {
      type: config.type ?? StorageType.SESSION,
      encrypt: config.encrypt ?? true,
      encryptor: config.encryptor ?? new WebCryptoEncryptor(),
      prefix: config.prefix ?? 'secure_',
      expiry: config.expiry ?? STORAGE_CONFIG.LIMITS.CACHE_EXPIRY,
      checkIntegrity: config.checkIntegrity ?? true,
      sanitize: config.sanitize ?? true
    }

    this.encryptor = this.config.encryptor

    // Clean up expired entries on initialization (async, don't block)
    void this.cleanup()
  }

  /**
   * Store data securely
   */
  async set<T>(key: string, value: T, options: { expiry?: number; encrypt?: boolean } = {}): Promise<void> {
    const fullKey = this.getFullKey(key)
    const encrypt = options.encrypt ?? this.config.encrypt

    // Sanitize value if needed
    const sanitized = this.config.sanitize ? this.sanitizeValue(value) : value

    // Create storage entry
    const entry: StorageEntry<T> = {
      data: sanitized as T,
      timestamp: Date.now(),
      expiry: options.expiry ?? this.config.expiry,
      encrypted: encrypt
    }

    // Add checksum for integrity
    if (this.config.checkIntegrity) {
      entry.checksum = await this.generateChecksum(JSON.stringify(sanitized))
    }

    // Serialize entry
    let serialized = JSON.stringify(entry)

    // Encrypt if needed
    if (encrypt) {
      try {
        serialized = await this.encryptor.encrypt(serialized)
      } catch (error) {
        logger.error('Encryption failed', { error, key })
        throw new Error('Failed to encrypt data')
      }
    }

    // Store based on type
    this.store(fullKey, serialized)

    logger.debug('Secure storage set', { key, encrypted: encrypt })
  }

  /**
   * Retrieve data securely
   */
  async get<T>(key: string): Promise<T | null> {
    const fullKey = this.getFullKey(key)
    const stored = this.retrieve(fullKey)

    if (!stored) {
      return null
    }

    try {
      // Parse entry
      let entry: StorageEntry<T>

      if (this.looksEncrypted(stored)) {
        // Decrypt if encrypted
        const decrypted = await this.encryptor.decrypt(stored)
        entry = JSON.parse(decrypted)
      } else {
        entry = JSON.parse(stored)
      }

      // Check expiry
      if (entry.expiry && Date.now() - entry.timestamp > entry.expiry) {
        this.remove(key)
        return null
      }

      // Verify integrity
      if (this.config.checkIntegrity && entry.checksum) {
        const checksum = await this.generateChecksum(JSON.stringify(entry.data))
        if (checksum !== entry.checksum) {
          logger.warn('Data integrity check failed', { key })
          this.remove(key)
          return null
        }
      }

      return entry.data
    } catch (error) {
      logger.error('Failed to retrieve secure data', { error, key })
      this.remove(key)
      return null
    }
  }

  /**
   * Remove data
   */
  remove(key: string): void {
    const fullKey = this.getFullKey(key)
    this.delete(fullKey)
  }

  /**
   * Clear all data
   */
  clear(): void {
    if (this.config.type === StorageType.MEMORY) {
      this.memoryStorage.clear()
    } else {
      const storage = this.getStorage()
      if (storage) {
        // Only clear our prefixed keys
        const keys = Object.keys(storage)
        keys.forEach(key => {
          if (key.startsWith(this.config.prefix)) {
            storage.removeItem(key)
          }
        })
      }
    }
  }

  /**
   * Check if key exists
   */
  async has(key: string): Promise<boolean> {
    const value = await this.get(key)
    return value !== null
  }

  /**
   * Get all keys
   */
  keys(): string[] {
    if (this.config.type === StorageType.MEMORY) {
      return Array.from(this.memoryStorage.keys())
        .map(k => k.replace(this.config.prefix, ''))
    }

    const storage = this.getStorage()
    if (!storage) return []

    return Object.keys(storage)
      .filter(k => k.startsWith(this.config.prefix))
      .map(k => k.replace(this.config.prefix, ''))
  }

  /**
   * Clean up expired entries
   */
  async cleanup(): Promise<void> {
    const keys = this.keys()
    let cleaned = 0

    for (const key of keys) {
      const value = await this.get(key)
      if (value === null) {
        cleaned++
      }
    }

    if (cleaned > 0) {
      logger.debug('Secure storage cleanup', { cleaned })
    }
  }

  // Private helper methods

  private getFullKey(key: string): string {
    return `${this.config.prefix}${key}`
  }

  private getStorage(): Storage | null {
    if (typeof window === 'undefined') return null

    switch (this.config.type) {
      case StorageType.LOCAL:
        return window.localStorage
      case StorageType.SESSION:
        return window.sessionStorage
      default:
        return null
    }
  }

  private store(key: string, value: string): void {
    if (this.config.type === StorageType.MEMORY) {
      // Store as string for consistency with other storage types
      this.memoryStorage.set(key, { raw: value })
    } else {
      const storage = this.getStorage()
      if (storage) {
        try {
          storage.setItem(key, value)
        } catch (error) {
          // Handle quota exceeded
          logger.warn('Storage quota exceeded', { error })
          // Run cleanup async to not block
          void this.cleanup()
          try {
            storage.setItem(key, value)
          } catch (retryError) {
            logger.error('Storage failed after cleanup', { error: retryError })
            throw retryError
          }
        }
      }
    }
  }

  private retrieve(key: string): string | null {
    if (this.config.type === StorageType.MEMORY) {
      const entry = this.memoryStorage.get(key)
      if (!entry) return null
      if (this.isRawMemoryEntry(entry)) {
        return entry.raw
      }
      return JSON.stringify(entry)
    }

    const storage = this.getStorage()
    return storage ? storage.getItem(key) : null
  }

  private delete(key: string): void {
    if (this.config.type === StorageType.MEMORY) {
      this.memoryStorage.delete(key)
    } else {
      const storage = this.getStorage()
      if (storage) {
        storage.removeItem(key)
      }
    }
  }

  private looksEncrypted(value: string): boolean {
    // Check if string looks like base64 encoded
    // More accurate check: base64 with proper padding and reasonable length
    try {
      if (!value || value.length < 20) return false
      // Check for base64 pattern
      if (!/^[A-Za-z0-9+/]*={0,2}$/.test(value)) return false
      // Try to decode and check if it looks like encrypted data
      const decoded = atob(value)
      // Encrypted data should have high entropy (many different byte values)
      const uniqueChars = new Set(decoded).size
      return uniqueChars > decoded.length * 0.6 // High entropy threshold
    } catch {
      return false
    }
  }

  private isRawMemoryEntry(entry: MemoryStoreValue): entry is { raw: string } {
    return Object.prototype.hasOwnProperty.call(entry, 'raw')
  }

  private async generateChecksum(data: string): Promise<string> {
    if (typeof window !== 'undefined' && window.crypto && window.crypto.subtle) {
      // Use Web Crypto API for checksum
      const encoder = new TextEncoder()
      const dataBuffer = encoder.encode(data)
      const hashBuffer = await crypto.subtle.digest('SHA-256', dataBuffer)
      const hashArray = Array.from(new Uint8Array(hashBuffer))
      return hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
    }

    // Fallback to simple checksum
    let checksum = 0
    for (let i = 0; i < data.length; i++) {
      checksum = ((checksum << 5) - checksum) + data.charCodeAt(i)
      checksum = checksum & checksum
    }
    return Math.abs(checksum).toString(36)
  }

  private sanitizeValue<T>(value: T): T {
    if (typeof value === 'string') {
      return this.sanitizeString(value) as unknown as T
    }

    if (Array.isArray(value)) {
      const sanitizedArray = value.map(item => this.sanitizeValue(item))
      return sanitizedArray as unknown as T
    }

    if (isRecord(value)) {
      const sanitizedEntries = Object.entries(value).map(([key, val]) => [
        this.sanitizeString(key),
        this.sanitizeValue(val),
      ])
      return Object.fromEntries(sanitizedEntries) as unknown as T
    }

    return value
  }

  private sanitizeString(str: string): string {
    if (typeof window !== 'undefined') {
      const domPurify = (window as DOMPurifyWindow).DOMPurify
      if (domPurify) {
        return domPurify.sanitize(str, { ALLOWED_TAGS: [] })
      }
    }

    // Enhanced XSS protection with more comprehensive patterns
    return str
      // Remove script tags and content
      .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
      // Remove javascript: protocol
      .replace(/javascript:/gi, '')
      // Remove all event handlers
      .replace(/on[a-z]+\s*=/gi, '')
      // Remove dangerous HTML tags
      .replace(/<(iframe|object|embed|applet|meta|link|style|base|form)\b[^>]*>/gi, '')
      // Remove src attributes with javascript:
      .replace(/src\s*=\s*["']?javascript:[^"'>]*/gi, '')
      // Remove href attributes with javascript:
      .replace(/href\s*=\s*["']?javascript:[^"'>]*/gi, '')
      // Remove data: URIs that could contain scripts
      .replace(/data:text\/html[^,]*,/gi, '')
      // Escape HTML entities
      .replace(/[<>"'&]/g, (char) => {
        const entities: Record<string, string> = {
          '<': '&lt;',
          '>': '&gt;',
          '"': '&quot;',
          "'": '&#39;',
          '&': '&amp;'
        }
        return entities[char] || char
      })
  }
}

// Create singleton instances for different storage types
export const secureLocalStorage = new SecureStorage({
  type: StorageType.LOCAL,
  encrypt: true
})

export const secureSessionStorage = new SecureStorage({
  type: StorageType.SESSION,
  encrypt: true
})

export const secureMemoryStorage = new SecureStorage({
  type: StorageType.MEMORY,
  encrypt: false // Memory storage doesn't need encryption
})

// React hook for secure storage
import { useCallback, useEffect, useState } from 'react'

export function useSecureStorage<T>(
  key: string,
  initialValue?: T,
  options: {
    storage?: SecureStorage
    expiry?: number
  } = {}
) {
  const storage = options.storage ?? secureSessionStorage
  const [value, setValue] = useState<T | undefined>(initialValue)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)

  // Load initial value
  useEffect(() => {
    const loadValue = async () => {
      try {
        const stored = await storage.get<T>(key)
        if (stored !== null) {
          setValue(stored)
        }
      } catch (err) {
        setError(err as Error)
        logger.error('Failed to load secure storage value', { error: err, key })
      } finally {
        setIsLoading(false)
      }
    }

    loadValue()
  }, [key, storage])

  // Set value
  const setStoredValue = useCallback(async (newValue: T) => {
    try {
      await storage.set(key, newValue, { expiry: options.expiry })
      setValue(newValue)
      setError(null)
    } catch (err) {
      setError(err as Error)
      logger.error('Failed to set secure storage value', { error: err, key })
    }
  }, [key, storage, options.expiry])

  // Remove value
  const removeValue = useCallback(() => {
    storage.remove(key)
    setValue(undefined)
    setError(null)
  }, [key, storage])

  return {
    value,
    setValue: setStoredValue,
    removeValue,
    isLoading,
    error
  }
}

// Export default
export default SecureStorage
