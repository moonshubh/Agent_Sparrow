"use client"

import React, { useEffect, useMemo, useState } from 'react'
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupContent,
  SidebarSeparator,
} from '@/components/ui/sidebar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Folder, Edit3, ArrowLeft, FolderOpen, BarChart3, Upload } from 'lucide-react'
import { useUIActions } from '@/lib/stores/ui-store'
import { UploadPdfPopover } from '@/components/feedme/UploadPdfPopover'
import { listFolders, assignConversationsToFolderSupabase } from '@/lib/feedme-api'

type Props = {
  side?: 'left' | 'right'
  conversationId: number
  title: string
  processingMethod?: string
  extractionConfidence?: number | null
  approvalStatus?: 'pending' | 'approved' | 'rejected' | 'processed' | 'published'
  extractedText?: string
  folderId?: number | null
  onTitleChange?: (title: string) => void
}

export function ConversationInfoSidebar({
  side = 'right',
  conversationId,
  title,
  processingMethod,
  extractionConfidence,
  approvalStatus,
  extractedText,
  folderId,
  onTitleChange,
}: Props) {
  const ui = useUIActions()
  const [folders, setFolders] = useState<Array<{ id: number; name: string; color: string }>>([])
  const [currentFolder, setCurrentFolder] = useState<number | null | undefined>(folderId)
  const [saving, setSaving] = useState(false)
  const [editingTitle, setEditingTitle] = useState(false)
  const [pendingTitle, setPendingTitle] = useState(title)

  useEffect(() => { setCurrentFolder(folderId ?? null) }, [folderId])
  useEffect(() => { if (!editingTitle) setPendingTitle(title) }, [title, editingTitle])

  useEffect(() => {
    (async () => {
      try {
        const resp = await listFolders()
        setFolders(resp.folders.map(f => ({ id: f.id, name: f.name, color: f.color })))
      } catch (e) {
        console.warn('Failed to load folders', e)
      }
    })()
  }, [])

  const stats = useMemo(() => {
    if (!extractedText) return null
    // Convert a small subset of Markdown/HTML to plain text for counts
    let plain = extractedText
    plain = plain.replace(/```[\s\s]*?```/g, ' ') // code fences
    plain = plain.replace(/`([^`]+)`/g, '$1') // inline code
    plain = plain.replace(/^#{1,6}\s+/gm, '') // headings
    plain = plain.replace(/\*\*([^*]+)\*\*/g, '$1').replace(/\*([^*]+)\*/g, '$1') // bold/italic
    plain = plain.replace(/!\[[^\]]*\]\([^)]*\)/g, ' ') // images
    plain = plain.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1 ($2)') // links
    plain = plain.replace(/<br\s*\/?>(\s*)/gi, '\n') //<br>
    plain = plain.replace(/<[^>]+>/g, '') // strip html tags
    const words = plain.trim().split(/\s+/).filter(Boolean).length
    const chars = plain.length
    const paras = plain.split(/\n\n+/).filter(p => p.trim().length > 0).length || 1
    const minRead = Math.max(1, Math.round(words / 200))
    return { words, chars, paras, minRead }
  }, [extractedText])

  const pmLabel = useMemo(() => {
    switch ((processingMethod || '').toLowerCase()) {
      case 'pdf_ocr': return 'PDF OCR'
      case 'pdf_ai': return 'AI PDF'
      case 'manual_text': return 'Manual Entry'
      case 'text_paste': return 'Text Paste'
      default: return 'Unknown'
    }
  }, [processingMethod])

  const approvalColor = useMemo(() => {
    switch (approvalStatus) {
      case 'approved': return 'bg-green-100 text-green-700 border-green-300'
      case 'rejected': return 'bg-red-100 text-red-700 border-red-300'
      case 'published': return 'bg-blue-100 text-blue-700 border-blue-300'
      case 'processed': return 'bg-amber-100 text-amber-700 border-amber-300'
      default: return 'bg-yellow-100 text-yellow-700 border-yellow-300'
    }
  }, [approvalStatus])

  const handleAssign = async (val: string) => {
    const fid = val === 'root' ? null : parseInt(val, 10)
    setSaving(true)
    try {
      await assignConversationsToFolderSupabase(fid, [conversationId])
      setCurrentFolder(fid)
    } catch (e) {
      console.error('Failed to assign folder', e)
    } finally {
      setSaving(false)
    }
  }

  const startEdit = () => {
    const evt = new CustomEvent('feedme:toggle-edit', { detail: { conversationId, action: 'start' } })
    document.dispatchEvent(evt)
  }

  const saveTitle = async () => {
    if (!pendingTitle || pendingTitle === title) { setEditingTitle(false); return }
    setSaving(true)
    try {
      await fetch(`/api/v1/feedme/conversations/${conversationId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: pendingTitle })
      })
      onTitleChange?.(pendingTitle)
      setEditingTitle(false)
    } catch (e) {
      console.error('Failed to update title', e)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Sidebar side={side} variant="floating" collapsible="none" className="w-[20rem] h-screen">
      <SidebarHeader>
        <div className="px-2 pt-2 pr-2">
          <div className="flex items-center justify-between">
            <div className="text-xs text-muted-foreground mb-1">Ticket</div>
            <Button variant="ghost" size="sm" onClick={() => ui.selectConversation(null)} className="h-7 px-2">
              <ArrowLeft className="h-4 w-4" />
              <span className="sr-only">Back</span>
            </Button>
          </div>
          {editingTitle ? (
            <div className="flex items-center gap-2 mt-1">
              <input
                className="text-base font-medium bg-background border rounded px-2 py-1 w-full"
                value={pendingTitle}
                onChange={(e) => setPendingTitle(e.target.value)}
              />
              <Button size="sm" onClick={saveTitle} disabled={saving}>Save</Button>
              <Button variant="outline" size="sm" onClick={() => { setEditingTitle(false); setPendingTitle(title) }} disabled={saving}>Cancel</Button>
            </div>
          ) : (
            <div className="mt-1 flex items-start justify-between gap-2 pr-2">
              <div className="text-base font-semibold leading-snug break-words break-all hyphens-auto whitespace-normal flex-1 min-w-0">
                {title}
              </div>
              <Button variant="outline" size="sm" onClick={() => setEditingTitle(true)} className="h-7 px-2">
                <Edit3 className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Tags</SidebarGroupLabel>
          <SidebarGroupContent className="px-2 flex flex-wrap gap-2">
            <Badge variant="secondary" className="bg-emerald-100 text-emerald-700 border border-emerald-300">{pmLabel}</Badge>
            <Badge variant="secondary" className="bg-sky-100 text-sky-700 border border-sky-300">
              {extractionConfidence != null ? `High Confidence (${Math.round(extractionConfidence * 100)}%)` : 'Confidence N/A'}
            </Badge>
            <Badge variant="secondary" className={approvalColor}>
              {approvalStatus ? approvalStatus.replace(/_/g,' ').replace(/\b\w/g, s=>s.toUpperCase()) : 'Pending Review'}
            </Badge>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarSeparator />

        <SidebarGroup>
          <SidebarGroupLabel>Folder</SidebarGroupLabel>
          <SidebarGroupContent className="px-2">
            <div className="flex items-center gap-2">
              <Folder className="h-4 w-4" />
              <Select onValueChange={handleAssign} value={currentFolder == null ? 'root' : String(currentFolder)} disabled={saving}>
                <SelectTrigger className="h-8 w-full">
                  <SelectValue placeholder="Assign folder..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="root">Unassigned</SelectItem>
                  {folders.map(f => (
                    <SelectItem key={f.id} value={String(f.id)}>{f.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarSeparator />

        <SidebarGroup>
          <SidebarGroupLabel>Actions</SidebarGroupLabel>
          <SidebarGroupContent className="px-2 space-y-2">
            <Button variant="outline" size="sm" onClick={startEdit} className="flex items-center gap-2 w-full">
              <Edit3 className="h-4 w-4" /> Edit Text
            </Button>
            <div className="grid grid-cols-3 gap-2">
              <Button variant="outline" size="sm" className="flex items-center gap-2" onClick={() => ui.toggleFolderPanel()}>
                <FolderOpen className="h-4 w-4" />
                <span className="sr-only">Folders</span>
              </Button>
              <Button variant="outline" size="sm" className="flex items-center gap-2" onClick={() => ui.setRightPanel('analytics' as any)}>
                <BarChart3 className="h-4 w-4" />
                <span className="sr-only">Analytics</span>
              </Button>
              <UploadPdfPopover>
                <Button variant="default" size="sm" className="flex items-center gap-2">
                  <Upload className="h-4 w-4" />
                  <span className="sr-only">Upload PDFs</span>
                </Button>
              </UploadPdfPopover>
            </div>
          </SidebarGroupContent>
        </SidebarGroup>

        {stats && (
          <>
            <SidebarSeparator />
            <SidebarGroup>
              <SidebarGroupLabel>Details</SidebarGroupLabel>
              <SidebarGroupContent className="px-2 text-xs text-muted-foreground space-x-3">
                <span>{stats.words.toLocaleString()} words</span>
                <span>{stats.chars.toLocaleString()} characters</span>
                <span>{stats.paras} paragraphs</span>
                <span>~{stats.minRead} min read</span>
              </SidebarGroupContent>
            </SidebarGroup>
          </>
        )}
      </SidebarContent>
    </Sidebar>
  )
}

export default ConversationInfoSidebar
