'use client'

import React, { useState } from 'react'
import { FeedMePageManager } from '@/components/feedme/FeedMePageManager'
import { Button } from '@/components/ui/button'
import { Upload, FolderOpen, BarChart3 } from 'lucide-react'
import { UploadPdfPopover } from '@/components/feedme/UploadPdfPopover'
import { useUIActions } from '@/lib/stores/ui-store'

/**
 * FeedMe - Customer Support Transcript Management
 * 
 * A comprehensive platform for managing customer support transcripts with AI-powered
 * knowledge extraction, conversation analysis, and intelligent search capabilities.
 */
export default function FeedMePage() {
  const ui = useUIActions()
  
  return (
    <div className="h-screen flex flex-col">
      <div className="flex items-center justify-end p-4 gap-2">
        {/* Top-right quick actions: Folders, Analytics, Upload PDFs */}
        <Button
          variant="ghost"
          size="sm"
          title="Folders"
          aria-label="Folders"
          onClick={() => ui.toggleFolderPanel()}
          className="h-9 w-9 p-0"
        >
          <FolderOpen className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          title="Analytics"
          aria-label="Analytics"
          onClick={() => ui.setRightPanel('analytics')}
          className="h-9 w-9 p-0"
        >
          <BarChart3 className="h-4 w-4" />
        </Button>
        <UploadPdfPopover>
          <Button className="flex items-center gap-2">
            <Upload className="w-4 h-4" />
            Upload PDFs
          </Button>
        </UploadPdfPopover>
      </div>
      <div className="flex-1">
        <FeedMePageManager />
      </div>
    </div>
  )
}
