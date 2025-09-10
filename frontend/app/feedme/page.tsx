'use client'

import React from 'react'
import { FeedMePageManager } from '@/components/feedme/FeedMePageManager'

/**
 * FeedMe - Customer Support Transcript Management
 * 
 * A comprehensive platform for managing customer support transcripts with AI-powered
 * knowledge extraction, conversation analysis, and intelligent search capabilities.
 */
export default function FeedMePage() {
  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <div className="flex-1">
        <FeedMePageManager />
      </div>
    </div>
  )
}
