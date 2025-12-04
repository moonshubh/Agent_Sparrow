'use client';

import React, { useMemo, useState } from 'react';
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
import { AlertTriangle, ShieldAlert, ListChecks } from 'lucide-react';

export function InterruptHandler() {
  const { interrupt, resolveInterrupt } = useAgent();
  const [isResolving, setIsResolving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const promptText = interrupt?.prompt || 'This action requires your input';
  const options = interrupt?.options || [];
  const interruptType = (interrupt?.type || interrupt?.category || '').toLowerCase();
  const severity = (interrupt?.severity || interrupt?.level || '').toLowerCase();
  const isHighRisk = Boolean(interrupt?.highRisk || interrupt?.dangerous || interruptType.includes('high') || severity === 'high');
  const emphasisIcon = isHighRisk ? <ShieldAlert className="w-12 h-12 text-red-500" /> : <AlertTriangle className="w-12 h-12 text-amber-500" />;
  const contextEntries = useMemo(() => {
    const context = interrupt?.context || interrupt?.metadata;
    if (!context || typeof context !== 'object') {
      return [] as Array<[string, unknown]>;
    }
    return Object.entries(context).slice(0, 6);
  }, [interrupt]);
  const detailList = Array.isArray(interrupt?.details) ? interrupt?.details : [];

  if (!interrupt) return null;

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
      <DialogContent hideClose className="max-w-xl">
        <DialogHeader>
          <div className="flex items-start gap-4">
            {emphasisIcon}
            <div>
              <DialogTitle>{isHighRisk ? 'High-risk action requires approval' : 'Human decision required'}</DialogTitle>
              <DialogDescription className="mt-2">
                {promptText}
              </DialogDescription>
              {interrupt.reason && (
                <p className="text-sm text-muted-foreground mt-2">{interrupt.reason}</p>
              )}
            </div>
          </div>
        </DialogHeader>

        {/* Show error message if resolution failed */}
        {error && (
          <div className="mt-4 rounded-md bg-red-50 border border-red-200 p-3">
            <p className="text-sm text-red-800">{error}</p>
          </div>
        )}

        {(detailList.length > 0 || contextEntries.length > 0) && (
          <div className="mt-4 rounded-lg border bg-slate-50 p-3 space-y-3 text-sm text-slate-700">
            {detailList.length > 0 && (
              <div>
                <div className="flex items-center gap-2 font-semibold text-slate-900">
                  <ListChecks className="w-4 h-4" /> Summary
                </div>
                <ul className="list-disc pl-5 mt-2 space-y-1">
                  {detailList.map((detail, idx) => {
                    const detailKey = typeof detail === 'string' ? detail : JSON.stringify(detail);
                    return (
                      <li key={detailKey || `detail-${idx}`}>
                        {typeof detail === 'string' ? detail : JSON.stringify(detail)}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
            {contextEntries.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Impacted resources</p>
                <div className="mt-1 grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                  {contextEntries.map(([key, value]) => (
                    <div key={key} className="rounded border bg-white px-2 py-1">
                      <p className="font-medium text-slate-800">{key}</p>
                      <p className="text-slate-600 truncate" title={String(value)}>
                        {typeof value === 'string' ? value : JSON.stringify(value)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Show custom options if provided */}
        {options.length > 0 ? (
          <div className="mt-4 space-y-2">
            {options
              .filter(option => option && option.value !== undefined && option.label)
              .map((option, idx) => (
                <Button
                  key={`${option.label}-${option.value}-${idx}`}
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
                {isHighRisk ? 'Abort' : 'Reject'}
              </Button>
              <Button
                onClick={() => handleResolve('approve')}
                disabled={isResolving}
                className={cn({ 'bg-red-600 hover:bg-red-500': isHighRisk })}
              >
                {isResolving ? 'Processing...' : isHighRisk ? 'Proceed anyway' : 'Approve'}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
