// Browser client
import { supabase } from "./browser-client";
export { supabase };

// Server and edge helpers
export * from "./server-client";
export * from "./edge-client";

// Helper to get the current session
export const getSession = async () => {
  const {
    data: { session },
    error,
  } = await supabase.auth.getSession();
  if (error) {
    console.error("Error getting session:", error);
    return null;
  }
  return session;
};

// Helper to get the current user
export const getCurrentUser = async () => {
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser();
  if (error) {
    console.error("Error getting user:", error);
    return null;
  }
  return user;
};

// Type definitions for Supabase
export type SupabaseUser = Awaited<ReturnType<typeof getCurrentUser>>;
export type SupabaseSession = Awaited<ReturnType<typeof getSession>>;
