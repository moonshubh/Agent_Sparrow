"use client"

import React, { useEffect, useState, useCallback, useMemo } from 'react'
import { useDebouncedCallback } from '@/lib/debounce'
import { Card } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from '@/components/ui/select'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Loader2, RefreshCw } from 'lucide-react'
import { useFoldersStore } from '@/lib/stores/folders-store'
import { cn } from '@/lib/utils'

interface ConversationSidebarProps {
  folderId?: number | null
  aiNote?: string
  onFolderChange: (folderId: number | null) => Promise<void>
  onSaveNote: (note: string) => Promise<void>
  onRegenerateNote?: () => Promise<void>
  onMarkReady?: () => Promise<void>
  isSavingFolder?: boolean
  isSavingNote?: boolean
  isMarkingReady?: boolean
}

export function ConversationSidebar({
  folderId,
  aiNote,
  onFolderChange,
  onSaveNote,
  onRegenerateNote,
  onMarkReady,
  isSavingFolder = false,
  isSavingNote = false,
  isMarkingReady = false,
}: ConversationSidebarProps) {
  const folders = useFoldersStore(state => state.folderTree)
  const loadFolders = useFoldersStore(state => state.actions.loadFolders)
  const [noteDraft, setNoteDraft] = useState(aiNote || '')
  const [noteTouched, setNoteTouched] = useState(false)
  const [folderValue, setFolderValue] = useState<string>('root')
  const [isRegenerating, setIsRegenerating] = useState(false)
  const [isNoteFocused, setIsNoteFocused] = useState(false)

  useEffect(() => { loadFolders().catch(() => {}) }, [loadFolders])

  useEffect(() => {
    if (folderId === null || folderId === undefined) {
      setFolderValue('root')
    } else {
      setFolderValue(String(folderId))
    }
  }, [folderId])

  useEffect(() => {
    if (!noteTouched) {
      setNoteDraft(aiNote || '')
    }
  }, [aiNote, noteTouched])

  const folderOptions = useMemo(() =>
    folders
      .filter(folder => folder.id !== 0)
      .map(folder => ({
        id: folder.id,
        name: folder.name || `Folder ${folder.id}`,
        color: folder.color || '#6b7280'
      })),
    [folders]
  )

  const handleSelectFolder = async (value: string) => {
    const previous = folderValue
    setFolderValue(value)
    const target = value === 'root' ? null : parseInt(value, 10)
    try {
      await onFolderChange(target)
    } catch (error) {
      setFolderValue(previous)
      throw error
    }
  }

  // Debounced auto-save for better performance
  const debouncedSaveNote = useDebouncedCallback(
    async (noteText: string) => {
      if (!noteText.trim()) return
      try {
        await onSaveNote(noteText.trim())
        setNoteTouched(false)
      } catch (error) {
        console.error('Failed to auto-save note:', error)
        // Keep noteTouched as true so user knows save failed
      }
    },
    2000 // 2 second debounce
  )

  const handleSaveNote = useCallback(async () => {
    try {
      await onSaveNote(noteDraft.trim())
      setNoteTouched(false)
    } catch (error) {
      console.error('Failed to save note:', error)
      // Keep noteTouched as true so user knows save failed
    }
  }, [noteDraft, onSaveNote])

  const handleRegenerateNote = useCallback(async () => {
    if (!onRegenerateNote) return
    setIsRegenerating(true)
    try {
      await onRegenerateNote()
    } catch (error) {
      console.error('Failed to regenerate note:', error)
    } finally {
      setIsRegenerating(false)
    }
  }, [onRegenerateNote])

  // Trigger debounced auto-save when note changes
  useEffect(() => {
    if (noteTouched && noteDraft.trim()) {
      debouncedSaveNote(noteDraft)
    }
  }, [noteDraft, noteTouched, debouncedSaveNote])

  return (
    <Card className="flex h-full flex-col border-border/60 bg-card shadow-sm">
      <ScrollArea className="h-full">
        <div className="space-y-6 p-5">
          <section className="space-y-2">
            <Label className="text-sm font-medium">
              Folder Assignment
            </Label>
            <Select value={folderValue} onValueChange={handleSelectFolder}>
              <SelectTrigger>
                <SelectValue placeholder="Choose folder" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="root">
                  <div className="flex items-center gap-2">
                    <div className="h-3 w-3 rounded-sm bg-gray-500" />
                    <span>Unassigned</span>
                  </div>
                </SelectItem>
                {folderOptions.map(folder => (
                  <SelectItem key={folder.id} value={String(folder.id)}>
                    <div className="flex items-center gap-2">
                      <div
                        className="h-3 w-3 rounded-sm"
                        style={{ backgroundColor: folder.color || '#6b7280' }}
                      />
                      <span>{folder.name}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {isSavingFolder && (
              <p className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" /> Updating folder…
              </p>
            )}
          </section>

          <Separator />

          <section className="space-y-2 flex-1">
            <div className="flex items-center justify-between group">
              <Label className="text-sm font-medium">AI Notes</Label>
              {onRegenerateNote && (
                <Button
                  size="icon"
                  variant="ghost"
                  className={cn(
                    "h-6 w-6 transition-opacity",
                    isNoteFocused || noteTouched ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                  )}
                  onClick={handleRegenerateNote}
                  disabled={isRegenerating}
                  title="Regenerate with AI"
                >
                  {isRegenerating ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="h-4 w-4" />
                  )}
                </Button>
              )}
            </div>
            <Textarea
              value={noteDraft}
              onChange={event => {
                setNoteDraft(event.target.value)
                setNoteTouched(true)
              }}
              onFocus={() => setIsNoteFocused(true)}
              onBlur={() => {
                setIsNoteFocused(false)
                // Save immediately on blur if there are changes
                if (noteTouched && noteDraft.trim()) {
                  handleSaveNote()
                }
              }}
              placeholder="Summaries generated by the AI model appear here."
              className="min-h-[240px] resize-y"
              aria-label="AI Notes"
              aria-describedby={noteTouched ? "auto-save-indicator" : undefined}
            />
            {noteTouched && (
              <p id="auto-save-indicator" className="text-xs text-muted-foreground">Auto-saving...</p>
            )}
          </section>

          {onMarkReady && (
            <>
              <Separator />
              <section className="space-y-2">
                <Label className="text-sm font-medium">Knowledge Base</Label>
                <p className="text-xs text-muted-foreground">
                  Mark this conversation as ready for the knowledge base after reviewing.
                </p>
                <Button
                  size="sm"
                  className="w-full"
                  onClick={onMarkReady}
                  disabled={isMarkingReady || isSavingFolder || folderValue === 'root'}
                >
                  {isMarkingReady && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Mark Ready for Knowledge Base
                </Button>
              </section>
            </>
          )}
        </div>
      </ScrollArea>
    </Card>
  )
}

export default ConversationSidebar
