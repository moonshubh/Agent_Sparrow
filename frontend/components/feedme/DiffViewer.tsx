/**
 * Diff Viewer Component
 * Displays differences between two conversation versions
 * 
 * Features:
 * - Side-by-side diff visualization
 * - Line-by-line comparison
 * - Added, removed, and modified line highlighting
 * - Statistics summary
 * - Responsive design with fallback to unified view
 */

'use client'

import React, { useState, useEffect } from 'react'
import { Button } from '../ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'
import { ScrollArea } from '../ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs'
import { 
  X, 
  Plus, 
  Minus, 
  Edit3, 
  BarChart3,
  RefreshCw,
  AlertCircle
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { 
  getVersionDiff, 
  type VersionDiff, 
  type ModifiedLine 
} from '../../lib/feedme-api'

interface DiffViewerProps {
  conversationId: number
  fromVersion: number
  toVersion: number
  onClose: () => void
}

interface DiffLineProps {
  content: string
  lineNumber?: number
  type: 'added' | 'removed' | 'modified' | 'unchanged'
  isOld?: boolean
}

function DiffLine({ content, lineNumber, type, isOld }: DiffLineProps) {
  const getLineClasses = () => {
    switch (type) {
      case 'added':
        return 'bg-green-50 border-green-200 text-green-900'
      case 'removed':
        return 'bg-red-50 border-red-200 text-red-900'
      case 'modified':
        return isOld 
          ? 'bg-orange-50 border-orange-200 text-orange-900'
          : 'bg-blue-50 border-blue-200 text-blue-900'
      default:
        return 'bg-background border-border'
    }
  }

  const getIconClasses = () => {
    switch (type) {
      case 'added':
        return 'text-green-600'
      case 'removed':
        return 'text-red-600'
      case 'modified':
        return 'text-blue-600'
      default:
        return 'text-muted-foreground'
    }
  }

  const getIcon = () => {
    switch (type) {
      case 'added':
        return <Plus className="h-3 w-3" />
      case 'removed':
        return <Minus className="h-3 w-3" />
      case 'modified':
        return <Edit3 className="h-3 w-3" />
      default:
        return null
    }
  }

  return (
    <div className={cn(
      "flex items-start gap-3 p-2 border-l-2 font-mono text-sm",
      getLineClasses()
    )}>
      <div className="flex items-center gap-2 flex-shrink-0 w-16">
        <span className={cn("text-xs", getIconClasses())}>
          {lineNumber || '—'}
        </span>
        <span className={getIconClasses()}>
          {getIcon()}
        </span>
      </div>
      <div className="flex-1 whitespace-pre-wrap break-words">
        {content || '\u00A0'}
      </div>
    </div>
  )
}

interface DiffStatsProps {
  stats: Record<string, number>
}

function DiffStats({ stats }: DiffStatsProps) {
  const total = stats.total_changes || 0
  const added = stats.added_count || 0
  const removed = stats.removed_count || 0
  const modified = stats.modified_count || 0

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm flex items-center gap-2">
          <BarChart3 className="h-4 w-4" />
          Change Summary
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Total Changes</span>
              <Badge variant="outline">{total}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-green-700">Added Lines</span>
              <Badge variant="outline" className="text-green-700 border-green-200">
                +{added}
              </Badge>
            </div>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-red-700">Removed Lines</span>
              <Badge variant="outline" className="text-red-700 border-red-200">
                -{removed}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-blue-700">Modified Lines</span>
              <Badge variant="outline" className="text-blue-700 border-blue-200">
                ~{modified}
              </Badge>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function DiffViewer({ 
  conversationId, 
  fromVersion, 
  toVersion, 
  onClose 
}: DiffViewerProps) {
  const [diff, setDiff] = useState<VersionDiff | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'unified' | 'split'>('unified')

  useEffect(() => {
    loadDiff()
  }, [conversationId, fromVersion, toVersion])

  const loadDiff = async () => {
    try {
      setIsLoading(true)
      setError(null)
      
      const diffData = await getVersionDiff(conversationId, fromVersion, toVersion)
      setDiff(diffData)
    } catch (error) {
      console.error('Failed to load diff:', error)
      setError(error instanceof Error ? error.message : 'Failed to load diff')
    } finally {
      setIsLoading(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-2 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Loading diff...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <AlertCircle className="h-8 w-8 mx-auto mb-2 text-red-500" />
          <p className="text-sm text-red-600 mb-4">{error}</p>
          <Button variant="outline" onClick={loadDiff}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Retry
          </Button>
        </div>
      </div>
    )
  }

  if (!diff) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <AlertCircle className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">No diff data available</p>
        </div>
      </div>
    )
  }

  const hasChanges = (diff.stats.total_changes || 0) > 0

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-semibold">
            Changes from Version {fromVersion} to Version {toVersion}
          </h3>
          <p className="text-sm text-muted-foreground">
            {hasChanges 
              ? `${diff.stats.total_changes} changes detected`
              : 'No changes between versions'
            }
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Stats */}
      {hasChanges && (
        <div className="mb-4">
          <DiffStats stats={diff.stats} />
        </div>
      )}

      {/* Content */}
      {!hasChanges ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <Edit3 className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
            <p className="text-lg font-medium mb-2">No Changes Found</p>
            <p className="text-sm text-muted-foreground">
              The content in version {fromVersion} and version {toVersion} is identical.
            </p>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-hidden">
          <Tabs value={viewMode} onValueChange={(value) => setViewMode(value as any)} className="h-full flex flex-col">
            <TabsList className="grid w-full grid-cols-2 mb-4">
              <TabsTrigger value="unified">Unified View</TabsTrigger>
              <TabsTrigger value="split">Split View</TabsTrigger>
            </TabsList>

            <TabsContent value="unified" className="flex-1 overflow-hidden mt-0">
              <ScrollArea className="h-full">
                <div className="space-y-1">
                  {/* Removed lines */}
                  {diff.removed_lines.map((line, index) => (
                    <DiffLine
                      key={`removed-${index}`}
                      content={line}
                      lineNumber={index + 1}
                      type="removed"
                    />
                  ))}
                  
                  {/* Added lines */}
                  {diff.added_lines.map((line, index) => (
                    <DiffLine
                      key={`added-${index}`}
                      content={line}
                      lineNumber={index + 1}
                      type="added"
                    />
                  ))}
                  
                  {/* Modified lines */}
                  {diff.modified_lines.map((modifiedLine, index) => (
                    <div key={`modified-${index}`} className="space-y-0">
                      <DiffLine
                        content={modifiedLine.original}
                        lineNumber={modifiedLine.line_number}
                        type="modified"
                        isOld={true}
                      />
                      <DiffLine
                        content={modifiedLine.modified}
                        lineNumber={modifiedLine.line_number}
                        type="modified"
                        isOld={false}
                      />
                    </div>
                  ))}
                  
                  {/* Context lines (sample) */}
                  {diff.unchanged_lines.slice(0, 5).map((line, index) => (
                    <DiffLine
                      key={`unchanged-${index}`}
                      content={line}
                      lineNumber={index + 1}
                      type="unchanged"
                    />
                  ))}
                </div>
              </ScrollArea>
            </TabsContent>

            <TabsContent value="split" className="flex-1 overflow-hidden mt-0">
              <div className="grid grid-cols-2 gap-4 h-full">
                {/* Before (Version fromVersion) */}
                <div className="flex flex-col">
                  <h4 className="text-sm font-medium mb-2 text-red-700">
                    Version {fromVersion} (Before)
                  </h4>
                  <ScrollArea className="flex-1 border rounded">
                    <div className="space-y-1 p-2">
                      {diff.removed_lines.map((line, index) => (
                        <DiffLine
                          key={`before-${index}`}
                          content={line}
                          lineNumber={index + 1}
                          type="removed"
                        />
                      ))}
                      {diff.modified_lines.map((modifiedLine, index) => (
                        <DiffLine
                          key={`before-modified-${index}`}
                          content={modifiedLine.original}
                          lineNumber={modifiedLine.line_number}
                          type="modified"
                          isOld={true}
                        />
                      ))}
                    </div>
                  </ScrollArea>
                </div>

                {/* After (Version toVersion) */}
                <div className="flex flex-col">
                  <h4 className="text-sm font-medium mb-2 text-green-700">
                    Version {toVersion} (After)
                  </h4>
                  <ScrollArea className="flex-1 border rounded">
                    <div className="space-y-1 p-2">
                      {diff.added_lines.map((line, index) => (
                        <DiffLine
                          key={`after-${index}`}
                          content={line}
                          lineNumber={index + 1}
                          type="added"
                        />
                      ))}
                      {diff.modified_lines.map((modifiedLine, index) => (
                        <DiffLine
                          key={`after-modified-${index}`}
                          content={modifiedLine.modified}
                          lineNumber={modifiedLine.line_number}
                          type="modified"
                          isOld={false}
                        />
                      ))}
                    </div>
                  </ScrollArea>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </div>
      )}
    </div>
  )
}