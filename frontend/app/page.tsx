"use client"

import { ProtectedRoute } from "@/components/auth/ProtectedRoute"
import AIChatPage from "@/app/chat/page"

export default function HomePage() {
  return (
    <ProtectedRoute>
      <AIChatPage />
    </ProtectedRoute>
  )
}
