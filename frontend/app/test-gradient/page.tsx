"use client"

import { GradientButton } from "@/components/ui/gradient-button"
import { Plus } from "lucide-react"

export default function TestGradientPage() {
  return (
    <div className="min-h-screen bg-background p-8">
      <div className="max-w-4xl mx-auto space-y-8">
        <h1 className="text-3xl font-bold mb-8">Gradient Button Test - Bug Fix Verification</h1>

        <div className="space-y-4">
          <h2 className="text-xl font-semibold text-green-500">✅ Fixed Implementation</h2>
          <p className="text-sm text-muted-foreground mb-4">
            The gradient should now appear BEHIND the button text when you hover.
          </p>

          <div className="flex gap-4 items-center">
            <GradientButton>
              <Plus className="h-4 w-4" />
              New Chat
            </GradientButton>

            <GradientButton variant="default" size="lg">
              Larger Button
            </GradientButton>

            <GradientButton variant="default" size="sm">
              Small
            </GradientButton>
          </div>
        </div>

        <div className="mt-12 p-6 bg-secondary rounded-lg">
          <h3 className="font-semibold mb-2">🐛 The Bug's Story (à la Grace Hopper)</h3>
          <p className="text-sm leading-relaxed mb-4">
            Like the famous moth found in the Mark II computer, this bug had a simple but elusive cause:
            CSS pseudo-elements with positive z-index values don't behave as expected in their stacking context.
          </p>
          <div className="space-y-2 text-sm">
            <p><strong>Root Cause:</strong> The ::before pseudo-element with z-index: 1 was appearing above its siblings.</p>
            <p><strong>Solution:</strong> Use z-index: -1 on the ::before element and z-index: 0 on the parent to establish proper stacking context.</p>
            <p><strong>Lesson:</strong> "The most dangerous phrase in the language is: We've always done it this way." - Sometimes positive z-index isn't the answer!</p>
          </div>
        </div>

        <div className="mt-8 p-4 bg-blue-500/10 border border-blue-500/20 rounded">
          <p className="text-sm">
            <strong>Testing Instructions:</strong> Hover over the buttons above. The gradient glow should appear
            as a subtle background effect behind the text, not on top of it.
          </p>
        </div>
      </div>
    </div>
  )
}