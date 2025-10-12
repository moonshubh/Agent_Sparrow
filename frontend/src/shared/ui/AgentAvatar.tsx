import { Avatar, AvatarImage, AvatarFallback } from "@/shared/ui/avatar"
import { cn } from "@/shared/lib/utils"

interface AgentAvatarProps {
  size?: number
  className?: string
}

export const AgentAvatar = ({ size, className }: AgentAvatarProps) => (
  <Avatar
    className={cn(
      "ring-1 ring-accent/30 bg-accent/10",
      className
    )}
    style={size ? { width: `${size}px`, height: `${size}px` } : undefined}
  >
    <AvatarImage src="/agent-sparrow-logo.png" alt="Agent Sparrow" />
    <AvatarFallback className="bg-accent/10 text-accent font-semibold">AS</AvatarFallback>
  </Avatar>
)