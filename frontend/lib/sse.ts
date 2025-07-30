/**
 * Server-Sent Events (SSE) client utilities for streaming responses.
 * 
 * Provides a robust SSE client with:
 * - Event-based message handling
 * - Automatic reconnection
 * - Error handling
 * - TypeScript support
 */

export interface SSEEvent {
  event: string
  data: any
}

export interface SSEOptions {
  url: string
  method?: 'GET' | 'POST'
  headers?: Record<string, string>
  body?: any
  onMessage?: (event: SSEEvent) => void
  onError?: (error: Error) => void
  onOpen?: () => void
  onClose?: () => void
  reconnect?: boolean
  reconnectDelay?: number
  reconnectAttempts?: number
}

export class SSEClient {
  private eventSource: EventSource | null = null
  private abortController: AbortController | null = null
  private reconnectCount = 0
  private closed = false
  
  constructor(private options: SSEOptions) {
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
      try {
        const data = JSON.parse(event.data)
        this.options.onMessage?.({ event: 'message', data })
      } catch (error) {
        // Handle non-JSON data
        this.options.onMessage?.({ event: 'message', data: event.data })
      }
    }
    
    this.eventSource.onerror = (error) => {
      this.handleError(new Error('EventSource error'))
    }
    
    // Add custom event listeners for typed events
    const events = ['thinking', 'token', 'completion.final', 'error']
    events.forEach(eventType => {
      this.eventSource?.addEventListener(eventType, (event: any) => {
        try {
          const data = JSON.parse(event.data)
          this.options.onMessage?.({ event: eventType, data })
        } catch (error) {
          this.options.onMessage?.({ event: eventType, data: event.data })
        }
      })
    })
  }
  
  private processLine(line: string): void {
    if (!line || line.startsWith(':')) {
      // Ignore empty lines and comments
      return
    }
    
    if (line.startsWith('data: ')) {
      const data = line.slice(6)
      
      try {
        const parsed = JSON.parse(data)
        
        // Check if it has an event field
        if (parsed.event && parsed.data) {
          this.options.onMessage?.({ 
            event: parsed.event, 
            data: parsed.data 
          })
        } else {
          // Default message event
          this.options.onMessage?.({ 
            event: 'message', 
            data: parsed 
          })
        }
      } catch (error) {
        // Handle non-JSON data
        this.options.onMessage?.({ 
          event: 'message', 
          data: data 
        })
      }
    }
  }
  
  private handleError(error: Error): void {
    this.options.onError?.(error)
    
    if (this.options.reconnect && 
        this.reconnectCount < (this.options.reconnectAttempts || 3) &&
        !this.closed) {
      this.reconnectCount++
      setTimeout(() => {
        if (!this.closed) {
          this.connect()
        }
      }, this.options.reconnectDelay)
    }
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
export async function streamChat(
  endpoint: string,
  request: any,
  handlers: {
    onThinking?: (data: any) => void
    onToken?: (token: string) => void
    onFinal?: (data: any) => void
    onError?: (error: Error) => void
  }
): Promise<() => void> {
  const client = new SSEClient({
    url: endpoint,
    method: 'POST',
    body: request,
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('auth_token') || ''}`
    },
    onMessage: (event) => {
      switch (event.event) {
        case 'thinking':
          handlers.onThinking?.(event.data)
          break
        case 'token':
          handlers.onToken?.(event.data.content)
          break
        case 'completion.final':
          handlers.onFinal?.(event.data)
          break
        case 'error':
          handlers.onError?.(new Error(event.data.error))
          break
      }
    },
    onError: handlers.onError
  })
  
  await client.connect()
  
  // Return cleanup function
  return () => client.close()
}