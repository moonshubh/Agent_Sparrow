/**
 * FolderTreeView Component
 * 
 * Hierarchical folder structure with expand/collapse functionality,
 * drag-and-drop between folders, context menus, and virtual scrolling.
 * 
 * Part of FeedMe v2.0 Phase 3B: Enhanced Folder Management
 */

'use client'

import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { FixedSizeTree as Tree } from 'react-window'
import { ChevronRight, ChevronDown, Folder, FolderOpen, MoreHorizontal, Plus, Edit2, Trash2, Move } from 'lucide-react'
import { useFeedMeStore, useActions, useFolders, useUI } from '@/lib/stores/feedme-store'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ContextMenu, ContextMenuContent, ContextMenuItem, ContextMenuSeparator, ContextMenuTrigger } from '@/components/ui/context-menu'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

// Types
interface TreeNode {
  id: number
  name: string
  description?: string
  parent_id?: number
  children: TreeNode[]
  isExpanded: boolean
  isSelected: boolean
  level: number
  conversation_count: number
  created_at: string
  updated_at: string
}

interface FolderTreeViewProps {
  height?: number
  className?: string
  onFolderSelect?: (folderId: number) => void
  onFolderCreate?: (parentId?: number) => void
  onFolderUpdate?: (folderId: number, updates: { name?: string; description?: string }) => void
  onFolderDelete?: (folderId: number) => void
  onFolderMove?: (folderId: number, newParentId?: number) => void
  enableDragDrop?: boolean
  enableContextMenu?: boolean
  showItemCounts?: boolean
}

interface TreeItemProps {
  index: number
  style: React.CSSProperties
  data: {
    nodes: TreeNode[]
    onToggle: (nodeId: number) => void
    onSelect: (nodeId: number) => void
    onContextMenu: (nodeId: number, event: React.MouseEvent) => void
    onEdit: (nodeId: number) => void
    onDelete: (nodeId: number) => void
    onMove: (sourceId: number, targetId: number) => void
    selectedNodes: Set<number>
    editingNode: number | null
    enableDragDrop: boolean
    enableContextMenu: boolean
    showItemCounts: boolean
  }
}

// Drag and Drop Types
interface DragState {
  isDragging: boolean
  draggedNode: TreeNode | null
  dropTarget: TreeNode | null
  dropPosition: 'before' | 'after' | 'inside' | null
}

