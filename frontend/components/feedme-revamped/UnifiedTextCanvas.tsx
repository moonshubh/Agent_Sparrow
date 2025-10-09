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
import { withErrorBoundary } from '@/components/feedme-revamped/ErrorBoundary'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Toggle } from '@/components/ui/toggle'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Edit3, Save, X, FileText, Bold, Italic, Underline, Code, List, ListOrdered, Bot, User, CheckCircle2, AlertTriangle, Clock } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatDistanceToNow } from 'date-fns'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import CharacterCount from '@tiptap/extension-character-count'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import UnderlineExtension from '@tiptap/extension-underline'
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
  // Use the actual DOMPurify type from the library
  const [purify, setPurify] = useState<typeof import('isomorphic-dompurify').default | null>(null)
  const [purifyLoading, setPurifyLoading] = useState(true)

  // Load DOMPurify on client side
  useEffect(() => {
    if (typeof window !== 'undefined') {
      import('isomorphic-dompurify').then(module => {
        // Access the default export which is the actual DOMPurify instance
        setPurify(() => module.default)
        setPurifyLoading(false)
      }).catch(err => {
        console.error('Failed to load DOMPurify:', err)
        setPurifyLoading(false)
      })
    }
  }, [])

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
    // Underline __text__
    html = html.replace(/__([^_]+)__/g, '<u>$1</u>')
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
    const finalHtml = styleNamesInHtml(blocks.join('\n'))

    // Sanitize HTML to prevent XSS if DOMPurify is available
    if (purify) {
      return purify.sanitize(finalHtml, {
        ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'a', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'code', 'pre', 'blockquote', 'img'],
        ALLOWED_ATTR: ['href', 'target', 'rel', 'src', 'alt', 'class'],
        ALLOWED_URI_REGEXP: /^(?:(?:(?:f|ht)tps?|mailto|tel|callto|cid|xmpp|data):|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i
      })
    }
    return finalHtml
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
    // Strong/Emphasis/Underline
    md = md.replace(/<strong[^>]*>([\s\S]*?)<\/strong>/gi, '**$1**')
    md = md.replace(/<b[^>]*>([\s\S]*?)<\/b>/gi, '**$1**')
    md = md.replace(/<u[^>]*>([\s\S]*?)<\/u>/gi, '__$1__')
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
    md = md.replace(/<ol[^>]*>([\s\S]*?)<\/ol>/gi, (_m: string, inner: string) => {
      let i = 0
      return `\n${inner.replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, (_m2: string, it: string) => `${++i}. ${it}\n`)}\n`
    })
    // Paragraphs
    md = md.replace(/<p[^>]*>([\s\S]*?)<\/p>/gi, '$1\n\n')
    // Blockquotes
    md = md.replace(/<blockquote[^>]*>([\s\S]*?)<\/blockquote>/gi, (_m: string, inr: string) => inr.split(/\n/).map((l: string) => `> ${l}`).join('\n') + '\n\n')
    // Remove remaining tags
    md = md.replace(/<[^>]+>/g, '')
    // Normalize spacing
    return md.split('\n').map(l => l.trimEnd()).join('\n').replace(/\n{3,}/g, '\n\n').trim()
  }

  const htmlToPlain = (html: string): string => {
    if (!purify) return html.replace(/<[^>]*>/g, '') // Fallback to simple tag stripping
    return purify.sanitize(html, { ALLOWED_TAGS: [], ALLOWED_ATTR: [] })
  }

  // Sanitize config for rendering - NEVER render unsanitized HTML
  const sanitizeHtml = (html: string) => {
    if (!purify) {
      // If DOMPurify isn't loaded, strip all HTML tags as a fallback
      return html.replace(/<[^>]*>/g, '')
    }
    return purify.sanitize(html, {
      ALLOWED_TAGS: ['p','br','strong','em','u','a','ul','ol','li','code','pre','blockquote','h1','h2','h3','img'],
      ALLOWED_ATTR: ['href','target','rel','src','alt','class'],
      ALLOW_DATA_ATTR: false,
      FORBID_TAGS: ['style','script','iframe','object','embed','link']
    })
  }

  // Handle auto-save - defined early for editor dependency
  const [isSaving, setIsSaving] = useState(false)
  const saveAbortControllerRef = useRef<AbortController | null>(null)

  const handleAutoSave = useCallback(async (html: string) => {
    const markdown = htmlToMarkdown(html)
    if (markdown === extractedText) return

    // Cancel any pending save request
    if (saveAbortControllerRef.current) {
      saveAbortControllerRef.current.abort()
    }

    // Create new abort controller for this save
    const abortController = new AbortController()
    saveAbortControllerRef.current = abortController

    setIsSaving(true)
    try {
      if (onTextUpdate) {
        await onTextUpdate(markdown)
      } else {
        await fetch(`/api/v1/feedme/conversations/${conversationId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            extracted_text: markdown,
            metadata: { ...(metadata || {}), content_format: 'markdown' }
          }),
          signal: abortController.signal
        })
      }
    } catch (error) {
      // Ignore abort errors
      if (error instanceof Error && error.name !== 'AbortError') {
        console.error('Failed to auto-save text:', error)
      }
    } finally {
      // Only update saving state if this request wasn't aborted
      if (!abortController.signal.aborted) {
        setIsSaving(false)
      }
    }
  }, [extractedText, onTextUpdate, conversationId, metadata])

  // Initialize Tiptap editor (stores HTML)
  const editor = useEditor({
    editable: !readOnly,
    extensions: [
      StarterKit.configure({ heading: { levels: [2, 3] } }),
      Placeholder.configure({ placeholder: 'Edit extracted content here…' }),
      CharacterCount.configure({ limit: 500000 }),
      Link.configure({ openOnClick: true, autolink: true }),
      Image.configure({ inline: false, allowBase64: false }),
      UnderlineExtension,
    ],
    content: '<p></p>',
    onUpdate: useCallback(({ editor }: any) => {
      const html = editor.getHTML()
      setEditedText(html)
    }, [])
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

  // Handle saving edited text (kept for compatibility but not used in UI)
  const handleSaveText = async () => {
    if (editedText === extractedText) {
      setIsEditing(false)
      return
    }

    setIsLoading(true)
    try {
      const markdown = htmlToMarkdown(editedText)
      if (onTextUpdate) {
        await onTextUpdate(markdown)
      } else {
        await fetch(`/api/v1/feedme/conversations/${conversationId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            extracted_text: markdown,
            metadata: { ...(metadata || {}), content_format: 'markdown' }
          })
        })
      }
      setIsEditing(false)
    } catch (error) {
      console.error('Failed to save text:', error)
      const html = isLikelyHtml(extractedText) ? extractedText : markdownToHtml(extractedText)
      setEditedText(html)
      editor?.commands.setContent(html)
    } finally {
      setIsLoading(false)
    }
  }

  // Handle canceling edit (kept for compatibility but not used in UI)
  const handleCancelEdit = () => {
    const html = isLikelyHtml(extractedText) ? extractedText : markdownToHtml(extractedText)
    setEditedText(html)
    editor?.commands.setContent(html)
    setIsEditing(false)
  }

  // Handle clicking outside to exit edit mode
  useEffect(() => {
    if (!isEditing) return

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement
      const editorElement = document.querySelector('.ProseMirror')
      const toolbarElement = document.querySelector('[data-toolbar="true"]')

      if (editorElement && !editorElement.contains(target) &&
          toolbarElement && !toolbarElement.contains(target)) {
        setIsEditing(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isEditing])

  // Handle auto-save with proper cleanup
  useEffect(() => {
    if (!isEditing || !editedText) return

    const timeoutId = setTimeout(() => {
      handleAutoSave(editedText)
    }, 2000) // Auto-save after 2 seconds of no activity

    return () => {
      clearTimeout(timeoutId)
    }
  }, [editedText, isEditing, handleAutoSave])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      // Cleanup any pending saves on unmount
      if (saveAbortControllerRef.current) {
        saveAbortControllerRef.current.abort()
      }
    }
  }, [])

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
 
  // Compare the markdown versions to determine if content has changed
  const currentMarkdown = useMemo(() => htmlToMarkdown(editedText), [editedText])
  const canSave = isEditing && (currentMarkdown !== extractedText)

  return (
    <Card className="border-0 shadow-none bg-transparent h-full">
      <CardContent className="flex h-full flex-col gap-4 p-0">
        <div className="flex-1">
          {isEditing ? (
            <div className={cn('relative flex h-full flex-col', fullPageMode ? 'p-4' : 'p-3')}>
              <div className="flex flex-wrap items-center justify-between gap-2 pb-3 pr-12" data-toolbar="true">
                <div className="flex items-center gap-2">
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
                    <Toggle
                      size="sm"
                      aria-label="Toggle underline"
                      pressed={!!editor?.isActive('underline')}
                      onPressedChange={() => {
                        if (editor?.isActive('underline')) {
                          editor?.chain().focus().unsetMark('underline').run()
                        } else {
                          editor?.chain().focus().setMark('underline').run()
                        }
                      }}
                    >
                      <Underline className="h-4 w-4" />
                    </Toggle>
                    <Toggle
                      size="sm"
                      aria-label="Toggle code"
                      pressed={!!editor?.isActive('code')}
                      onPressedChange={() => editor?.chain().focus().toggleCode().run()}
                    >
                      <Code className="h-4 w-4" />
                    </Toggle>
                  </div>
                  <ToggleGroup
                    type="single"
                    size="sm"
                    aria-label="List type"
                    value={editor?.isActive('orderedList') ? 'ol' : (editor?.isActive('bulletList') ? 'ul' : undefined)}
                    onValueChange={(val) => {
                      if (!editor) return
                      if (val === 'ul') {
                        editor.chain().focus().toggleBulletList().run()
                      } else if (val === 'ol') {
                        editor.chain().focus().toggleOrderedList().run()
                      } else {
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
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  {isSaving ? (
                    <>
                      <div className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />
                      Saving...
                    </>
                  ) : (
                    'Auto-saving enabled'
                  )}
                </div>
              </div>
              <div
                className={cn(
                  'font-sans text-foreground rounded-md border border-border/40 bg-[hsl(var(--brand-surface)/0.95)]',
                  fullPageMode ? 'max-h-[calc(78vh-56px)] overflow-y-auto p-4 pb-12' : 'max-h-[360px] overflow-y-auto p-3 pb-8'
                )}
              >
                <EditorContent
                  editor={editor}
                  className={cn(
                    'prose max-w-none leading-7 text-sm dark:prose-invert',
                    'prose-p:my-3 prose-li:my-1 prose-ul:my-3 prose-ol:my-3',
                    'prose-headings:mt-6 prose-headings:mb-3',
                    '[&_code.agent-name]:bg-blue-100 [&_code.agent-name]:text-blue-900 [&_code.agent-name]:px-1 [&_code.agent-name]:py-0.5 [&_code.agent-name]:rounded [&_code.agent-name]:text-sm [&_code.agent-name]:font-semibold',
                    '[&_code.customer-name]:bg-amber-100 [&_code.customer-name]:text-amber-900 [&_code.customer-name]:px-1 [&_code.customer-name]:py-0.5 [&_code.customer-name]:rounded [&_code.customer-name]:text-sm [&_code.customer-name]:font-semibold'
                  )}
                />
              </div>
              <div className="absolute bottom-4 right-4 rounded bg-background px-2 py-1 text-xs text-muted-foreground shadow">
                {editedText.length.toLocaleString()} characters
              </div>
            </div>
          ) : purifyLoading ? (
            <div className={cn(
              'flex items-center justify-center rounded-md border border-border/40 bg-[hsl(var(--brand-surface)/0.95)]',
              fullPageMode ? 'min-h-[calc(82vh)]' : 'min-h-[380px]'
            )}>
              <div className="text-center space-y-2">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent mx-auto" />
                <p className="text-sm text-muted-foreground">Loading content viewer...</p>
              </div>
            </div>
          ) : (
            <div
              className={cn(
                'prose max-w-none font-sans text-sm leading-relaxed dark:prose-invert rounded-md border border-border/40 text-foreground bg-[hsl(var(--brand-surface)/0.95)]',
                fullPageMode ? 'max-h-[calc(82vh)] overflow-y-auto p-6 pb-12' : 'max-h-[380px] overflow-y-auto p-4 pb-8',
                '[&_code.agent-name]:bg-blue-100 [&_code.agent-name]:text-blue-900 [&_code.agent-name]:px-1 [&_code.agent-name]:py-0.5 [&_code.agent-name]:rounded [&_code.agent-name]:text-sm [&_code.agent-name]:font-semibold [&_code.agent-name]:not-italic',
                '[&_code.customer-name]:bg-amber-100 [&_code.customer-name]:text-amber-900 [&_code.customer-name]:px-1 [&_code.customer-name]:py-0.5 [&_code.customer-name]:rounded [&_code.customer-name]:text-sm [&_code.customer-name]:font-semibold [&_code.customer-name]:not-italic'
              )}
              dangerouslySetInnerHTML={{ __html: sanitizeHtml(isLikelyHtml(extractedText) ? styleNamesInHtml(extractedText) : markdownToHtml(extractedText)) }}
            />
          )}
        </div>

        {showApprovalControls && approvalStatus === 'pending' && (
          <div className="rounded-lg border border-border/60 bg-muted/20 px-4 py-3">
            <p className="text-xs text-muted-foreground mb-3">Review and decide whether this conversation should be added to the knowledge base.</p>
            <div className="flex flex-wrap items-center gap-3">
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
          </div>
        )}

        {approvalStatus === 'approved' && approvedBy && (
          <div className="rounded-lg border border-border/60 bg-muted/10 px-4 py-3 text-sm text-muted-foreground">
            <div className="flex flex-wrap items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-green-600" />
              <span>Approved by {approvedBy}</span>
              {approvedAt && (
                <span>• {formatDistanceToNow(new Date(approvedAt), { addSuffix: true })}</span>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// Export the component wrapped with error boundary
export default withErrorBoundary(UnifiedTextCanvas)
