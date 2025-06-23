"use client"

import React, { useMemo, useRef, useEffect, useState } from 'react'
import dynamic from 'next/dynamic'
import MessageBubble from './MessageBubble'
import { UnifiedMessage } from '@/hooks/useUnifiedChat'

interface VirtualizedMessageListProps {
  messages: UnifiedMessage[]
  onRetry?: () => void
  onRate?: (messageId: string, rating: 'up' | 'down') => void
  containerHeight: number
}

const ITEM_HEIGHT = 120 // Estimated average message height
const BUFFER_SIZE = 5 // Number of items to render outside viewport

export default function VirtualizedMessageList({
  messages,
  onRetry,
  onRate,
  containerHeight
}: VirtualizedMessageListProps) {
  const [scrollTop, setScrollTop] = useState(0)
  const scrollElementRef = useRef<HTMLDivElement>(null)
  
  // Calculate which items should be visible
  const visibleRange = useMemo(() => {
    const startIndex = Math.max(0, Math.floor(scrollTop / ITEM_HEIGHT) - BUFFER_SIZE)
    const endIndex = Math.min(
      messages.length - 1,
      Math.ceil((scrollTop + containerHeight) / ITEM_HEIGHT) + BUFFER_SIZE
    )
    
    return { startIndex, endIndex }
  }, [scrollTop, containerHeight, messages.length])
  
  // Calculate total height and offset for virtual scrolling
  const totalHeight = messages.length * ITEM_HEIGHT
  const offsetY = visibleRange.startIndex * ITEM_HEIGHT
  
  // Get visible messages
  const visibleMessages = messages.slice(
    visibleRange.startIndex,
    visibleRange.endIndex + 1
  )
  
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop)
  }
  
  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (scrollElementRef.current) {
      const shouldAutoScroll = 
        scrollTop + containerHeight >= totalHeight - (ITEM_HEIGHT * 2)
      
      if (shouldAutoScroll) {
        scrollElementRef.current.scrollTop = totalHeight
      }
    }
  }, [messages.length, totalHeight, scrollTop, containerHeight])
  
  // For small numbers of messages, don't use virtualization
  if (messages.length < 50) {
    return (
      <div 
        ref={scrollElementRef}
        className="h-full overflow-y-auto"
        onScroll={handleScroll}
      >
        <div className="space-y-6 p-4">
          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              id={message.id}
              type={message.type}
              content={message.content}
              timestamp={message.timestamp}
              agentType={message.agentType}
              metadata={message.metadata}
              streaming={message.streaming}
              onRetry={message.type === 'agent' ? onRetry : undefined}
              onRate={onRate ? (rating) => onRate(message.id, rating) : undefined}
            />
          ))}
        </div>
      </div>
    )
  }
  
  return (
    <div 
      ref={scrollElementRef}
      className="h-full overflow-y-auto"
      onScroll={handleScroll}
    >
      {/* Total height container for scrollbar */}
      <div style={{ height: totalHeight, position: 'relative' }}>
        {/* Visible items container */}
        <div 
          style={{ 
            transform: `translateY(${offsetY}px)`,
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0
          }}
          className="space-y-6 p-4"
        >
          {visibleMessages.map((message, index) => (
            <MessageBubble
              key={message.id}
              id={message.id}
              type={message.type}
              content={message.content}
              timestamp={message.timestamp}
              agentType={message.agentType}
              metadata={message.metadata}
              streaming={message.streaming}
              onRetry={message.type === 'agent' ? onRetry : undefined}
              onRate={onRate ? (rating) => onRate(message.id, rating) : undefined}
            />
          ))}
        </div>
      </div>
    </div>
  )
}