/**
 * Unified Text Canvas for FeedMe System
 * Replaces fragmented Q&A sections with a single editable text area
 * 
 * Features:
 * - Display extracted text in a unified canvas
 * - Edit text with real-time preview
 * - Processing method indicators (PDF OCR, manual entry, etc.)
 * - Confidence scoring and quality indicators
 * - Approval workflow integration
 * - Text statistics and metadata
 */

'use client'

import React, { useState, useEffect, useCallback, useRef } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
// Replaced textarea with Tiptap rich text editor
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Edit3, Save, X, FileText, AlertTriangle, CheckCircle2, Info, Clock, User, Bot, Sparkles, Folder } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatDistanceToNow } from 'date-fns'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import CharacterCount from '@tiptap/extension-character-count'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import Highlight from '@tiptap/extension-highlight'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { mdToHtml, htmlToMd } from '@/lib/markdown'
import { feedMeApi } from '@/lib/feedme-api'
import { useUIStore } from '@/lib/stores/ui-store'
import { listFolders, assignConversationsToFolderSupabase } from '@/lib/feedme-api'
import { uploadImageToSupabase } from '@/lib/storage'

// Types
interface ProcessingMetadata {
  processing_method: 'pdf_ocr' | 'manual_text' | 'text_paste'
  extraction_confidence?: number
  processing_time_ms?: number
  quality_metrics?: Record<string, number>
  extraction_method?: string
  warnings?: string[]
}

interface TextStatistics {
  character_count: number
  word_count: number
  line_count: number
  paragraph_count: number
  estimated_read_time_minutes: number
}

interface UnifiedTextCanvasProps {
  conversationId: number
  title: string
  ticketId?: string | null
  extractedText: string
  metadata?: Record<string, any> | null
  processingMetadata: ProcessingMetadata
  approvalStatus: 'pending' | 'approved' | 'rejected'
  approvedBy?: string
  approvedAt?: string
  pdfCleaned?: boolean
  pdfCleanedAt?: string
  originalPdfSize?: number
  folderId?: number | null
  onTextUpdate?: (text: string) => Promise<void>
  onApprovalAction?: (action: 'approve' | 'reject' | 'edit_and_approve', data?: any) => Promise<void>
  readOnly?: boolean
  showApprovalControls?: boolean
  fullPageMode?: boolean
}

