"use client"

import { useCallback, useState } from 'react'
import Image from 'next/image'
import { useRouter } from 'next/navigation'
import { BarChart3, PanelsTopLeft, ChevronDown } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/shared/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/shared/ui/tooltip'
import { GlobalKnowledgeObservabilityDialog } from '@/features/global-knowledge/components/GlobalKnowledgeObservabilityDialog'

interface FeedMeButtonProps {
  onClick?: () => void
}

export function FeedMeButton({ onClick }: FeedMeButtonProps) {
  const router = useRouter()
  const [isHovered, setIsHovered] = useState(false)
  const [observabilityOpen, setObservabilityOpen] = useState(false)

  const handleNavigate = useCallback(() => {
    onClick?.()
    router.push('/feedme-revamped')
  }, [onClick, router])

  const handleObservability = useCallback(() => {
    onClick?.()
    setObservabilityOpen(true)
  }, [onClick])

  return (
    <>
      <TooltipProvider>
        <DropdownMenu>
          <Tooltip>
            <TooltipTrigger asChild>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 px-2 gap-2 hover:bg-mb-blue-300/10 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
                  onMouseEnter={() => setIsHovered(true)}
                  onMouseLeave={() => setIsHovered(false)}
                  aria-label="FeedMe quick actions"
                >
                  <Image
                    src="/feedme-icon.png"
                    alt="FeedMe"
                    width={20}
                    height={20}
                    className={`transition-opacity ${isHovered ? 'opacity-100' : 'opacity-70'}`}
                  />
                  <span className="text-sm">FeedMe</span>
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                </Button>
              </DropdownMenuTrigger>
            </TooltipTrigger>
            <TooltipContent>FeedMe quick actions</TooltipContent>
          </Tooltip>
          <DropdownMenuContent align="end" className="w-64">
            <DropdownMenuItem onSelect={handleNavigate}>
              <PanelsTopLeft className="mr-2 h-4 w-4 text-muted-foreground" />
              <div className="flex flex-col">
                <span className="text-sm font-medium leading-none">Open Feed Me</span>
                <span className="text-xs text-muted-foreground">
                  Go to the full Feed Me workspace
                </span>
              </div>
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={handleObservability}>
              <BarChart3 className="mr-2 h-4 w-4 text-muted-foreground" />
              <div className="flex flex-col">
                <span className="text-sm font-medium leading-none">
                  Global Knowledge Observability
                </span>
                <span className="text-xs text-muted-foreground">
                  View live knowledge ingestion health
                </span>
              </div>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </TooltipProvider>

      <GlobalKnowledgeObservabilityDialog
        open={observabilityOpen}
        onOpenChange={setObservabilityOpen}
      />
    </>
  )
}
