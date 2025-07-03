/**
 * DragDropManager Component
 * 
 * Advanced drag-and-drop system with visual feedback, drop zones,
 * conflict resolution, and progress indicators for move operations.
 * 
 * Part of FeedMe v2.0 Phase 3B: Enhanced Folder Management
 */

'use client'

import React, { useState, useCallback, useRef, useEffect } from 'react'
import { 
  DragDropContext, 
  Droppable, 
  Draggable, 
  DropResult,
  DragStart,
  DragUpdate
} from '@hello-pangea/dnd'
import { 
  Folder, FolderOpen, FileText, Move, Copy, Trash2, 
  CheckCircle, AlertCircle, Clock, X, ArrowRight
} from 'lucide-react'
import { useActions, useConversations, useFolders } from '@/lib/stores/feedme-store'
import type { Conversation, Folder as FolderType } from '@/lib/stores/feedme-store'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'

// Types
interface DragDropManagerProps {
  className?: string
  onMoveComplete?: (movedItems: MoveOperation[]) => void
  onError?: (error: string) => void
  enableConflictResolution?: boolean
  enableBulkOperations?: boolean
  maxConcurrentOperations?: number
}

interface MoveOperation {
  type: 'file' | 'folder'
  sourceId: number
  targetId: number | null
  status: 'pending' | 'processing' | 'completed' | 'failed'
  progress: number
  error?: string
  item: Conversation | FolderType
}

interface ConflictResolution {
  sourceItem: Conversation | FolderType
  targetFolder: FolderType
  conflictType: 'duplicate_name' | 'permission_denied' | 'circular_reference'
  resolution: 'skip' | 'rename' | 'replace' | 'merge'
}

interface DropZoneProps {
  folderId: number | null
  folderName: string
  isActive: boolean
  isOver: boolean
  canDrop: boolean
  itemCount: number
  onDrop: (folderId: number | null) => void
}

// Drop Zone Component
const DropZone: React.FC<DropZoneProps> = ({
  folderId,
  folderName,
  isActive,
  isOver,
  canDrop,
  itemCount,
  onDrop
}) => {
  return (
    <Droppable droppableId={`folder-${folderId || 'root'}`} type="ITEM">
      {(provided, snapshot) => (
        <div
          ref={provided.innerRef}
          {...provided.droppableProps}
          className={cn(
            'border-2 border-dashed rounded-lg p-4 transition-all duration-200',
            'min-h-[80px] flex flex-col items-center justify-center',
            canDrop && isOver && 'border-accent bg-accent/10 scale-105',
            canDrop && !isOver && 'border-muted-foreground/30',
            !canDrop && 'border-muted-foreground/10 opacity-50',
            isActive && 'ring-2 ring-accent/50'
          )}
          onClick={() => canDrop && onDrop(folderId)}
        >
          <div className="flex items-center gap-2 mb-2">
            {folderId ? (
              isOver ? <FolderOpen className="h-6 w-6 text-accent" /> : <Folder className="h-6 w-6 text-muted-foreground" />
            ) : (
              <Folder className="h-6 w-6 text-muted-foreground" />
            )}
            <span className="font-medium">
              {folderName}
            </span>
          </div>
          
          {itemCount > 0 && (
            <Badge variant="secondary" className="text-xs">
              {itemCount} items
            </Badge>
          )}
          
          {isOver && canDrop && (
            <div className="mt-2 text-xs text-accent font-medium">
              Drop here to move
            </div>
          )}
          
          {!canDrop && isOver && (
            <div className="mt-2 text-xs text-destructive">
              Cannot drop here
            </div>
          )}
          
          {provided.placeholder}
        </div>
      )}
    </Droppable>
  )
}

