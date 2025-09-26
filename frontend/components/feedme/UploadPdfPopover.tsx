"use client"

import React, { useCallback, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Upload, File as FileIcon } from "lucide-react"
import { useConversationsStore } from "@/lib/stores/conversations-store"

interface UploadPdfPopoverProps {
  children: React.ReactNode
  onUploaded?: () => void
}

export function UploadPdfPopover({ children, onUploaded }: UploadPdfPopoverProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [open, setOpen] = useState(false)
  const [isHovering, setIsHovering] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const actions = useConversationsStore((s) => s.actions)

  const validatePdf = (file: File): string | null => {
    if (!file) return "No file selected"
    const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")
    if (!isPdf) return "Only PDF files are supported"
    // 20MB cap consistent with docs
    const maxSize = 20 * 1024 * 1024
    if (file.size > maxSize) return "PDF must be smaller than 20MB"
    return null
  }

  const handleUpload = useCallback(async (file: File) => {
    const validation = validatePdf(file)
    if (validation) {
      setError(validation)
      return
    }
    setError(null)
    const title = file.name.replace(/\.pdf$/i, "")
    await actions.uploadConversation({ type: "file", title, file, autoProcess: true })
    setOpen(false)
    onUploaded?.()
  }, [actions, onUploaded])

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) void handleUpload(file)
    // reset input so same file can be re-selected
    if (fileInputRef.current) fileInputRef.current.value = ""
  }

  const onDrop: React.DragEventHandler<HTMLDivElement> = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    const file = e.dataTransfer.files?.[0]
    if (file) void handleUpload(file)
  }

  const onDragOver: React.DragEventHandler<HTMLDivElement> = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(true)
  }

  const onDragLeave: React.DragEventHandler<HTMLDivElement> = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <div onMouseEnter={() => setIsHovering(true)} onMouseLeave={() => setIsHovering(false)}>
          {children}
        </div>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0 overflow-hidden">
        <Tabs defaultValue="single" className="w-full">
          <TabsList className="grid grid-cols-2 m-2">
            <TabsTrigger value="single">Single File</TabsTrigger>
            <TabsTrigger value="drag">Drag & Drop</TabsTrigger>
          </TabsList>

          <TabsContent value="single" className="m-0">
            <div className="p-4 space-y-3">
              <p className="text-sm text-muted-foreground">Upload a single PDF file (max 20MB)</p>
              <div className="flex items-center gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf"
                  className="hidden"
                  onChange={onFileChange}
                />
                <Button onClick={() => fileInputRef.current?.click()} className="gap-2">
                  <Upload className="h-4 w-4" />
                  Choose PDF
                </Button>
              </div>
              {error && <p className="text-xs text-destructive">{error}</p>}
              <p className="text-xs text-muted-foreground">We’ll auto-queue processing after upload.</p>
            </div>
          </TabsContent>

          <TabsContent value="drag" className="m-0">
            <div className="p-4">
              <div
                onDrop={onDrop}
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                className={`border-2 border-dashed rounded-md p-6 text-center transition-colors ${dragActive ? "border-accent bg-accent/5" : "border-muted"}`}
              >
                <FileIcon className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
                <p className="text-sm">Drag a PDF here</p>
                <p className="text-xs text-muted-foreground">Single file only • Max 20MB</p>
              </div>
              {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
            </div>
          </TabsContent>
        </Tabs>
      </PopoverContent>
    </Popover>
  )
}

