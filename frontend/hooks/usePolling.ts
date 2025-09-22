import { useEffect, useRef, useCallback, useState } from 'react'

interface UsePollingOptions {
  enabled: boolean
  interval: number
  onPoll: () => Promise<void>
  onError?: (error: Error) => void
}

export function usePolling({ enabled, interval, onPoll, onError }: UsePollingOptions) {
  const intervalIdRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const mountedRef = useRef(true)
  const [isPolling, setIsPolling] = useState(false)

  const stopPolling = useCallback(() => {
    if (intervalIdRef.current) {
      clearInterval(intervalIdRef.current)
      intervalIdRef.current = null
      setIsPolling(false)
    }
  }, [])

  const startPolling = useCallback(() => {
    stopPolling() // Clear any existing interval

    if (!enabled) return

    const pollWithErrorHandling = async () => {
      if (!mountedRef.current) return

      try {
        await onPoll()
      } catch (error) {
        onError?.(error instanceof Error ? error : new Error(String(error)))
      }
    }

    // Initial poll
    void pollWithErrorHandling()

    // Set up interval for subsequent polls
    intervalIdRef.current = setInterval(pollWithErrorHandling, interval)
    setIsPolling(true)
  }, [enabled, interval, onPoll, onError, stopPolling])

  useEffect(() => {
    mountedRef.current = true

    if (enabled) {
      startPolling()
    }

    return () => {
      mountedRef.current = false
      stopPolling()
    }
  }, [enabled, startPolling, stopPolling])

  return {
    startPolling,
    stopPolling,
    isPolling,
  }
}