// Tree Item Component
const TreeItem: React.FC<TreeItemProps> = ({ index, style, data }) => {
  const {
    nodes,
    onToggle,
    onSelect,
    onContextMenu,
    onEdit,
    onDelete,
    onMove,
    selectedNodes,
    editingNode,
    enableDragDrop,
    enableContextMenu,
    showItemCounts
  } = data

  const node = nodes[index]
  const [isHovered, setIsHovered] = useState(false)
  const [dragState, setDragState] = useState<DragState>({
    isDragging: false,
    draggedNode: null,
    dropTarget: null,
    dropPosition: null
  })

  const handleDragStart = useCallback((e: React.DragEvent, node: TreeNode) => {
    if (!enableDragDrop) return
    
    e.dataTransfer.setData('application/json', JSON.stringify(node))
    e.dataTransfer.effectAllowed = 'move'
    setDragState(prev => ({ ...prev, isDragging: true, draggedNode: node }))
  }, [enableDragDrop])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    if (!enableDragDrop) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [enableDragDrop])

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    if (!enableDragDrop) return
    e.preventDefault()
    setDragState(prev => ({ ...prev, dropTarget: node }))
  }, [enableDragDrop, node])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    if (!enableDragDrop) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX
    const y = e.clientY
    
    if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) {
      setDragState(prev => ({ ...prev, dropTarget: null, dropPosition: null }))
    }
  }, [enableDragDrop])

  const handleDrop = useCallback((e: React.DragEvent) => {
    if (!enableDragDrop) return
    e.preventDefault()
    
    try {
      const draggedData = JSON.parse(e.dataTransfer.getData('application/json')) as TreeNode
      if (draggedData.id !== node.id && draggedData.id !== node.parent_id) {
        onMove(draggedData.id, node.id)
      }
    } catch (error) {
      console.error('Failed to parse drag data:', error)
    }
    
    setDragState({
      isDragging: false,
      draggedNode: null,
      dropTarget: null,
      dropPosition: null
    })
  }, [enableDragDrop, node.id, node.parent_id, onMove])

  const handleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    onSelect(node.id)
  }, [node.id, onSelect])

  const handleToggle = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    onToggle(node.id)
  }, [node.id, onToggle])

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    if (!enableContextMenu) return
    e.preventDefault()
    onContextMenu(node.id, e)
  }, [enableContextMenu, node.id, onContextMenu])

  const isSelected = selectedNodes.has(node.id)
  const isDropTarget = dragState.dropTarget?.id === node.id
  const hasChildren = node.children.length > 0

  return (
    <div
      style={style}
      className={cn(
        'flex items-center gap-2 px-2 py-1 text-sm cursor-pointer transition-colors',
        'hover:bg-accent/50',
        isSelected && 'bg-accent text-accent-foreground',
        isDropTarget && 'bg-accent/70 ring-2 ring-accent',
        'select-none'
      )}
      draggable={enableDragDrop}
      onDragStart={(e) => handleDragStart(e, node)}
      onDragOver={handleDragOver}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={handleClick}
      onContextMenu={handleContextMenu}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Indentation */}
      <div style={{ width: `${node.level * 16}px` }} />
      
      {/* Toggle Button */}
      <Button
        variant="ghost"
        size="sm"
        className="h-4 w-4 p-0 hover:bg-transparent"
        onClick={handleToggle}
        disabled={!hasChildren}
      >
        {hasChildren ? (
          node.isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />
        ) : (
          <div className="h-3 w-3" />
        )}
      </Button>

      {/* Folder Icon */}
      <div className="flex-shrink-0">
        {node.isExpanded ? (
          <FolderOpen className="h-4 w-4 text-accent" />
        ) : (
          <Folder className="h-4 w-4 text-muted-foreground" />
        )}
      </div>

      {/* Folder Name */}
      <div className="flex-1 min-w-0">
        {editingNode === node.id ? (
          <Input
            className="h-6 px-1 py-0 text-xs"
            defaultValue={node.name}
            onBlur={(e) => {
              if (e.target.value.trim() !== node.name) {
                onEdit(node.id)
              }
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.currentTarget.blur()
              }
              if (e.key === 'Escape') {
                onEdit(-1) // Cancel edit
              }
            }}
            autoFocus
          />
        ) : (
          <span className="truncate">{node.name}</span>
        )}
      </div>

      {/* Item Count Badge */}
      {showItemCounts && node.conversation_count > 0 && (
        <Badge variant="secondary" className="text-xs h-5 px-1">
          {node.conversation_count}
        </Badge>
      )}

      {/* Context Menu Trigger */}
      {enableContextMenu && isHovered && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="h-6 w-6 p-0">
              <MoreHorizontal className="h-3 w-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onEdit(node.id)}>
              <Edit2 className="h-3 w-3 mr-2" />
              Rename
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onMove(node.id, node.parent_id)}>
              <Move className="h-3 w-3 mr-2" />
              Move
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem 
              onClick={() => onDelete(node.id)}
              className="text-destructive"
            >
              <Trash2 className="h-3 w-3 mr-2" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  )
}

