/**
 * FeedMe Authentication Helper
 * 
 * Provides JWT token generation and management for FeedMe WebSocket connections.
 * This is a simplified implementation for the integration demo.
 */

interface FeedMeUser {
  id: string
  email: string
  role: 'admin' | 'moderator' | 'viewer' | 'user'
  permissions: string[]
}

interface JWTPayload {
  sub: string // User ID
  email: string
  role: string
  permissions: string[]
  exp: number // Expiration timestamp
  iat: number // Issued at timestamp
}

class FeedMeAuth {
  private static instance: FeedMeAuth
  private currentUser: FeedMeUser | null = null
  private authToken: string | null = null

  private constructor() {
    // Load existing auth from localStorage on init
    this.loadAuthFromStorage()
  }

  static getInstance(): FeedMeAuth {
    if (!FeedMeAuth.instance) {
      FeedMeAuth.instance = new FeedMeAuth()
    }
    return FeedMeAuth.instance
  }

  /**
   * Generate a mock JWT token for WebSocket authentication
   * In production, this would be provided by your authentication service
   */
  generateMockToken(user: FeedMeUser): string {
    const now = Math.floor(Date.now() / 1000)
    const payload: JWTPayload = {
      sub: user.id,
      email: user.email,
      role: user.role,
      permissions: user.permissions,
      exp: now + (24 * 60 * 60), // 24 hours
      iat: now
    }

    // ⚠️  **SECURITY WARNING - INSECURE DEMO IMPLEMENTATION** ⚠️
    // This JWT creation code is INSECURE and must NEVER be used in production!
    // Real JWT tokens require proper signing with a secret key using libraries like 'jsonwebtoken'.
    // This demo implementation lacks cryptographic security and can be easily forged.
    // For production: Use a proper JWT library with HMAC SHA256 or RSA signing algorithms.
    const header = { typ: 'JWT', alg: 'HS256' }
    const headerB64 = btoa(JSON.stringify(header))
    const payloadB64 = btoa(JSON.stringify(payload))
    const signature = 'demo-signature' // In production, this would be properly signed

    return `${headerB64}.${payloadB64}.${signature}`
  }

  /**
   * Login with user credentials (simplified for demo)
   */
  login(userId: string, role: 'admin' | 'moderator' | 'viewer' | 'user' = 'user'): boolean {
    try {
      // Define role-based permissions
      const rolePermissions = {
        admin: [
          'processing:read', 'processing:write',
          'approval:read', 'approval:write', 'approval:admin',
          'analytics:read', 'system:monitor'
        ],
        moderator: [
          'processing:read',
          'approval:read', 'approval:write',
          'analytics:read'
        ],
        viewer: [
          'processing:read',
          'approval:read'
        ],
        user: [
          'processing:read'
        ]
      }

      const user: FeedMeUser = {
        id: userId,
        email: userId.includes('@') ? userId : `${userId}@mailbird.com`,
        role,
        permissions: rolePermissions[role]
      }

      this.currentUser = user
      this.authToken = this.generateMockToken(user)

      // Store in localStorage for persistence
      this.saveAuthToStorage()

      console.log(`✓ FeedMe Auth: Logged in as ${user.email} (${user.role})`)
      return true

    } catch (error) {
      console.error('FeedMe Auth: Login failed:', error)
      return false
    }
  }

  /**
   * Logout and clear authentication
   */
  logout(): void {
    this.currentUser = null
    this.authToken = null
    this.clearAuthFromStorage()
    console.log('✓ FeedMe Auth: Logged out')
  }

  /**
   * Get current authentication token
   */
  getToken(): string | null {
    // Check if token is expired
    if (this.authToken && this.isTokenExpired(this.authToken)) {
      console.warn('FeedMe Auth: Token expired, logging out')
      this.logout()
      return null
    }
    return this.authToken
  }

  /**
   * Get current user information
   */
  getCurrentUser(): FeedMeUser | null {
    return this.currentUser
  }

