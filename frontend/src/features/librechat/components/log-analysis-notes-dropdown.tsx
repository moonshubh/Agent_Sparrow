"use client";

import React, { memo } from "react";

interface LogAnalysisNote {
  readonly file_name?: string;
  readonly internal_notes?: string;
  readonly confidence?: number;
  readonly evidence?: readonly string[];
  readonly recommended_actions?: readonly string[];
  readonly open_questions?: readonly string[];
  readonly created_at?: string;
}

type LogAnalysisNotes = Readonly<Record<string, LogAnalysisNote>>;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

const isOptionalString = (value: unknown): value is string | undefined =>
  value === undefined || typeof value === "string";

const isOptionalNumber = (value: unknown): value is number | undefined =>
  value === undefined || (typeof value === "number" && Number.isFinite(value));

const isOptionalStringArray = (
  value: unknown,
): value is readonly string[] | undefined =>
  value === undefined ||
  (Array.isArray(value) && value.every((item) => typeof item === "string"));

const isLogAnalysisNote = (value: unknown): value is LogAnalysisNote => {
  if (!isRecord(value)) return false;

  return (
    isOptionalString(value.file_name) &&
    isOptionalString(value.internal_notes) &&
    isOptionalNumber(value.confidence) &&
    isOptionalString(value.created_at) &&
    isOptionalStringArray(value.evidence) &&
    isOptionalStringArray(value.recommended_actions) &&
    isOptionalStringArray(value.open_questions)
  );
};

const toNotes = (raw: unknown): LogAnalysisNotes | null => {
  if (!isRecord(raw)) return null;
  const entries = Object.entries(raw).filter(([, v]) => isLogAnalysisNote(v));
  if (!entries.length) return null;
  return Object.fromEntries(entries) as LogAnalysisNotes;
};

const formatConfidence = (confidence?: number): string | null => {
  if (confidence === undefined || !Number.isFinite(confidence)) return null;
  const pct = Math.round(confidence * 100);
  if (Number.isNaN(pct)) return null;
  return `~${pct}%`;
};

export const LogAnalysisNotesDropdown = memo(function LogAnalysisNotesDropdown({
  notes: rawNotes,
}: {
  notes: unknown;
}) {
  const notes = toNotes(rawNotes);
  if (!notes) return null;

  const rows = Object.entries(notes)
    .map(([id, note]) => ({ id, note }))
    .sort((a, b) => {
      const aTs =
        typeof a.note.created_at === "string"
          ? Date.parse(a.note.created_at)
          : 0;
      const bTs =
        typeof b.note.created_at === "string"
          ? Date.parse(b.note.created_at)
          : 0;
      return aTs - bTs;
    });

  const title =
    rows.length === 1
      ? "Technical details (1 log)"
      : `Technical details (${rows.length} logs)`;

  return (
    <details className="lc-log-notes" aria-label="Technical details">
      <summary className="lc-log-notes-summary">{title}</summary>
      <div className="lc-log-notes-body">
        {rows.map(({ id, note }, idx) => {
          const fileName =
            typeof note.file_name === "string" && note.file_name.trim()
              ? note.file_name.trim()
              : `Log ${idx + 1}`;
          const confidence = formatConfidence(note.confidence);

          return (
            <section key={id} className="lc-log-note">
              <header className="lc-log-note-header">
                <div className="lc-log-note-title">{fileName}</div>
                <div className="lc-log-note-meta">
                  {confidence ? <span>Confidence: {confidence}</span> : null}
                  {typeof note.created_at === "string" &&
                  note.created_at.trim() ? (
                    <span>{note.created_at}</span>
                  ) : null}
                </div>
              </header>

              {typeof note.internal_notes === "string" &&
              note.internal_notes.trim() ? (
                <div className="lc-log-note-section">
                  <div className="lc-log-note-section-title">
                    Internal diagnostic notes
                  </div>
                  <pre className="lc-log-note-pre">{note.internal_notes}</pre>
                </div>
              ) : null}

              {Array.isArray(note.evidence) && note.evidence.length ? (
                <div className="lc-log-note-section">
                  <div className="lc-log-note-section-title">Evidence</div>
                  <ul className="lc-log-note-list">
                    {note.evidence.map((item, i) => (
                      <li key={`${id}-evidence-${i}`}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {Array.isArray(note.recommended_actions) &&
              note.recommended_actions.length ? (
                <div className="lc-log-note-section">
                  <div className="lc-log-note-section-title">
                    Recommended actions
                  </div>
                  <ul className="lc-log-note-list">
                    {note.recommended_actions.map((item, i) => (
                      <li key={`${id}-actions-${i}`}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {Array.isArray(note.open_questions) &&
              note.open_questions.length ? (
                <div className="lc-log-note-section">
                  <div className="lc-log-note-section-title">
                    Open questions
                  </div>
                  <ul className="lc-log-note-list">
                    {note.open_questions.map((item, i) => (
                      <li key={`${id}-questions-${i}`}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </section>
          );
        })}
      </div>
    </details>
  );
});
