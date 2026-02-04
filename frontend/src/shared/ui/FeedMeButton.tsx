"use client";

import { useCallback, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { PanelsTopLeft } from "lucide-react";

import { Button } from "@/shared/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/shared/ui/tooltip";

interface FeedMeButtonProps {
  onClick?: () => void;
}

export function FeedMeButton({ onClick }: FeedMeButtonProps) {
  const router = useRouter();
  const [isHovered, setIsHovered] = useState(false);

  const handleNavigate = useCallback(() => {
    onClick?.();
    router.push("/feedme");
  }, [onClick, router]);

  return (
    <>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 px-2 gap-2 hover:bg-mb-blue-300/10 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
              onMouseEnter={() => setIsHovered(true)}
              onMouseLeave={() => setIsHovered(false)}
              aria-label="Open FeedMe"
              onClick={handleNavigate}
            >
              <PanelsTopLeft className="mr-1 h-4 w-4 text-muted-foreground" />
              <Image
                src="/feedme-icon.png"
                alt="FeedMe"
                width={20}
                height={20}
                className={`transition-opacity ${isHovered ? "opacity-100" : "opacity-70"}`}
              />
              <span className="text-sm">FeedMe</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>Open Feed Me</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </>
  );
}
