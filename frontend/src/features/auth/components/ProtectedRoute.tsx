"use client";

import React, { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "@/features/auth/hooks/useAuth";
import { Loader2 } from "lucide-react";

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: string[];
  fallback?: React.ReactNode;
  redirectTo?: string;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  requiredRole,
  fallback,
  redirectTo = "/login",
}) => {
  const { user, isLoading, isAuthenticated } = useAuth();
  const pathname = usePathname() ?? "/";

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!isLoading && !isAuthenticated) {
      const returnUrl = encodeURIComponent(pathname);
      window.location.href = `${redirectTo}?returnUrl=${returnUrl}`;
    }
  }, [isLoading, isAuthenticated, pathname, redirectTo]);

  // Show loading state
  if (isLoading) {
    return (
      <div
        className="flex h-screen items-center justify-center"
        role="status"
        aria-live="polite"
        aria-label="Loading authentication status"
      >
        <div className="flex flex-col items-center gap-2">
          <Loader2 className="h-8 w-8 animate-spin text-accent" />
          <p className="text-sm text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  // Not authenticated
  if (!isAuthenticated) {
    return fallback ? (
      <>{fallback}</>
    ) : (
      <main
        className="flex h-screen items-center justify-center"
        role="alert"
        aria-live="assertive"
      >
        <section className="text-center" tabIndex={-1}>
          <h1 className="text-2xl font-semibold">Authentication Required</h1>
          <p className="mt-2 text-muted-foreground">
            Please log in to access this page.
          </p>
        </section>
      </main>
    );
  }

  // Check role-based access if required
  if (requiredRole && requiredRole.length > 0) {
    const userRole = user?.user_metadata?.role || user?.app_metadata?.role;
    const hasRequiredRole = requiredRole.some((role) => role === userRole);

    if (!hasRequiredRole) {
      return (
        <main
          className="flex h-screen items-center justify-center"
          role="alert"
          aria-live="assertive"
        >
          <section className="text-center" tabIndex={-1}>
            <h1 className="text-2xl font-semibold">Access Denied</h1>
            <p className="mt-2 text-muted-foreground">
              You don't have permission to access this page.
            </p>
          </section>
        </main>
      );
    }
  }

  // Authenticated and authorized
  return <>{children}</>;
};

// Higher-order component for protecting pages
export function withAuth<P extends object>(
  Component: React.ComponentType<P>,
  options?: Omit<ProtectedRouteProps, "children">,
) {
  const ProtectedComponent = function (props: P) {
    return (
      <ProtectedRoute {...options}>
        <Component {...props} />
      </ProtectedRoute>
    );
  };

  // Add displayName for better debugging experience
  ProtectedComponent.displayName = `withAuth(${Component.displayName || Component.name || "Component"})`;

  return ProtectedComponent;
}
