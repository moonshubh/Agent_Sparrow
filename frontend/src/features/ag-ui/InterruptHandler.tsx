'use client';

import React from 'react';
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

  if (!interrupt) return null;

  const promptText = interrupt.prompt || 'This action requires your input';
  const options = interrupt.options || [];

  return (
    <Dialog open onOpenChange={() => {}}>
      <DialogContent hideClose className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Human decision required</DialogTitle>
          <DialogDescription className="mt-2">
            {promptText}
          </DialogDescription>
        </DialogHeader>

        {/* Show custom options if provided */}
        {options.length > 0 ? (
          <div className="mt-4 space-y-2">
            {options.map((option, idx) => (
              <Button
                key={idx}
                onClick={() => resolveInterrupt(option.value)}
                variant="outline"
                className="w-full justify-start"
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
                onClick={() => resolveInterrupt('reject')}
                variant="secondary"
              >
                Reject
              </Button>
              <Button
                onClick={() => resolveInterrupt('approve')}
              >
                Approve
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}