'use client';

import React, { useState } from 'react';
import { useAgent } from './hooks/useAgent';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from '@/shared/ui/dialog';
import { Button } from '@/shared/ui/button';
import { cn } from '@/shared/lib/utils';

export function InterruptHandler() {
  const { interrupt, resolveInterrupt } = useAgent();
  const [isResolving, setIsResolving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!interrupt) return null;

  const promptText = interrupt.prompt || 'This action requires your input';
  const options = interrupt.options || [];

  // Async handler for interrupt resolution with error handling
  const handleResolve = async (value: string) => {
    if (isResolving) return;

    setIsResolving(true);
    setError(null);

    try {
      await resolveInterrupt(value);
      // Dialog will close automatically on successful resolution
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to resolve interrupt. Please try again.'
      );
    } finally {
      setIsResolving(false);
    }
  };

  return (
    <Dialog open onOpenChange={() => {}}>
      <DialogContent hideClose className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Human decision required</DialogTitle>
          <DialogDescription className="mt-2">
            {promptText}
          </DialogDescription>
        </DialogHeader>

        {/* Show error message if resolution failed */}
        {error && (
          <div className="mt-4 rounded-md bg-red-50 border border-red-200 p-3">
            <p className="text-sm text-red-800">{error}</p>
          </div>
        )}

        {/* Show custom options if provided */}
        {options.length > 0 ? (
          <div className="mt-4 space-y-2">
            {options
              .filter(option => option && option.value !== undefined && option.label)
              .map((option, idx) => (
                <Button
                  key={option.id || idx}
                  onClick={() => handleResolve(option.value)}
                  variant="outline"
                  className="w-full justify-start"
                  disabled={isResolving}
                >
                  {option.label}
                </Button>
              ))}
          </div>
        ) : (
          <>
            {/* Show debug payload in development */}
            {process.env.NODE_ENV === 'development' && (
              <div className="mt-4">
                <div className="text-xs text-slate-500 mb-2">Debug Payload:</div>
                <pre className="max-h-64 overflow-auto rounded-md border bg-slate-50 p-3 text-xs">
                  {JSON.stringify(interrupt, null, 2)}
                </pre>
              </div>
            )}

            {/* Default approve/reject buttons */}
            <DialogFooter className="mt-6">
              <Button
                onClick={() => handleResolve('reject')}
                variant="secondary"
                disabled={isResolving}
              >
                Reject
              </Button>
              <Button
                onClick={() => handleResolve('approve')}
                disabled={isResolving}
              >
                {isResolving ? 'Processing...' : 'Approve'}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}