"use client"

import React from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { FileSearch, Clock } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SystemStatusMessageProps {
  phase: "analyzing" | "processing"
  filesize?: string
  lines?: number
  startedAt: Date
}

export default function SystemStatusMessage({ 
  phase, 
  filesize, 
  lines, 
  startedAt 
}: SystemStatusMessageProps) {
  const formatTime = (date: Date) => {
    return date.toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit',
      hour12: true 
    })
  }

  const getPhaseText = () => {
    switch (phase) {
      case "analyzing":
        return "Analyzing"
      case "processing":
        return "Processing"
      default:
        return "Working on"
    }
  }

  // Extract filename from filesize string if present
  const getFileName = () => {
    if (!filesize) return "Log.log"
    // If filesize contains filename, extract it
    if (filesize.includes('"')) {
      const match = filesize.match(/"([^"]*)"/)
      return match ? match[1] : "Log.log"
    }
    return "Log.log"
  }

  const formatFileSize = () => {
    if (!filesize) return "Unknown KB"
    // Extract just the size part if it's in a complex string
    const sizeMatch = filesize.match(/(\d+(?:\.\d+)?\s*[KMG]?B)/i)
    return sizeMatch ? sizeMatch[1] : filesize
  }

  return (
    <div className="flex justify-center mb-4">
      <div className={cn(
        "inline-flex items-center gap-2 rounded-lg bg-muted/40 px-3 py-1.5",
        "text-xs font-medium text-muted-foreground shadow border border-border/30"
      )}>
        {/* Animated Icon */}
        <FileSearch className="w-3.5 h-3.5 text-primary animate-pulse" />
        
        {/* Status Text */}
        <span>
          🔍 {getPhaseText()} "{getFileName()}" 
          {filesize && (
            <>
              {" "}({formatFileSize()}
              {lines && <> · {lines.toLocaleString()} lines</>})
            </>
          )}
          … 
        </span>
        
        {/* Time with subtle separator */}
        <span className="text-muted-foreground/70 flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {formatTime(startedAt)}
        </span>
        
        {/* Subtle loading animation */}
        <Skeleton className="w-12 h-1 bg-primary/20" />
      </div>
    </div>
  )
}