  /**
   * Check if user is authenticated
   */
  isAuthenticated(): boolean {
    return this.getToken() !== null
  }

  /**
   * Check if user has specific permission
   */
  hasPermission(permission: string): boolean {
    if (!this.currentUser) return false
    return this.currentUser.permissions.includes(permission)
  }

  /**
   * Get WebSocket URL with authentication token
   */
  getWebSocketUrl(baseUrl: string): string {
    const token = this.getToken()
    if (token) {
      const separator = baseUrl.includes('?') ? '&' : '?'
      return `${baseUrl}${separator}token=${encodeURIComponent(token)}`
    }
    return baseUrl
  }

  /**
   * Auto-login for demo purposes
   */
  autoLogin(): boolean {
    // Check if already authenticated
    if (this.isAuthenticated()) {
      return true
    }

    // For demo, auto-login as a test user
    const demoUserId = 'demo@mailbird.com'
    const demoRole = 'admin' // Use admin for full permissions in demo

    return this.login(demoUserId, demoRole)
  }

  /**
   * Private helper methods
   */
  private isTokenExpired(token: string): boolean {
    try {
      const parts = token.split('.')
      if (parts.length !== 3) return true

      const payload = JSON.parse(atob(parts[1])) as JWTPayload
      const now = Math.floor(Date.now() / 1000)
      return payload.exp <= now

    } catch (error) {
      console.error('FeedMe Auth: Error checking token expiration:', error)
      return true
    }
  }

  // ⚠️  **SECURITY WARNING - localStorage XSS Vulnerability** ⚠️
  // Storing authentication tokens in localStorage is vulnerable to Cross-Site Scripting (XSS) attacks.
  // Malicious scripts can access localStorage and steal tokens. Consider using:
  // - HttpOnly cookies for sensitive authentication data
  // - sessionStorage for temporary session data
  // - Secure, encrypted storage solutions for production applications
  private saveAuthToStorage(): void {
    try {
      if (typeof window !== 'undefined' && this.currentUser && this.authToken) {
        localStorage.setItem('feedme_user', JSON.stringify(this.currentUser))
        localStorage.setItem('feedme_auth_token', this.authToken)
      }
    } catch (error) {
      console.error('FeedMe Auth: Error saving to storage:', error)
    }
  }

  private loadAuthFromStorage(): void {
    try {
      if (typeof window !== 'undefined') {
        const storedUser = localStorage.getItem('feedme_user')
        const storedToken = localStorage.getItem('feedme_auth_token')

        if (storedUser && storedToken) {
          this.currentUser = JSON.parse(storedUser)
          this.authToken = storedToken

          // Verify token is still valid
          if (this.isTokenExpired(storedToken)) {
            this.logout()
          } else {
            console.log(`✓ FeedMe Auth: Restored session for ${this.currentUser?.email}`)
          }
        }
      }
    } catch (error) {
      console.error('FeedMe Auth: Error loading from storage:', error)
      this.clearAuthFromStorage()
    }
  }

  private clearAuthFromStorage(): void {
    try {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('feedme_user')
        localStorage.removeItem('feedme_auth_token')
      }
    } catch (error) {
      console.error('FeedMe Auth: Error clearing storage:', error)
    }
  }
}

// Export singleton instance
export const feedMeAuth = FeedMeAuth.getInstance()

// Export types for use in other modules
export type { FeedMeUser, JWTPayload }

// Export convenience functions
export const getCurrentUser = () => feedMeAuth.getCurrentUser()
export const getAuthToken = () => feedMeAuth.getToken()
export const isAuthenticated = () => feedMeAuth.isAuthenticated()
export const hasPermission = (permission: string) => feedMeAuth.hasPermission(permission)
export const login = (userId: string, role: 'admin' | 'moderator' | 'viewer' | 'user' = 'user') => feedMeAuth.login(userId, role)
export const logout = () => feedMeAuth.logout()
export const autoLogin = () => feedMeAuth.autoLogin()
export const getWebSocketUrl = (baseUrl: string) => feedMeAuth.getWebSocketUrl(baseUrl)