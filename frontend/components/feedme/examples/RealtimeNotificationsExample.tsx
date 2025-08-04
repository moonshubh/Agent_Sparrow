/**
 * Example: Real-time Notifications using Modular Stores
 * 
 * Demonstrates WebSocket integration with proper cleanup and reconnection.
 */

'use client'

import React, { useEffect } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Bell, Wifi, WifiOff, RefreshCw, CheckCircle } from 'lucide-react'

// Import specific realtime hooks - NO legacy imports
import { 
  useRealtime,
  useRealtimeActions,
  type ProcessingUpdate
} from '@/lib/stores/realtime-store'
import { useStoreSync } from '@/lib/stores/store-composition'

export function RealtimeNotificationsExample() {
  const { 
    isConnected, 
    connectionStatus, 
    processingUpdates, 
    notifications,
    heartbeat,
    reconnection
  } = useRealtime()
  const realtimeActions = useRealtimeActions()

  // Enable cross-store synchronization
  useStoreSync()

  // Connect on mount with auto-cleanup
  useEffect(() => {
    realtimeActions.connect()
    
    // Cleanup is automatic via window.beforeunload listener
    return () => {
      // Component unmount cleanup if needed
    }
  }, [])

  const handleReconnect = () => {
    realtimeActions.reconnect()
  }

  const getConnectionIcon = () => {
    switch (connectionStatus) {
      case 'connected':
        return <Wifi className="h-4 w-4 text-green-600" />
      case 'connecting':
      case 'reconnecting':
        return <RefreshCw className="h-4 w-4 text-blue-600 animate-spin" />
      default:
        return <WifiOff className="h-4 w-4 text-red-600" />
    }
  }

  return (
    <div className="space-y-4">
      {/* Connection Status */}
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {getConnectionIcon()}
              <span className="text-sm font-medium">
                {connectionStatus === 'connected' ? 'Connected' : 
                 connectionStatus === 'reconnecting' ? `Reconnecting (${reconnection.attempts}/${5})` :
                 'Disconnected'}
              </span>
            </div>
            {!isConnected && (
              <Button size="sm" onClick={handleReconnect}>
                Reconnect
              </Button>
            )}
          </div>

          {/* Heartbeat Info */}
          {isConnected && heartbeat.latency && (
            <div className="mt-2 text-xs text-muted-foreground">
              Latency: {heartbeat.latency}ms
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
