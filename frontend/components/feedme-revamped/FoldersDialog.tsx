"use client"

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { FolderPlus, Trash2 } from 'lucide-react'
import FolderBits from './FolderBits'
import { useFoldersStore, type Folder } from '@/lib/stores/folders-store'
import { useUIStore } from '@/lib/stores/ui-store'

type Props = { isOpen: boolean; onClose: () => void }

export default function FoldersDialog({ isOpen, onClose }: Props) {
  const actions = useFoldersStore(s => s.actions)
  const folderTree = useFoldersStore(s => s.folderTree)
  const isLoading = useFoldersStore(s => s.isLoading)
  const showToast = useUIStore(s => s.actions.showToast)

  const [createOpen, setCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Folder | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editingName, setEditingName] = useState('')

  const renameInputRef = useRef<HTMLInputElement | null>(null)
  const renamingRef = useRef(false)

  useEffect(() => {
    if (isOpen) actions.loadFolders().catch(() => {})
  }, [isOpen, actions])

  useEffect(() => {
    if (editingId === null) {
      renameInputRef.current = null
      return
    }
    const node = renameInputRef.current
    if (node) {
      const currentId = editingId
      requestAnimationFrame(() => {
        if (editingId === currentId) {
          node.focus()
          node.select()
        }
      })
    }
  }, [editingId])

  const flatList = useMemo(() => folderTree, [folderTree])

  const startRename = useCallback((folder: Folder) => {
    setEditingId(folder.id)
    setEditingName(folder.name)
  }, [])

  const cancelRename = useCallback(() => {
    setEditingId(null)
    setEditingName('')
  }, [])

  const commitRename = useCallback(async () => {
    if (editingId === null) return
    if (renamingRef.current) return

    const folder = flatList.find(item => item.id === editingId)
    if (!folder) {
      cancelRename()
      return
    }

    const trimmed = editingName.trim()
    if (!trimmed) {
      showToast({
        title: 'Folder name required',
        description: 'Folder names must include at least one character.',
        duration: 3800,
      })
      setEditingName(folder.name)
      cancelRename()
      return
    }

    if (trimmed === folder.name) {
      cancelRename()
      return
    }

    try {
      renamingRef.current = true
      await actions.updateFolder(folder.id, { name: trimmed })
      cancelRename()
    } catch (error) {
      console.error('Failed to rename folder', error)
      showToast({
        title: 'Rename failed',
        description: 'We could not rename that folder. Please try again.',
        duration: 4200,
      })
      setEditingName(folder.name)
      cancelRename()
    } finally {
      renamingRef.current = false
    }
  }, [editingId, editingName, actions, flatList, cancelRename, showToast])

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-[1000px] w-[1000px] p-0 overflow-hidden">
        <div className="flex items-center justify-between px-6 pr-16 pt-6 pb-3">
          <DialogHeader className="p-0">
            <DialogTitle>Folders</DialogTitle>
          </DialogHeader>
          <Button size="sm" onClick={() => setCreateOpen(true)} className="mr-2 gap-2">
            <FolderPlus className="h-4 w-4" /> Create New
          </Button>
        </div>
        <Separator />
        <section className="min-h-[560px] max-h-[560px] overflow-y-auto p-6">
          {isLoading && <p className="text-sm text-muted-foreground">Loading folders…</p>}
          {!isLoading && flatList.length === 0 && (
            <p className="text-sm text-muted-foreground">No folders yet. Create one to get started.</p>
          )}
          {!isLoading && flatList.length > 0 && (
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-6">
              {flatList.map(folder => {
                  const isEditing = editingId === folder.id
                  const folderColor = folder.color && folder.color.trim() ? folder.color : '#0095ff'
                  const docsCount = typeof folder.conversationCount === 'number'
                    ? folder.conversationCount
                    : typeof (folder as any).conversation_count === 'number'
                      ? (folder as any).conversation_count
                      : undefined
                  return (
                    <li
                      key={folder.id}
                      className="group relative flex min-h-[240px] flex-col items-center rounded-2xl border border-border/40 bg-background/70 px-4 pb-6 pt-4 shadow-sm transition hover:-translate-y-1 hover:border-border"
                    >
                      <div className="flex w-full justify-end">
                        <button
                          type="button"
                          onClick={event => {
                            event.stopPropagation()
                            setDeleteTarget(folder)
                          }}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-background/80 text-muted-foreground opacity-0 transition hover:text-destructive focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 group-hover:opacity-100"
                          aria-label={`Delete ${folder.name}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>

                      <div className="mt-1 flex w-full justify-center">
                        <div className="relative inline-flex">
                          {typeof docsCount === 'number' && (
                            <span className="pointer-events-none absolute bottom-1 right-1 z-10 text-[11px] font-semibold text-foreground opacity-0 transition group-hover:opacity-100">
                              {docsCount}
                            </span>
                          )}
                          <FolderBits color={folderColor} className="transition-transform duration-300" size={1.08} />
                        </div>
                      </div>

                      <div className="mt-6 flex w-full flex-col items-center gap-2">
                        {isEditing ? (
                          <Input
                            ref={node => {
                              if (isEditing) renameInputRef.current = node
                            }}
                            value={editingName}
                            onChange={e => setEditingName(e.target.value)}
                            onBlur={() => {
                              void commitRename()
                            }}
                            onKeyDown={e => {
                              if (e.key === 'Enter') {
                                e.preventDefault()
                                void commitRename()
                              } else if (e.key === 'Escape') {
                                e.preventDefault()
                                setEditingName(folder.name)
                                cancelRename()
                              }
                            }}
                            className="h-9 w-full rounded-lg border border-border/70 bg-background/80 text-center text-sm font-medium shadow-sm focus-visible:ring-2 focus-visible:ring-ring/30"
                            placeholder="Folder name"
                          />
                        ) : (
                          <span
                            onDoubleClick={() => startRename(folder)}
                            title="Double-click to rename"
                            className="cursor-text text-sm font-semibold text-foreground/90 transition hover:text-foreground"
                          >
                            {folder.name}
                          </span>
                        )}
                      </div>
                    </li>
                  )
              })}
            </ul>
          )}
        </section>

        <CreateOrEditFolder
          title="Create Folder"
          open={createOpen}
          onOpenChange={setCreateOpen}
          onSubmit={async (name, color) => {
            await actions.createFolder({ name, color })
            setCreateOpen(false)
          }}
        />

        <ConfirmDelete
          open={!!deleteTarget}
          name={deleteTarget?.name || ''}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={async () => {
            if (deleteTarget) await actions.deleteFolder(deleteTarget.id)
            setDeleteTarget(null)
          }}
        />
      </DialogContent>
    </Dialog>
  )
}

// Small components
function CreateOrEditFolder({ title, open, onOpenChange, onSubmit, initialName = '', initialColor = '#0095ff' }: {
  title: string
  open: boolean
  onOpenChange: (v: boolean) => void
  onSubmit: (name: string, color?: string) => Promise<void>
  initialName?: string
  initialColor?: string
}) {
  const [name, setName] = useState(initialName)
  const [color, setColor] = useState(initialColor)

  useEffect(() => {
    setName(initialName)
    setColor(initialColor)
  }, [initialName, initialColor, open])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>Set a name and color for the folder.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <label className="text-sm">Name</label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="Folder name" className="mt-1" />
          </div>
          <div>
            <label className="text-sm">Color</label>
            <div className="mt-2 flex flex-wrap gap-2">
              {['#0095ff', '#38b6ff', '#10b981', '#f59e0b', '#ef4444', '#a78bfa', '#f472b6', '#6b7280'].map(c => (
                <button
                  key={c}
                  className="h-6 w-6 rounded-full border"
                  style={{ backgroundColor: c, borderColor: 'rgba(255,255,255,0.25)' }}
                  onClick={() => setColor(c)}
                  aria-label={`color ${c}`}
                ></button>
              ))}
              <input type="color" value={color} onChange={e => setColor(e.target.value)} className="h-6 w-10 rounded" />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!name.trim()} onClick={() => onSubmit(name.trim(), color)}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ConfirmDelete({ open, name, onCancel, onConfirm }: { open: boolean; name: string; onCancel: () => void; onConfirm: () => Promise<void> }) {
  return (
    <Dialog open={open} onOpenChange={onCancel}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>Delete Folder</DialogTitle>
          <DialogDescription>This action cannot be undone.</DialogDescription>
        </DialogHeader>
        <p>Are you sure you want to delete “{name}”?</p>
        <DialogFooter>
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={onConfirm}>
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
