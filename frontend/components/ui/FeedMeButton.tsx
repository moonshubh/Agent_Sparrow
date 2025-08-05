"use client"

import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Upload, ExternalLink } from 'lucide-react'
import Image from 'next/image'
import FeedMeConversationManager from '@/components/feedme/FeedMeConversationManager'
import { EnhancedFeedMeModal } from '@/components/feedme/EnhancedFeedMeModal'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'
import { useWebSocketConnection } from '@/hooks/useWebSocket'

interface FeedMeButtonProps {
  onClick?: () => void
  mode?: 'manager' | 'upload' | 'navigate'
}

export function FeedMeButton({ onClick, mode = 'navigate' }: FeedMeButtonProps) {
  const [isHovered, setIsHovered] = useState(false)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const router = useRouter()
  // Disable WebSocket connection entirely to prevent errors
  const webSocketEnabled = false // Disabled until auth system is ready
  const { isConnected } = useWebSocketConnection({ 
    autoConnect: webSocketEnabled
  })

  const handleClick = () => {
    if (mode === 'navigate') {
      router.push('/feedme')
    } else {
      setIsModalOpen(true)
    }
    onClick?.()
  }

  const handleUploadComplete = (results: any[]) => {
    // Optionally refresh conversations or show success notification
    console.log('Upload completed:', results)
  }

  const tooltipText = mode === 'upload' 
    ? 'FeedMe - Upload transcripts' 
    : mode === 'navigate' 
      ? 'FeedMe - Open full page' 
      : 'FeedMe - Manage conversations'

  return (
    <>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="relative">
              <Button
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0 hover:bg-mb-blue-300/10 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
                onMouseEnter={() => setIsHovered(true)}
                onMouseLeave={() => setIsHovered(false)}
                onClick={handleClick}
                aria-label={tooltipText}
              >
                <Image 
                  src="/feedme-icon.png"
                  alt="FeedMe"
                  width={16}
                  height={16}
                  className={`transition-opacity ${
                    isHovered ? 'opacity-100' : 'opacity-70'
                  }`}
                />
              </Button>
              {/* Connection status indicator - only show when WebSocket is enabled */}
              {mode === 'manager' && webSocketEnabled && (
                <div 
                  className={`absolute -top-1 -right-1 h-2 w-2 rounded-full ${
                    isConnected ? 'bg-green-500' : 'bg-gray-400'
                  }`}
                  title={isConnected ? 'Real-time updates active' : 'Real-time updates offline'}
                />
              )}
            </div>
          </TooltipTrigger>
          <TooltipContent>
            <p>{tooltipText}</p>
            {mode === 'manager' && webSocketEnabled && (
              <p className="text-xs text-muted-foreground">
                Real-time: {isConnected ? 'Connected' : 'Offline'}
              </p>
            )}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      
      <ErrorBoundary>
        {mode === 'manager' ? (
          <FeedMeConversationManager
            isOpen={isModalOpen}
            onClose={() => setIsModalOpen(false)}
          />
        ) : (
          <EnhancedFeedMeModal
            isOpen={isModalOpen}
            onClose={() => setIsModalOpen(false)}
            onUploadComplete={handleUploadComplete}
          />
        )}
      </ErrorBoundary>
    </>
  )
}