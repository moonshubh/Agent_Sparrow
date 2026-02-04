import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/shared/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-organic text-sm font-medium ring-offset-background transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        // Dark Academia Theme - Warm scholarly aesthetic
        default:
          "bg-primary text-primary-foreground hover:bg-terracotta-400 shadow-academia-sm hover:shadow-academia-md",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90 shadow-academia-sm",
        outline:
          "border border-border bg-transparent text-foreground hover:bg-secondary hover:text-secondary-foreground",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80 border border-border",
        ghost:
          "text-foreground hover:bg-secondary hover:text-secondary-foreground",
        link: "text-terracotta-400 underline-offset-4 hover:underline hover:text-terracotta-300",
        gradient:
          "bg-[linear-gradient(to_right,hsl(var(--card))_0%,hsl(var(--card))_85%,hsl(var(--terracotta-500))_92%,hsl(var(--terracotta-600))_97%,hsl(var(--gold-600))_100%)] text-primary-foreground shadow-lg shadow-terracotta-500/20 hover:shadow-terracotta-500/35 hover:scale-[1.02]",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-organic-sm px-3",
        lg: "h-11 rounded-organic px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends
    React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
