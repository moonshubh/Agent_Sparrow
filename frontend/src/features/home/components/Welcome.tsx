"use client"

import React from 'react'
import { Avatar, AvatarImage, AvatarFallback } from '@/shared/ui/avatar'

interface WelcomeProps {
  hasMessages: boolean
}

export function Welcome({ hasMessages }: WelcomeProps) {
  return (
    <div className={`flex flex-col items-center justify-center transition-all duration-500 ${
      hasMessages ? 'opacity-0 translate-y-2 pointer-events-none h-0 overflow-hidden' : 'opacity-100 translate-y-0 h-auto'
    }`}>
      {/* Avatar */}
      <Avatar className="size-16 bg-transparent ring-1 ring-accent/20 mx-auto mb-4">
        <AvatarImage className="object-contain p-1" src="/Sparrow_logo.png" alt="Agent Sparrow" />
        <AvatarFallback>AS</AvatarFallback>
      </Avatar>
      
      {/* Tagline */}
      <p className="text-sm text-muted-foreground mb-12">
        Ask, upload, get answers.
      </p>
    </div>
  )
}