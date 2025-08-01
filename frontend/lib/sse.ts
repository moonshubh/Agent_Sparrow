/**
 * Server-Sent Events (SSE) client utilities for streaming responses.
 * 
 * Provides a robust SSE client with:
 * - Event-based message handling
 * - Automatic reconnection
 * - Error handling
 * - TypeScript support
 */

export interface SSEEvent<T = unknown> {
  event: string
  data: T
}

export interface SSEOptions<T = unknown> {
  url: string
  method?: 'GET' | 'POST'
  headers?: Record<string, string>
  body?: unknown
  onMessage?: (event: SSEEvent<T>) => void
  onError?: (error: Error) => void
  onOpen?: () => void
  onClose?: () => void
  reconnect?: boolean
  reconnectDelay?: number
  reconnectAttempts?: number
}

export class SSEClient<T = unknown> {
  private eventSource: EventSource | null = null
  private abortController: AbortController | null = null
  private reconnectCount = 0
  private closed = false
  private currentEventType: string | null = null
  private lastEventId: string | null = null
  
  constructor(private options: SSEOptions<T>) {
    this.options = {
      method: 'GET',
      reconnect: true,
      reconnectDelay: 1000,
      reconnectAttempts: 3,
      ...options
    }
  }
  
  async connect(): Promise<void> {
    if (this.eventSource) {
      this.close()
    }
    
    this.closed = false
    this.abortController = new AbortController()
    
    try {
      if (this.options.method === 'GET') {
        // For GET requests, use EventSource
        this.eventSource = new EventSource(this.options.url)
        this.setupEventHandlers()
      } else {
        // For POST requests, use fetch with streaming
        await this.fetchStream()
      }
    } catch (error) {
      this.handleError(error as Error)
    }
  }
  
  private async fetchStream(): Promise<void> {
    try {
      const response = await fetch(this.options.url, {
        method: this.options.method,
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          ...this.options.headers
        },
        body: this.options.body ? JSON.stringify(this.options.body) : undefined,
        signal: this.abortController?.signal
      })
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      
      if (!response.body) {
        throw new Error('Response body is empty')
      }
      
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      
      this.options.onOpen?.()
      
      while (!this.closed) {
        const { done, value } = await reader.read()
        
        if (done) {
          break
        }
        
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        
        // Keep the last incomplete line in the buffer
        buffer = lines.pop() || ''
        
        for (const line of lines) {
          this.processLine(line)
        }
      }
      
      // Process any remaining data
      if (buffer) {
        this.processLine(buffer)
      }
      
      this.options.onClose?.()
      
    } catch (error) {
      if (error instanceof Error && error.name !== 'AbortError') {
        this.handleError(error)
      }
    }
  }
  
  private setupEventHandlers(): void {
    if (!this.eventSource) return
    
    this.eventSource.onopen = () => {
      this.reconnectCount = 0
      this.options.onOpen?.()
    }
    
    this.eventSource.onmessage = (event) => {
      const parsedData = this.safeParseJSON(event.data)
      this.options.onMessage?.({ event: 'message', data: parsedData })
    }
    
    this.eventSource.onerror = (error) => {
      this.handleError(new Error(`EventSource error: ${error.type || 'Unknown error'}`), error)
    }
    
    // Add custom event listeners for typed events
    const events = ['thinking', 'token', 'completion.final', 'error']
    events.forEach(eventType => {
      this.eventSource?.addEventListener(eventType, (event: Event) => {
        const messageEvent = event as MessageEvent
        const parsedData = this.safeParseJSON(messageEvent.data)
        this.options.onMessage?.({ event: eventType, data: parsedData })
      })
    })
  }
  
  private processLine(line: string): void {
    if (!line || line.startsWith(':')) {
      // Ignore empty lines and comments
      return
    }
    
    // Handle SSE specification fields
    if (line.startsWith('event: ')) {
      // Store event type for next data line
      this.currentEventType = line.slice(7).trim()
      return
    }
    
    if (line.startsWith('id: ')) {
      // Store event ID for reconnection
      this.lastEventId = line.slice(4).trim()
      return
    }
    
    if (line.startsWith('retry: ')) {
      // Update reconnection delay
      const retryDelay = parseInt(line.slice(7))
      if (!isNaN(retryDelay)) {
        this.options.reconnectDelay = retryDelay
      }
      return
    }
    
    if (line.startsWith('data: ')) {
      const data = line.slice(6)
      const parsedData = this.safeParseJSON(data)
      
      // Use stored event type or check if data has event field
      let eventType = this.currentEventType || 'message'
      let eventData = parsedData
      
      if (this.isEventDataObject(parsedData)) {
        eventType = parsedData.event
        eventData = parsedData.data
      }
      
      this.options.onMessage?.({ 
        event: eventType, 
        data: eventData 
      })
      
      // Reset event type after processing
      this.currentEventType = null
    }
  }
  
  private safeParseJSON(data: string): unknown {
    try {
      return JSON.parse(data)
    } catch {
      return data
    }
  }
  
  /**
   * Type guard to check if data is an event object with event and data fields
   */
  private isEventDataObject(data: unknown): data is { event: string; data: unknown } {
    return (
      typeof data === 'object' && 
      data !== null && 
      'event' in data && 
      'data' in data &&
      typeof (data as Record<string, unknown>).event === 'string'
    )
  }
  
  /**
   * Type guard to check if data is a token object with content field
   */
  private static isTokenObject(data: unknown): data is { content: string } {
    return (
      typeof data === 'object' && 
      data !== null && 
      'content' in data &&
      typeof (data as Record<string, unknown>).content === 'string'
    )
  }
  
  /**
   * Type guard to check if data is an error object with error field
   */
  private static isErrorObject(data: unknown): data is { error: string } {
    return (
      typeof data === 'object' && 
      data !== null && 
      'error' in data &&
      typeof (data as Record<string, unknown>).error === 'string'
    )
  }
  
  private handleError(error: Error, originalError?: Event): void {
    // Create enhanced error with original details
    const enhancedError = new Error(error.message)
    enhancedError.name = error.name
    enhancedError.stack = error.stack
    if (originalError) {
      // Add originalError property in a type-safe way
      Object.defineProperty(enhancedError, 'originalError', {
        value: originalError,
        writable: true,
        enumerable: true,
        configurable: true
      })
    }
    
    this.options.onError?.(enhancedError)
    
    if (this.options.reconnect && 
        this.reconnectCount < (this.options.reconnectAttempts || 3) &&
        !this.closed) {
      this.reconnectCount++
      
      // Exponential backoff: delay = baseDelay * (2 ^ attempt)
      const exponentialDelay = (this.options.reconnectDelay || 1000) * Math.pow(2, this.reconnectCount - 1)
      const maxDelay = 30000 // Cap at 30 seconds
      const finalDelay = Math.min(exponentialDelay, maxDelay)
      
      setTimeout(() => {
        if (!this.closed) {
          this.connect()
        }
      }, finalDelay)
    }
  }
  
  /**
   * Get the last event ID for reconnection purposes
   */
  getLastEventId(): string | null {
    return this.lastEventId
  }
  
  close(): void {
    this.closed = true
    
    if (this.eventSource) {
      this.eventSource.close()
      this.eventSource = null
    }
    
    if (this.abortController) {
      this.abortController.abort()
      this.abortController = null
    }
    
    this.options.onClose?.()
  }
}


