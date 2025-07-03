/**
 * FileGridView Component
 * 
 * Grid layout with thumbnail previews, multi-select with keyboard shortcuts,
 * bulk operations panel, file type indicators, and processing status.
 * 
 * Part of FeedMe v2.0 Phase 3B: Enhanced Folder Management
 */

'use client'

import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { FixedSizeGrid as Grid } from 'react-window'
import { 
  FileText, File, Upload, CheckCircle2, AlertCircle, Clock, 
  MoreHorizontal, Eye, Edit, Trash2, Download, Move, Filter,
  Grid3X3, List, Table, Search, X, ChevronDown
} from 'lucide-react'
import { useConversations, useActions, useUI } from '@/lib/stores/feedme-store'
import type { Conversation } from '@/lib/stores/feedme-store'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Separator } from '@/components/ui/separator'
import { Progress } from '@/components/ui/progress'

// Types
interface FileGridViewProps {
  height?: number
  className?: string
  onFileSelect?: (fileId: number) => void
  onFilePreview?: (fileId: number) => void
  onFileEdit?: (fileId: number) => void
  onFileDelete?: (fileId: number) => void
  onFileMove?: (fileIds: number[], targetFolderId: number) => void
  onBulkAction?: (action: string, fileIds: number[]) => void
  enableMultiSelect?: boolean
  enableBulkActions?: boolean
  showThumbnails?: boolean
  itemSize?: number
  columnsCount?: number
}

interface GridItemProps {
  columnIndex: number
  rowIndex: number
  style: React.CSSProperties
  data: {
    conversations: Conversation[]
    columnsCount: number
    onSelect: (id: number, event: React.MouseEvent) => void
    onPreview: (id: number) => void
    onEdit: (id: number) => void
    onDelete: (id: number) => void
    selectedIds: Set<number>
    enableMultiSelect: boolean
    showThumbnails: boolean
  }
}

// File Status Component
const FileStatus: React.FC<{ 
  status: Conversation['processing_status'], 
  progress?: number,
  size?: 'sm' | 'md' 
}> = ({ status, progress, size = 'md' }) => {
  const iconSize = size === 'sm' ? 'h-3 w-3' : 'h-4 w-4'
  
  switch (status) {
    case 'completed':
      return (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger>
              <CheckCircle2 className={cn(iconSize, 'text-green-500')} />
            </TooltipTrigger>
            <TooltipContent>
              <p>Processing completed</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )
    case 'processing':
      return (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger>
              <div className="flex items-center gap-1">
                <Clock className={cn(iconSize, 'text-blue-500 animate-spin')} />
                {progress !== undefined && (
                  <span className="text-xs">{Math.round(progress)}%</span>
                )}
              </div>
            </TooltipTrigger>
            <TooltipContent>
              <p>Processing in progress{progress ? ` (${Math.round(progress)}%)` : ''}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )
    case 'failed':
      return (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger>
              <AlertCircle className={cn(iconSize, 'text-red-500')} />
            </TooltipTrigger>
            <TooltipContent>
              <p>Processing failed</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )
    default:
      return (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger>
              <Upload className={cn(iconSize, 'text-gray-400')} />
            </TooltipTrigger>
            <TooltipContent>
              <p>Pending processing</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )
  }
}

// File Type Icon Component
const FileTypeIcon: React.FC<{ 
  filename: string, 
  mimeType?: string,
  size?: 'sm' | 'md' | 'lg' 
}> = ({ filename, mimeType, size = 'md' }) => {
  const iconSize = size === 'sm' ? 'h-4 w-4' : size === 'md' ? 'h-6 w-6' : 'h-8 w-8'
  
  if (mimeType?.startsWith('text/') || filename.endsWith('.txt') || filename.endsWith('.log')) {
    return <FileText className={cn(iconSize, 'text-blue-500')} />
  }
  
  return <File className={cn(iconSize, 'text-gray-500')} />
}

// Quality Score Badge
const QualityScoreBadge: React.FC<{ score?: number }> = ({ score }) => {
  if (score === undefined) return null
  
  const variant = score >= 0.8 ? 'default' : score >= 0.6 ? 'secondary' : 'destructive'
  const color = score >= 0.8 ? 'text-green-600' : score >= 0.6 ? 'text-yellow-600' : 'text-red-600'
  
  return (
    <Badge variant={variant} className={cn('text-xs', color)}>
      {Math.round(score * 100)}%
    </Badge>
  )
}

