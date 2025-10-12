"use client"

import { ProtectedRoute } from "@/features/auth/components/ProtectedRoute"
import AIChatPage from "@/app/chat/page"

export default function HomePage() {
  return (
    <ProtectedRoute>
      <AIChatPage />
    </ProtectedRoute>
  )
}
