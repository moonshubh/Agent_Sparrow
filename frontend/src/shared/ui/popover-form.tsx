"use client"

import React from "react"
import { X, Check, Loader2 } from "lucide-react"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"

type PopoverFormProps = {
  title?: string
  open: boolean
  setOpen: (v: boolean) => void
  width?: string
  height?: string
  showCloseButton?: boolean
  showSuccess?: boolean
  openChild: React.ReactNode
  successChild?: React.ReactNode
}

export function PopoverForm({
  title,
  open,
  setOpen,
  width = "364px",
  height = "auto",
  showCloseButton = true,
  showSuccess = false,
  openChild,
  successChild,
}: PopoverFormProps) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-[70] grid place-items-center overflow-hidden">
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-[2px]"
        onClick={() => setOpen(false)}
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          "relative rounded-xl border border-border/50 bg-popover text-popover-foreground shadow-2xl",
          "animate-in fade-in zoom-in-95 duration-150",
        )}
        style={{ width, height }}
      >
        {showCloseButton && (
          <button
            aria-label="Close"
            className="absolute right-2 top-2 inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/40"
            onClick={() => setOpen(false)}
          >
            <X className="h-4 w-4" />
          </button>
        )}
        {title && (
          <div className="px-4 pt-4 pb-2 text-sm font-medium text-foreground/90">
            {title}
          </div>
        )}

        <div className="px-3 pb-3 pt-1">
          {showSuccess ? successChild : openChild}
        </div>
      </div>
    </div>
  )
}

export function PopoverFormButton({
  loading,
  children = "Submit",
  onClick,
  className,
}: {
  loading?: boolean
  children?: React.ReactNode
  onClick?: () => void
  className?: string
}) {
  return (
    <Button
      type="button"
      onClick={onClick}
      disabled={loading}
      variant="default"
      className={cn("h-9 px-3", className)}
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <Check className="h-4 w-4" />
      )}
      <span>{children}</span>
    </Button>
  )
}

export function PopoverFormSeparator() {
  return <div className="h-px w-full bg-border" />
}

export function PopoverFormCutOutLeftIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <circle cx="10" cy="10" r="9" className="fill-popover stroke-border" />
    </svg>
  )
}

export function PopoverFormCutOutRightIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <circle cx="10" cy="10" r="9" className="fill-popover stroke-border" />
    </svg>
  )
}

export function PopoverFormSuccess({
  title = "Submitted",
  description = "Thanks for your input!",
}: {
  title?: string
  description?: string
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-primary">
        <Check className="h-5 w-5" />
      </div>
      <div className="text-base font-medium">{title}</div>
      <div className="text-sm text-muted-foreground">{description}</div>
    </div>
  )
}
