"use client";

import React, { useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  GitMerge,
  X,
  CheckCircle,
  XCircle,
  Clock,
  ArrowRight,
} from "lucide-react";
import {
  useDuplicateCandidates,
  useMergeMemories,
  useDismissDuplicate,
} from "../hooks";
import { ConfidenceBadge } from "./ConfidenceBadge";
import type { DuplicateCandidate } from "../types";

export default function DuplicateReview() {
  const {
    data: candidates,
    isLoading,
    refetch,
  } = useDuplicateCandidates("pending");
  const mergeMemories = useMergeMemories();
  const dismissDuplicate = useDismissDuplicate();

  const handleMerge = useCallback(
    async (candidate: DuplicateCandidate, keepMemoryId: string) => {
      try {
        await mergeMemories.mutateAsync({
          duplicate_candidate_id: candidate.id,
          keep_memory_id: keepMemoryId,
        });
        refetch();
      } catch (err: unknown) {
        console.error("Failed to merge:", err);
      }
    },
    [mergeMemories, refetch],
  );

  const handleDismiss = useCallback(
    async (candidateId: string) => {
      try {
        await dismissDuplicate.mutateAsync({ candidateId });
        refetch();
      } catch (err: unknown) {
        console.error("Failed to dismiss:", err);
      }
    },
    [dismissDuplicate, refetch],
  );

  // Defer functionality - mark for later review (uses dismiss with 'deferred' notes)
  const handleDefer = useCallback(
    async (candidateId: string) => {
      try {
        await dismissDuplicate.mutateAsync({
          candidateId,
          notes: "Deferred for later review",
        });
        refetch();
      } catch (err: unknown) {
        console.error("Failed to defer:", err);
      }
    },
    [dismissDuplicate, refetch],
  );

  if (isLoading) {
    return (
      <div className="memory-loading">
        <div className="memory-loading-spinner" />
        <p>Loading duplicate candidates...</p>
      </div>
    );
  }

  if (!candidates || candidates.length === 0) {
    return (
      <div className="memory-empty memory-empty-success">
        <CheckCircle size={48} className="memory-empty-icon" />
        <h3>All Clear!</h3>
        <p>No duplicate candidates to review</p>
      </div>
    );
  }

  return (
    <div className="duplicate-review-container">
      <div className="duplicate-review-header">
        <GitMerge size={20} />
        <h2>Duplicate Review Queue</h2>
        <span className="duplicate-review-count">
          {candidates.length} pending
        </span>
      </div>

      <div className="duplicate-review-list">
        <AnimatePresence>
          {candidates.map((candidate, index) => (
            <motion.div
              key={candidate.id}
              className="duplicate-card"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, x: -100 }}
              transition={{ delay: index * 0.05 }}
            >
              <div className="duplicate-card-header">
                <div className="duplicate-similarity">
                  <span className="duplicate-similarity-value">
                    {(candidate.similarity_score * 100).toFixed(1)}%
                  </span>
                  <span className="duplicate-similarity-label">similarity</span>
                </div>
                <div className="duplicate-card-actions">
                  <button
                    className="duplicate-action-btn duplicate-action-dismiss"
                    onClick={() => handleDismiss(candidate.id)}
                    disabled={dismissDuplicate.isPending}
                    title="Not a duplicate"
                  >
                    <XCircle size={16} />
                    <span>Not Duplicate</span>
                  </button>
                  <button
                    className="duplicate-action-btn duplicate-action-defer"
                    onClick={() => handleDefer(candidate.id)}
                    disabled={dismissDuplicate.isPending}
                    title="Review later"
                  >
                    <Clock size={16} />
                    <span>Defer</span>
                  </button>
                </div>
              </div>

              <div className="duplicate-memories-grid">
                {/* Memory 1 */}
                <div className="duplicate-memory-card">
                  <div className="duplicate-memory-header">
                    <ConfidenceBadge
                      score={candidate.memory1?.confidence_score || 0}
                    />
                    <span className="duplicate-memory-retrievals">
                      {candidate.memory1?.retrieval_count || 0} retrievals
                    </span>
                  </div>
                  <p className="duplicate-memory-content">
                    {candidate.memory1?.content || "Memory not found"}
                  </p>
                  <button
                    className="duplicate-keep-btn"
                    onClick={() =>
                      handleMerge(candidate, candidate.memory_id_1)
                    }
                    disabled={mergeMemories.isPending || !candidate.memory1}
                    title={
                      !candidate.memory1
                        ? "Memory not available"
                        : "Keep this memory"
                    }
                  >
                    <ArrowRight size={14} />
                    <span>Keep this one</span>
                  </button>
                </div>

                <div className="duplicate-vs">
                  <span>VS</span>
                </div>

                {/* Memory 2 */}
                <div className="duplicate-memory-card">
                  <div className="duplicate-memory-header">
                    <ConfidenceBadge
                      score={candidate.memory2?.confidence_score || 0}
                    />
                    <span className="duplicate-memory-retrievals">
                      {candidate.memory2?.retrieval_count || 0} retrievals
                    </span>
                  </div>
                  <p className="duplicate-memory-content">
                    {candidate.memory2?.content || "Memory not found"}
                  </p>
                  <button
                    className="duplicate-keep-btn"
                    onClick={() =>
                      handleMerge(candidate, candidate.memory_id_2)
                    }
                    disabled={mergeMemories.isPending || !candidate.memory2}
                    title={
                      !candidate.memory2
                        ? "Memory not available"
                        : "Keep this memory"
                    }
                  >
                    <ArrowRight size={14} />
                    <span>Keep this one</span>
                  </button>
                </div>
              </div>

              <div className="duplicate-detected-info">
                <Clock size={12} />
                <span>
                  Detected{" "}
                  {new Date(candidate.detected_at).toLocaleDateString()} via{" "}
                  {candidate.detection_method}
                </span>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
