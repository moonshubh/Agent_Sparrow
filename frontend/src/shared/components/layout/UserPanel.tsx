"use client";

import React, { useState, useRef, useEffect } from "react";
import { User } from "@supabase/supabase-js";
import { UserAvatar } from "@/shared/ui/UserAvatar";
import { Card, CardContent } from "@/shared/ui/card";
import { Button } from "@/shared/ui/button";
import { LogOut, Settings, Key, User as UserIcon } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { useRouter } from "next/navigation";

interface UserPanelProps {
  user: User | null;
  isAuthenticated: boolean;
  isOnline?: boolean;
  onLogout: () => void;
}

export const UserPanel: React.FC<UserPanelProps> = ({
  user,
  isAuthenticated,
  isOnline = true,
  onLogout,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const router = useRouter();
  const toggleButtonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const handleNavigation = (path: string) => {
    router.push(path);
    setIsExpanded(false);
  };

  const handleToggle = () => {
    setIsExpanded(!isExpanded);
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handleToggle();
    } else if (event.key === "Escape" && isExpanded) {
      setIsExpanded(false);
      toggleButtonRef.current?.focus();
    }
  };

  // Focus management
  useEffect(() => {
    if (isExpanded && panelRef.current) {
      // Focus the first focusable element in the panel
      panelRef.current.focus();
    }
  }, [isExpanded]);

  // Close panel when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        panelRef.current &&
        !panelRef.current.contains(event.target as Node) &&
        toggleButtonRef.current &&
        !toggleButtonRef.current.contains(event.target as Node)
      ) {
        setIsExpanded(false);
      }
    };

    if (isExpanded) {
      document.addEventListener("mousedown", handleClickOutside);
      return () =>
        document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [isExpanded]);

  const getUserName = () => {
    if (!user) return "User";
    return (
      user.user_metadata?.full_name ||
      user.user_metadata?.name ||
      user.email?.split("@")[0] ||
      "User"
    );
  };

  if (!isAuthenticated || !user) {
    return null;
  }

  return (
    <div className="fixed bottom-6 right-6 z-50">
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            ref={panelRef}
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            transition={{ duration: 0.2 }}
            className="mb-3"
            tabIndex={-1}
            onKeyDown={handleKeyDown}
            role="menu"
            aria-label="User panel menu"
          >
            <Card className="w-64 border-border/50 bg-card/95 backdrop-blur-sm shadow-lg">
              <CardContent className="p-4">
                <div className="flex items-center gap-3 mb-4">
                  <UserAvatar
                    user={user}
                    size="lg"
                    showStatus
                    statusType={isOnline ? "online" : "offline"}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">
                      {getUserName()}
                    </p>
                    <p className="text-xs text-muted-foreground truncate">
                      {user.email}
                    </p>
                  </div>
                </div>

                <div className="space-y-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full justify-start gap-2"
                    onClick={() => handleNavigation("/profile")}
                    role="menuitem"
                  >
                    <UserIcon className="h-4 w-4" />
                    Profile
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full justify-start gap-2"
                    onClick={() => handleNavigation("/api-keys")}
                    role="menuitem"
                  >
                    <Key className="h-4 w-4" />
                    API Keys
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full justify-start gap-2"
                    onClick={() => handleNavigation("/settings")}
                    role="menuitem"
                  >
                    <Settings className="h-4 w-4" />
                    Settings
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full justify-start gap-2 text-destructive hover:text-destructive"
                    onClick={() => {
                      onLogout();
                      setIsExpanded(false);
                    }}
                    role="menuitem"
                  >
                    <LogOut className="h-4 w-4" />
                    Sign Out
                  </Button>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.div
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        className="relative"
      >
        <Button
          ref={toggleButtonRef}
          variant="outline"
          size="icon"
          className={cn(
            "h-12 w-12 rounded-full border-2 border-accent/30 bg-background/80 backdrop-blur-sm shadow-lg hover:border-accent/50 hover:bg-background/90",
            isExpanded && "border-accent/50 bg-background/90",
          )}
          onClick={handleToggle}
          onKeyDown={handleKeyDown}
          aria-label={`User menu for ${getUserName()}${isExpanded ? " (expanded)" : " (collapsed)"}`}
          aria-expanded={isExpanded}
          aria-haspopup="menu"
        >
          <UserAvatar user={user} size="md" />
        </Button>

        {/* Dynamic status indicator */}
        <div
          className={cn(
            "absolute -bottom-1 -right-1 h-4 w-4 rounded-full border-2 border-background",
            isOnline ? "bg-green-500" : "bg-gray-400",
          )}
          aria-label={`User status: ${isOnline ? "online" : "offline"}`}
        />
      </motion.div>
    </div>
  );
};
