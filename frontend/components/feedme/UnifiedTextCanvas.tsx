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

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Toggle } from '@/components/ui/toggle'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
// Replaced textarea with Tiptap rich text editor
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent } from '@/components/ui/tabs'
import { Edit3, Save, X, FileText, Bold, Italic, List, ListOrdered, Bot, User, CheckCircle2, AlertTriangle, Clock } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatDistanceToNow } from 'date-fns'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import CharacterCount from '@tiptap/extension-character-count'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import { uploadImageToSupabase } from '@/lib/storage'
import DOMPurify from 'isomorphic-dompurify'

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
  onTextUpdate,
  onApprovalAction,
  readOnly = false,
  showApprovalControls = false,
  fullPageMode = false
}: UnifiedTextCanvasProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [editedText, setEditedText] = useState(extractedText)
  const [isLoading, setIsLoading] = useState(false)
  const [textStats, setTextStats] = useState<TextStatistics | null>(null)
  // Folder selection and title editing are handled in the sidebar
  const [showNotes, setShowNotes] = useState(false)
  const [aiNote, setAiNote] = useState<string>((metadata as any)?.ai_comment || '')

  // ---------- Minimal Markdown/HTML helpers (LLM-friendly store = Markdown) ----------
  const isLikelyHtml = (text: string): boolean => /<\s*(p|br|ul|ol|li|h[1-6]|strong|em|a|img|code|pre)\b/i.test(text)

  const escapeHtml = (s: string) => s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Helper to detect and style agent/customer names
  const styleNamesInHtml = (html: string): string => {
    // Pattern to detect names at the beginning of lines or after dates
    // Common patterns in support tickets:
    // "**Name LastName Month Day, Year at Time**" (agent messages)
    // "**Name LastName** Month Day, Year at Time" (customer messages)
    // Also handle patterns like "Mailbird Support: Name LastName"
    
    // Style agent names (Mailbird Support staff)
    html = html.replace(/(<strong>)?Mailbird Support:?\s*([A-Z][a-z]+\s+[A-Z][a-z]+)(<\/strong>)?/g, 
      '<code class="agent-name bg-blue-100 text-blue-900 px-1 py-0.5 rounded text-sm font-semibold">Mailbird Support: $2</code>')
    
    // Style any name that appears after a strong tag and date pattern (agents)
    html = html.replace(/(<strong>)([A-Z][a-z]+\s+[A-Z][a-z]+)(\s+[A-Z][a-z]+ \d+, \d{4} at \d+:\d+)(<\/strong>)/g,
      '<code class="agent-name bg-blue-100 text-blue-900 px-1 py-0.5 rounded text-sm font-semibold">$2</code>$3')
    
    // Style customer names (typically at the start without "Mailbird Support")
    html = html.replace(/^(<p>)?(<strong>)?([A-Z][a-z]+\s+[A-Z][a-z]+)(?!\s*:?\s*Mailbird)(\s+[A-Z][a-z]+ \d+, \d{4} at \d+:\d+)/gm,
      '$1<code class="customer-name bg-amber-100 text-amber-900 px-1 py-0.5 rounded text-sm font-semibold">$3</code>$4')
    
    return html
  }

  // Convert a subset of Markdown we use into HTML (bold, italic, lists, headings, links, code, paragraphs)
  const markdownToHtml = (md: string): string => {
    if (!md) return ''
    // Code blocks ```
    let html = md.replace(/```([\s\S]*?)```/g, (_m, code) => `<pre><code>${escapeHtml(code.trim())}</code></pre>`)
    // Inline code `code`
    html = html.replace(/`([^`]+)`/g, (_m, code) => `<code>${escapeHtml(code)}</code>`)
    // Headings #, ##, ### (limit to h1-h3 for readability)
    html = html.replace(/^(#{1,3})\s+(.+)$/gm, (_m, hashes, text) => {
      const level = Math.min(hashes.length, 3)
      return `<h${level}>${text.trim()}</h${level}>`
    })
    // Bold **text**
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    // Italic _text_ or *text*
    html = html.replace(/(^|\W)_(.+?)_(?=\W|$)/g, '$1<em>$2</em>')
    html = html.replace(/(^|\W)\*(.+?)\*(?=\W|$)/g, '$1<em>$2</em>')
    // Links [text](url)
    html = html.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    // Lists: group consecutive - or * lines
    html = html.replace(/(?:^|\n)([\t ]*[-*] .+(?:\n[\t ]*[-*] .+)*)/g, (m) => {
      const items = m.trim().split(/\n/).map(l => l.replace(/^[-*]\s+/, '').trim())
      return `\n<ul>${items.map(it => `<li>${it}</li>`).join('')}</ul>`
    })
    // Ordered lists: 1. 2. ...
    html = html.replace(/(?:^|\n)([\t ]*\d+\. .+(?:\n[\t ]*\d+\. .+)*)/g, (m) => {
      const items = m.trim().split(/\n/).map(l => l.replace(/^\d+\.\s+/, '').trim())
      return `\n<ol>${items.map(it => `<li>${it}</li>`).join('')}</ol>`
    })
    // Paragraphs: split on blank lines
    const blocks = html.split(/\n\n+/).map(b => b.trim()).filter(Boolean).map(b => {
      if (/^<\/?(h\d|ul|ol|li|pre|blockquote|p|img|code)/i.test(b)) return b
      return `<p>${b.replace(/\n/g, '<br />')}</p>`
    })
    
    // Apply name styling after all other conversions
    return styleNamesInHtml(blocks.join('\n'))
  }

  const htmlToMarkdown = (html: string): string => {
    if (!html) return ''
    let md = html
    // Normalize line breaks
    md = md.replace(/<br\s*\/?>(\s*)/gi, '\n')
    // Code blocks
    md = md.replace(/<pre[^>]*>\s*<code[^>]*>([\s\S]*?)<\/code>\s*<\/pre>/gi, (_m, code) => `\n\n\
