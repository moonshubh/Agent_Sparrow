"use client"

import React, { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { FileText, Upload } from 'lucide-react'
import { FeedMeConversationManager } from '@/components/feedme/FeedMeConversationManager'
import { EnhancedFeedMeModal } from '@/components/feedme/EnhancedFeedMeModal'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'
import { useWebSocketConnection } from '@/hooks/useWebSocket'

interface FeedMeButtonProps {
  onClick?: () => void
  mode?: 'manager' | 'upload'
}

export function FeedMeButton({ onClick, mode = 'manager' }: FeedMeButtonProps) {
  const [isHovered, setIsHovered] = useState(false)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const { isConnected } = useWebSocketConnection()

  const handleClick = () => {
    setIsModalOpen(true)
    onClick?.()
  }

  const handleUploadComplete = (results: any[]) => {
    // Optionally refresh conversations or show success notification
    console.log('Upload completed:', results)
  }

  const Icon = mode === 'upload' ? Upload : FileText
  const tooltipText = mode === 'upload' 
    ? 'FeedMe - Upload transcripts' 
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
                className="h-8 w-8 p-0 hover:bg-accent/10 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
                onMouseEnter={() => setIsHovered(true)}
                onMouseLeave={() => setIsHovered(false)}
                onClick={handleClick}
                aria-label={tooltipText}
              >
                <Icon 
                  className={`h-4 w-4 transition-colors ${
                    isHovered ? 'text-accent' : 'text-muted-foreground'
                  }`}
                />
              </Button>
              {/* Connection status indicator */}
              {mode === 'manager' && (
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
            {mode === 'manager' && (
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