export function UnifiedTextCanvas({
  conversationId,
  title,
  ticketId,
  extractedText,
  metadata,
  processingMetadata,
  approvalStatus,
  approvedBy,
  approvedAt,
  pdfCleaned = false,
  pdfCleanedAt,
  originalPdfSize,
  folderId: initialFolderId,
  onTextUpdate,
  onApprovalAction,
  readOnly = false,
  showApprovalControls = false,
  fullPageMode = false
}: UnifiedTextCanvasProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [editedMd, setEditedMd] = useState(extractedText)
  const [usage, setUsage] = useState<{ daily_used: number; daily_limit: number; utilization: { daily: number; rpm: number } } | null>(null)
  const [embUsage, setEmbUsage] = useState<{ daily_used: number; daily_limit: number; utilization: { daily: number; rpm: number; tpm: number } } | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [textStats, setTextStats] = useState<TextStatistics | null>(null)
  const [folders, setFolders] = useState<Array<{ id: number; name: string; color: string }>>([])
  const [folderId, setFolderId] = useState<number | null | undefined>(initialFolderId)
  const [subject, setSubject] = useState(title)
  const [showNotes, setShowNotes] = useState(false)
  const [aiNote, setAiNote] = useState<string>((metadata as any)?.ai_comment || '')

  // Initialize Tiptap editor (stores HTML)
  const editor = useEditor({
    editable: !readOnly,
    extensions: [
      StarterKit.configure({ heading: { levels: [2, 3] } }),
      Placeholder.configure({ placeholder: 'Edit extracted content here…' }),
      CharacterCount.configure({ limit: 500000 }),
      Link.configure({ openOnClick: true, autolink: true }),
      Image.configure({ inline: false, allowBase64: false }),
      Highlight,
    ],
    content: extractedText?.trim().length ? mdToHtml(extractedText) : '<p></p>',
    onUpdate: ({ editor }) => {
      const html = editor.getHTML()
      const md = htmlToMd(html)
      setEditedMd(md)
    },
  })

  // Paste/drop images: upload to Supabase storage and insert by URL
  useEffect(() => {
    if (!editor) return
    const view = editor.view
    const handlePaste = async (e: ClipboardEvent) => {
      const items = e.clipboardData?.items
      if (!items) return
      for (const item of items) {
        if (item.kind === 'file') {
          const file = item.getAsFile()
          if (file && file.type.startsWith('image/')) {
            e.preventDefault()
            try {
              const url = await uploadImageToSupabase(file, conversationId)
              editor.chain().focus().setImage({ src: url }).run()
            } catch (err) {
              console.error('Image upload failed', err)
            }
          }
        }
      }
    }
    const handleDrop = async (e: DragEvent) => {
      if (!e.dataTransfer) return
      const files = Array.from(e.dataTransfer.files || [])
      const image = files.find(f => f.type.startsWith('image/'))
      if (image) {
        e.preventDefault()
        try {
          const url = await uploadImageToSupabase(image, conversationId)
          editor.chain().focus().setImage({ src: url }).run()
        } catch (err) {
          console.error('Image upload failed', err)
        }
      }
    }
    view.dom.addEventListener('paste', handlePaste as any)
    view.dom.addEventListener('drop', handleDrop as any)
    return () => {
      view.dom.removeEventListener('paste', handlePaste as any)
      view.dom.removeEventListener('drop', handleDrop as any)
    }
  }, [editor, conversationId])

  // Calculate text statistics
  const calculateTextStats = useCallback((text: string): TextStatistics => {
    const lines = text.split('\n')
    const paragraphs = text.split('\n\n').filter(p => p.trim().length > 0)
    const words = text.trim().split(/\s+/).filter(w => w.length > 0)
    
    return {
      character_count: text.length,
      word_count: words.length,
      line_count: lines.length,
      paragraph_count: paragraphs.length,
      estimated_read_time_minutes: Math.max(1, Math.ceil(words.length / 200))
    }
  }, [])

  // Update text statistics when text changes
  useEffect(() => {
    if (extractedText) {
      setTextStats(calculateTextStats(extractedText))
    }
  }, [extractedText, calculateTextStats])

  // Update edited content when extracted text changes
  useEffect(() => {
    setEditedMd(extractedText)
    if (editor && extractedText) {
      editor.commands.setContent(mdToHtml(extractedText))
    }
  }, [extractedText])

  // Fetch Gemini usage and warn if nearing limit
  useEffect(() => {
    let mounted = true
    ;(async () => {
      try {
        const u = await feedMeApi.getGeminiUsage()
        if (mounted) setUsage({ daily_used: u.daily_used, daily_limit: u.daily_limit, utilization: u.utilization })
        if (u.utilization.daily > 0.8) {
          useUIStore.getState().actions.showToast({
            type: 'warning',
            title: 'AI Usage',
            message: `Gemini daily usage at ${Math.round(u.utilization.daily * 100)}%`,
            duration: 4000,
          })
        }
        const eu = await feedMeApi.getEmbeddingUsage()
        if (mounted) {
          setEmbUsage({ daily_used: eu.daily_used, daily_limit: eu.daily_limit, utilization: eu.utilization })
          // Optional: You can store embUsage in a separate state if displaying separately
          if (eu.utilization.daily > 0.8 || eu.utilization.tpm > 0.8) {
            useUIStore.getState().actions.showToast({
              type: 'warning',
              title: 'Embeddings Usage',
              message: `Embeddings usage nearing limits (daily ${Math.round(eu.utilization.daily * 100)}%, tpm ${Math.round(eu.utilization.tpm * 100)}%)`,
              duration: 4000,
            })
          }
        }
      } catch (_) {
        // ignore
      }
    })()
    return () => { mounted = false }
  }, [])

  // Load folders for assignment
  useEffect(() => {
    async function load() {
      try {
        const resp = await listFolders()
        setFolders(resp.folders.map(f => ({ id: f.id, name: f.name, color: f.color })))
      } catch (e) {
        console.warn('Failed to load folders', e)
      }
    }
    load()
  }, [])

  // Handle saving edited text
  const handleSaveText = async () => {
    const aiNoteChanged = aiNote !== ((metadata as any)?.ai_comment || '')
    if (!onTextUpdate && !(subject !== title || aiNoteChanged || editedMd !== extractedText)) {
      setIsEditing(false)
      return
    }

    setIsLoading(true)
    try {
      // Prepare merged metadata (preserve existing keys)
      const mergedMeta = { ...(metadata || {}) }
      if (aiNoteChanged) {
        mergedMeta['ai_comment'] = aiNote
      }

      // Save text/subject/notes
      const payload: any = {}
      if (editedMd !== extractedText) payload.extracted_text = editedMd
      if (subject !== title) payload.title = subject
      if (aiNoteChanged) payload.metadata = mergedMeta

      await fetch(`/api/v1/feedme/conversations/${conversationId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      setIsEditing(false)
    } catch (error) {
      console.error('Failed to save text:', error)
      // Reset to original text on error
      setEditedMd(extractedText)
      editor?.commands.setContent(mdToHtml(extractedText))
      setSubject(title)
      setAiNote(((metadata as any)?.ai_comment || ''))
    } finally {
      setIsLoading(false)
    }
  }

  // Handle canceling edit
  const handleCancelEdit = () => {
    setEditedMd(extractedText)
    setIsEditing(false)
  }

  // Handle approval actions
  const handleApprovalAction = async (action: 'approve' | 'reject' | 'edit_and_approve') => {
    if (!onApprovalAction) return

    setIsLoading(true)
    try {
      const data = action === 'edit_and_approve' ? { edited_text: editedMd } : undefined
      await onApprovalAction(action, data)
      if (action === 'edit_and_approve') {
        setIsEditing(false)
      }
    } catch (error) {
      console.error('Failed to process approval action:', error)
    } finally {
      setIsLoading(false)
    }
  }

  // Get processing method display info
  const getProcessingMethodInfo = () => {
    const { processing_method, extraction_confidence, extraction_method } = processingMetadata
    
    const methodInfo = {
      pdf_ocr: {
        label: 'PDF OCR',
        icon: <Bot className="h-4 w-4" />,
        color: 'bg-blue-100 text-blue-700',
        description: 'Text extracted using OCR technology'
      },
      pdf_ai: {
        label: 'PDF AI',
        icon: <Bot className="h-4 w-4" />,
        color: 'bg-blue-100 text-blue-700',
        description: 'Extracted with Gemini vision (Markdown)'
      },
      manual_text: {
        label: 'Manual Entry',
        icon: <User className="h-4 w-4" />,
        color: 'bg-green-100 text-green-700',
        description: 'Manually entered text'
      },
      text_paste: {
        label: 'Text Paste',
        icon: <FileText className="h-4 w-4" />,
        color: 'bg-purple-100 text-purple-700',
        description: 'Pasted text content'
      }
    }

    const info = methodInfo[processing_method] || methodInfo.manual_text
    
    return {
      ...info,
      confidence: extraction_confidence,
      enhanced: extraction_method === 'ocr_fallback'
    }
  }

  // Get confidence indicator
  const getConfidenceIndicator = (confidence?: number) => {
    if (confidence === undefined) return null

    if (confidence >= 0.9) {
      return <Badge variant="outline" className="bg-green-100 text-green-700 border-green-300">
        <CheckCircle2 className="h-3 w-3 mr-1" />
        High Confidence ({Math.round(confidence * 100)}%)
      </Badge>
    } else if (confidence >= 0.7) {
      return <Badge variant="outline" className="bg-yellow-100 text-yellow-700 border-yellow-300">
        <AlertTriangle className="h-3 w-3 mr-1" />
        Medium Confidence ({Math.round(confidence * 100)}%)
      </Badge>
    } else {
      return <Badge variant="outline" className="bg-red-100 text-red-700 border-red-300">
        <AlertTriangle className="h-3 w-3 mr-1" />
        Low Confidence ({Math.round(confidence * 100)}%)
      </Badge>
    }
  }

  // Get approval status indicator
  const getApprovalStatusIndicator = () => {
    switch (approvalStatus) {
      case 'approved':
        return <Badge variant="outline" className="bg-green-100 text-green-700 border-green-300">
          <CheckCircle2 className="h-3 w-3 mr-1" />
          Approved
        </Badge>
      case 'rejected':
        return <Badge variant="outline" className="bg-red-100 text-red-700 border-red-300">
          <X className="h-3 w-3 mr-1" />
          Rejected
        </Badge>
      default:
        return <Badge variant="outline" className="bg-yellow-100 text-yellow-700 border-yellow-300">
          <Clock className="h-3 w-3 mr-1" />
          Pending Review
        </Badge>
    }
  }

  const methodInfo = getProcessingMethodInfo()
  const canSave = !!folderId && (
    (isEditing && (editedMd !== extractedText || subject !== title)) ||
    (aiNote !== ((metadata as any)?.ai_comment || ''))
  )

  return (
    <div className="space-y-6">
      {/* Header with metadata */}
      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-muted-foreground">Ticket:</span>
                <span className="text-sm font-mono bg-muted px-2 py-0.5 rounded">{ticketId || 'Unknown'}</span>
              </div>
              <div className="mt-2">
                {isEditing ? (
                  <input
                    className="text-lg font-semibold bg-background border rounded px-2 py-1 w-full max-w-xl"
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                  />
                ) : (
                  <CardTitle className="text-lg">{subject}</CardTitle>
                )}
              </div>
              <div className="flex items-center gap-4 mt-2">
                <Badge variant="outline" className={cn("text-sm", methodInfo.color)}>
                  {methodInfo.icon}
                  <span className="ml-1">{methodInfo.label}</span>
                  {methodInfo.enhanced && <Sparkles className="h-3 w-3 ml-1" />}
                </Badge>
                {usage && (
                  <Badge variant="outline" className="text-sm bg-blue-50 text-blue-700 border-blue-300">
                    AI Budget: {usage.daily_used}/{usage.daily_limit}
                  </Badge>
                )}
                {embUsage && (
                  <Badge variant="outline" className="text-sm bg-purple-50 text-purple-700 border-purple-300">
                    Embeddings: {embUsage.daily_used}/{embUsage.daily_limit}
                  </Badge>
                )}
                {getConfidenceIndicator(methodInfo.confidence)}
                {getApprovalStatusIndicator()}
              </div>
            </div>
            
            <div className="flex items-center gap-2">
              {/* Assign to Folder selector */}
              <div className="flex items-center gap-2">
                <Folder className="h-4 w-4 text-muted-foreground" />
                <select
                  className="border rounded px-2 py-1 text-sm bg-background"
                  value={folderId ?? ''}
                  onChange={async (e) => {
                    const val = e.target.value === '' ? null : Number(e.target.value)
                    try {
                      await assignConversationsToFolderSupabase(val as any, [conversationId])
                      setFolderId(val)
                    } catch (err) {
                      console.error('Folder assignment failed', err)
                    }
                  }}
                >
                  <option value="">Assign folder…</option>
                  {folders.map(f => (
                    <option key={f.id} value={f.id}>{f.name}</option>
                  ))}
                </select>
              </div>
              {!readOnly && (
                <>
                  {isEditing ? (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleCancelEdit}
                        disabled={isLoading}
                      >
                        <X className="h-4 w-4 mr-1" />
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        onClick={handleSaveText}
                        disabled={isLoading || !canSave}
                      >
                        <Save className="h-4 w-4 mr-1" />
                        Save
                      </Button>
                    </>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setIsEditing(true)}
                      disabled={isLoading}
                    >
                      <Edit3 className="h-4 w-4 mr-1" />
                      Edit
                    </Button>
                  )}
                </>
              )}
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {/* Processing warnings */}
          {processingMetadata.warnings && processingMetadata.warnings.length > 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
              <div className="flex items-start gap-2">
                <Info className="h-4 w-4 text-yellow-600 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-yellow-800">Processing Notes</p>
                  <ul className="text-sm text-yellow-700 mt-1 space-y-1">
                    {processingMetadata.warnings.map((warning, index) => (
                      <li key={index}>• {warning}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* Text statistics */}
          {textStats && (
            <div className="flex items-center gap-6 text-sm text-muted-foreground">
              <span>{textStats.word_count.toLocaleString()} words</span>
              <span>{textStats.character_count.toLocaleString()} characters</span>
              <span>{textStats.paragraph_count} paragraphs</span>
              <span>~{textStats.estimated_read_time_minutes} min read</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Main content area */}
      <Tabs defaultValue="text" className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="text" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Text Content
          </TabsTrigger>
          <TabsTrigger value="metadata" className="flex items-center gap-2">
            <Info className="h-4 w-4" />
            Metadata
          </TabsTrigger>
        </TabsList>

        <TabsContent value="text" className="space-y-4">
          <Card className={cn(fullPageMode && "border-0 shadow-none")}> 
            <CardContent className="p-0">
              {isEditing ? (
                <div className={cn("relative", fullPageMode && "min-h-[calc(100vh-300px)] p-2")}> 
                  <div className={cn('border rounded-md prose prose-base max-w-none', fullPageMode ? 'min-h-[calc(100vh-320px)] p-3' : 'min-h-[400px] p-2')}>
                    <EditorContent editor={editor} />
                  </div>
                  <div className="absolute bottom-4 right-4 text-xs text-muted-foreground bg-background px-2 py-1 rounded">
                    {editedMd.length.toLocaleString()} chars (MD)
                  </div>
                </div>
              ) : (
                <ScrollArea className={cn(fullPageMode ? "h-[calc(100vh-300px)]" : "h-[400px]")}> 
                  <div className={cn("prose prose-base max-w-none leading-relaxed", fullPageMode ? "p-6" : "p-4")}> 
                    {editedMd ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{editedMd}</ReactMarkdown>
                    ) : (
                      <div className="text-muted-foreground italic">No text content available</div>
                    )}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>

          {/* AI Notes (collapsible, editable) */}
          <Card>
            <CardHeader className="py-3 flex flex-row items-center justify-between">
              <CardTitle className="text-base">AI Notes</CardTitle>
              <Button variant="ghost" size="sm" onClick={() => setShowNotes(s => !s)}>
                {showNotes ? 'Hide' : 'Show'}
              </Button>
            </CardHeader>
            {showNotes && (
              <CardContent>
                <Textarea
                  value={aiNote}
                  onChange={(e) => setAiNote(e.target.value)}
                  placeholder="Short AI comment to aid retrieval/search..."
                  rows={4}
                  className="font-sans text-sm"
                />
                <div className="text-xs text-muted-foreground mt-1">Editable. Included in metadata (ai_comment).</div>
              </CardContent>
            )}
          </Card>

          {/* Approval controls */}
          {showApprovalControls && approvalStatus === 'pending' && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Approval Actions</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-3">
                  <Button
                    variant="outline"
                    onClick={() => handleApprovalAction('approve')}
                    disabled={isLoading}
                    className="text-green-700 border-green-300 hover:bg-green-50"
                  >
                    <CheckCircle2 className="h-4 w-4 mr-1" />
                    Approve
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => handleApprovalAction('reject')}
                    disabled={isLoading}
                    className="text-red-700 border-red-300 hover:bg-red-50"
                  >
                    <X className="h-4 w-4 mr-1" />
                    Reject
                  </Button>
                  {isEditing && (
                    <Button
                      onClick={() => handleApprovalAction('edit_and_approve')}
                      disabled={isLoading || editedText === extractedText}
                      className="text-blue-700 bg-blue-50 border-blue-300 hover:bg-blue-100"
                    >
                      <Edit3 className="h-4 w-4 mr-1" />
                      Edit & Approve
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Approval history */}
          {approvalStatus === 'approved' && approvedBy && (
            <Card>
              <CardContent className="pt-4 space-y-2">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="h-4 w-4 text-green-600" />
                  <span>Approved by {approvedBy}</span>
                  {approvedAt && (
                    <span>• {formatDistanceToNow(new Date(approvedAt), { addSuffix: true })}</span>
                  )}
                </div>
                
                {/* PDF cleanup status */}
                {processingMetadata.processing_method === 'pdf_ocr' && (
                  <div className="flex items-center gap-2 text-sm">
                    {pdfCleaned ? (
                      <>
                        <Badge variant="outline" className="bg-green-50 text-green-700 border-green-300">
                          <CheckCircle2 className="h-3 w-3 mr-1" />
                          PDF Cleaned
                        </Badge>
                        {originalPdfSize && (
                          <span className="text-muted-foreground">
                            • Saved {(originalPdfSize / 1024 / 1024).toFixed(2)} MB
                          </span>
                        )}
                        {pdfCleanedAt && (
                          <span className="text-muted-foreground">
                            • {formatDistanceToNow(new Date(pdfCleanedAt), { addSuffix: true })}
                          </span>
                        )}
                      </>
                    ) : (
                      <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-300">
                        <Clock className="h-3 w-3 mr-1" />
                        PDF Cleanup Pending
                      </Badge>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="metadata" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Processing Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="font-medium">Method:</span>
                  <span className="ml-2">{methodInfo.label}</span>
                </div>
                {methodInfo.confidence !== undefined && (
                  <div>
                    <span className="font-medium">Confidence:</span>
                    <span className="ml-2">{Math.round(methodInfo.confidence * 100)}%</span>
                  </div>
                )}
                {processingMetadata.processing_time_ms && (
                  <div>
                    <span className="font-medium">Processing Time:</span>
                    <span className="ml-2">{processingMetadata.processing_time_ms}ms</span>
                  </div>
                )}
                <div>
                  <span className="font-medium">Conversation ID:</span>
                  <span className="ml-2">{conversationId}</span>
                </div>
              </div>

              {processingMetadata.quality_metrics && (
                <>
                  <Separator />
                  <div>
                    <h4 className="font-medium mb-2">Quality Metrics</h4>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      {Object.entries(processingMetadata.quality_metrics).map(([key, value]) => (
                        <div key={key}>
                          <span className="font-medium capitalize">{key.replace('_', ' ')}:</span>
                          <span className="ml-2">
                            {typeof value === 'number' ? 
                              (value < 1 ? `${Math.round(value * 100)}%` : value.toLocaleString()) 
                              : String(value)
                            }
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}

export default UnifiedTextCanvas
