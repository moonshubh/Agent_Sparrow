"use client"

import React, { useEffect, useRef, useState } from 'react'
import { Mic, MicOff } from 'lucide-react'

type Props = {
  onFinalText: (text: string) => void
  onInterimText?: (text: string) => void
  className?: string
}

export function VoiceButton({ onFinalText, onInterimText, className }: Props) {
  const [listening, setListening] = useState(false)
  const recognitionRef = useRef<any>(null)

  useEffect(() => {
    const SR: any = (typeof window !== 'undefined' && ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)) || null
    if (!SR) return
    const rec = new SR()
    rec.continuous = false
    rec.interimResults = true
    rec.lang = 'en-US'
    rec.onresult = (event: any) => {
      let interim = ''
      let finalText = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript
        if (event.results[i].isFinal) finalText += transcript
        else interim += transcript
      }
      if (interim && onInterimText) onInterimText(interim)
      if (finalText) onFinalText(finalText)
    }
    rec.onend = () => setListening(false)
    recognitionRef.current = rec
    return () => {
      try { rec.abort() } catch {}
    }
  }, [onFinalText, onInterimText])

  const toggle = () => {
    const rec = recognitionRef.current
    if (!rec) {
      alert('Voice input is not supported in this browser.')
      return
    }
    if (!listening) {
      try { rec.start(); setListening(true) } catch {}
    } else {
      try { rec.stop(); setListening(false) } catch {}
    }
  }

  return (
    <button
      type="button"
      aria-label={listening ? 'Stop voice input' : 'Start voice input'}
      onClick={toggle}
      className={className || 'p-2 rounded-full hover:bg-muted text-muted-foreground relative'}
    >
      {listening ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
      {listening && (
        <span
          aria-hidden
          className="absolute -top-0.5 -right-0.5 inline-flex items-center justify-center"
        >
          <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse shadow-[0_0_8px_rgba(239,68,68,0.7)]" />
        </span>
      )}
    </button>
  )
}
