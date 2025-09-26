"""
Zendesk PDF Print Normalizer

Heuristic normalizer for Zendesk "print" PDFs converted to extracted text.
Goals:
- Derive ticket_id from filename or content
- Derive subject if present (fallback to provided title)
- Produce a simplified Q/A paragraph structure:
  Q: <customer content>
  A: <agent content>
  ...
- Omit names and emails; perform light cleanup only
"""

from __future__ import annotations

import re
from typing import Tuple, Dict, Any


TICKET_RE_FILENAME = re.compile(r"tickets_(\d+)_print\.pdf$", re.IGNORECASE)
TICKET_RE_TEXT = re.compile(r"Ticket\s*#?(\d{3,})", re.IGNORECASE)
SUBJECT_RE_TEXT = re.compile(r"^\s*(Subject|Re:)\s*[:\-]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def _guess_ticket_id(original_filename: str | None, text: str) -> str | None:
    if original_filename:
        m = TICKET_RE_FILENAME.search(original_filename)
        if m:
            return m.group(1)
    m2 = TICKET_RE_TEXT.search(text or "")
    if m2:
        return m2.group(1)
    return None


def _guess_subject(text: str, fallback_title: str | None) -> str:
    if text:
        m = SUBJECT_RE_TEXT.search(text)
        if m:
            # Group 2 contains subject text
            subj = m.group(2).strip()
            # Trim overly long subjects
            return subj[:200]
    return (fallback_title or "Untitled Conversation")[:200]


def _split_paragraphs(text: str) -> list[str]:
    # Normalize newlines and split on blank lines
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = [p.strip() for p in re.split(r"\n\s*\n+", t) if p.strip()]
    return parts


def _redact_identities(s: str) -> str:
    # Remove emails and names in common headers
    s = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[redacted]", s)
    s = re.sub(r"^(From|To|Cc|Bcc):.*$", "", s, flags=re.IGNORECASE | re.MULTILINE)
    return s.strip()


def _is_agent_paragraph(p: str) -> bool:
    # Heuristic: paragraphs containing typical support signatures/phrases
    lower = p.lower()
    agent_markers = [
        "best regards", "kind regards", "support team", "mailbird", "thanks for reaching out",
        "let me know", "we apologize", "please try", "we recommend", "our team"
    ]
    return any(m in lower for m in agent_markers)


def _build_qa_flow(paragraphs: list[str]) -> str:
    if not paragraphs:
        return ""
    out: list[str] = []
    # Redact identities and remove obvious headers in each paragraph
    cleaned = [_redact_identities(p) for p in paragraphs]

    # Attempt to pair Q/A by alternating; bias paragraphs that look like agent responses as A
    i = 0
    expecting_q = True
    while i < len(cleaned):
        p = cleaned[i]
        if expecting_q:
            out.append("Q: " + p)
            expecting_q = False
        else:
            # If this paragraph doesn't look like an agent response, but the next does, use next as A
            a_para = p
            if not _is_agent_paragraph(p) and i + 1 < len(cleaned) and _is_agent_paragraph(cleaned[i + 1]):
                a_para = cleaned[i + 1]
                i += 1
            out.append("A: " + a_para)
            expecting_q = True
        i += 1

    # Ensure the flow ends at an A or Q; it's okay if odd count, last Q stays without A
    return "\n\n".join(out).strip()


def normalize_zendesk_print_text(
    text: str,
    original_filename: str | None = None,
    fallback_title: str | None = None
) -> Tuple[str, Dict[str, Any]]:
    """
    Produce normalized Q/A text and metadata from Zendesk print text.
    Returns: (normalized_text, metadata)
    metadata includes: ticket_id, subject
    """
    ticket_id = _guess_ticket_id(original_filename, text)
    subject = _guess_subject(text, fallback_title)

    paragraphs = _split_paragraphs(text)
    normalized = _build_qa_flow(paragraphs)

    meta = {
        "ticket_id": ticket_id,
        "subject": subject,
    }
    return normalized or text, meta

