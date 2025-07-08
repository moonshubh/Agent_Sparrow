/**
 * Real-time Store - WebSocket Connection Management
 * 
 * Handles WebSocket connections with automatic reconnection, proper cleanup,
 * and exponential backoff for reliable real-time communication.
 */

import React from 'react'
import { create } from 'zustand'
import { devtools, subscribeWithSelector } from 'zustand/middleware'
import { feedMeAuth } from '@/lib/auth/feedme-auth'

// Configuration constants for notification timeouts
const NOTIFICATION_TIMEOUTS = {
  PROCESSING_UPDATE_REMOVAL: 10000, // 10 seconds for completed/failed processing updates
  INFO_NOTIFICATION_REMOVAL: 5000,  // 5 seconds for info notifications
} as const

// Types
export interface ProcessingUpdate {
  conversation_id: number
  status: 'pending' | 'processing' | 'completed' | 'failed'
  progress: number
  message?: string
  examples_extracted?: number
}

export interface Notification {
  id: string
  type: 'info' | 'success' | 'warning' | 'error'
  title: string
  message: string
  timestamp: string
  read: boolean
  actions?: NotificationAction[]
}

export interface NotificationAction {
  label: string
  action: () => void
  variant?: 'default' | 'destructive'
}

interface ReconnectionConfig {
  enabled: boolean
  maxAttempts: number
  baseDelay: number // milliseconds
  maxDelay: number // milliseconds
  backoffFactor: number
}

interface HeartbeatConfig {
  enabled: boolean
  interval: number // milliseconds
  timeout: number // milliseconds
}

export interface RealtimeState {
  // Connection State
  isConnected: boolean
  connectionStatus: 'connecting' | 'connected' | 'disconnected' | 'error' | 'reconnecting'
  lastUpdate: string | null
  
  // WebSocket Management
  websocket: WebSocket | null
  wsUrl: string | null
  
  // Reconnection State
  reconnection: {
    isReconnecting: boolean
    attempts: number
    nextRetryIn: number
    lastError: string | null
  }
  
  // Heartbeat State
  heartbeat: {
    isActive: boolean
    lastPing: string | null
    lastPong: string | null
    latency: number | null
  }
  
  // Data State
  processingUpdates: Record<number, ProcessingUpdate>
  notifications: Notification[]
  
  // Timers (tracked for cleanup)
  timers: {
    reconnectTimer: NodeJS.Timeout | null
    heartbeatTimer: NodeJS.Timeout | null
    heartbeatTimeout: NodeJS.Timeout | null
  }
}

interface RealtimeActions {
  // Connection Management
  connect: (url?: string) => Promise<void>
  disconnect: () => void
  reconnect: () => Promise<void>
  
  // Configuration
  updateReconnectionConfig: (config: Partial<ReconnectionConfig>) => void
  updateHeartbeatConfig: (config: Partial<HeartbeatConfig>) => void
  
  // Processing Updates
  handleProcessingUpdate: (update: ProcessingUpdate) => void
  clearProcessingUpdate: (conversationId: number) => void
  getProcessingStatus: (conversationId: number) => ProcessingUpdate | null
  
  // Notifications
  addNotification: (notification: Omit<Notification, 'id' | 'timestamp'>) => void
  markNotificationRead: (id: string) => void
  removeNotification: (id: string) => void
  clearNotifications: () => void
  
  // Internal Methods
  cleanup: () => void
  resetReconnectionState: () => void
  updateConnectionStatus: (status: RealtimeState['connectionStatus']) => void
}

export interface RealtimeStore extends RealtimeState {
  actions: RealtimeActions
}

// Default Configuration
const DEFAULT_RECONNECTION_CONFIG: ReconnectionConfig = {
  enabled: true,
  maxAttempts: 5,
  baseDelay: 1000,
  maxDelay: 30000,
  backoffFactor: 2
}

const DEFAULT_HEARTBEAT_CONFIG: HeartbeatConfig = {
  enabled: true,
  interval: 30000,
  timeout: 10000
}

