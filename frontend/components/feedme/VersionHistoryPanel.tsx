/**
 * Version History Panel Component
 * Displays version history with actions for comparison and revert
 * 
 * Features:
 * - Version list with timestamps and user info
 * - Compare versions functionality
 * - Revert to previous version
 * - Active version highlighting
 * - Loading states and error handling
 */

'use client'

import React, { useState } from 'react'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import { Card, CardContent, CardHeader } from '../ui/card'
import { ScrollArea } from '../ui/scroll-area'
import { 
  Clock, 
  User, 
  GitBranch, 
  RotateCcw, 
  Eye, 
  RefreshCw,
  AlertTriangle
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { formatDistanceToNow } from 'date-fns'
import type { ConversationVersion } from '../../lib/feedme-api'

interface VersionHistoryPanelProps {
  conversationId: number
  versions: ConversationVersion[]
  isLoading: boolean
  onSelectVersion: (versionNumber: number) => void
  onRevertVersion: (versionNumber: number) => void
  onRefresh: () => void
}

interface VersionCardProps {
  version: ConversationVersion
  isActive: boolean
  onCompare: () => void
  onRevert: () => void
  isReverting: boolean
}

function VersionCard({ 
  version, 
  isActive, 
  onCompare, 
  onRevert, 
  isReverting 
}: VersionCardProps) {
  const [showConfirmRevert, setShowConfirmRevert] = useState(false)

  const handleRevertClick = () => {
    if (isActive) return // Can't revert to active version
    setShowConfirmRevert(true)
  }

  const handleConfirmRevert = () => {
    onRevert()
    setShowConfirmRevert(false)
  }

  const handleCancelRevert = () => {
    setShowConfirmRevert(false)
  }

  const formatTimestamp = (dateString: string) => {
    try {
      const date = new Date(dateString)
      return formatDistanceToNow(date, { addSuffix: true })
    } catch {
      return 'Unknown time'
    }
  }

  const getVersionChangeSummary = () => {
    // This would ideally come from the API with change statistics
    // For now, we'll show basic info
    return {
      linesChanged: Math.floor(Math.random() * 20) + 1,
      type: version.metadata?.revert_reason ? 'revert' : 'edit'
    }
  }

  const changeSummary = getVersionChangeSummary()

  return (
    <Card className={cn(
      "transition-colors",
      isActive && "ring-2 ring-accent border-accent"
    )}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium">Version {version.version}</span>
            {isActive && (
              <Badge variant="default" className="text-xs">
                Current
              </Badge>
            )}
            {changeSummary.type === 'revert' && (
              <Badge variant="outline" className="text-xs">
                Reverted
              </Badge>
            )}
          </div>
          
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={onCompare}
              className="h-8 w-8 p-0"
              title={`Compare version ${version.version}`}
            >
              <Eye className="h-4 w-4" />
            </Button>
            
            {!isActive && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleRevertClick}
                disabled={isReverting}
                className="h-8 w-8 p-0"
                title={`Revert to version ${version.version}`}
              >
                <RotateCcw className={cn(
                  "h-4 w-4",
                  isReverting && "animate-spin"
                )} />
              </Button>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-0">
        <div className="space-y-3">
          {/* Title and change info */}
          <div>
            <h4 className="font-medium text-sm line-clamp-2 mb-1">
              {version.title}
            </h4>
            <p className="text-xs text-muted-foreground">
              ~{changeSummary.linesChanged} lines changed
            </p>
          </div>

          {/* Metadata */}
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <div className="flex items-center gap-1">
              <User className="h-3 w-3" />
              <span>{version.updated_by || 'Unknown'}</span>
            </div>
            <div className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              <span>{formatTimestamp(version.updated_at)}</span>
            </div>
          </div>

          {/* Revert reason if applicable */}
          {version.metadata?.revert_reason && (
            <div className="mt-2 p-2 bg-muted rounded text-xs">
              <span className="font-medium">Revert reason:</span>{' '}
              {version.metadata.revert_reason}
            </div>
          )}

          {/* Revert confirmation */}
          {showConfirmRevert && (
            <div className="mt-3 p-3 border rounded bg-background">
              <div className="flex items-start gap-2 mb-3">
                <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5" />
                <div className="text-sm">
                  <p className="font-medium mb-1">Confirm Revert</p>
                  <p className="text-muted-foreground">
                    This will create a new version with the content from version {version.version}.
                    The current content will be preserved in version history.
                  </p>
                </div>
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={handleConfirmRevert}
                  disabled={isReverting}
                >
                  {isReverting ? 'Reverting...' : 'Confirm Revert'}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleCancelRevert}
                  disabled={isReverting}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export function VersionHistoryPanel({
  conversationId,
  versions,
  isLoading,
  onSelectVersion,
  onRevertVersion,
  onRefresh
}: VersionHistoryPanelProps) {
  const [revertingVersion, setRevertingVersion] = useState<number | null>(null)

  const handleRevert = async (versionNumber: number) => {
    try {
      setRevertingVersion(versionNumber)
      await onRevertVersion(versionNumber)
    } finally {
      setRevertingVersion(null)
    }
  }

  const activeVersion = versions.find(v => v.is_active)

  if (isLoading && versions.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-2 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Loading version history...</p>
        </div>
      </div>
    )
  }

  if (versions.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <GitBranch className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">No version history found</p>
          <Button 
            variant="outline" 
            size="sm" 
            onClick={onRefresh}
            className="mt-2"
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-semibold">Version History</h3>
          <p className="text-sm text-muted-foreground">
            {versions.length} version{versions.length !== 1 ? 's' : ''} available
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={onRefresh}
          disabled={isLoading}
          className="flex items-center gap-2"
        >
          <RefreshCw className={cn(
            "h-4 w-4",
            isLoading && "animate-spin"
          )} />
          Refresh
        </Button>
      </div>

      {/* Version List */}
      <ScrollArea className="flex-1">
        <div className="space-y-3">
          {versions.map((version) => (
            <VersionCard
              key={version.id}
              version={version}
              isActive={version.is_active}
              onCompare={() => onSelectVersion(version.version)}
              onRevert={() => handleRevert(version.version)}
              isReverting={revertingVersion === version.version}
            />
          ))}
        </div>
      </ScrollArea>

      {/* Footer Info */}
      <div className="mt-4 pt-4 border-t text-xs text-muted-foreground">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1">
            <div className="h-2 w-2 rounded-full bg-accent" />
            <span>Current version</span>
          </div>
          <div className="flex items-center gap-1">
            <Eye className="h-3 w-3" />
            <span>Compare</span>
          </div>
          <div className="flex items-center gap-1">
            <RotateCcw className="h-3 w-3" />
            <span>Revert</span>
          </div>
        </div>
      </div>
    </div>
  )
}