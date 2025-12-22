"""CLI utilities for reviewing playbook learned entries in Markdown.

Workflow:
1) Export pending entries to Markdown files for human review.
2) Edit Markdown in an editor (set status to approved/rejected, tweak content).
3) Import reviewed entries back into Supabase.
4) Recompile playbooks to workspace storage.

Usage:
  python -m app.agents.unified.playbooks.review_cli export --out playbooks_review/2025-12-22
  python -m app.agents.unified.playbooks.review_cli import --in playbooks_review/2025-12-22 \\
    --reviewed-by "shubh"
  python -m app.agents.unified.playbooks.review_cli compile --categories sending,features,licensing
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml
from loguru import logger

from app.agents.harness.store import SparrowWorkspaceStore
from app.agents.unified.playbooks.extractor import (
    LEARNED_ENTRIES_TABLE,
    STATUS_APPROVED,
    STATUS_PENDING_REVIEW,
    STATUS_REJECTED,
    PlaybookExtractor,
)
from app.db.supabase.client import get_supabase_client


DEFAULT_CATEGORIES: Tuple[str, ...] = (
    "account_setup",
    "sync_auth",
    "licensing",
    "sending",
    "performance",
    "features",
)

PLACEHOLDER = "_Missing_"

SECTION_TITLES = {
    "problem summary": "problem_summary",
    "diagnostic questions": "diagnostic_questions",
    "resolution steps": "resolution_steps",
    "final solution": "final_solution",
    "why it worked": "why_it_worked",
    "key learnings": "key_learnings",
}


def _split_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            raw = "\n".join(lines[1:idx])
            body = "\n".join(lines[idx + 1 :])
            meta = yaml.safe_load(raw) if raw.strip() else {}
            return (meta or {}), body

    return {}, text


def _parse_sections(body: str) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for line in body.splitlines():
        header_match = re.match(r"^##\s+(.*)$", line.strip())
        if header_match:
            title = header_match.group(1).strip().lower()
            current = SECTION_TITLES.get(title)
            if current:
                sections[current] = []
            else:
                current = None
            continue

        if current:
            sections[current].append(line)

    return sections


def _clean_text(lines: Iterable[str]) -> str:
    text = "\n".join(lines).strip()
    if not text or text == PLACEHOLDER:
        return ""
    return text


def _extract_bullets(lines: Iterable[str]) -> List[str]:
    items: List[str] = []
    for line in lines:
        match = re.match(r"^\s*[-*]\s+(.*)$", line)
        if match:
            item = match.group(1).strip()
            if item and item != PLACEHOLDER:
                items.append(item)
    if items:
        return items

    fallback = _clean_text(lines)
    return [fallback] if fallback else []


def _split_action_rationale(text: str) -> Tuple[str, Optional[str]]:
    match = re.match(r"^(.*)\(rationale:\s*(.*)\)\s*$", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    for delimiter in (" - ", " | ", " -- "):
        if delimiter in text:
            action, rationale = text.split(delimiter, 1)
            return action.strip(), rationale.strip() or None

    return text.strip(), None


def _extract_steps(lines: Iterable[str]) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []
    for line in lines:
        match = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        if not match:
            continue
        text = match.group(1).strip()
        if not text or text == PLACEHOLDER:
            continue
        action, rationale = _split_action_rationale(text)
        step: Dict[str, Any] = {"step": len(steps) + 1, "action": action}
        if rationale:
            step["rationale"] = rationale
        steps.append(step)
    return steps


def _render_section(title: str, content: str) -> str:
    body = content.strip() if content.strip() else PLACEHOLDER
    return f"## {title}\n\n{body}\n"


def _render_list_section(title: str, items: List[str], numbered: bool = False) -> str:
    if not items:
        items = [PLACEHOLDER]
    lines: List[str] = []
    for idx, item in enumerate(items, 1):
        if numbered:
            lines.append(f"{idx}. {item}")
        else:
            lines.append(f"- {item}")
    return f"## {title}\n\n" + "\n".join(lines) + "\n"


def _render_steps(steps: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for step in steps:
        if isinstance(step, dict):
            action = str(step.get("action") or step.get("step") or "").strip()
            rationale = str(step.get("rationale") or "").strip()
            if rationale:
                lines.append(f"{action} (Rationale: {rationale})")
            else:
                lines.append(f"{action}")
        else:
            lines.append(str(step))
    return lines


def _render_entry_markdown(row: Dict[str, Any]) -> str:
    meta = {
        "id": row.get("id"),
        "conversation_id": row.get("conversation_id"),
        "category": row.get("category"),
        "status": row.get("status", STATUS_PENDING_REVIEW),
        "quality_score": row.get("quality_score"),
        "reviewed_by": row.get("reviewed_by"),
        "reviewed_at": row.get("reviewed_at"),
        "source_message_count": row.get("source_message_count"),
        "source_word_count": row.get("source_word_count"),
        "created_at": row.get("created_at"),
    }

    frontmatter = yaml.safe_dump(meta, sort_keys=False).strip()
    body = [
        "# Playbook Review Entry",
        "",
        "Edit the sections below. Set frontmatter status to approved/rejected when ready.",
        "",
        _render_section("Problem Summary", str(row.get("problem_summary") or "")),
        _render_list_section(
            "Diagnostic Questions",
            list(row.get("diagnostic_questions") or []),
            numbered=False,
        ),
        _render_list_section(
            "Resolution Steps",
            _render_steps(list(row.get("resolution_steps") or [])),
            numbered=True,
        ),
        _render_section("Final Solution", str(row.get("final_solution") or "")),
        _render_section("Why It Worked", str(row.get("why_it_worked") or "")),
        _render_section("Key Learnings", str(row.get("key_learnings") or "")),
    ]

    return f"---\n{frontmatter}\n---\n\n" + "\n".join(body).strip() + "\n"


def _parse_categories(values: Optional[List[str]]) -> List[str]:
    if not values:
        return []
    categories: List[str] = []
    for value in values:
        categories.extend([item.strip() for item in value.split(",") if item.strip()])
    return categories


def _fetch_entries(
    status: str,
    categories: List[str],
    created_after: Optional[str],
    created_before: Optional[str],
    limit: Optional[int],
    page_size: int = 500,
) -> List[Dict[str, Any]]:
    client = get_supabase_client()
    all_rows: List[Dict[str, Any]] = []
    offset = 0

    while True:
        query = (
            client.table(LEARNED_ENTRIES_TABLE)
            .select("*")
            .eq("status", status)
            .order("created_at", desc=False)
        )
        if categories:
            query = query.in_("category", categories)
        if created_after:
            query = query.gte("created_at", created_after)
        if created_before:
            query = query.lte("created_at", created_before)

        if limit:
            remaining = max(0, limit - len(all_rows))
            if remaining == 0:
                break
            page_size = min(page_size, remaining)

        response = query.range(offset, offset + page_size - 1).execute()
        rows = response.data or []
        all_rows.extend(rows)

        if limit and len(all_rows) >= limit:
            return all_rows[:limit]
        if len(rows) < page_size:
            break
        offset += page_size

    return all_rows


def export_entries(args: argparse.Namespace) -> None:
    categories = _parse_categories(args.categories)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = _fetch_entries(
        status=args.status,
        categories=categories,
        created_after=args.created_after,
        created_before=args.created_before,
        limit=args.limit,
    )
    if not rows:
        logger.info("No entries found for export.")
        return

    written = 0
    for row in rows:
        category = str(row.get("category") or "unknown")
        entry_id = str(row.get("id") or "unknown")
        conversation_id = str(row.get("conversation_id") or "conversation")
        safe_conv = re.sub(r"[^a-zA-Z0-9_-]+", "-", conversation_id).strip("-")
        filename = f"{category}-{safe_conv}-{entry_id[:8]}.md"
        dest = out_dir / category
        dest.mkdir(parents=True, exist_ok=True)
        (dest / filename).write_text(_render_entry_markdown(row), encoding="utf-8")
        written += 1

    logger.info("Exported %s entries to %s", written, out_dir)


def _parse_entry_from_markdown(
    path: Path,
    prefer_body: bool,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    meta, body = _split_frontmatter(text)
    sections = _parse_sections(body)

    parsed: Dict[str, Any] = {}
    if prefer_body:
        problem_summary = _clean_text(sections.get("problem_summary", []))
        final_solution = _clean_text(sections.get("final_solution", []))
        why_it_worked = _clean_text(sections.get("why_it_worked", []))
        key_learnings = _clean_text(sections.get("key_learnings", []))
        diagnostic_questions = _extract_bullets(sections.get("diagnostic_questions", []))
        resolution_steps = _extract_steps(sections.get("resolution_steps", []))

        if problem_summary:
            parsed["problem_summary"] = problem_summary
        if final_solution:
            parsed["final_solution"] = final_solution
        if why_it_worked:
            parsed["why_it_worked"] = why_it_worked
        if key_learnings:
            parsed["key_learnings"] = key_learnings
        if diagnostic_questions:
            parsed["diagnostic_questions"] = diagnostic_questions
        if resolution_steps:
            parsed["resolution_steps"] = resolution_steps
    else:
        for key in (
            "problem_summary",
            "final_solution",
            "why_it_worked",
            "key_learnings",
        ):
            value = meta.get(key)
            if isinstance(value, str) and value.strip():
                parsed[key] = value.strip()

        diag = meta.get("diagnostic_questions")
        if isinstance(diag, list) and diag:
            parsed["diagnostic_questions"] = diag

        steps = meta.get("resolution_steps")
        if isinstance(steps, list) and steps:
            parsed["resolution_steps"] = steps

    return meta, parsed


def import_entries(args: argparse.Namespace) -> None:
    in_dir = Path(args.input)
    if not in_dir.exists():
        raise SystemExit(f"Input folder not found: {in_dir}")

    client = get_supabase_client()
    reviewed_by_default = args.reviewed_by
    updated = 0
    skipped = 0

    for path in sorted(in_dir.rglob("*.md")):
        meta, parsed = _parse_entry_from_markdown(path, prefer_body=not args.prefer_frontmatter)
        entry_id = meta.get("id")
        if not entry_id:
            logger.warning("Missing entry id in %s", path)
            skipped += 1
            continue

        status = meta.get("status", STATUS_PENDING_REVIEW)
        status = str(status).strip()
        payload: Dict[str, Any] = {}

        payload.update(parsed)

        if status in (STATUS_APPROVED, STATUS_REJECTED, STATUS_PENDING_REVIEW):
            payload["status"] = status

        reviewed_by = meta.get("reviewed_by") or reviewed_by_default
        quality_score = meta.get("quality_score")

        if status in (STATUS_APPROVED, STATUS_REJECTED):
            if not reviewed_by:
                logger.warning("Missing reviewed_by for %s (status=%s)", path, status)
                skipped += 1
                continue
            payload["reviewed_by"] = reviewed_by
            payload["reviewed_at"] = meta.get("reviewed_at") or datetime.now(
                timezone.utc
            ).isoformat()
            if quality_score is not None:
                payload["quality_score"] = float(quality_score)

        if not payload:
            skipped += 1
            continue

        if args.dry_run:
            logger.info("Dry-run update %s: %s", entry_id, payload.keys())
            updated += 1
            continue

        try:
            client.table(LEARNED_ENTRIES_TABLE).update(payload).eq("id", entry_id).execute()
            updated += 1
        except Exception as exc:
            logger.warning("Failed to update %s: %s", entry_id, exc)
            skipped += 1

    logger.info("Import complete. Updated=%s Skipped=%s", updated, skipped)


async def compile_playbooks(args: argparse.Namespace) -> None:
    categories = _parse_categories(args.categories)
    if not categories:
        categories = list(DEFAULT_CATEGORIES)

    extractor = PlaybookExtractor()
    workspace = SparrowWorkspaceStore(session_id="playbook-compiler")

    for category in categories:
        playbook = await extractor.build_playbook_with_learned(category)
        content = playbook.to_prompt_context(include_pending=args.include_pending).strip()
        if not content:
            logger.info("No content for category=%s", category)
            continue

        compiled = (
            "<!-- auto-generated by playbook review CLI; source: "
            "/playbooks/source + playbook_learned_entries -->\n\n"
            f"{content}\n"
        )
        path = f"/playbooks/{category}.md"
        await workspace.write_file(path, compiled)
        logger.info("Compiled %s to %s", category, path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Playbook review Markdown utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Export entries to Markdown.")
    export_parser.add_argument("--out", required=True, help="Output folder for Markdown files.")
    export_parser.add_argument(
        "--categories",
        action="append",
        help="Comma-separated categories to export (repeatable).",
    )
    export_parser.add_argument(
        "--status",
        default=STATUS_PENDING_REVIEW,
        help="Status to export (default: pending_review).",
    )
    export_parser.add_argument(
        "--created-after",
        help="ISO timestamp (inclusive) for created_at filter.",
    )
    export_parser.add_argument(
        "--created-before",
        help="ISO timestamp (inclusive) for created_at filter.",
    )
    export_parser.add_argument("--limit", type=int, help="Limit number of entries.")
    export_parser.set_defaults(func=export_entries)

    import_parser = subparsers.add_parser(
        "import",
        help="Import reviewed Markdown back to Supabase.",
    )
    import_parser.add_argument(
        "--in",
        dest="input",
        required=True,
        help="Folder with Markdown files.",
    )
    import_parser.add_argument(
        "--reviewed-by",
        help="Default reviewer name for approvals/rejections.",
    )
    import_parser.add_argument(
        "--prefer-frontmatter",
        action="store_true",
        help="Use frontmatter fields instead of body sections.",
    )
    import_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show updates without writing to Supabase.",
    )
    import_parser.set_defaults(func=import_entries)

    compile_parser = subparsers.add_parser("compile", help="Compile playbooks to workspace store.")
    compile_parser.add_argument(
        "--categories",
        action="append",
        help="Comma-separated categories to compile (repeatable).",
    )
    compile_parser.add_argument(
        "--include-pending",
        action="store_true",
        help="Include pending entries in compiled playbook output.",
    )
    compile_parser.set_defaults(func=compile_playbooks)

    args = parser.parse_args()
    if args.command == "compile":
        asyncio.run(args.func(args))
    else:
        args.func(args)


if __name__ == "__main__":
    main()