// Main Component
export const FolderTreeView: React.FC<FolderTreeViewProps> = ({
  height = 400,
  className,
  onFolderSelect,
  onFolderCreate,
  onFolderUpdate,
  onFolderDelete,
  onFolderMove,
  enableDragDrop = true,
  enableContextMenu = true,
  showItemCounts = true
}) => {
  const folders = useFolders()
  const { selectedFolders } = useUI()
  const { toggleFolderExpanded, selectFolder } = useActions()
  
  const [editingNode, setEditingNode] = useState<number | null>(null)
  const [contextMenuNode, setContextMenuNode] = useState<number | null>(null)
  const treeRef = useRef<Tree>(null)

  // Transform folders to tree structure
  const treeData = useMemo(() => {
    const folderList = Object.values(folders)
    const nodeMap = new Map<number, TreeNode>()
    
    // Create nodes
    folderList.forEach(folder => {
      nodeMap.set(folder.id, {
        id: folder.id,
        name: folder.name,
        description: folder.description,
        parent_id: folder.parent_id,
        children: [],
        isExpanded: folder.isExpanded || false,
        isSelected: folder.isSelected || false,
        level: 0,
        conversation_count: folder.conversation_count || 0,
        created_at: folder.created_at,
        updated_at: folder.updated_at
      })
    })

    // Build tree structure
    const roots: TreeNode[] = []
    nodeMap.forEach(node => {
      if (node.parent_id) {
        const parent = nodeMap.get(node.parent_id)
        if (parent) {
          parent.children.push(node)
          node.level = parent.level + 1
        }
      } else {
        roots.push(node)
      }
    })

    // Flatten tree for virtual scrolling
    const flattenTree = (nodes: TreeNode[], level = 0): TreeNode[] => {
      const result: TreeNode[] = []
      
      nodes.forEach(node => {
        node.level = level
        result.push(node)
        
        if (node.isExpanded && node.children.length > 0) {
          result.push(...flattenTree(node.children, level + 1))
        }
      })
      
      return result
    }

    return flattenTree(roots)
  }, [folders])

  // Event handlers
  const handleToggle = useCallback((nodeId: number) => {
    toggleFolderExpanded(nodeId)
  }, [toggleFolderExpanded])

  const handleSelect = useCallback((nodeId: number) => {
    const isSelected = selectedFolders.includes(nodeId)
    selectFolder(nodeId, !isSelected)
    onFolderSelect?.(nodeId)
  }, [selectedFolders, selectFolder, onFolderSelect])

  const handleContextMenu = useCallback((nodeId: number, event: React.MouseEvent) => {
    setContextMenuNode(nodeId)
  }, [])

  const handleEdit = useCallback((nodeId: number) => {
    setEditingNode(nodeId === editingNode ? null : nodeId)
  }, [editingNode])

  const handleDelete = useCallback((nodeId: number) => {
    if (window.confirm('Are you sure you want to delete this folder?')) {
      onFolderDelete?.(nodeId)
    }
  }, [onFolderDelete])

  const handleMove = useCallback((sourceId: number, targetId: number) => {
    onFolderMove?.(sourceId, targetId)
  }, [onFolderMove])

  const handleCreateFolder = useCallback(() => {
    const parentId = selectedFolders.length === 1 ? selectedFolders[0] : undefined
    onFolderCreate?.(parentId)
  }, [selectedFolders, onFolderCreate])

  const selectedNodesSet = useMemo(() => new Set(selectedFolders), [selectedFolders])

  const itemData = useMemo(() => ({
    nodes: treeData,
    onToggle: handleToggle,
    onSelect: handleSelect,
    onContextMenu: handleContextMenu,
    onEdit: handleEdit,
    onDelete: handleDelete,
    onMove: handleMove,
    selectedNodes: selectedNodesSet,
    editingNode,
    enableDragDrop,
    enableContextMenu,
    showItemCounts
  }), [
    treeData,
    handleToggle,
    handleSelect,
    handleContextMenu,
    handleEdit,
    handleDelete,
    handleMove,
    selectedNodesSet,
    editingNode,
    enableDragDrop,
    enableContextMenu,
    showItemCounts
  ])

  return (
    <div className={cn('flex flex-col', className)}>
      {/* Header */}
      <div className="flex items-center justify-between p-2 border-b">
        <h3 className="text-sm font-medium">Folders</h3>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleCreateFolder}
                className="h-6 w-6 p-0"
              >
                <Plus className="h-3 w-3" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p>Create new folder</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      {/* Tree View */}
      <div className="flex-1 overflow-hidden">
        {treeData.length > 0 ? (
          <Tree
            ref={treeRef}
            height={height}
            itemCount={treeData.length}
            itemSize={28}
            itemData={itemData}
            width="100%"
          >
            {TreeItem}
          </Tree>
        ) : (
          <div className="flex items-center justify-center h-32 text-muted-foreground">
            <div className="text-center">
              <Folder className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No folders yet</p>
              <Button
                variant="outline"
                size="sm"
                onClick={handleCreateFolder}
                className="mt-2"
              >
                <Plus className="h-3 w-3 mr-1" />
                Create folder
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Context Menu */}
      {enableContextMenu && contextMenuNode && (
        <ContextMenu>
          <ContextMenuTrigger />
          <ContextMenuContent>
            <ContextMenuItem onClick={() => handleEdit(contextMenuNode)}>
              <Edit2 className="h-3 w-3 mr-2" />
              Rename
            </ContextMenuItem>
            <ContextMenuItem onClick={() => onFolderCreate?.(contextMenuNode)}>
              <Plus className="h-3 w-3 mr-2" />
              Create subfolder
            </ContextMenuItem>
            <ContextMenuSeparator />
            <ContextMenuItem onClick={() => handleMove(contextMenuNode, undefined)}>
              <Move className="h-3 w-3 mr-2" />
              Move to root
            </ContextMenuItem>
            <ContextMenuSeparator />
            <ContextMenuItem 
              onClick={() => handleDelete(contextMenuNode)}
              className="text-destructive"
            >
              <Trash2 className="h-3 w-3 mr-2" />
              Delete
            </ContextMenuItem>
          </ContextMenuContent>
        </ContextMenu>
      )}
    </div>
  )
}

export default FolderTreeView