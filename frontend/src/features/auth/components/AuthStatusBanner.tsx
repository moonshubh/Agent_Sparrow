'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Alert, AlertDescription, AlertTitle } from '@/shared/ui/alert';
import { Button } from '@/shared/ui/button';
import { Badge } from '@/shared/ui/badge';
import { Card } from '@/shared/ui/card';
import { 
  ShieldOff, 
  ShieldCheck, 
  AlertTriangle,
  Clock,
  RefreshCw,
  LogIn,
  X,
  CheckCircle,
  Info
} from 'lucide-react';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { cn } from '@/shared/lib/utils';
import { toast } from 'sonner';

interface AuthStatusBannerProps {
  className?: string;
  dismissible?: boolean;
  compact?: boolean;
  autoRefresh?: boolean;
  onAuthChange?: (isAuthenticated: boolean) => void;
}

export const AuthStatusBanner: React.FC<AuthStatusBannerProps> = ({
  className,
  dismissible = true,
  compact = false,
  autoRefresh = false,
  onAuthChange
}) => {
  const { user, session, isAuthenticated, isLoading, refreshToken } = useAuth();
  const [isDismissed, setIsDismissed] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [sessionExpiryWarning, setSessionExpiryWarning] = useState(false);

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      await refreshToken();
      toast.success('Session refreshed successfully');
      setSessionExpiryWarning(false);
    } catch (error) {
      toast.error('Failed to refresh session');
    } finally {
      setIsRefreshing(false);
    }
  }, [refreshToken]);

  useEffect(() => {
    if (onAuthChange) {
      onAuthChange(isAuthenticated);
    }
  }, [isAuthenticated, onAuthChange]);

  useEffect(() => {
    if (!session) return;

    // Check if session is about to expire (within 5 minutes)
    const checkExpiry = () => {
      const expiresAt = session.expires_at;
      if (!expiresAt) return;

      const expiryTime = new Date(expiresAt * 1000).getTime();
      const now = Date.now();
      const fiveMinutes = 5 * 60 * 1000;

      if (expiryTime - now <= fiveMinutes) {
        setSessionExpiryWarning(true);
        
        if (autoRefresh) {
          handleRefresh();
        }
      } else {
        setSessionExpiryWarning(false);
      }
    };

    checkExpiry();
    const interval = setInterval(checkExpiry, 60000); // Check every minute

    return () => clearInterval(interval);
  }, [session, autoRefresh, handleRefresh]);

  const handleDismiss = () => {
    setIsDismissed(true);
  };

  if (isLoading) {
    return null;
  }

  if (isDismissed) {
    return null;
  }

  // Don't show banner if authenticated and no warnings
  if (isAuthenticated && !sessionExpiryWarning) {
    return null;
  }

  const getBannerVariant = () => {
    if (!isAuthenticated) return 'destructive';
    if (sessionExpiryWarning) return 'warning';
    return 'default';
  };

  const getBannerIcon = () => {
    if (!isAuthenticated) return <ShieldOff className="h-4 w-4" />;
    if (sessionExpiryWarning) return <Clock className="h-4 w-4" />;
    return <ShieldCheck className="h-4 w-4" />;
  };

  const getBannerTitle = () => {
    if (!isAuthenticated) return 'Authentication Required';
    if (sessionExpiryWarning) return 'Session Expiring Soon';
    return 'Authenticated';
  };

  const getBannerDescription = () => {
    if (!isAuthenticated) {
      return 'Please sign in to access all features and save your chat history.';
    }
    if (sessionExpiryWarning) {
      return 'Your session will expire soon. Refresh to stay signed in.';
    }
    return `Signed in as ${user?.email}`;
  };

  if (compact) {
    return (
      <div className={cn(
        "flex items-center gap-2 px-3 py-1.5 rounded-lg glass-effect",
        "border transition-all duration-200",
        !isAuthenticated && "border-destructive/50 bg-destructive/10",
        sessionExpiryWarning && "border-yellow-500/50 bg-yellow-500/10",
        isAuthenticated && !sessionExpiryWarning && "border-green-500/50 bg-green-500/10",
        className
      )}>
        {getBannerIcon()}
        <span className="text-xs font-medium">
          {!isAuthenticated ? 'Not authenticated' : 
           sessionExpiryWarning ? 'Session expiring' : 
           'Authenticated'}
        </span>
        {sessionExpiryWarning && (
          <Button
            size="sm"
            variant="ghost"
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="h-5 px-1.5"
          >
            <RefreshCw className={cn(
              "h-3 w-3",
              isRefreshing && "animate-spin"
            )} />
          </Button>
        )}
        {!isAuthenticated && (
          <Button
            size="sm"
            variant="ghost"
            asChild
            className="h-5 px-1.5"
          >
            <a href="/login">
              <LogIn className="h-3 w-3" />
            </a>
          </Button>
        )}
      </div>
    );
  }

  return (
    <Alert 
      className={cn(
        "glass-effect backdrop-blur-xl",
        "animate-in slide-in-from-top duration-300",
        className
      )}
      variant={getBannerVariant() as any}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          {getBannerIcon()}
          <div className="space-y-1">
            <AlertTitle className="text-sm font-semibold">
              {getBannerTitle()}
            </AlertTitle>
            <AlertDescription className="text-xs">
              {getBannerDescription()}
            </AlertDescription>
            
            {!isAuthenticated && (
              <div className="flex items-center gap-2 mt-2">
                <Button
                  size="sm"
                  variant="default"
                  asChild
                >
                  <a href="/login" className="flex items-center gap-1">
                    <LogIn className="h-3 w-3" />
                    Sign In
                  </a>
                </Button>
                <span className="text-xs text-muted-foreground">
                  or continue with limited access
                </span>
              </div>
            )}
            
            {sessionExpiryWarning && (
              <div className="flex items-center gap-2 mt-2">
                <Button
                  size="sm"
                  variant="default"
                  onClick={handleRefresh}
                  disabled={isRefreshing}
                >
                  <RefreshCw className={cn(
                    "h-3 w-3 mr-1",
                    isRefreshing && "animate-spin"
                  )} />
                  Refresh Session
                </Button>
                {session?.expires_at && (
                  <span className="text-xs text-muted-foreground">
                    Expires {new Date(session.expires_at * 1000).toLocaleTimeString()}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
        
        {dismissible && (
          <Button
            size="sm"
            variant="ghost"
            onClick={handleDismiss}
            className="h-6 w-6 p-0"
          >
            <X className="h-3 w-3" />
          </Button>
        )}
      </div>
    </Alert>
  );
};

// Persistent auth status indicator
export const AuthStatusIndicator: React.FC<{ className?: string }> = ({ className }) => {
  const { isAuthenticated, user } = useAuth();

  return (
    <div className={cn(
      "flex items-center gap-2 px-2.5 py-1 rounded-full glass-effect",
      "border transition-all duration-200",
      isAuthenticated ? "border-green-500/30" : "border-yellow-500/30",
      className
    )}>
      {isAuthenticated ? (
        <>
          <CheckCircle className="h-3 w-3 text-green-500" />
          <span className="text-xs font-medium text-green-500">Authenticated</span>
        </>
      ) : (
        <>
          <AlertTriangle className="h-3 w-3 text-yellow-500" />
          <span className="text-xs font-medium text-yellow-500">Guest Mode</span>
        </>
      )}
    </div>
  );
};
