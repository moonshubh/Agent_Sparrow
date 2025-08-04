/**
 * Simple Folder Context Menu
 * Uses absolute positioning relative to parent container
 */

'use client'

import React, { useEffect, useRef } from 'react'
import { Pencil, FolderPlus, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useFoldersActions } from '@/lib/stores/folders-store'

interface FolderContextMenuSimpleProps {
  folderId: number
  folderName: string
  isOpen: boolean
  onClose: () => void
  className?: string
}

export function FolderContextMenuSimple({
  folderId,
  folderName,
  isOpen,
  onClose,
  className
}: FolderContextMenuSimpleProps) {
  const menuRef = useRef<HTMLDivElement>(null)
  const foldersActions = useFoldersActions()

  useEffect(() => {
    if (!isOpen) return

    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        // Don't close if clicking on the trigger button
        const target = event.target as HTMLElement
        if (target.closest('[data-more-button]')) {
          return
        }
        onClose()
      }
    }

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    // Add event listeners
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleEscape)

    // Cleanup
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleEscape)
    }
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

  return (
    <div
      ref={menuRef}
      className={cn(
        "absolute right-0 top-6 z-50",
        "min-w-[180px] py-1",
        "bg-popover border rounded-md shadow-md",
        "animate-in fade-in-0 zoom-in-95 duration-200",
        className
      )}
      role="menu"
      aria-label={`Context menu for ${folderName}`}
    >
      {/* Rename */}
      <button
        className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground transition-colors"
        onClick={handleRename}
        role="menuitem"
      >
        <Pencil className="h-4 w-4" />
        <span>Rename</span>
      </button>

      {/* Add Subfolder */}
      <button
        className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground transition-colors"
        onClick={handleAddSubfolder}
        role="menuitem"
      >
        <FolderPlus className="h-4 w-4" />
        <span>Add Subfolder</span>
      </button>

      {/* Divider */}
      <div className="h-px bg-border my-1" />

      {/* Delete */}
      <button
        className="flex items-center gap-2 w-full px-3 py-2 text-sm text-destructive hover:bg-destructive/10 transition-colors"
        onClick={handleDelete}
        role="menuitem"
      >
        <Trash2 className="h-4 w-4" />
        <span>Delete Folder</span>
      </button>
    </div>
  )
}