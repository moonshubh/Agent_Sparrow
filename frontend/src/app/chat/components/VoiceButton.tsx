"use client"

import React, { useEffect, useRef, useState } from 'react'
import { Mic, MicOff } from 'lucide-react'

type Props = {
  onFinalText: (text: string) => void
  onInterimText?: (text: string) => void
  className?: string
}

type SpeechRecognitionResultLike = {
  isFinal: boolean
  0: {
    transcript: string
  }
}

type SpeechRecognitionEventLike = {
  resultIndex: number
  results: ArrayLike<SpeechRecognitionResultLike>
}

type MinimalSpeechRecognition = {
  continuous: boolean
  interimResults: boolean
  lang: string
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onend: (() => void) | null
}

type SpeechRecognitionConstructor = new () => MinimalSpeechRecognition

const getSpeechRecognitionCtor = (): SpeechRecognitionConstructor | null => {
  if (typeof window === 'undefined') return null
  const globalAny = window as typeof window & {
    SpeechRecognition?: SpeechRecognitionConstructor
    webkitSpeechRecognition?: SpeechRecognitionConstructor
  }
  return globalAny.SpeechRecognition || globalAny.webkitSpeechRecognition || null
}

export function VoiceButton({ onFinalText, onInterimText, className }: Props) {
  const [listening, setListening] = useState(false)
  const recognitionRef = useRef<MinimalSpeechRecognition | null>(null)

  useEffect(() => {
    const SpeechRecognitionCtor = getSpeechRecognitionCtor()
    if (!SpeechRecognitionCtor) return

    const recognition = new SpeechRecognitionCtor()
    recognition.continuous = false
    recognition.interimResults = true
    recognition.lang = 'en-US'
    recognition.onresult = (event) => {
      let interim = ''
      let finalText = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i]
        const transcript = result[0]?.transcript ?? ''
        if (result.isFinal) {
          finalText += transcript
        } else {
          interim += transcript
        }
      }
      if (interim && onInterimText) onInterimText(interim)
      if (finalText) onFinalText(finalText)
    }
    recognition.onend = () => setListening(false)
    recognitionRef.current = recognition

    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort()
        } catch {
          // ignore abort errors
        }
        recognitionRef.current = null
      }
    }
  }, [onFinalText, onInterimText])

  const toggle = () => {
    const recognition = recognitionRef.current
    if (!recognition) {
      alert('Voice input is not supported in this browser.')
      return
    }
    if (!listening) {
      try {
        recognition.start()
        setListening(true)
      } catch {
        setListening(false)
      }
    } else {
      try {
        recognition.stop()
      } finally {
        setListening(false)
      }
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
