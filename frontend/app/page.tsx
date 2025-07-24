"use client"

import UnifiedChatInterface from "@/components/chat/UnifiedChatInterface"
import { ProtectedRoute } from "@/components/auth/ProtectedRoute"

export default function HomePage() {
  return (
    <ProtectedRoute>
      <UnifiedChatInterface />
    </ProtectedRoute>
  )
}