// Grid Item Component
const GridItem: React.FC<GridItemProps> = ({ columnIndex, rowIndex, style, data }) => {
  const {
    conversations,
    columnsCount,
    onSelect,
    onPreview,
    onEdit,
    onDelete,
    selectedIds,
    enableMultiSelect,
    showThumbnails
  } = data

  const index = rowIndex * columnsCount + columnIndex
  const conversation = conversations[index]
  
  if (!conversation) {
    return <div style={style} />
  }

  const isSelected = selectedIds.has(conversation.id)
  const [isHovered, setIsHovered] = useState(false)

  const handleClick = useCallback((e: React.MouseEvent) => {
    onSelect(conversation.id, e)
  }, [conversation.id, onSelect])

  const handlePreview = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    onPreview(conversation.id)
  }, [conversation.id, onPreview])

  const handleEdit = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    onEdit(conversation.id)
  }, [conversation.id, onEdit])

  const handleDelete = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    onDelete(conversation.id)
  }, [conversation.id, onDelete])

  return (
    <div style={style} className="p-1">
      <Card
        className={cn(
          'h-full cursor-pointer transition-all duration-200',
          'hover:shadow-md hover:scale-[1.02]',
          isSelected && 'ring-2 ring-accent shadow-md',
          'group'
        )}
        onClick={handleClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        <CardContent className="p-3 h-full flex flex-col">
          {/* Header */}
          <div className="flex items-start justify-between mb-2">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              {enableMultiSelect && (
                <Checkbox
                  checked={isSelected}
                  onChange={() => {}}
                  className="flex-shrink-0"
                  onClick={(e) => e.stopPropagation()}
                />
              )}
              <FileTypeIcon 
                filename={conversation.original_filename || 'unknown'} 
                size="sm"
              />
            </div>
            <div className="flex items-center gap-1">
              <FileStatus 
                status={conversation.processing_status} 
                size="sm"
              />
              {(isHovered || isSelected) && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <MoreHorizontal className="h-3 w-3" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={handlePreview}>
                      <Eye className="h-3 w-3 mr-2" />
                      Preview
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={handleEdit}>
                      <Edit className="h-3 w-3 mr-2" />
                      Edit
                    </DropdownMenuItem>
                    <DropdownMenuItem>
                      <Download className="h-3 w-3 mr-2" />
                      Download
                    </DropdownMenuItem>
                    <DropdownMenuItem>
                      <Move className="h-3 w-3 mr-2" />
                      Move
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem 
                      onClick={handleDelete}
                      className="text-destructive"
                    >
                      <Trash2 className="h-3 w-3 mr-2" />
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
          </div>

          {/* Thumbnail or Preview */}
          {showThumbnails && (
            <div className="flex-1 mb-2 min-h-[80px] bg-muted/30 rounded flex items-center justify-center">
              <FileTypeIcon 
                filename={conversation.original_filename || 'unknown'} 
                size="lg"
              />
            </div>
          )}

          {/* Content */}
          <div className="flex-1 min-h-0">
            <h4 className="text-sm font-medium mb-1 truncate" title={conversation.title}>
              {conversation.title}
            </h4>
            <p className="text-xs text-muted-foreground mb-2 line-clamp-2">
              {conversation.original_filename}
            </p>
            
            {/* Progress Bar for Processing */}
            {conversation.processing_status === 'processing' && conversation.examples_extracted !== undefined && (
              <Progress 
                value={conversation.examples_extracted} 
                className="h-1 mb-2" 
              />
            )}

            {/* Metadata */}
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>
                {conversation.examples_extracted || 0} examples
              </span>
              <QualityScoreBadge score={conversation.quality_score} />
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between mt-2 pt-2 border-t">
            <span className="text-xs text-muted-foreground">
              {new Date(conversation.created_at).toLocaleDateString()}
            </span>
            {conversation.updated_at && (
              <span className="text-xs text-muted-foreground">
                {new Date(conversation.updated_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

// Bulk Actions Panel
const BulkActionsPanel: React.FC<{
  selectedCount: number
  onAction: (action: string) => void
  onClear: () => void
}> = ({ selectedCount, onAction, onClear }) => {
  if (selectedCount === 0) return null

  return (
    <div className="flex items-center justify-between p-3 bg-accent/10 border rounded-lg">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">
          {selectedCount} file{selectedCount === 1 ? '' : 's'} selected
        </span>
        <Button variant="ghost" size="sm" onClick={onClear}>
          <X className="h-3 w-3" />
        </Button>
      </div>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => onAction('move')}>
          <Move className="h-3 w-3 mr-1" />
          Move
        </Button>
        <Button variant="outline" size="sm" onClick={() => onAction('download')}>
          <Download className="h-3 w-3 mr-1" />
          Download
        </Button>
        <Button 
          variant="outline" 
          size="sm" 
          onClick={() => onAction('delete')}
          className="text-destructive"
        >
          <Trash2 className="h-3 w-3 mr-1" />
          Delete
        </Button>
      </div>
    </div>
  )
}

// Main Component
export const FileGridView: React.FC<FileGridViewProps> = ({
  height = 600,
  className,
  onFileSelect,
  onFilePreview,
  onFileEdit,
  onFileDelete,
  onFileMove,
  onBulkAction,
  enableMultiSelect = true,
  enableBulkActions = true,
  showThumbnails = true,
  itemSize = 200,
  columnsCount = 4
}) => {
  const { items: conversations, isLoading } = useConversations()
  const { selectedConversations, viewMode } = useUI()
  const { selectConversation, selectAllConversations, setViewMode } = useActions()

  const [searchQuery, setSearchQuery] = useState('')
  const [sortBy, setSortBy] = useState<'name' | 'date' | 'size' | 'status'>('date')
  const [filterBy, setFilterBy] = useState<'all' | 'completed' | 'processing' | 'failed'>('all')
  
  const gridRef = useRef<Grid>(null)

  // Filter and sort conversations
  const filteredConversations = useMemo(() => {
    let filtered = [...conversations]

    // Search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase()
      filtered = filtered.filter(conv => 
        conv.title.toLowerCase().includes(query) ||
        (conv.original_filename || '').toLowerCase().includes(query)
      )
    }

    // Status filter
    if (filterBy !== 'all') {
      filtered = filtered.filter(conv => conv.processing_status === filterBy)
    }

    // Sort
    filtered.sort((a, b) => {
      switch (sortBy) {
        case 'name':
          return a.title.localeCompare(b.title)
        case 'date':
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        case 'size':
          return (b.examples_extracted || 0) - (a.examples_extracted || 0)
        case 'status':
          return (a.processing_status || '').localeCompare(b.processing_status || '')
        default:
          return 0
      }
    })

    return filtered
  }, [conversations, searchQuery, sortBy, filterBy])

  // Calculate grid dimensions
  const actualColumnsCount = Math.max(1, Math.floor((window.innerWidth - 100) / itemSize))
  const rowCount = Math.ceil(filteredConversations.length / actualColumnsCount)

  // Event handlers
  const handleSelect = useCallback((id: number, event: React.MouseEvent) => {
    if (enableMultiSelect && (event.ctrlKey || event.metaKey)) {
      const isSelected = selectedConversations.includes(id)
      selectConversation(id, !isSelected)
    } else if (enableMultiSelect && event.shiftKey && selectedConversations.length > 0) {
      // Shift-click multi-select
      const lastSelected = selectedConversations[selectedConversations.length - 1]
      const startIndex = filteredConversations.findIndex(c => c.id === lastSelected)
      const endIndex = filteredConversations.findIndex(c => c.id === id)
      
      const [start, end] = startIndex <= endIndex ? [startIndex, endIndex] : [endIndex, startIndex]
      
      for (let i = start; i <= end; i++) {
        selectConversation(filteredConversations[i].id, true)
      }
    } else {
      // Clear other selections and select this one
      selectedConversations.forEach(selectedId => {
        if (selectedId !== id) {
          selectConversation(selectedId, false)
        }
      })
      selectConversation(id, true)
      onFileSelect?.(id)
    }
  }, [enableMultiSelect, selectedConversations, selectConversation, onFileSelect, filteredConversations])

  const handlePreview = useCallback((id: number) => {
    onFilePreview?.(id)
  }, [onFilePreview])

  const handleEdit = useCallback((id: number) => {
    onFileEdit?.(id)
  }, [onFileEdit])

  const handleDelete = useCallback((id: number) => {
    if (window.confirm('Are you sure you want to delete this file?')) {
      onFileDelete?.(id)
    }
  }, [onFileDelete])

  const handleBulkAction = useCallback((action: string) => {
    onBulkAction?.(action, selectedConversations)
  }, [onBulkAction, selectedConversations])

  const handleClearSelection = useCallback(() => {
    selectAllConversations(false)
  }, [selectAllConversations])

  const handleSelectAll = useCallback(() => {
    const allSelected = filteredConversations.every(c => selectedConversations.includes(c.id))
    if (allSelected) {
      selectAllConversations(false)
    } else {
      filteredConversations.forEach(c => selectConversation(c.id, true))
    }
  }, [filteredConversations, selectedConversations, selectAllConversations, selectConversation])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
        e.preventDefault()
        handleSelectAll()
      }
      if (e.key === 'Escape') {
        handleClearSelection()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleSelectAll, handleClearSelection])

  const selectedIdsSet = useMemo(() => new Set(selectedConversations), [selectedConversations])

  const itemData = useMemo(() => ({
    conversations: filteredConversations,
    columnsCount: actualColumnsCount,
    onSelect: handleSelect,
    onPreview: handlePreview,
    onEdit: handleEdit,
    onDelete: handleDelete,
    selectedIds: selectedIdsSet,
    enableMultiSelect,
    showThumbnails
  }), [
    filteredConversations,
    actualColumnsCount,
    handleSelect,
    handlePreview,
    handleEdit,
    handleDelete,
    selectedIdsSet,
    enableMultiSelect,
    showThumbnails
  ])

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Toolbar */}
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-3 w-3 text-muted-foreground" />
            <Input
              placeholder="Search files..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-7 w-48"
            />
          </div>
          <Select value={filterBy} onValueChange={(value: any) => setFilterBy(value)}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All files</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
              <SelectItem value="processing">Processing</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
            </SelectContent>
          </Select>
          <Select value={sortBy} onValueChange={(value: any) => setSortBy(value)}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="date">Date</SelectItem>
              <SelectItem value="name">Name</SelectItem>
              <SelectItem value="size">Size</SelectItem>
              <SelectItem value="status">Status</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          {enableMultiSelect && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleSelectAll}
              disabled={filteredConversations.length === 0}
            >
              Select All
            </Button>
          )}
          <div className="flex items-center border rounded-md">
            <Button
              variant={viewMode === 'grid' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => setViewMode('grid')}
              className="rounded-r-none"
            >
              <Grid3X3 className="h-3 w-3" />
            </Button>
            <Button
              variant={viewMode === 'list' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => setViewMode('list')}
              className="rounded-none"
            >
              <List className="h-3 w-3" />
            </Button>
            <Button
              variant={viewMode === 'table' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => setViewMode('table')}
              className="rounded-l-none"
            >
              <Table className="h-3 w-3" />
            </Button>
          </div>
        </div>
      </div>

      {/* Bulk Actions */}
      {enableBulkActions && (
        <BulkActionsPanel
          selectedCount={selectedConversations.length}
          onAction={handleBulkAction}
          onClear={handleClearSelection}
        />
      )}

      {/* Grid Content */}
      <div className="flex-1 overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Clock className="h-8 w-8 animate-spin mx-auto mb-2 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">Loading files...</p>
            </div>
          </div>
        ) : filteredConversations.length > 0 ? (
          <Grid
            ref={gridRef}
            columnCount={actualColumnsCount}
            columnWidth={itemSize}
            height={height}
            rowCount={rowCount}
            rowHeight={itemSize}
            itemData={itemData}
            width="100%"
          >
            {GridItem}
          </Grid>
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <FileText className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
              <h3 className="text-lg font-medium mb-2">No files found</h3>
              <p className="text-sm text-muted-foreground mb-4">
                {searchQuery ? 'Try adjusting your search criteria' : 'Upload some files to get started'}
              </p>
              {searchQuery && (
                <Button variant="outline" onClick={() => setSearchQuery('')}>
                  Clear search
                </Button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Status Bar */}
      <div className="flex items-center justify-between p-2 border-t text-xs text-muted-foreground">
        <span>
          {filteredConversations.length} of {conversations.length} files
          {selectedConversations.length > 0 && ` · ${selectedConversations.length} selected`}
        </span>
        <span>
          {conversations.filter(c => c.processing_status === 'completed').length} completed ·{' '}
          {conversations.filter(c => c.processing_status === 'processing').length} processing ·{' '}
          {conversations.filter(c => c.processing_status === 'failed').length} failed
        </span>
      </div>
    </div>
  )
}

export default FileGridView