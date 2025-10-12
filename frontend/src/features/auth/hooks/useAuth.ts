import { useAuth as useAuthContext } from '@/shared/contexts/AuthContext';
import { useEffect, useState } from 'react';
import { supabase } from '@/services/supabase/browser-client';
import { Session } from '@supabase/supabase-js';

// Extend useAuth to include session data
export const useAuth = () => {
  const authContext = useAuthContext();
  const [session, setSession] = useState<Session | null>(null);

  useEffect(() => {
    const getSession = async () => {
      const { data: { session } } = await supabase.auth.getSession();
      setSession(session);
    };

    getSession();

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
    });

    return () => subscription.unsubscribe();
  }, []);

  return {
    ...authContext,
    session
  };
};