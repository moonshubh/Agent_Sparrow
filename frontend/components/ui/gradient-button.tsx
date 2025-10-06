"use client"

import * as React from "react"
import { cn } from "@/lib/utils"
import { Button, ButtonProps } from "./button"

export interface GradientButtonProps extends ButtonProps {
  children: React.ReactNode
}

const GradientButton = React.forwardRef<HTMLButtonElement, GradientButtonProps>(
  ({ className, children, ...props }, ref) => {
    const buttonRef = React.useRef<HTMLButtonElement>(null)
    const [mousePosition, setMousePosition] = React.useState({ x: "50%", y: "50%" })

    const handleMouseMove = (e: React.MouseEvent<HTMLButtonElement>) => {
      if (!buttonRef.current) return

      const rect = buttonRef.current.getBoundingClientRect()
      const x = ((e.clientX - rect.left) / rect.width) * 100
      const y = ((e.clientY - rect.top) / rect.height) * 100

      setMousePosition({ x: `${x}%`, y: `${y}%` })
    }

    const handleMouseLeave = () => {
      setMousePosition({ x: "50%", y: "50%" })
    }

    React.useImperativeHandle(ref, () => buttonRef.current!)

    // Merge caller styles with our CSS variables, ensuring vars win
    const mergedStyle: React.CSSProperties = {
      ...(props.style as React.CSSProperties | undefined),
      ["--mouse-x" as any]: mousePosition.x,
      ["--mouse-y" as any]: mousePosition.y,
    }

    // Compose mouse handlers so consumer callbacks still fire
    const composedOnMouseMove = (e: React.MouseEvent<HTMLButtonElement>) => {
      handleMouseMove(e)
      props.onMouseMove?.(e)
    }
    const composedOnMouseLeave = (e: React.MouseEvent<HTMLButtonElement>) => {
      handleMouseLeave()
      props.onMouseLeave?.(e)
    }

    return (
      <Button
        ref={buttonRef}
        className={cn("gradient-glow-button", className)}
        style={mergedStyle}
        onMouseMove={composedOnMouseMove}
        onMouseLeave={composedOnMouseLeave}
        {...(() => {
          const { onMouseMove, onMouseLeave, style, ...rest } = props
          return rest
        })()}
      >
        <span className="relative flex items-center justify-center gap-2">
          {children}
        </span>
      </Button>
    )
  }
)

GradientButton.displayName = "GradientButton"

export { GradientButton }