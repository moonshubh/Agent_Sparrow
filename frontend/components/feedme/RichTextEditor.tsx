/**
 * Rich Text Editor Component
 * Simple rich text editor with formatting toolbar for transcript editing
 * 
 * Features:
 * - Basic formatting (bold, italic, underline)
 * - Line breaks and paragraphs
 * - Keyboard shortcuts
 * - Undo/redo functionality
 * - Auto-save capabilities
 */

'use client'

import React, { useRef, useEffect, useState, useCallback } from 'react'
import { Button } from '../ui/button'
import { 
  Bold, 
  Italic, 
  Underline, 
  Undo2, 
  Redo2,
  Type,
  AlignLeft,
  List
} from 'lucide-react'
import { cn } from '../../lib/utils'

interface RichTextEditorProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
  disabled?: boolean
}

interface ToolbarButtonProps {
  command: string
  icon: React.ReactNode
  title: string
  isActive?: boolean
  onClick: () => void
}

function ToolbarButton({ command, icon, title, isActive, onClick }: ToolbarButtonProps) {
  return (
    <Button
      type="button"
      variant={isActive ? "default" : "ghost"}
      size="sm"
      className={cn(
        "h-8 w-8 p-0",
        isActive && "bg-accent text-accent-foreground"
      )}
      onClick={onClick}
      title={title}
      aria-label={title}
      aria-pressed={isActive}
      role="button"
    >
      {icon}
    </Button>
  )
}