\`\`\`\n${code}\n\`\`\`\n\n`)
    // Inline code
    md = md.replace(/<code[^>]*>([\s\S]*?)<\/code>/gi, (_m, code) => '`' + code + '`')
    // Headings
    md = md.replace(/<h1[^>]*>([\s\S]*?)<\/h1>/gi, '# $1\n\n')
    md = md.replace(/<h2[^>]*>([\s\S]*?)<\/h2>/gi, '## $1\n\n')
    md = md.replace(/<h3[^>]*>([\s\S]*?)<\/h3>/gi, '### $1\n\n')
    // Strong/Emphasis
    md = md.replace(/<strong[^>]*>([\s\S]*?)<\/strong>/gi, '**$1**')
    md = md.replace(/<b[^>]*>([\s\S]*?)<\/b>/gi, '**$1**')
    md = md.replace(/<em[^>]*>([\s\S]*?)<\/em>/gi, '*$1*')
    md = md.replace(/<i[^>]*>([\s\S]*?)<\/i>/gi, '*$1*')
    // Links
    md = md.replace(/<a[^>]*href=["'](https?:[^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi, '[$2]($1)')
    // Images
    md = md.replace(/<img[^>]*src=["'](https?:[^"']+)["'][^>]*alt=["']([^"']*)["'][^>]*\/?>(?:<\/img>)?/gi, '![$2]($1)')
    md = md.replace(/<img[^>]*src=["'](https?:[^"']+)["'][^>]*\/?>(?:<\/img>)?/gi, '![]($1)')
    // Lists
    md = md.replace(/<ul[^>]*>([\s\S]*?)<\/ul>/gi, (_m, inner) => {
      const items = inner.replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, '- $1\n')
      return `\n${items}\n`
    })
    md = md.replace(/<ol[^>]*>([\s\S]*?)<\/ol>/gi, (_m, inner) => {
      let i = 0
      return `\n${inner.replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, (_m2, it) => `${++i}. ${it}\n`)}\n`
    })
    // Paragraphs
    md = md.replace(/<p[^>]*>([\s\S]*?)<\/p>/gi, '$1\n\n')
    // Blockquotes
    md = md.replace(/<blockquote[^>]*>([\s\S]*?)<\/blockquote>/gi, (_m, inr) => inr.split(/\n/).map(l => `> ${l}`).join('\n') + '\n\n')
    // Remove remaining tags
    md = md.replace(/<[^>]+>/g, '')
    // Normalize spacing
    return md.split('\n').map(l => l.trimEnd()).join('\n').replace(/\n{3,}/g, '\n\n').trim()
  }

  const htmlToPlain = (html: string): string => DOMPurify.sanitize(html, { ALLOWED_TAGS: [], ALLOWED_ATTR: [] })

  // Sanitize config for rendering
  const sanitizeHtml = (html: string) => DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['p','br','strong','em','a','ul','ol','li','code','pre','blockquote','h1','h2','h3','img'],
    ALLOWED_ATTR: ['href','target','rel','src','alt','class'],
    ALLOW_DATA_ATTR: false,
    FORBID_TAGS: ['style','script','iframe','object','embed','link']
  })

  // Initialize Tiptap editor (stores HTML)
  const editor = useEditor({
    editable: !readOnly,
    extensions: [
      StarterKit.configure({ heading: { levels: [2, 3] } }),
      Placeholder.configure({ placeholder: 'Edit extracted content here…' }),
      CharacterCount.configure({ limit: 500000 }),
      Link.configure({ openOnClick: true, autolink: true }),
      Image.configure({ inline: false, allowBase64: false }),
    ],
    content: '<p></p>',
    onUpdate: ({ editor }) => setEditedText(editor.getHTML()),
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

  // Update text statistics when text changes (compute from plain text)
  useEffect(() => {
    if (!extractedText) { setTextStats(null); return }
    const html = isLikelyHtml(extractedText) ? extractedText : markdownToHtml(extractedText)
    const plain = htmlToPlain(html)
    setTextStats(calculateTextStats(plain))
  }, [extractedText, calculateTextStats])

  // Initialize/refresh editor content preserving formatting
  useEffect(() => {
    if (!editor) return
    const html = isLikelyHtml(extractedText) ? extractedText : markdownToHtml(extractedText)
    setEditedText(html)
    editor.commands.setContent(html || '<p></p>')
  }, [extractedText, editor])

  // Folder selection is handled in the sidebar; nothing to load here

  // Handle saving edited text
  const handleSaveText = async () => {
    const aiNoteChanged = aiNote !== ((metadata as any)?.ai_comment || '')
    if (!onTextUpdate && !(aiNoteChanged || editedText !== extractedText)) {
      setIsEditing(false)
      return
    }

    setIsLoading(true)
    try {
      // Prepare merged metadata (preserve existing keys)
    const mergedMeta = { ...(metadata || {}) }
      mergedMeta['content_format'] = 'markdown'
      if (aiNoteChanged) {
        mergedMeta['ai_comment'] = aiNote
      }

      // Save text/notes
      const payload: any = {}
      if (editedText !== extractedText) {
        // Convert editor HTML → Markdown for storage
        payload.extracted_text = htmlToMarkdown(editedText)
      }
      const needMetaUpdate = aiNoteChanged || (metadata as any)?.content_format !== 'markdown'
      if (needMetaUpdate) payload.metadata = mergedMeta

      await fetch(`/api/v1/feedme/conversations/${conversationId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      setIsEditing(false)
    } catch (error) {
      console.error('Failed to save text:', error)
      // Reset to original text on error
      const html = isLikelyHtml(extractedText) ? extractedText : markdownToHtml(extractedText)
      setEditedText(html)
      editor?.commands.setContent(html)
      setAiNote(((metadata as any)?.ai_comment || ''))
    } finally {
      setIsLoading(false)
    }
  }

  // Handle canceling edit
  const handleCancelEdit = () => {
    setEditedText(extractedText)
    setIsEditing(false)
  }

  // Handle approval actions
  const handleApprovalAction = async (action: 'approve' | 'reject' | 'edit_and_approve') => {
    if (!onApprovalAction) return

    setIsLoading(true)
    try {
      const data = action === 'edit_and_approve' ? { edited_text: editedText } : undefined
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

  // Listen for external edit toggles from sidebar
  useEffect(() => {
    const onToggle = (e: Event) => {
      const ce = e as CustomEvent<{ conversationId: number; action: 'start' | 'stop' }>
      if (!ce?.detail) return
      if (ce.detail.conversationId === conversationId) {
        setIsEditing(ce.detail.action === 'start')
      }
    }
    document.addEventListener('feedme:toggle-edit', onToggle as EventListener)
    return () => document.removeEventListener('feedme:toggle-edit', onToggle as EventListener)
  }, [conversationId])

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
 
  const canSave = (isEditing && (editedText !== extractedText)) ||
    (aiNote !== ((metadata as any)?.ai_comment || ''))

  return (
    <div className="space-y-6">
      {/* Removed legacy header; info now lives in the sidebar */}

      {/* Main content area */}
      <Tabs defaultValue="text" className="w-full">
        <TabsContent value="text" className="space-y-4">
          {/* AI Notes (collapsible, editable) moved above content */}
          <Card className="border-0 shadow-none bg-transparent">
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

          <Card className="border-0 shadow-none bg-transparent"> 
            <CardContent className="p-0">
              {isEditing ? (
                <div className={cn("relative", fullPageMode ? "min-h-[60vh] p-2" : "p-2")}> 
                {/* Formatting toolbar + actions */}
                <div className="flex items-center justify-between gap-2 pb-2">
                  <div className="flex items-center gap-2">
                  {/* Inline formatting: Bold + Italic */}
                  <div className="flex items-center gap-1">
                    <Toggle
                      size="sm"
                      aria-label="Toggle bold"
                      pressed={!!editor?.isActive('bold')}
                      onPressedChange={() => editor?.chain().focus().toggleBold().run()}
                    >
                      <Bold className="h-4 w-4" />
                    </Toggle>
                    <Toggle
                      size="sm"
                      aria-label="Toggle italic"
                      pressed={!!editor?.isActive('italic')}
                      onPressedChange={() => editor?.chain().focus().toggleItalic().run()}
                    >
                      <Italic className="h-4 w-4" />
                    </Toggle>
                  </div>

                  {/* List formatting: Bulleted vs Numbered (mutually exclusive) */}
                  <ToggleGroup type="single" size="sm" aria-label="List type" value={
                      editor?.isActive('orderedList') ? 'ol' : (editor?.isActive('bulletList') ? 'ul' : undefined)
                    } onValueChange={(val) => {
                      if (!editor) return
                      if (val === 'ul') {
                        editor.chain().focus().toggleBulletList().run()
                      } else if (val === 'ol') {
                        editor.chain().focus().toggleOrderedList().run()
                      } else {
                        // Clicking the active item again clears list
                        if (editor.isActive('orderedList')) editor.chain().focus().toggleOrderedList().run()
                        if (editor.isActive('bulletList')) editor.chain().focus().toggleBulletList().run()
                      }
                    }}
                  >
                    <ToggleGroupItem value="ul" aria-label="Bulleted list">
                      <List className="h-4 w-4" />
                    </ToggleGroupItem>
                    <ToggleGroupItem value="ol" aria-label="Numbered list">
                      <ListOrdered className="h-4 w-4" />
                    </ToggleGroupItem>
                  </ToggleGroup>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={handleCancelEdit} disabled={!isEditing || isLoading}>
                      <X className="h-4 w-4 mr-1" /> Cancel
                    </Button>
                    <Button size="sm" onClick={handleSaveText} disabled={!isEditing || isLoading || !canSave}>
                      <Save className="h-4 w-4 mr-1" /> Save
                    </Button>
                  </div>
                </div>
                <div className={cn('font-sans', fullPageMode ? 'min-h-[60vh] p-3' : 'min-h-[400px] p-2')}>
                  <EditorContent
                    editor={editor}
                    className={cn(
                      'prose max-w-none leading-7 text-sm',
                      'prose-p:my-3 prose-li:my-1 prose-ul:my-3 prose-ol:my-3',
                      'prose-headings:mt-6 prose-headings:mb-3',
                      '[&_code.agent-name]:bg-blue-100 [&_code.agent-name]:text-blue-900 [&_code.agent-name]:px-1 [&_code.agent-name]:py-0.5 [&_code.agent-name]:rounded [&_code.agent-name]:text-sm [&_code.agent-name]:font-semibold',
                      '[&_code.customer-name]:bg-amber-100 [&_code.customer-name]:text-amber-900 [&_code.customer-name]:px-1 [&_code.customer-name]:py-0.5 [&_code.customer-name]:rounded [&_code.customer-name]:text-sm [&_code.customer-name]:font-semibold'
                    )}
                  />
                </div>
                <div className="absolute bottom-4 right-4 text-xs text-muted-foreground bg-background px-2 py-1 rounded">
                  {editedText.length.toLocaleString()} characters
                </div>
              </div>
            ) : (
              <div className={cn(
                "prose max-w-none font-sans text-sm leading-relaxed",
                fullPageMode ? "p-6" : "p-4",
                "[&_code.agent-name]:bg-blue-100 [&_code.agent-name]:text-blue-900 [&_code.agent-name]:px-1 [&_code.agent-name]:py-0.5 [&_code.agent-name]:rounded [&_code.agent-name]:text-sm [&_code.agent-name]:font-semibold [&_code.agent-name]:not-italic",
                "[&_code.customer-name]:bg-amber-100 [&_code.customer-name]:text-amber-900 [&_code.customer-name]:px-1 [&_code.customer-name]:py-0.5 [&_code.customer-name]:rounded [&_code.customer-name]:text-sm [&_code.customer-name]:font-semibold [&_code.customer-name]:not-italic"
              )}
                dangerouslySetInnerHTML={{ __html: sanitizeHtml(isLikelyHtml(extractedText) ? styleNamesInHtml(extractedText) : markdownToHtml(extractedText)) }}
              />
            )}
          </CardContent>
        </Card>

          {/* Approval controls */}
          {showApprovalControls && approvalStatus === 'pending' && (
            <Card className="border-0 shadow-none bg-transparent">
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
            <Card className="border-0 shadow-none bg-transparent">
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
      </Tabs>
    </div>
  )
}

export default UnifiedTextCanvas
