"use client"

import { useRouter } from "next/navigation"
import { useEffect } from "react"

export default function SettingsPage() {
  const router = useRouter()

  useEffect(() => {
    // Redirect to chat immediately - settings should be opened as modal from chat
    router.replace('/chat')
  }, [router])

  return null
}