export function RichTextEditor({ 
  value, 
  onChange, 
  placeholder = "Start typing...", 
  className,
  disabled = false 
}: RichTextEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null)
  const [isEditorFocused, setIsEditorFocused] = useState(false)
  const [toolbarState, setToolbarState] = useState({
    bold: false,
    italic: false,
    underline: false
  })

  // Initialize editor content
  useEffect(() => {
    if (editorRef.current && editorRef.current.innerHTML !== value) {
      editorRef.current.innerHTML = value
    }
  }, [value])

  // Update toolbar state based on current selection
  const updateToolbarState = useCallback(() => {
    if (disabled) return
    
    try {
      const selection = window.getSelection()
      if (!selection || selection.rangeCount === 0) return
      
      const range = selection.getRangeAt(0)
      const parentElement = range.commonAncestorContainer.nodeType === Node.TEXT_NODE 
        ? range.commonAncestorContainer.parentElement 
        : range.commonAncestorContainer as Element
      
      if (!parentElement) return
      
      // Check for formatting by traversing parent elements
      let element = parentElement
      const state = { bold: false, italic: false, underline: false }
      
      while (element && element !== editorRef.current) {
        const style = window.getComputedStyle(element)
        if (style.fontWeight === 'bold' || style.fontWeight === '700' || element.tagName === 'B' || element.tagName === 'STRONG') {
          state.bold = true
        }
        if (style.fontStyle === 'italic' || element.tagName === 'I' || element.tagName === 'EM') {
          state.italic = true
        }
        if (style.textDecoration.includes('underline') || element.tagName === 'U') {
          state.underline = true
        }
        element = element.parentElement as Element
      }
      
      setToolbarState(state)
    } catch (error) {
      // Ignore errors in selection detection
      console.warn('Error updating toolbar state:', error)
    }
  }, [disabled])

  // Handle content changes
  const handleInput = useCallback((e: React.FormEvent<HTMLDivElement>) => {
    if (disabled) return
    
    const target = e.target as HTMLDivElement
    const content = target.innerHTML
    onChange(content)
  }, [onChange, disabled])

  // Handle keyboard shortcuts
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return

    // Ctrl/Cmd + B for bold
    if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
      e.preventDefault()
      execCommand('bold')
    }
    
    // Ctrl/Cmd + I for italic
    if ((e.ctrlKey || e.metaKey) && e.key === 'i') {
      e.preventDefault()
      execCommand('italic')
    }
    
    // Ctrl/Cmd + U for underline
    if ((e.ctrlKey || e.metaKey) && e.key === 'u') {
      e.preventDefault()
      execCommand('underline')
    }

    // Ctrl/Cmd + Z for undo
    if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
      e.preventDefault()
      execCommand('undo')
    }

    // Ctrl/Cmd + Y or Ctrl/Cmd + Shift + Z for redo
    if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
      e.preventDefault()
      execCommand('redo')
    }
  }, [disabled])

  // Execute formatting commands
  const execCommand = useCallback((command: string, value?: string) => {
    if (disabled) return
    
    try {
      document.execCommand(command, false, value)
      updateToolbarState()
      
      // Trigger onChange to capture the updated content
      if (editorRef.current) {
        onChange(editorRef.current.innerHTML)
      }
    } catch (error) {
      console.warn('Failed to execute command:', command, error)
    }
  }, [disabled, onChange, updateToolbarState])

  // Handle selection changes
  useEffect(() => {
    const handleSelectionChange = () => {
      if (isEditorFocused) {
        updateToolbarState()
      }
    }

    document.addEventListener('selectionchange', handleSelectionChange)
    return () => document.removeEventListener('selectionchange', handleSelectionChange)
  }, [isEditorFocused, updateToolbarState])

  // Focus management
  const handleFocus = () => {
    setIsEditorFocused(true)
    updateToolbarState()
  }

  const handleBlur = () => {
    setIsEditorFocused(false)
  }

  // Paste handling to clean up pasted content
  const handlePaste = useCallback((e: React.ClipboardEvent<HTMLDivElement>) => {
    if (disabled) return

    e.preventDefault()
    
    // Get plain text from clipboard
    const text = e.clipboardData.getData('text/plain')
    
    // Insert as plain text to avoid unwanted formatting
    document.execCommand('insertText', false, text)
    
    // Update content
    if (editorRef.current) {
      onChange(editorRef.current.innerHTML)
    }
  }, [disabled, onChange])

  return (
    <div className={cn("border rounded-md overflow-hidden", className)}>
      {/* Toolbar */}
      <div 
        role="toolbar" 
        className="flex items-center gap-1 p-2 border-b bg-muted/30"
        aria-label="Text formatting toolbar"
      >
        <div className="flex items-center gap-1">
          <ToolbarButton
            command="bold"
            icon={<Bold className="h-4 w-4" />}
            title="Bold (Ctrl+B)"
            isActive={toolbarState.bold}
            onClick={() => execCommand('bold')}
          />
          <ToolbarButton
            command="italic"
            icon={<Italic className="h-4 w-4" />}
            title="Italic (Ctrl+I)"
            isActive={toolbarState.italic}
            onClick={() => execCommand('italic')}
          />
          <ToolbarButton
            command="underline"
            icon={<Underline className="h-4 w-4" />}
            title="Underline (Ctrl+U)"
            isActive={toolbarState.underline}
            onClick={() => execCommand('underline')}
          />
        </div>

        <div className="w-px h-6 bg-border mx-2" />

        <div className="flex items-center gap-1">
          <ToolbarButton
            command="insertUnorderedList"
            icon={<List className="h-4 w-4" />}
            title="Bullet List"
            onClick={() => execCommand('insertUnorderedList')}
          />
        </div>

        <div className="w-px h-6 bg-border mx-2" />

        <div className="flex items-center gap-1">
          <ToolbarButton
            command="undo"
            icon={<Undo2 className="h-4 w-4" />}
            title="Undo (Ctrl+Z)"
            onClick={() => execCommand('undo')}
          />
          <ToolbarButton
            command="redo"
            icon={<Redo2 className="h-4 w-4" />}
            title="Redo (Ctrl+Y)"
            onClick={() => execCommand('redo')}
          />
        </div>

        <div className="flex-1" />

        <div className="text-xs text-muted-foreground">
          Ctrl+B/I/U for formatting
        </div>
      </div>

      {/* Editor */}
      <div
        ref={editorRef}
        contentEditable={!disabled}
        className={cn(
          "min-h-[200px] max-h-[400px] overflow-y-auto p-4 focus:outline-none",
          "prose prose-sm max-w-none",
          "[&>*]:my-1 [&>*:first-child]:mt-0 [&>*:last-child]:mb-0",
          disabled && "opacity-50 cursor-not-allowed"
        )}
        onInput={handleInput}
        onKeyDown={handleKeyDown}
        onFocus={handleFocus}
        onBlur={handleBlur}
        onPaste={handlePaste}
        role="textbox"
        aria-label="Transcript content"
        aria-multiline="true"
        style={{
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word'
        }}
        data-placeholder={placeholder}
      />

      {/* Placeholder styling */}
      <style jsx>{`
        [contenteditable][data-placeholder]:empty:before {
          content: attr(data-placeholder);
          color: #9ca3af;
          pointer-events: none;
          position: absolute;
        }
      `}</style>
    </div>
  )
}