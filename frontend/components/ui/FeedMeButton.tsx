"use client"

import React, { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Upload } from 'lucide-react'
import { FeedMeModal } from '@/components/feedme/FeedMeModal'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'

interface FeedMeButtonProps {
  onClick?: () => void
}

export function FeedMeButton({ onClick }: FeedMeButtonProps) {
  const [isHovered, setIsHovered] = useState(false)
  const [isModalOpen, setIsModalOpen] = useState(false)

  const handleClick = () => {
    setIsModalOpen(true)
    onClick?.()
  }

  return (
    <>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 hover:bg-accent/10 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
              onMouseEnter={() => setIsHovered(true)}
              onMouseLeave={() => setIsHovered(false)}
              onClick={handleClick}
              aria-label="FeedMe - Upload customer support transcripts"
            >
              <Upload 
                className={`h-4 w-4 transition-colors ${
                  isHovered ? 'text-accent' : 'text-muted-foreground'
                }`}
              />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>FeedMe - Upload transcripts</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      
      <ErrorBoundary>
        <FeedMeModal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
        />
      </ErrorBoundary>
    </>
  )
}