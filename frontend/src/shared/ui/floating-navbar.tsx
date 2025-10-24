"use client"

import * as React from "react"
import { cn } from "@/shared/lib/utils"

export type FloatingNavItem = {
  name: string
  icon?: React.ReactNode
  href?: string
  onClick?: () => void
  active?: boolean
}

interface FloatingNavProps extends React.HTMLAttributes<HTMLDivElement> {
  navItems: FloatingNavItem[]
  align?: "left" | "center" | "right"
}

export function FloatingNav({ navItems, align = "left", className, children, ...props }: React.PropsWithChildren<FloatingNavProps>) {
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full border border-border/40 bg-background/80 backdrop-blur px-2 py-1 shadow-sm",
        align === "left" && "justify-start",
        align === "center" && "justify-center",
        align === "right" && "ml-auto",
        className,
      )}
      {...props}
    >
      {navItems.map((item, idx) => {
        const Comp = item.href ? "a" : "button"
        const base = "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs transition-colors"
        const isActive = item.active
        const style = isActive
          ? "bg-primary/15 text-primary border border-primary/30"
          : "text-foreground/80 hover:text-foreground hover:bg-muted/60"
        return (
          <Comp
            key={idx}
            className={cn(base, style)}
            href={item.href}
            onClick={(e: any) => {
              if (item.onClick) {
                e.preventDefault()
                item.onClick()
              }
            }}
          >
            {item.icon}
            <span>{item.name}</span>
          </Comp>
        )
      })}
      {children}
    </div>
  )
}