// Store Implementation
export const useRealtimeStore = create<RealtimeStore>()(
  devtools(
    subscribeWithSelector((set, get) => ({
      // Initial State
      isConnected: false,
      connectionStatus: 'disconnected',
      lastUpdate: null,
      websocket: null,
      wsUrl: null,
      
      reconnection: {
        isReconnecting: false,
        attempts: 0,
        nextRetryIn: 0,
        lastError: null
      },
      
      heartbeat: {
        isActive: false,
        lastPing: null,
        lastPong: null,
        latency: null
      },
      
      processingUpdates: {},
      notifications: [],
      
      timers: {
        reconnectTimer: null,
        heartbeatTimer: null,
        heartbeatTimeout: null
      },
      
      actions: {
        // ===========================
        // Connection Management
        // ===========================
        
        connect: async (url?: string) => {
          const state = get()
          
          // Clean up existing connection
          if (state.websocket) {
            state.actions.disconnect()
          }
          
          // Determine WebSocket URL
          let wsUrl = url
          if (!wsUrl) {
            const baseUrl = process.env.NODE_ENV === 'development' 
              ? 'ws://localhost:8000' 
              : window.location.origin.replace('http', 'ws')
            wsUrl = `${baseUrl}/ws/feedme/global`
          }
          
          // Ensure authentication is initialized
          feedMeAuth.autoLogin()
          
          // Add authentication token
          const authUrl = feedMeAuth.getWebSocketUrl(wsUrl)
          
          set(state => ({
            connectionStatus: 'connecting',
            wsUrl: authUrl,
            reconnection: {
              ...state.reconnection,
              lastError: null
            }
          }))
          
          try {
            const ws = new WebSocket(authUrl)
            
            // Configure WebSocket event handlers
            ws.onopen = () => {
              console.log('✓ WebSocket connected')
              
              set(state => ({
                websocket: ws,
                isConnected: true,
                connectionStatus: 'connected',
                lastUpdate: new Date().toISOString(),
                reconnection: {
                  ...state.reconnection,
                  isReconnecting: false,
                  attempts: 0,
                  nextRetryIn: 0,
                  lastError: null
                }
              }))
              
              // Start heartbeat
              get().actions.startHeartbeat()
            }
            
            ws.onmessage = (event) => {
              try {
                const data = JSON.parse(event.data)
                get().actions.handleMessage(data)
                
                set({
                  lastUpdate: new Date().toISOString()
                })
              } catch (error) {
                console.error('Failed to parse WebSocket message:', error)
              }
            }
            
            ws.onerror = (error) => {
              console.error('WebSocket error:', error)
              
              set(state => ({
                connectionStatus: 'error',
                reconnection: {
                  ...state.reconnection,
                  lastError: 'Connection error occurred'
                }
              }))
            }
            
            ws.onclose = (event) => {
              console.log('WebSocket closed:', event.code, event.reason)
              
              set({
                websocket: null,
                isConnected: false,
                connectionStatus: 'disconnected',
                heartbeat: {
                  isActive: false,
                  lastPing: null,
                  lastPong: null,
                  latency: null
                }
              })
              
              // Clean up timers
              get().actions.cleanupTimers()
              
              // Attempt reconnection if not intentional disconnect
              // Exclude close codes that indicate intentional disconnection: 1000 (normal), 1001 (going away)
              const intentionalCloseCodes = [1000, 1001]
              if (!intentionalCloseCodes.includes(event.code) && DEFAULT_RECONNECTION_CONFIG.enabled) {
                get().actions.scheduleReconnection()
              }
            }
            
          } catch (error) {
            console.error('Failed to create WebSocket connection:', error)
            
            set(state => ({
              connectionStatus: 'error',
              reconnection: {
                ...state.reconnection,
                lastError: error instanceof Error ? error.message : 'Unknown connection error'
              }
            }))
            
            // Schedule reconnection
            if (DEFAULT_RECONNECTION_CONFIG.enabled) {
              get().actions.scheduleReconnection()
            }
          }
        },
        
        disconnect: () => {
          const state = get()
          
          if (state.websocket) {
            // Intentional disconnect - code 1000
            state.websocket.close(1000, 'User disconnected')
          }
          
          // Clean up all timers
          state.actions.cleanupTimers()
          
          set({
            websocket: null,
            isConnected: false,
            connectionStatus: 'disconnected',
            reconnection: {
              isReconnecting: false,
              attempts: 0,
              nextRetryIn: 0,
              lastError: null
            },
            heartbeat: {
              isActive: false,
              lastPing: null,
              lastPong: null,
              latency: null
            }
          })
        },
        
        reconnect: async () => {
          const state = get()
          
          // Reset reconnection state
          state.actions.resetReconnectionState()
          
          // Reconnect using last URL
          await state.actions.connect(state.wsUrl || undefined)
        },
        
        // ===========================
        // Configuration
        // ===========================
        
        updateReconnectionConfig: (config) => {
          Object.assign(DEFAULT_RECONNECTION_CONFIG, config)
        },
        
        updateHeartbeatConfig: (config) => {
          Object.assign(DEFAULT_HEARTBEAT_CONFIG, config)
          
          // Restart heartbeat with new config
          const state = get()
          if (state.isConnected && state.heartbeat.isActive) {
            state.actions.cleanupHeartbeat()
            state.actions.startHeartbeat()
          }
        },
        
        // ===========================
        // Processing Updates
        // ===========================
        
        handleProcessingUpdate: (update) => {
          set(state => ({
            processingUpdates: {
              ...state.processingUpdates,
              [update.conversation_id]: update
            }
          }))
          
          // Auto-remove completed/failed updates after delay
          if (update.status === 'completed' || update.status === 'failed') {
            setTimeout(() => {
              get().actions.clearProcessingUpdate(update.conversation_id)
            }, NOTIFICATION_TIMEOUTS.PROCESSING_UPDATE_REMOVAL)
          }
        },
        
        clearProcessingUpdate: (conversationId) => {
          set(state => {
            const updates = { ...state.processingUpdates }
            delete updates[conversationId]
            return { processingUpdates: updates }
          })
        },
        
        getProcessingStatus: (conversationId) => {
          return get().processingUpdates[conversationId] || null
        },
        
        // ===========================
        // Notifications
        // ===========================
        
        addNotification: (notification) => {
          const newNotification: Notification = {
            ...notification,
            id: `notification-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
            timestamp: new Date().toISOString()
          }
          
          set(state => ({
            notifications: [newNotification, ...state.notifications]
          }))
          
          // Auto-remove info notifications after configured delay
          if (notification.type === 'info') {
            setTimeout(() => {
              get().actions.markNotificationRead(newNotification.id)
            }, NOTIFICATION_TIMEOUTS.INFO_NOTIFICATION_REMOVAL)
          }
          
          return newNotification.id
        },
        
        markNotificationRead: (id) => {
          set(state => ({
            notifications: state.notifications.map(n => 
              n.id === id ? { ...n, read: true } : n
            )
          }))
        },
        
        removeNotification: (id) => {
          set(state => ({
            notifications: state.notifications.filter(n => n.id !== id)
          }))
        },
        
        clearNotifications: () => {
          set({ notifications: [] })
        },
        
        // ===========================
        // Internal Methods
        // ===========================
        
        cleanup: () => {
          const state = get()
          state.actions.disconnect()
        },
        
        resetReconnectionState: () => {
          set(state => ({
            reconnection: {
              ...state.reconnection,
              isReconnecting: false,
              attempts: 0,
              nextRetryIn: 0,
              lastError: null
            }
          }))
        },
        
        updateConnectionStatus: (status) => {
          set({ connectionStatus: status })
        },
        
        // ===========================
        // Private Methods (exposed for internal use)
        // ===========================
        
        startHeartbeat: () => {
          if (!DEFAULT_HEARTBEAT_CONFIG.enabled) return
          
          const heartbeatTimer = setInterval(() => {
            const state = get()
            if (state.websocket?.readyState === WebSocket.OPEN) {
              const pingTime = Date.now()
              state.websocket.send(JSON.stringify({ 
                type: 'ping',
                timestamp: pingTime
              }))
              
              set(state => ({
                heartbeat: {
                  ...state.heartbeat,
                  isActive: true,
                  lastPing: new Date(pingTime).toISOString()
                }
              }))
              
              // Set timeout for pong response
              const heartbeatTimeout = setTimeout(() => {
                console.warn('Heartbeat timeout - connection may be lost')
                // Don't force disconnect, let natural close handle it
              }, DEFAULT_HEARTBEAT_CONFIG.timeout)
              
              set(state => ({
                timers: {
                  ...state.timers,
                  heartbeatTimeout
                }
              }))
            }
          }, DEFAULT_HEARTBEAT_CONFIG.interval)
          
          set(state => ({
            timers: {
              ...state.timers,
              heartbeatTimer
            }
          }))
        },
        
        cleanupHeartbeat: () => {
          const state = get()
          
          if (state.timers.heartbeatTimer) {
            clearInterval(state.timers.heartbeatTimer)
          }
          
          if (state.timers.heartbeatTimeout) {
            clearTimeout(state.timers.heartbeatTimeout)
          }
          
          set(state => ({
            timers: {
              ...state.timers,
              heartbeatTimer: null,
              heartbeatTimeout: null
            },
            heartbeat: {
              ...state.heartbeat,
              isActive: false
            }
          }))
        },
        
        cleanupTimers: () => {
          const state = get()
          
          // Clear all timers
          if (state.timers.reconnectTimer) {
            clearTimeout(state.timers.reconnectTimer)
          }
          
          if (state.timers.heartbeatTimer) {
            clearInterval(state.timers.heartbeatTimer)
          }
          
          if (state.timers.heartbeatTimeout) {
            clearTimeout(state.timers.heartbeatTimeout)
          }
          
          set(state => ({
            timers: {
              reconnectTimer: null,
              heartbeatTimer: null,
              heartbeatTimeout: null
            }
          }))
        },
        
        scheduleReconnection: () => {
          const state = get()
          
          if (state.reconnection.attempts >= DEFAULT_RECONNECTION_CONFIG.maxAttempts) {
            console.error('Max reconnection attempts reached')
            
            set(state => ({
              connectionStatus: 'error',
              reconnection: {
                ...state.reconnection,
                isReconnecting: false,
                lastError: 'Max reconnection attempts exceeded'
              }
            }))
            
            // Add notification for user
            state.actions.addNotification({
              type: 'error',
              title: 'Connection Lost',
              message: 'Failed to reconnect after multiple attempts. Please refresh the page.',
              read: false,
              actions: [
                {
                  label: 'Retry',
                  action: () => get().actions.reconnect()
                },
                {
                  label: 'Refresh Page',
                  action: () => window.location.reload()
                }
              ]
            })
            
            return
          }
          
          // Calculate delay with exponential backoff
          const delay = Math.min(
            DEFAULT_RECONNECTION_CONFIG.baseDelay * 
            Math.pow(DEFAULT_RECONNECTION_CONFIG.backoffFactor, state.reconnection.attempts),
            DEFAULT_RECONNECTION_CONFIG.maxDelay
          )
          
          console.log(`Scheduling reconnection in ${delay}ms (attempt ${state.reconnection.attempts + 1}/${DEFAULT_RECONNECTION_CONFIG.maxAttempts})`)
          
          set(state => ({
            connectionStatus: 'reconnecting',
            reconnection: {
              ...state.reconnection,
              isReconnecting: true,
              nextRetryIn: delay
            }
          }))
          
          const reconnectTimer = setTimeout(() => {
            const currentState = get()
            
            set(state => ({
              reconnection: {
                ...state.reconnection,
                attempts: state.reconnection.attempts + 1
              }
            }))
            
            currentState.actions.connect(currentState.wsUrl || undefined)
          }, delay)
          
          set(state => ({
            timers: {
              ...state.timers,
              reconnectTimer
            }
          }))
        },
        
        handleMessage: (data: any) => {
          const state = get()
          
          switch (data.type) {
            case 'pong':
              // Handle heartbeat response
              const pongTime = Date.now()
              // Defensive check for timestamp - ensure it's a valid number
              const pingTime = (data.timestamp && typeof data.timestamp === 'number' && !isNaN(data.timestamp)) 
                ? data.timestamp 
                : pongTime // Use current time as fallback to avoid negative latency
              const latency = pongTime - pingTime
              
              // Clear heartbeat timeout
              if (state.timers.heartbeatTimeout) {
                clearTimeout(state.timers.heartbeatTimeout)
              }
              
              set(state => ({
                heartbeat: {
                  ...state.heartbeat,
                  lastPong: new Date(pongTime).toISOString(),
                  latency
                },
                timers: {
                  ...state.timers,
                  heartbeatTimeout: null
                }
              }))
              break
              
            case 'processing_update':
              if (data.conversation_id && data.status) {
                state.actions.handleProcessingUpdate(data as ProcessingUpdate)
              }
              break
              
            case 'folder_counts_update':
              // Update folder conversation counts
              if (data.folder_counts && typeof data.folder_counts === 'object') {
                // Import folders store dynamically to avoid circular dependency
                import('./folders-store').then(({ useFoldersStore }) => {
                  useFoldersStore.getState().actions.updateConversationCounts(data.folder_counts)
                }).catch(err => {
                  console.error('Failed to update folder counts:', err)
                })
              }
              break
              
            case 'notification':
              state.actions.addNotification({
                type: data.level || 'info',
                title: data.title || 'Notification',
                message: data.message || '',
                read: false
              })
              break
              
            default:
              console.log('Received unknown WebSocket message type:', data.type)
          }
        }
      }
    })),
    {
      name: 'feedme-realtime-store'
    }
  )
)

// Stable default state for SSR
const SSR_DEFAULT_STATE = {
  isConnected: false,
  connectionStatus: 'disconnected' as const,
  lastUpdate: null,
  processingUpdates: {},
  notifications: [],
  heartbeat: { isActive: false, lastPing: null, lastPong: null, latency: null },
  reconnection: { attempts: 0, isReconnecting: false, nextRetryIn: 0 }
}

// Convenience hooks with SSR safety - using individual selectors to avoid infinite loops
export const useRealtime = () => {
  // Only access store after client-side hydration
  const [isClient, setIsClient] = React.useState(false)
  
  React.useEffect(() => {
    setIsClient(true)
  }, [])
  
  // Individual selectors to avoid object creation on every render
  const isConnected = useRealtimeStore(state => state.isConnected)
  const connectionStatus = useRealtimeStore(state => state.connectionStatus)
  const lastUpdate = useRealtimeStore(state => state.lastUpdate)
  const processingUpdates = useRealtimeStore(state => state.processingUpdates)
  const notifications = useRealtimeStore(state => state.notifications)
  const heartbeat = useRealtimeStore(state => state.heartbeat)
  const reconnection = useRealtimeStore(state => state.reconnection)
  
  // Return stable default state during SSR
  if (!isClient) {
    return SSR_DEFAULT_STATE
  }
  
  // Return actual store values on client
  return {
    isConnected,
    connectionStatus,
    lastUpdate,
    processingUpdates,
    notifications,
    heartbeat,
    reconnection
  }
}

export const useRealtimeActions = () => useRealtimeStore(state => state.actions)

// Auto-cleanup on page unload
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    useRealtimeStore.getState().actions.cleanup()
  })
}