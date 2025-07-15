/**
 * FolderTreeItem Component - Enhanced with Active State & Color Logic
 * 
 * Apple/Google-level polish for folder tree items:
 * - Active highlighting with 20% lighter folder color background
 * - Color badge using exact folder color
 * - Smooth hover states and transitions
 * - Perfect accessibility with ARIA attributes
 * - Auto-hide on folder selection integration
 */

'use client'

import React, { useCallback, useState, useRef } from 'react'
import { ChevronRight, ChevronDown, Folder, FolderOpen, MoreHorizontal, MessageCircle } from 'lucide-react'
import { useFoldersActions } from '@/lib/stores/folders-store'
import { useUISidebar, useUIActions } from '@/lib/stores/ui-store'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { FolderContextMenu } from './FolderContextMenu'
import tinycolor from 'tinycolor2'

interface Folder {
  id: number
  name: string
  parent_id: number | null
  conversationCount?: number
  conversation_count?: number
  isExpanded?: boolean
  path?: string
  description?: string
  color?: string
  created_at: string | Date
  updated_at: string | Date
  children?: Folder[]
}

interface FolderTreeItemProps {
  folder: Folder
  level: number
  onSelect?: (folderId: number) => void
  onFolderSelect?: (folderId: number | null) => void
  className?: string
}

export function FolderTreeItem({ 
  folder, 
  level, 
  onSelect, 
  onFolderSelect,
  className 
}: FolderTreeItemProps) {
  const [isContextMenuOpen, setIsContextMenuOpen] = useState(false)
  const [contextMenuPosition, setContextMenuPosition] = useState({ x: 0, y: 0 })
  const [isHovered, setIsHovered] = useState(false)
  const moreButtonRef = useRef<HTMLButtonElement>(null)
  
  const foldersActions = useFoldersActions()
  const { activeFolderId } = useUISidebar()
  const { setActiveFolder, closeFolderPanel } = useUIActions()
  
  const isUnassignedFolder = folder.id === 0
  const isActive = activeFolderId === folder.id
  const folderColor = folder.color || '#2196f3'
  const conversationCount = folder.conversationCount || folder.conversation_count || 0

  // Calculate background colors using folder color
  const baseBackgroundColor = tinycolor(folderColor).setAlpha(0.15).toRgbString()
  const activeBackgroundColor = tinycolor(folderColor).setAlpha(0.25).toRgbString()
  const hoverBackgroundColor = tinycolor(folderColor).lighten(6).setAlpha(0.2).toRgbString()
  
  // Calculate text color for contrast
  const textColor = tinycolor(folderColor).isDark() ? '#ffffff' : '#000000'

  const handleToggle = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    if (isUnassignedFolder) return
    
    foldersActions.expandFolder(folder.id, !folder.isExpanded)
  }, [folder.id, folder.isExpanded, foldersActions, isUnassignedFolder])

  const handleSelect = useCallback(() => {
    // Set active folder in UI store
    setActiveFolder(folder.id)
    
    // Trigger external handlers
    onSelect?.(folder.id)
    onFolderSelect?.(folder.id)
    
    // Auto-hide folder panel after selection
    closeFolderPanel()
  }, [folder.id, onSelect, onFolderSelect, setActiveFolder, closeFolderPanel])

  const handleCreateSubfolder = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    foldersActions.openCreateModal(folder.id)
  }, [folder.id, foldersActions])

  const handleDeleteFolder = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    foldersActions.openDeleteModal(folder.id)
  }, [folder.id, foldersActions])

  const handleMoreClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    
    if (moreButtonRef.current) {
      const rect = moreButtonRef.current.getBoundingClientRect()
      
      // Position menu to the right of the button with small gap
      const menuX = rect.right + 4  // 4px gap to the right of button
      const menuY = rect.top
      
      setContextMenuPosition({
        x: menuX,
        y: menuY
      })
    }
    
    setIsContextMenuOpen(!isContextMenuOpen)
  }, [isContextMenuOpen])

  const handleContextMenuClose = useCallback(() => {
    setIsContextMenuOpen(false)
  }, [])

  return (
    <div 
      className={cn(
        "w-full transition-all duration-150",
        className
      )}
    >
      <div 
        className={cn(
          "flex items-center gap-2 px-2 py-1.5 cursor-pointer rounded-md group",
          "transition-colors duration-150",
          "focus-within:ring-1 focus-within:ring-accent/50",
          isUnassignedFolder && "border-b border-border/40 mb-2",
          // Use calculated background color for active state
          "relative"
        )}
        style={{ 
          paddingLeft: `${level * 16 + 8}px`,
          backgroundColor: isHovered ? hoverBackgroundColor : (isActive ? activeBackgroundColor : baseBackgroundColor),
          '--hover-color': hoverBackgroundColor,
          '--text-color': textColor
        } as React.CSSProperties & { '--hover-color': string; '--text-color': string }}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onClick={handleSelect}
        role="treeitem"
        aria-selected={isActive}
        aria-expanded={!isUnassignedFolder ? folder.isExpanded : undefined}
        aria-level={level + 1}
        data-active={isActive}
        data-testid={`folder-item-${folder.id}`}
      >
        {/* Expand/Collapse Button */}
        {!isUnassignedFolder && (
          <Button
            variant="ghost"
            size="sm"
            className="h-4 w-4 p-0 hover:bg-mb-blue-300/20 transition-colors duration-150"
            onClick={handleToggle}
            aria-label={folder.isExpanded ? 'Collapse folder' : 'Expand folder'}
          >
            {folder.isExpanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </Button>
        )}

        {/* Folder Icon */}
        {isUnassignedFolder ? (
          <MessageCircle className="h-4 w-4 text-accent ml-6" aria-label="All conversations" />
        ) : folder.isExpanded ? (
          <FolderOpen className="h-4 w-4 text-blue-500" />
        ) : (
          <Folder className="h-4 w-4 text-blue-500" />
        )}

        {/* Remove color dot - using full row color instead */}

        {/* Folder Name */}
        <span className={cn(
          "flex-1 text-sm truncate",
          isUnassignedFolder && "font-medium text-accent",
          isActive && "font-medium"
        )}>
          {folder.name}
        </span>

        {/* Conversation Count Badge - Hover to reveal */}
        <Badge 
          variant="secondary" 
          data-badge
          className={cn(
            "text-xs h-5 px-1.5 transition-opacity duration-200",
            isActive 
              ? "bg-white/20 text-current border-current/20" 
              : "bg-accent/20 text-accent border-accent/30",
            isHovered ? "opacity-100" : "opacity-0"
          )}
        >
          {conversationCount}
        </Badge>

        {/* More Actions Menu - Hover to reveal with custom context menu */}
        {!isUnassignedFolder && (
          <div className="relative">
            <Button 
              ref={moreButtonRef}
              variant="ghost" 
              size="sm" 
              data-more-button
              className={cn(
                "h-6 w-6 p-0 hover:bg-mb-blue-300/20 transition-all duration-200",
                isHovered ? "opacity-100" : "opacity-0"
              )}
              onClick={handleMoreClick}
              aria-label={`More actions for ${folder.name}`}
            >
              <MoreHorizontal className="h-3 w-3" />
            </Button>
            
            <FolderContextMenu
              folderId={folder.id}
              folderName={folder.name}
              isOpen={isContextMenuOpen}
              onClose={handleContextMenuClose}
              triggerRef={moreButtonRef}
              position={contextMenuPosition}
            />
          </div>
        )}
      </div>
    </div>
  )
}