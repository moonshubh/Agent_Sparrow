/**
 * WebSocket Connection Hook
 *
 * Custom hook for managing WebSocket connections with automatic reconnection,
 * connection status tracking, and integration with FeedMe store.
 */

"use client";

import { useEffect, useCallback, useRef } from "react";
import { useRealtime, useRealtimeActions } from "@/state/stores/realtime-store";

interface UseWebSocketOptions {
  autoConnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  debug?: boolean;
}

interface WebSocketConnection {
  isConnected: boolean;
  connectionStatus:
    | "connecting"
    | "connected"
    | "disconnected"
    | "error"
    | "reconnecting";
  connect: () => void;
  disconnect: () => void;
  reconnect: () => void;
  lastUpdate: string | null;
}

export const useWebSocket = (
  options: UseWebSocketOptions = {},
): WebSocketConnection => {
  const {
    autoConnect = true,
    reconnectInterval = 5000,
    maxReconnectAttempts = 5,
    debug = false,
  } = options;

  const { isConnected, connectionStatus, lastUpdate } = useRealtime();
  const {
    connect: realtimeConnect,
    disconnect: realtimeDisconnect,
    addNotification,
  } = useRealtimeActions();

  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<NodeJS.Timeout | null>(null);
  const isManualDisconnect = useRef(false);
  const isMounted = useRef(false);

  const log = useCallback(
    (message: string, ...args: any[]) => {
      if (debug) {
        console.log(`[WebSocket] ${message}`, ...args);
      }
    },
    [debug],
  );

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    if (!isMounted.current) {
      log("Attempted to connect after unmount, ignoring");
      return;
    }
    log("Connecting...");
    isManualDisconnect.current = false;
    clearReconnectTimer();
    realtimeConnect();
  }, [realtimeConnect, clearReconnectTimer, log]);

  const scheduleReconnect = useCallback(() => {
    if (isManualDisconnect.current) {
      log("Skipping reconnect - manual disconnect");
      return;
    }

    if (reconnectAttempts.current >= maxReconnectAttempts) {
      log("Max reconnect attempts reached");
      addNotification({
        type: "error",
        title: "Connection Failed",
        message: `Failed to reconnect after ${maxReconnectAttempts} attempts. Please refresh the page.`,
        read: false,
        actions: [
          {
            label: "Retry",
            action: () => {
              reconnectAttempts.current = 0;
              connect();
            },
          },
        ],
      });
      return;
    }

    const delay = Math.min(
      reconnectInterval * Math.pow(2, reconnectAttempts.current),
      30000,
    );
    log(
      `Scheduling reconnect in ${delay}ms (attempt ${reconnectAttempts.current + 1}/${maxReconnectAttempts})`,
    );

    reconnectTimer.current = setTimeout(() => {
      if (!isMounted.current) {
        log("Skipping reconnect - component unmounted");
        return;
      }
      reconnectAttempts.current++;
      realtimeConnect();
    }, delay);
  }, [
    reconnectInterval,
    maxReconnectAttempts,
    realtimeConnect,
    addNotification,
    log,
    connect,
  ]);

  const disconnect = useCallback(() => {
    log("Disconnecting...");
    isManualDisconnect.current = true;
    clearReconnectTimer();
    reconnectAttempts.current = 0;
    realtimeDisconnect();
  }, [realtimeDisconnect, clearReconnectTimer, log]);

  const reconnect = useCallback(() => {
    log("Manual reconnect triggered");
    reconnectAttempts.current = 0;
    disconnect();
    setTimeout(() => connect(), 100);
  }, [connect, disconnect, log]);

  // Monitor connection status changes
  useEffect(() => {
    log("Connection status changed:", connectionStatus);

    if (connectionStatus === "connected") {
      // Reset reconnect attempts on successful connection
      reconnectAttempts.current = 0;
      clearReconnectTimer();
    } else if (
      connectionStatus === "disconnected" ||
      connectionStatus === "error"
    ) {
      // Schedule reconnect if not manually disconnected
      if (!isManualDisconnect.current) {
        scheduleReconnect();
      }
    }
  }, [connectionStatus, scheduleReconnect, clearReconnectTimer, log]);

  // Mount/unmount effect - only runs once
  useEffect(() => {
    isMounted.current = true;
    log("WebSocket hook mounted");

    // Cleanup on unmount
    return () => {
      log("Cleaning up WebSocket connection");
      isMounted.current = false;
      isManualDisconnect.current = true;
      clearReconnectTimer();
      realtimeDisconnect();
    };
  }, [log, clearReconnectTimer, realtimeDisconnect]);

  // Separate auto-connect effect that can respond to state changes
  useEffect(() => {
    // Only auto-connect if:
    // 1. Component is mounted
    // 2. autoConnect is enabled
    // 3. Currently disconnected
    // 4. Not connected
    if (
      isMounted.current &&
      autoConnect &&
      connectionStatus === "disconnected" &&
      !isConnected
    ) {
      log("Auto-connecting due to state change");
      connect();
    }
  }, [autoConnect, connectionStatus, isConnected, connect, log]);

  // Handle page visibility changes for connection management
  useEffect(() => {
    // Skip if running on server-side
    if (typeof document === "undefined") return;

    const handleVisibilityChange = () => {
      if (document.hidden) {
        log("Page hidden - pausing reconnection attempts");
        clearReconnectTimer();
      } else if (!isConnected && !isManualDisconnect.current) {
        log("Page visible - resuming connection");
        connect();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [isConnected, connect, clearReconnectTimer, log]);

  // Handle online/offline events
  useEffect(() => {
    // Skip if running on server-side
    if (typeof window === "undefined") return;

    const handleOnline = () => {
      log("Network online - attempting to reconnect");
      if (!isConnected && !isManualDisconnect.current) {
        reconnectAttempts.current = 0;
        connect();
      }
    };

    const handleOffline = () => {
      log("Network offline - clearing reconnect timer");
      clearReconnectTimer();
    };

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [isConnected, connect, clearReconnectTimer, log]);

  return {
    isConnected,
    connectionStatus,
    connect,
    disconnect,
    reconnect,
    lastUpdate,
  };
};

// Hook for components that need WebSocket connection management
export const useWebSocketConnection = (options?: UseWebSocketOptions) => {
  return useWebSocket({
    autoConnect: true,
    debug: process.env.NODE_ENV === "development",
    ...options,
  });
};

// Hook for monitoring real-time processing updates
export const useProcessingUpdates = () => {
  const { processingUpdates } = useRealtime();
  const { handleProcessingUpdate } = useRealtimeActions();

  const getProcessingStatus = useCallback(
    (conversationId: number) => {
      return processingUpdates[conversationId] || null;
    },
    [processingUpdates],
  );

  const isProcessing = useCallback(
    (conversationId: number) => {
      const update = processingUpdates[conversationId];
      return update?.status === "processing" || update?.status === "pending";
    },
    [processingUpdates],
  );

  const getProcessingProgress = useCallback(
    (conversationId: number) => {
      const update = processingUpdates[conversationId];
      return update?.progress || 0;
    },
    [processingUpdates],
  );

  return {
    processingUpdates,
    getProcessingStatus,
    isProcessing,
    getProcessingProgress,
    handleProcessingUpdate,
  };
};

// Hook for notifications management
export const useNotifications = () => {
  const { notifications } = useRealtime();
  const { addNotification, markNotificationRead, clearNotifications } =
    useRealtimeActions();

  const unreadCount = notifications.filter((n) => !n.read).length;
  const recentNotifications = notifications.slice(0, 10);

  const markAllAsRead = useCallback(() => {
    notifications.forEach((notification) => {
      if (!notification.read) {
        markNotificationRead(notification.id);
      }
    });
  }, [notifications, markNotificationRead]);

  return {
    notifications: recentNotifications,
    unreadCount,
    addNotification,
    markNotificationRead,
    markAllAsRead,
    clearNotifications,
  };
};
