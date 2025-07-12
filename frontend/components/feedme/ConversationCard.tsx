/**
 * ConversationCard Component
 * 
 * Unified card design for conversation display with:
 * - "Move to Folder" dropdown action
 * - Processing status indicators
 * - Hover states and interactions
 * - Accessible keyboard navigation
 */

'use client'

import React from 'react'
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger,
  DropdownMenuSeparator
} from '@/components/ui/dropdown-menu'
import { 
  MoreHorizontal, 
  FolderOpen, 
  MessageCircle, 
  Calendar,
  User,
  CheckCircle,
  Clock,
  AlertCircle,
  Loader2
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useFolders } from '@/lib/stores/folders-store'

export interface Conversation {
  id: number
  title: string
  folder_id?: number | null
  processing_status: 'pending' | 'processing' | 'completed' | 'failed'
  total_examples?: number
  uploaded_by?: string
  created_at: string
  updated_at: string
}

interface ConversationCardProps {
  conversation: Conversation
  onSelect: (id: number) => void
  onMoveToFolder: (conversationId: number, folderId: number | null) => void
  showMoveAction?: boolean
  isSelected?: boolean
  className?: string
}

export function ConversationCard({ 
  conversation, 
  onSelect, 
  onMoveToFolder, 
  showMoveAction = true, 
  isSelected = false,
  className 
}: ConversationCardProps) {
  const { folders } = useFolders()

  const getStatusInfo = (status: Conversation['processing_status']) => {
    switch (status) {
      case 'completed':
        return { icon: CheckCircle, color: 'text-green-600', bg: 'bg-green-50', label: 'Completed' }
      case 'processing':
        return { icon: Loader2, color: 'text-blue-600', bg: 'bg-blue-50', label: 'Processing' }
      case 'pending':
        return { icon: Clock, color: 'text-yellow-600', bg: 'bg-yellow-50', label: 'Pending' }
      case 'failed':
        return { icon: AlertCircle, color: 'text-red-600', bg: 'bg-red-50', label: 'Failed' }
      default:
        return { icon: Clock, color: 'text-gray-600', bg: 'bg-gray-50', label: 'Unknown' }
    }
  }

  const statusInfo = getStatusInfo(conversation.processing_status)
  const StatusIcon = statusInfo.icon

  const currentFolder = conversation.folder_id ? folders[conversation.folder_id] : null
  const availableFolders = Object.values(folders).filter(f => f.id !== conversation.folder_id)

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    })
  }

  const handleCardClick = () => {
    onSelect(conversation.id)
  }

  const handleMoveToFolder = (folderId: number | null) => {
    onMoveToFolder(conversation.id, folderId)
  }

  return (
    <Card className={cn(
      "conversation-card cursor-pointer transition-all duration-200 hover:shadow-md hover:bg-mb-blue-300/5",
      isSelected && "ring-2 ring-accent bg-accent/5",
      "group",
      className
    )}>
      <CardHeader className="pb-2" onClick={handleCardClick}>
        <div className="flex items-start justify-between">
          <CardTitle className="text-sm font-medium line-clamp-2 group-hover:text-mb-blue-300 transition-colors">
            {conversation.title}
          </CardTitle>
          {showMoveAction && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="h-6 w-6 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
                  data-testid="conversation-actions-menu"
                >
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuItem onClick={() => handleMoveToFolder(null)}>
                  <MessageCircle className="h-4 w-4 mr-2" />
                  Move to Unassigned
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                {availableFolders.map((folder) => (
                  <DropdownMenuItem 
                    key={folder.id}
                    onClick={() => handleMoveToFolder(folder.id)}
                    data-testid={`move-to-folder-${folder.id}`}
                  >
                    <FolderOpen className="h-4 w-4 mr-2" />
                    {folder.name}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </CardHeader>

      <CardContent className="pb-2" onClick={handleCardClick}>
        <div className="space-y-2">
          {/* Status Badge */}
          <div className="flex items-center gap-2">
            <div className={cn("flex items-center gap-1 px-2 py-1 rounded-md text-xs", statusInfo.bg)}>
              <StatusIcon className={cn("h-3 w-3", statusInfo.color, conversation.processing_status === 'processing' && "animate-spin")} />
              <span className={statusInfo.color}>{statusInfo.label}</span>
            </div>
            {conversation.total_examples && conversation.total_examples > 0 && (
              <Badge variant="secondary" className="text-xs">
                {conversation.total_examples} examples
              </Badge>
            )}
          </div>

          {/* Folder Info */}
          {currentFolder && (
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <FolderOpen className="h-3 w-3" />
              <span>{currentFolder.name}</span>
            </div>
          )}
        </div>
      </CardContent>

      <CardFooter className="pt-2" onClick={handleCardClick}>
        <div className="flex items-center justify-between w-full text-xs text-muted-foreground">
          <div className="flex items-center gap-1">
            <Calendar className="h-3 w-3" />
            <span>{formatDate(conversation.created_at)}</span>
          </div>
          {conversation.uploaded_by && (
            <div className="flex items-center gap-1">
              <User className="h-3 w-3" />
              <span>{conversation.uploaded_by}</span>
            </div>
          )}
        </div>
      </CardFooter>
    </Card>
  )
}