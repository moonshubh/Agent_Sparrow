'use client'

import React, { useState } from 'react'
import { FeedMePageManager } from '@/components/feedme/FeedMePageManager'
import { EnhancedFeedMeModal } from '@/components/feedme/EnhancedFeedMeModal'
import { Button } from '@/components/ui/button'
import { Upload } from 'lucide-react'

/**
 * FeedMe - Customer Support Transcript Management
 * 
 * A comprehensive platform for managing customer support transcripts with AI-powered
 * knowledge extraction, conversation analysis, and intelligent search capabilities.
 */
export default function FeedMePage() {
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false)
  
  return (
    <div className="h-screen flex flex-col">
      <div className="flex items-center justify-end p-4">
        <Button 
          onClick={() => setIsUploadModalOpen(true)}
          className="flex items-center gap-2"
        >
          <Upload className="w-4 h-4" />
          Upload Transcript
        </Button>
      </div>
      <div className="flex-1">
        <FeedMePageManager />
      </div>
      <EnhancedFeedMeModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        onUploadComplete={(results) => {
          // Refresh the page or update the conversation list
          window.location.reload()
        }}
      />
    </div>
  )
}