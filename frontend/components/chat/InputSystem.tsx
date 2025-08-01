"use client"

import React, { useState, useRef, useCallback, useEffect, useImperativeHandle, forwardRef } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Send,
  Paperclip,
  X,
  Upload,
  FileText,
  Loader2,
  Mic,
  MicOff,
  Plus,
  Sparkles
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { useDebouncedCallback, usePerformanceMonitor } from '@/hooks/usePerformance'

interface InputSystemProps {
  value: string
  onChange: (value: string) => void
  onSubmit: (message: string, files?: File[]) => Promise<void>
  files: File[]
  onFilesChange: (files: File[]) => void
  isLoading: boolean
  placeholder?: string
  maxFiles?: number
  acceptedFileTypes?: string[]
  disabled?: boolean
  isWelcomeMode?: boolean
}

export interface InputSystemRef {
  clearInput: () => void
  focusInput: () => void
  getInputValue: () => string
}

interface FileUploadProps {
  files: File[]
  onFilesChange: (files: File[]) => void
  maxFiles?: number
  acceptedFileTypes?: string[]
  className?: string
}

function FileUploadZone({ 
  files, 
  onFilesChange, 
  maxFiles = 5, 
  acceptedFileTypes = ['.log', '.txt', '.json', '.csv'],
  className 
}: FileUploadProps) {
  const [isDragOver, setIsDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  
  const handleFileSelect = (selectedFiles: FileList | null) => {
    if (!selectedFiles) return
    
    const fileArray = Array.from(selectedFiles)
    const validFiles = fileArray.filter(file => {
      const extension = '.' + file.name.split('.').pop()?.toLowerCase()
      return acceptedFileTypes.includes(extension) || file.type.includes('text')
    })
    
    if (validFiles.length !== fileArray.length) {
      toast.warning('Some files were skipped. Only text and log files are supported.')
    }
    
    if (files.length + validFiles.length > maxFiles) {
      toast.error(`Maximum ${maxFiles} files allowed`)
      return
    }
    
    onFilesChange([...files, ...validFiles])
  }
  
  const removeFile = (index: number) => {
    onFilesChange(files.filter((_, i) => i !== index))
  }
  
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(true)
  }
  
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
  }
  
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    handleFileSelect(e.dataTransfer.files)
  }
  
  return (
    <div className={cn("space-y-3", className)}>
      {/* File List */}
      {files.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-chat-metadata">
            Uploaded Files ({files.length}/{maxFiles})
          </div>
          {files.map((file, index) => (
            <div key={index} className="flex items-center justify-between bg-chat-agent-bg border border-border/50 rounded-lg px-3 py-2">
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <FileText className="w-4 h-4 text-primary flex-shrink-0" />
                <span className="text-sm font-medium text-foreground truncate">
                  {file.name}
                </span>
                <Badge variant="outline" className="text-xs flex-shrink-0">
                  {(file.size / 1024).toFixed(1)}KB
                </Badge>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => removeFile(index)}
                className="h-6 w-6 p-0 text-chat-metadata hover:text-destructive"
              >
                <X className="w-3 h-3" />
              </Button>
            </div>
          ))}
        </div>
      )}
      
      {/* Upload Area */}
      {files.length < maxFiles && (
        <div
          className={cn(
            "relative border-2 border-dashed rounded-lg transition-all duration-200",
            isDragOver 
              ? "border-primary bg-primary/5" 
              : "border-border/50 hover:bg-mb-blue-300/5"
          )}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={acceptedFileTypes.join(',')}
            onChange={(e) => handleFileSelect(e.target.files)}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          />
          <div className="flex items-center justify-center gap-2 p-4">
            <Upload className="w-4 h-4 text-chat-metadata" />
            <span className="text-sm text-chat-metadata">
              {isDragOver ? 'Drop files here' : 'Drag files or click to upload'}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

// QuickSuggestions component removed for cleaner zen design

const InputSystem = forwardRef<InputSystemRef, InputSystemProps>(function InputSystem({
  value,
  onChange,
  onSubmit,
  files,
  onFilesChange,
  isLoading,
  placeholder = "Ask a question, upload logs, or request research...",
  maxFiles = 5,
  acceptedFileTypes = ['.log', '.txt', '.json', '.csv'],
  disabled = false,
  isWelcomeMode = false
}: InputSystemProps, ref) {
  const [isRecording, setIsRecording] = useState(false)
  const [isDragOver, setIsDragOver] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const submitTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  
  // Expose methods to parent components
  useImperativeHandle(ref, () => ({
    clearInput: () => {
      clearInputSafely()
    },
    focusInput: () => {
      textareaRef.current?.focus()
    },
    getInputValue: () => value
  }), [value])
  
  // Safe input clearing with proper state management
  const clearInputSafely = useCallback(() => {
    // Clear the timeout if it exists
    if (submitTimeoutRef.current) {
      clearTimeout(submitTimeoutRef.current)
      submitTimeoutRef.current = null
    }
    
    // Reset all states
    onChange('')
    onFilesChange([])
    setIsSubmitting(false)
    
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = isWelcomeMode ? '32px' : '48px'
      // Focus with a small delay to ensure proper clearing
      setTimeout(() => {
        textareaRef.current?.focus()
      }, 0)
    }
  }, [onChange, onFilesChange, isWelcomeMode])
  
  // Performance monitoring in development
  usePerformanceMonitor('InputSystem', 16)
  
  // Auto-resize textarea with debouncing for better performance
  const adjustTextareaHeight = useCallback(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      const newHeight = Math.min(textarea.scrollHeight, 120) // Max 120px
      textarea.style.height = `${newHeight}px`
    }
  }, [])
  
  // Debounced version of textarea height adjustment
  const debouncedAdjustHeight = useDebouncedCallback(
    adjustTextareaHeight,
    50, // 50ms delay
    [adjustTextareaHeight]
  )
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (submitTimeoutRef.current) {
        clearTimeout(submitTimeoutRef.current)
      }
    }
  }, [])
  
  useEffect(() => {
    // Use debounced version for better performance during rapid typing
    if (value.length > 0) {
      debouncedAdjustHeight()
    } else {
      // Immediately adjust when input is cleared
      adjustTextareaHeight()
    }
  }, [value, adjustTextareaHeight, debouncedAdjustHeight])

  // File handling functions
  const handleFileSelect = (selectedFiles: FileList | null) => {
    if (!selectedFiles) return
    
    const fileArray = Array.from(selectedFiles)
    const validFiles = fileArray.filter(file => {
      const extension = '.' + file.name.split('.').pop()?.toLowerCase()
      return acceptedFileTypes.includes(extension) || file.type.includes('text')
    })
    
    if (validFiles.length !== fileArray.length) {
      toast.warning('Some files were skipped. Only text and log files are supported.')
    }
    
    if (files.length + validFiles.length > maxFiles) {
      toast.error(`Maximum ${maxFiles} files allowed`)
      return
    }
    
    onFilesChange([...files, ...validFiles])
  }

  const removeFile = (index: number) => {
    onFilesChange(files.filter((_, i) => i !== index))
  }

  const handlePaperclipClick = () => {
    fileInputRef.current?.click()
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    handleFileSelect(e.dataTransfer.files)
  }
  
  const handleSubmit = async () => {
    if ((!value.trim() && files.length === 0) || isLoading || disabled || isSubmitting) return
    
    const messageText = value.trim() || (files.length > 0 ? 'Please analyze the uploaded files' : '')
    
    // Prevent double submission
    setIsSubmitting(true)
    
    try {
      // Clear input immediately for better UX
      const currentValue = value
      const currentFiles = [...files]
      clearInputSafely()
      
      await onSubmit(messageText, currentFiles.length > 0 ? currentFiles : undefined)
      
      // Additional safety timeout to ensure state is cleared
      submitTimeoutRef.current = setTimeout(() => {
        setIsSubmitting(false)
        submitTimeoutRef.current = null
      }, 500)
      
    } catch (error) {
      // Restore input values on error using preserved values
      onChange(currentValue)
      onFilesChange(currentFiles)
      setIsSubmitting(false)
      console.error('Failed to send message:', error)
      toast.error('Failed to send message')
    }
  }
  
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !isLoading && !disabled && !isSubmitting) {
      e.preventDefault()
      handleSubmit()
    }
    
    // ESC key to clear input
    if (e.key === 'Escape' && !isLoading) {
      e.preventDefault()
      clearInputSafely()
    }
  }
  
  const canSubmit = (value.trim() || files.length > 0) && !isLoading && !disabled && !isSubmitting
  
  return (
    <div className="space-y-3">
      {/* Uploaded Files List */}
      {files.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-chat-metadata">
            Uploaded Files ({files.length}/{maxFiles})
          </div>
          {files.map((file, index) => (
            <div key={index} className="flex items-center justify-between bg-chat-agent-bg border border-border/50 rounded-lg px-3 py-2">
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <FileText className="w-4 h-4 text-primary flex-shrink-0" />
                <span className="text-sm font-medium text-foreground truncate">
                  {file.name}
                </span>
                <Badge variant="outline" className="text-xs flex-shrink-0">
                  {(file.size / 1024).toFixed(1)}KB
                </Badge>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => removeFile(index)}
                className="h-6 w-6 p-0 text-chat-metadata hover:text-destructive"
              >
                <X className="w-3 h-3" />
              </Button>
            </div>
          ))}
        </div>
      )}
      
      {/* Main Input Area with Drag & Drop */}
      <div className={cn(
        "relative",
        isWelcomeMode && "flex justify-center"
      )}>
        <div 
          className={cn(
            "relative flex items-end gap-2 transition-all duration-200",
            isWelcomeMode 
              ? "w-full max-w-[600px] bg-background/80 backdrop-blur-sm border border-border/50 rounded-3xl px-6 py-4 shadow-lg focus-within:ring-2 focus-within:ring-accent"
              : "w-full bg-background/90 backdrop-blur-sm border border-border/60 rounded-2xl px-4 py-3 shadow-md focus-within:border-accent focus-within:shadow-lg",
            isDragOver 
              ? "border-accent bg-accent/10 border-2 shadow-lg" 
              : "",
            disabled && "opacity-50 cursor-not-allowed"
          )}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {/* Hidden File Input */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={acceptedFileTypes.join(',')}
            onChange={(e) => handleFileSelect(e.target.files)}
            className="hidden"
          />
          
          {/* Drag Overlay */}
          {isDragOver && (
            <div className="absolute inset-0 flex items-center justify-center bg-primary/10 rounded-xl z-10">
              <div className="text-sm font-medium text-primary">Drop files to upload</div>
            </div>
          )}
          
          {/* Textarea */}
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(e) => {
                onChange(e.target.value)
                // Immediate height adjustment for better UX
                if (e.target.value.length < 50) {
                  adjustTextareaHeight()
                }
              }}
              onKeyDown={handleKeyDown}
              placeholder={files.length > 0 ? "Describe the issue or ask questions about the uploaded files..." : placeholder}
              disabled={disabled || isLoading}
              aria-label="Type your message"
              aria-describedby="input-help-text"
              role="textbox"
              aria-multiline="true"
              className={cn(
                "w-full resize-none border-0 bg-transparent px-0 py-1",
                "text-chat-input-text placeholder:text-chat-metadata",
                "focus:outline-none focus:ring-0 transition-all duration-150",
                isWelcomeMode 
                  ? "text-lg min-h-[32px] max-h-[120px]" 
                  : "text-sm min-h-[40px] max-h-[120px]"
              )}
              style={{ height: isWelcomeMode ? '32px' : '48px' }}
            />
            
            {/* Character count for longer messages */}
            {value.length > 100 && (
              <div className="absolute bottom-1 right-1 text-xs text-chat-metadata">
                {value.length}
              </div>
            )}
          </div>
          
          {/* Action Buttons */}
          <div className="flex items-center gap-1 pr-2 pb-2">
            {/* File Upload Button */}
            <Button
              variant="ghost"
              size="sm"
              onClick={handlePaperclipClick}
              disabled={disabled || files.length >= maxFiles}
              className={cn(
                "h-8 w-8 p-0 text-chat-metadata hover:text-foreground",
                files.length > 0 && "text-primary"
              )}
            >
              <Paperclip className="w-4 h-4" />
            </Button>
            
            {/* Voice Recording (Future Enhancement) */}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsRecording(!isRecording)}
              disabled={disabled}
              className={cn(
                "h-8 w-8 p-0 text-chat-metadata hover:text-foreground",
                isRecording && "text-red-500"
              )}
            >
              {isRecording ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
            </Button>
            
            {/* Send Button */}
            <Button
              onClick={handleSubmit}
              disabled={!canSubmit}
              size="sm"
              className={cn(
                "h-8 w-8 p-0 rounded-lg transition-all",
                canSubmit 
                  ? "bg-primary hover:bg-mb-blue-300/90 text-primary-foreground" 
                  : "bg-muted text-muted-foreground cursor-not-allowed"
              )}
              aria-label="Send message"
            >
              {(isLoading || isSubmitting) ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </Button>
          </div>
        </div>
        
      </div>
      
      {/* Accessibility helper text */}
      <div id="input-help-text" className="sr-only">
        Type your message and press Enter to send, or Shift+Enter for new line. Press Escape to clear input.
      </div>
    </div>
  )
})

InputSystem.displayName = 'InputSystem'

export default InputSystem