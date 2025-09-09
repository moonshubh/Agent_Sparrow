/**
 * FolderContextMenu Component - Right-Aligned Context Menu with Apple/Google-level Polish
 * 
 * Features:
 * - Right-aligned positioning (left: 100% + 8px)
 * - Enhanced contrast with WCAG AA compliance
 * - Lucide icons for actions
 * - Outside-click and Esc key handling
 * - Proper keyboard navigation
 */

'use client'

import React, { useState, useRef } from 'react'
import { Pencil, FolderPlus, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { useOutsideClick } from '@/hooks/useOutsideClick'
import { useFoldersActions } from '@/lib/stores/folders-store'

interface FolderContextMenuProps {
  folderId: number
  folderName: string
  isOpen: boolean
  onClose: () => void
  triggerRef: React.RefObject<HTMLElement>
  position?: { x: number; y: number }
  className?: string
}

export function FolderContextMenu({
  folderId,
  folderName,
  isOpen,
  onClose,
  triggerRef,
  position,
  className
}: FolderContextMenuProps) {
  const foldersActions = useFoldersActions()
  
  // Outside click detection
  const menuRef = useOutsideClick({
    enabled: isOpen,
    excludeElements: [triggerRef],
    onClickOutside: onClose
  })

  // Keyboard handling
  React.useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  const handleRename = () => {
    foldersActions.openEditModal(folderId)
    onClose()
  }

  const handleAddSubfolder = () => {
    foldersActions.openCreateModal(folderId)
    onClose()
  }

  const handleDelete = () => {
    foldersActions.openDeleteModal(folderId)
    onClose()
  }

  if (!isOpen) return null

  // Calculate position based on trigger element
  const menuStyle: React.CSSProperties = {}
  if (triggerRef.current) {
    const rect = triggerRef.current.getBoundingClientRect()
    const menuWidth = 160 // min-width
    const menuHeight = 120 // approximate height
    const viewportWidth = window.innerWidth
    const viewportHeight = window.innerHeight
    
    // Position to the right of the button, but flip to left if not enough space
    let left = rect.right + 8
    if (left + menuWidth > viewportWidth - 20) {
      left = rect.left - menuWidth - 8
    }
    
    // Position at the same level as button, but adjust if too close to bottom
    let top = rect.top
    if (top + menuHeight > viewportHeight - 20) {
      top = viewportHeight - menuHeight - 20
    }
    
    menuStyle.left = `${left}px`
    menuStyle.top = `${top}px`
  } else if (position) {
    menuStyle.left = `${position.x}px`
    menuStyle.top = `${position.y}px`
  }

  return (
    <div
      ref={menuRef}
      className={cn(
        "fixed z-[300] min-w-[160px]",
        "border rounded-md shadow-lg",
        "animate-in fade-in-0 zoom-in-95 duration-200",
        // Enhanced contrast background and border
        "backdrop-blur-sm bg-gray-900/95 border-white/[0.08]",
        className
      )}
      style={menuStyle}
      role="menu"
      aria-label={`Context menu for ${folderName}`}
    >
      <div className="py-1">
        {/* Rename */}
        <Button
          variant="ghost"
          className={cn(
            "w-full justify-start px-3 py-2 h-auto",
            "text-white/90 hover:text-white",
            "hover:bg-white/10 transition-colors duration-150",
            "rounded-none border-0"
          )}
          onClick={handleRename}
          role="menuitem"
        >
          <Pencil className="h-4 w-4 mr-3 text-blue-400" />
          <span className="text-sm">Rename</span>
        </Button>

        {/* Add Subfolder */}
        <Button
          variant="ghost"
          className={cn(
            "w-full justify-start px-3 py-2 h-auto",
            "text-white/90 hover:text-white",
            "hover:bg-white/10 transition-colors duration-150",
            "rounded-none border-0"
          )}
          onClick={handleAddSubfolder}
          role="menuitem"
        >
          <FolderPlus className="h-4 w-4 mr-3 text-green-400" />
          <span className="text-sm">Add Subfolder</span>
        </Button>

        {/* Delete */}
        <Button
          variant="ghost"
          className={cn(
            "w-full justify-start px-3 py-2 h-auto",
            "text-red-300 hover:text-red-200",
            "hover:bg-red-500/20 transition-colors duration-150",
            "rounded-none border-0"
          )}
          onClick={handleDelete}
          role="menuitem"
        >
          <Trash2 className="h-4 w-4 mr-3" />
          <span className="text-sm">Delete Folder</span>
        </Button>
      </div>
    </div>
  )
}