/**
 * Convenience function to create a streaming chat connection
 */
export async function streamChat<T = unknown>(
  endpoint: string,
  request: unknown,
  handlers: {
    onThinking?: (data: T) => void
    onToken?: (token: string) => void
    onFinal?: (data: T) => void
    onError?: (error: Error) => void
  }
): Promise<() => void> {
  // Validate inputs
  if (!endpoint) {
    throw new Error('Endpoint URL is required')
  }
  
  // Safely access localStorage
  let authToken = ''
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      authToken = localStorage.getItem('auth_token') || ''
    }
  } catch (error) {
    console.warn('Failed to access localStorage:', error)
  }
  
  const client = new SSEClient<T>({
    url: endpoint,
    method: 'POST',
    body: request,
    headers: {
      'Authorization': `Bearer ${authToken}`
    },
    onMessage: (event) => {
      // Validate event data before processing
      if (!event || typeof event.event !== 'string') {
        console.warn('Invalid SSE event received:', event)
        return
      }
      
      switch (event.event) {
        case 'thinking':
          handlers.onThinking?.(event.data)
          break
        case 'token':
          // Use type guard instead of 'as any'
          if (SSEClient.isTokenObject(event.data)) {
            handlers.onToken?.(event.data.content)
          } else {
            handlers.onToken?.(String(event.data))
          }
          break
        case 'completion.final':
          handlers.onFinal?.(event.data)
          break
        case 'error':
          // Use type guard instead of 'as any'
          const errorMessage = SSEClient.isErrorObject(event.data)
            ? event.data.error 
            : String(event.data)
          handlers.onError?.(new Error(errorMessage))
          break
      }
    },
    onError: handlers.onError
  })
  
  await client.connect()
  
  // Return cleanup function
  return () => client.close()
}