// Draggable Item Component
const DraggableItem: React.FC<{
  item: Conversation | FolderType
  index: number
  type: 'file' | 'folder'
  isSelected: boolean
  onSelect: (id: number, selected: boolean) => void
}> = ({ item, index, type, isSelected, onSelect }) => {
  return (
    <Draggable draggableId={`${type}-${item.id}`} index={index}>
      {(provided, snapshot) => (
        <Card
          ref={provided.innerRef}
          {...provided.draggableProps}
          {...provided.dragHandleProps}
          className={cn(
            'mb-2 cursor-grab active:cursor-grabbing',
            snapshot.isDragging && 'rotate-2 shadow-lg z-50',
            isSelected && 'ring-2 ring-accent',
            'transition-all duration-200'
          )}
        >
          <CardContent className="p-3 flex items-center gap-3">
            <Checkbox
              checked={isSelected}
              onCheckedChange={(checked) => onSelect(item.id, !!checked)}
              onClick={(e) => e.stopPropagation()}
            />
            
            {type === 'folder' ? (
              <Folder className="h-4 w-4 text-accent flex-shrink-0" />
            ) : (
              <FileText className="h-4 w-4 text-blue-500 flex-shrink-0" />
            )}
            
            <div className="flex-1 min-w-0">
              <div className="font-medium text-sm truncate">
                {type === 'folder' ? item.name : (item as Conversation).title}
              </div>
              <div className="text-xs text-muted-foreground">
                {type === 'folder' 
                  ? `${(item as FolderType).conversation_count || 0} files`
                  : (item as Conversation).original_filename
                }
              </div>
            </div>
            
            {type === 'file' && (
              <div className="flex-shrink-0">
                {(item as Conversation).processing_status === 'completed' && (
                  <CheckCircle className="h-4 w-4 text-green-500" />
                )}
                {(item as Conversation).processing_status === 'processing' && (
                  <Clock className="h-4 w-4 text-blue-500 animate-spin" />
                )}
                {(item as Conversation).processing_status === 'failed' && (
                  <AlertCircle className="h-4 w-4 text-red-500" />
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </Draggable>
  )
}

// Move Operations Panel
const MoveOperationsPanel: React.FC<{
  operations: MoveOperation[]
  onCancel: (operationId: string) => void
  onRetry: (operationId: string) => void
  onClear: () => void
}> = ({ operations, onCancel, onRetry, onClear }) => {
  if (operations.length === 0) return null

  const inProgress = operations.filter(op => op.status === 'processing').length
  const completed = operations.filter(op => op.status === 'completed').length
  const failed = operations.filter(op => op.status === 'failed').length

  return (
    <Card className="mb-4">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-medium text-sm">Move Operations</h3>
          <div className="flex gap-2">
            <Badge variant="secondary">{inProgress} in progress</Badge>
            <Badge variant="default">{completed} completed</Badge>
            {failed > 0 && <Badge variant="destructive">{failed} failed</Badge>}
            <Button variant="ghost" size="sm" onClick={onClear}>
              <X className="h-3 w-3" />
            </Button>
          </div>
        </div>

        <div className="space-y-2 max-h-40 overflow-y-auto">
          {operations.map((operation, index) => (
            <div key={index} className="flex items-center gap-3 p-2 border rounded">
              <div className="flex-shrink-0">
                {operation.type === 'folder' ? (
                  <Folder className="h-4 w-4" />
                ) : (
                  <FileText className="h-4 w-4" />
                )}
              </div>
              
              <div className="flex-1 min-w-0">
                <div className="text-sm truncate">
                  {operation.type === 'folder' 
                    ? operation.item.name
                    : (operation.item as Conversation).title
                  }
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>Moving to:</span>
                  <ArrowRight className="h-3 w-3" />
                  <span>{operation.targetId ? `Folder ${operation.targetId}` : 'Root'}</span>
                </div>
              </div>

              <div className="flex-shrink-0">
                {operation.status === 'processing' && (
                  <div className="flex items-center gap-2">
                    <Progress value={operation.progress} className="w-16 h-2" />
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onCancel(`${operation.type}-${operation.sourceId}`)}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                )}
                {operation.status === 'completed' && (
                  <CheckCircle className="h-4 w-4 text-green-500" />
                )}
                {operation.status === 'failed' && (
                  <div className="flex items-center gap-1">
                    <AlertCircle className="h-4 w-4 text-red-500" />
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onRetry(`${operation.type}-${operation.sourceId}`)}
                    >
                      Retry
                    </Button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

// Conflict Resolution Dialog
const ConflictResolutionDialog: React.FC<{
  conflicts: ConflictResolution[]
  isOpen: boolean
  onResolve: (resolutions: ConflictResolution[]) => void
  onCancel: () => void
}> = ({ conflicts, isOpen, onResolve, onCancel }) => {
  const [resolutions, setResolutions] = useState<ConflictResolution[]>(conflicts)

  const updateResolution = useCallback((index: number, resolution: ConflictResolution['resolution']) => {
    setResolutions(prev => prev.map((r, i) => i === index ? { ...r, resolution } : r))
  }, [])

  const handleResolve = useCallback(() => {
    onResolve(resolutions)
  }, [resolutions, onResolve])

  return (
    <Dialog open={isOpen} onOpenChange={onCancel}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Resolve Conflicts</DialogTitle>
          <DialogDescription>
            Some items cannot be moved due to conflicts. Please choose how to resolve each conflict.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {conflicts.map((conflict, index) => (
            <Card key={index}>
              <CardContent className="p-4">
                <div className="flex items-start gap-3 mb-3">
                  <AlertCircle className="h-5 w-5 text-yellow-500 flex-shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <h4 className="font-medium text-sm mb-1">
                      {conflict.sourceItem.name} → {conflict.targetFolder.name}
                    </h4>
                    <p className="text-xs text-muted-foreground">
                      {conflict.conflictType === 'duplicate_name' && 'An item with this name already exists'}
                      {conflict.conflictType === 'permission_denied' && 'You do not have permission to move this item'}
                      {conflict.conflictType === 'circular_reference' && 'Cannot move folder into itself or its subfolder'}
                    </p>
                  </div>
                </div>

                <Select
                  value={conflict.resolution}
                  onValueChange={(value: ConflictResolution['resolution']) => updateResolution(index, value)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="skip">Skip this item</SelectItem>
                    {conflict.conflictType === 'duplicate_name' && (
                      <>
                        <SelectItem value="rename">Rename and move</SelectItem>
                        <SelectItem value="replace">Replace existing</SelectItem>
                        <SelectItem value="merge">Merge (folders only)</SelectItem>
                      </>
                    )}
                  </SelectContent>
                </Select>
              </CardContent>
            </Card>
          ))}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button onClick={handleResolve}>
            Apply Resolutions
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Main Component
export const DragDropManager: React.FC<DragDropManagerProps> = ({
  className,
  onMoveComplete,
  onError,
  enableConflictResolution = true,
  enableBulkOperations = true,
  maxConcurrentOperations = 5
}) => {
  const conversations = useConversations()
  const folders = useFolders()
  const { updateConversation, updateFolder } = useActions()

  const [draggedItems, setDraggedItems] = useState<Set<string>>(new Set())
  const [moveOperations, setMoveOperations] = useState<MoveOperation[]>([])
  const [conflicts, setConflicts] = useState<ConflictResolution[]>([])
  const [showConflictDialog, setShowConflictDialog] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<Set<number>>(new Set())
  const [selectedFolders, setSelectedFolders] = useState<Set<number>>(new Set())

  // Handle drag start
  const handleDragStart = useCallback((start: DragStart) => {
    const [type, id] = start.draggableId.split('-')
    const itemId = parseInt(id)
    
    if (enableBulkOperations) {
      const isSelected = type === 'file' 
        ? selectedFiles.has(itemId)
        : selectedFolders.has(itemId)
      
      if (!isSelected) {
        // If item being dragged is not selected, clear selection and select only this item
        if (type === 'file') {
          setSelectedFiles(new Set([itemId]))
          setSelectedFolders(new Set())
        } else {
          setSelectedFolders(new Set([itemId]))
          setSelectedFiles(new Set())
        }
      }
    }
    
    setDraggedItems(new Set([start.draggableId]))
  }, [enableBulkOperations, selectedFiles, selectedFolders])

  // Handle drag end
  const handleDragEnd = useCallback((result: DropResult) => {
    setDraggedItems(new Set())
    
    if (!result.destination) return

    const [sourceType, sourceId] = result.draggableId.split('-')
    const [, targetId] = result.destination.droppableId.split('-')
    const targetFolderId = targetId === 'root' ? null : parseInt(targetId)

    // Get items to move
    const itemsToMove: Array<{ type: 'file' | 'folder', id: number, item: Conversation | FolderType }> = []
    
    if (enableBulkOperations) {
      // Include all selected items of the same type
      if (sourceType === 'file') {
        selectedFiles.forEach(id => {
          const conversation = conversations.items.find(c => c.id === id)
          if (conversation) {
            itemsToMove.push({ type: 'file', id, item: conversation })
          }
        })
      } else {
        selectedFolders.forEach(id => {
          const folder = Object.values(folders).find(f => f.id === id)
          if (folder) {
            itemsToMove.push({ type: 'folder', id, item: folder })
          }
        })
      }
    } else {
      // Single item move
      const id = parseInt(sourceId)
      if (sourceType === 'file') {
        const conversation = conversations.items.find(c => c.id === id)
        if (conversation) {
          itemsToMove.push({ type: 'file', id, item: conversation })
        }
      } else {
        const folder = Object.values(folders).find(f => f.id === id)
        if (folder) {
          itemsToMove.push({ type: 'folder', id, item: folder })
        }
      }
    }

    // Check for conflicts
    const detectedConflicts: ConflictResolution[] = []
    
    itemsToMove.forEach(({ type, id, item }) => {
      // Check for circular reference (folders)
      if (type === 'folder' && targetFolderId) {
        const isCircular = checkCircularReference(id, targetFolderId, folders)
        if (isCircular) {
          detectedConflicts.push({
            sourceItem: item,
            targetFolder: Object.values(folders).find(f => f.id === targetFolderId)!,
            conflictType: 'circular_reference',
            resolution: 'skip'
          })
          return
        }
      }

      // Check for duplicate names
      const targetItems = targetFolderId 
        ? Object.values(folders).filter(f => f.parent_id === targetFolderId)
        : Object.values(folders).filter(f => !f.parent_id)
      
      const duplicateExists = targetItems.some(targetItem => 
        targetItem.name === item.name && targetItem.id !== id
      )
      
      if (duplicateExists) {
        detectedConflicts.push({
          sourceItem: item,
          targetFolder: Object.values(folders).find(f => f.id === targetFolderId) || { name: 'Root' } as FolderType,
          conflictType: 'duplicate_name',
          resolution: 'rename'
        })
      }
    })

    if (detectedConflicts.length > 0 && enableConflictResolution) {
      setConflicts(detectedConflicts)
      setShowConflictDialog(true)
      return
    }

    // Proceed with move operations
    performMoveOperations(itemsToMove, targetFolderId)
  }, [conversations.items, folders, enableBulkOperations, selectedFiles, selectedFolders, enableConflictResolution])

  // Check circular reference
  const checkCircularReference = useCallback((folderId: number, targetFolderId: number, folders: Record<number, FolderType>): boolean => {
    if (folderId === targetFolderId) return true
    
    const targetFolder = folders[targetFolderId]
    if (!targetFolder || !targetFolder.parent_id) return false
    
    return checkCircularReference(folderId, targetFolder.parent_id, folders)
  }, [])

  // Perform move operations
  const performMoveOperations = useCallback(async (
    itemsToMove: Array<{ type: 'file' | 'folder', id: number, item: Conversation | FolderType }>,
    targetFolderId: number | null
  ) => {
    const operations: MoveOperation[] = itemsToMove.map(({ type, id, item }) => ({
      type,
      sourceId: id,
      targetId: targetFolderId,
      status: 'pending' as const,
      progress: 0,
      item
    }))

    setMoveOperations(prev => [...prev, ...operations])

    // Process operations with concurrency limit
    const chunks = []
    for (let i = 0; i < operations.length; i += maxConcurrentOperations) {
      chunks.push(operations.slice(i, i + maxConcurrentOperations))
    }

    for (const chunk of chunks) {
      await Promise.all(chunk.map(async (operation) => {
        try {
          // Update operation status
          setMoveOperations(prev => prev.map(op => 
            op.sourceId === operation.sourceId && op.type === operation.type
              ? { ...op, status: 'processing' as const }
              : op
          ))

          // Simulate progress
          for (let progress = 0; progress <= 100; progress += 20) {
            setMoveOperations(prev => prev.map(op => 
              op.sourceId === operation.sourceId && op.type === operation.type
                ? { ...op, progress }
                : op
            ))
            await new Promise(resolve => setTimeout(resolve, 100))
          }

          // Perform the actual move
          if (operation.type === 'file') {
            updateConversation(operation.sourceId, { folder_id: targetFolderId })
          } else {
            updateFolder(operation.sourceId, { parent_id: targetFolderId })
          }

          // Mark as completed
          setMoveOperations(prev => prev.map(op => 
            op.sourceId === operation.sourceId && op.type === operation.type
              ? { ...op, status: 'completed' as const, progress: 100 }
              : op
          ))

        } catch (error) {
          setMoveOperations(prev => prev.map(op => 
            op.sourceId === operation.sourceId && op.type === operation.type
              ? { 
                  ...op, 
                  status: 'failed' as const, 
                  error: error instanceof Error ? error.message : 'Unknown error' 
                }
              : op
          ))
          onError?.(error instanceof Error ? error.message : 'Move operation failed')
        }
      }))
    }

    onMoveComplete?.(operations)
  }, [maxConcurrentOperations, updateConversation, updateFolder, onMoveComplete, onError])

  // Handle conflict resolution
  const handleConflictResolution = useCallback((resolutions: ConflictResolution[]) => {
    setShowConflictDialog(false)
    
    // Process items that don't need to be skipped
    const itemsToMove = resolutions
      .filter(r => r.resolution !== 'skip')
      .map(r => ({
        type: (r.sourceItem as any).title ? 'file' as const : 'folder' as const,
        id: r.sourceItem.id,
        item: r.sourceItem
      }))
    
    if (itemsToMove.length > 0) {
      const targetFolderId = resolutions[0]?.targetFolder.id || null
      performMoveOperations(itemsToMove, targetFolderId)
    }
    
    setConflicts([])
  }, [performMoveOperations])

  // Event handlers for selection
  const handleFileSelect = useCallback((id: number, selected: boolean) => {
    setSelectedFiles(prev => {
      const newSet = new Set(prev)
      if (selected) {
        newSet.add(id)
      } else {
        newSet.delete(id)
      }
      return newSet
    })
  }, [])

  const handleFolderSelect = useCallback((id: number, selected: boolean) => {
    setSelectedFolders(prev => {
      const newSet = new Set(prev)
      if (selected) {
        newSet.add(id)
      } else {
        newSet.delete(id)
      }
      return newSet
    })
  }, [])

  // Clean up completed operations
  const handleClearOperations = useCallback(() => {
    setMoveOperations(prev => prev.filter(op => op.status === 'processing'))
  }, [])

  const handleCancelOperation = useCallback((operationId: string) => {
    // In a real implementation, this would cancel the ongoing operation
    setMoveOperations(prev => prev.filter(op => `${op.type}-${op.sourceId}` !== operationId))
  }, [])

  const handleRetryOperation = useCallback((operationId: string) => {
    const [type, sourceId] = operationId.split('-')
    const operation = moveOperations.find(op => op.type === type && op.sourceId === parseInt(sourceId))
    
    if (operation) {
      performMoveOperations([{
        type: operation.type,
        id: operation.sourceId,
        item: operation.item
      }], operation.targetId)
    }
  }, [moveOperations, performMoveOperations])

  return (
    <div className={cn('space-y-4', className)}>
      <DragDropContext onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        {/* Move Operations Panel */}
        <MoveOperationsPanel
          operations={moveOperations}
          onCancel={handleCancelOperation}
          onRetry={handleRetryOperation}
          onClear={handleClearOperations}
        />

        {/* Drop Zones */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <DropZone
            folderId={null}
            folderName="Root Folder"
            isActive={false}
            isOver={false}
            canDrop={true}
            itemCount={conversations.items.filter(c => !c.folder_id).length}
            onDrop={() => {}}
          />
          
          {Object.values(folders).map(folder => (
            <DropZone
              key={folder.id}
              folderId={folder.id}
              folderName={folder.name}
              isActive={false}
              isOver={false}
              canDrop={true}
              itemCount={folder.conversation_count || 0}
              onDrop={() => {}}
            />
          ))}
        </div>

        {/* Draggable Items */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Files */}
          <div>
            <h3 className="font-medium mb-3">Files</h3>
            <Droppable droppableId="files" type="ITEM">
              {(provided) => (
                <div ref={provided.innerRef} {...provided.droppableProps}>
                  {conversations.items.map((conversation, index) => (
                    <DraggableItem
                      key={conversation.id}
                      item={conversation}
                      index={index}
                      type="file"
                      isSelected={selectedFiles.has(conversation.id)}
                      onSelect={handleFileSelect}
                    />
                  ))}
                  {provided.placeholder}
                </div>
              )}
            </Droppable>
          </div>

          {/* Folders */}
          <div>
            <h3 className="font-medium mb-3">Folders</h3>
            <Droppable droppableId="folders" type="ITEM">
              {(provided) => (
                <div ref={provided.innerRef} {...provided.droppableProps}>
                  {Object.values(folders).map((folder, index) => (
                    <DraggableItem
                      key={folder.id}
                      item={folder}
                      index={index}
                      type="folder"
                      isSelected={selectedFolders.has(folder.id)}
                      onSelect={handleFolderSelect}
                    />
                  ))}
                  {provided.placeholder}
                </div>
              )}
            </Droppable>
          </div>
        </div>
      </DragDropContext>

      {/* Conflict Resolution Dialog */}
      <ConflictResolutionDialog
        conflicts={conflicts}
        isOpen={showConflictDialog}
        onResolve={handleConflictResolution}
        onCancel={() => setShowConflictDialog(false)}
      />
    </div>
  )
}

export default DragDropManager