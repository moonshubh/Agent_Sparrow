"use client"

import React, { useEffect, useMemo, useState } from 'react'
import { Image as ImageIcon, FileText, X, Paperclip, ChevronLeft, ChevronRight } from 'lucide-react'

export type MediaAttachment = {
  file: File
}

export type LogAttachment = {
  file: File
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

export function Attachments({
  mediaFiles,
  logFile,
  onRemoveMedia,
  onRemoveLog,
}: {
  mediaFiles: File[]
  logFile: File | null
  onRemoveMedia: (index: number) => void
  onRemoveLog: () => void
}) {
  if (mediaFiles.length === 0 && !logFile) return null

  // Generate object URLs for image previews and revoke them on cleanup
  const [urls, setUrls] = useState<string[]>([])
  const [imageUrls, setImageUrls] = useState<string[]>([])
  const [imageIndexByFileIndex, setImageIndexByFileIndex] = useState<Record<number, number>>({})
  const [lightboxOpen, setLightboxOpen] = useState(false)
  const [activeImage, setActiveImage] = useState(0)
  useEffect(() => {
    const next: string[] = []
    const images: string[] = []
    const indexMap: Record<number, number> = {}
    for (const f of mediaFiles) {
      if (f.type.startsWith('image/')) {
        try {
          const u = URL.createObjectURL(f)
          next.push(u)
          indexMap[next.length - 1] = images.length
          images.push(u)
        } catch {}
      } else {
        next.push('')
      }
    }
    setUrls(next)
    setImageUrls(images)
    setImageIndexByFileIndex(indexMap)
    return () => {
      for (const u of next) {
        if (u) URL.revokeObjectURL(u)
      }
    }
  }, [mediaFiles])

  const openLightbox = (fileIdx: number) => {
    const imgIdx = imageIndexByFileIndex[fileIdx]
    if (typeof imgIdx === 'number') {
      setActiveImage(imgIdx)
      setLightboxOpen(true)
    }
  }

  const closeLightbox = () => setLightboxOpen(false)
  const prevImage = () => setActiveImage((i) => (i - 1 + imageUrls.length) % imageUrls.length)
  const nextImage = () => setActiveImage((i) => (i + 1) % imageUrls.length)
  
  React.useEffect(() => {
    if (!lightboxOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeLightbox()
      if (e.key === 'ArrowLeft') prevImage()
      if (e.key === 'ArrowRight') nextImage()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [lightboxOpen, imageUrls.length])

  return (
    <div className="flex flex-wrap gap-2">
      {mediaFiles.map((f, idx) => {
        const isImage = f.type.startsWith('image/')
        return (
          <div key={idx} className="group flex items-center gap-2 px-2 py-1.5 rounded-full border border-border/60 bg-muted/30 text-xs">
            {isImage ? (
              urls[idx] ? (
                <img src={urls[idx]} alt={f.name} className="w-6 h-6 rounded object-cover cursor-zoom-in" onClick={() => openLightbox(idx)} />
              ) : (
                <ImageIcon className="w-3.5 h-3.5 text-mb-blue-500" />
              )
            ) : (
              <Paperclip className="w-3.5 h-3.5 text-mb-blue-500" />
            )}
            <span className="max-w-[160px] truncate" title={f.name}>{f.name}</span>
            <span className="text-muted-foreground">{formatBytes(f.size)}</span>
            <button
              type="button"
              className="ml-1 rounded hover:bg-muted p-0.5"
              onClick={() => onRemoveMedia(idx)}
              aria-label={`Remove ${f.name}`}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )
      })}
      {logFile && (
        <div className="group flex items-center gap-2 px-2 py-1.5 rounded-full border border-orange-500/40 dark:border-orange-500/60 bg-orange-500/10 dark:bg-orange-500/20 text-xs">
          <FileText className="w-3.5 h-3.5 text-orange-500" />
          <span className="font-medium text-orange-600 dark:text-orange-300">Log Analysis</span>
          <span className="max-w-[200px] truncate" title={logFile.name}>{logFile.name}</span>
          <span className="text-muted-foreground">{formatBytes(logFile.size)}</span>
          <button
            type="button"
            className="ml-1 rounded hover:bg-muted p-0.5"
            onClick={onRemoveLog}
            aria-label={`Remove ${logFile.name}`}
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
      {/* Lightbox Overlay */}
      {lightboxOpen && imageUrls.length > 0 && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4" onClick={closeLightbox}>
          <button type="button" className="absolute left-4 text-white/80 hover:text-white" onClick={(e) => { e.stopPropagation(); prevImage() }} aria-label="Previous image">
            <ChevronLeft className="w-6 h-6" />
          </button>
          <img src={imageUrls[activeImage]} alt="Attachment preview" className="max-h-[90vh] max-w-[90vw] object-contain rounded shadow-lg" onClick={(e) => e.stopPropagation()} />
          <button type="button" className="absolute right-4 text-white/80 hover:text-white" onClick={(e) => { e.stopPropagation(); nextImage() }} aria-label="Next image">
            <ChevronRight className="w-6 h-6" />
          </button>
          <button type="button" className="absolute top-4 right-4 text-white/80 hover:text-white" onClick={(e) => { e.stopPropagation(); closeLightbox() }} aria-label="Close preview">
            <X className="w-6 h-6" />
          </button>
        </div>
      )}
    </div>
  )
}
