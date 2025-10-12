import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/shared/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        // Global style change: all buttons use black background with white text (except custom GradientButton)
        default: "bg-black text-white hover:bg-black/85",
        destructive: "bg-black text-white hover:bg-black/85",
        outline: "border border-input bg-black text-white hover:bg-black/85",
        secondary: "bg-black text-white hover:bg-black/85",
        ghost: "bg-black text-white hover:bg-black/85",
        link: "text-white underline-offset-4 hover:opacity-80",
        gradient: "bg-[linear-gradient(to_right,hsl(0_0%_14.9%)_0%,hsl(0_0%_14.9%)_90%,hsl(217.2_83.2%_53.3%)_93%,hsl(225.9_70.7%_40.2%)_97%,hsl(226.2_57%_21%)_100%)] text-white shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 hover:scale-[1.02] transition-colors transition-[box-shadow] transition-transform duration-200",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
