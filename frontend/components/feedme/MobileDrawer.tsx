/**
 * MobileDrawer Component
 * 
 * Collapsible drawer for mobile folder navigation with:
 * - Touch-friendly folder tree
 * - Overlay with backdrop
 * - Gesture support for open/close
 * - Automatic close on selection
 */

'use client'

import React from 'react'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Menu, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { FolderPane } from './FolderPane'
import { useUIPanels, useUIActions } from '@/lib/stores/ui-store'

interface MobileDrawerProps {
  selectedFolderId: number | null
  onFolderSelect: (folderId: number | null) => void
  onFolderCreate: () => void
  className?: string
}

export function MobileDrawer({ 
  selectedFolderId, 
  onFolderSelect, 
  onFolderCreate,
  className 
}: MobileDrawerProps) {
  const { showMobileDrawer } = useUIPanels()
  const { toggleMobileDrawer } = useUIActions()

  const handleFolderSelect = (folderId: number | null) => {
    onFolderSelect(folderId)
    // Auto-close drawer after selection on mobile
    toggleMobileDrawer()
  }

  const handleFolderCreate = () => {
    onFolderCreate()
    // Keep drawer open for create folder modal
  }

  return (
    <>
      {/* Mobile Menu Button */}
      <Button
        variant="ghost"
        size="sm"
        onClick={toggleMobileDrawer}
        className={cn("md:hidden h-9 w-9 px-0", className)}
        title="Open folder navigation"
        data-testid="mobile-drawer-trigger"
      >
        <Menu className="h-4 w-4" />
        <span className="sr-only">Open folder navigation</span>
      </Button>

      {/* Mobile Drawer */}
      <Sheet open={showMobileDrawer} onOpenChange={toggleMobileDrawer}>
        <SheetContent side="left" className="w-80 p-0 feedme-mobile-drawer">
          <SheetHeader className="px-4 py-3 border-b">
            <div className="flex items-center justify-between">
              <SheetTitle className="text-lg font-semibold">
                Feed<span className="text-accent">Me</span> Folders
              </SheetTitle>
              <Button
                variant="ghost"
                size="sm"
                onClick={toggleMobileDrawer}
                className="h-6 w-6 p-0"
                title="Close folder navigation"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </SheetHeader>
          
          <div className="h-full">
            <FolderPane
              selectedFolderId={selectedFolderId}
              onFolderSelect={handleFolderSelect}
              onFolderCreate={handleFolderCreate}
              className="h-full border-0"
            />
          </div>
        </SheetContent>
      </Sheet>
    </>
  )
}

/**
 * Mobile Drawer Trigger Button
 * 
 * Standalone button for triggering mobile drawer from anywhere
 */
export function MobileDrawerTrigger({ className }: { className?: string }) {
  const { toggleMobileDrawer } = useUIActions()

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={toggleMobileDrawer}
      className={cn("md:hidden h-9 w-9 px-0", className)}
      title="Open folder navigation"
      data-testid="mobile-drawer-trigger-standalone"
    >
      <Menu className="h-4 w-4" />
      <span className="sr-only">Open folder navigation</span>
    </Button>
  )
}