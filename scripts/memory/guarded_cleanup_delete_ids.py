#!/usr/bin/env python3
"""
Guarded cleanup helper for memory ID delete-sets.

Usage:
  python scripts/memory/guarded_cleanup_delete_ids.py --ids-file /path/to/ids.txt
  python scripts/memory/guarded_cleanup_delete_ids.py --ids-file /path/to/ids.txt --apply

Notes:
- Dry-run by default.
- Cleanup guard excludes edited memories with confidence >= 0.6.
- Manual single-memory delete endpoint remains unchanged by design.
- Apply mode requires DB migration `041_add_guarded_memory_delete_rpc.sql`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Iterable, TypeVar

from app.memory.edit_state import CLEANUP_PROTECTED_MIN_CONFIDENCE
from app.memory.memory_ui_service import get_memory_ui_service

DELETE_RPC_NAME = "delete_memories_with_relationship_cleanup"


def _read_ids(ids_file: Path) -> list[str]:
    raw = ids_file.read_text(encoding="utf-8")
    items = [line.strip().strip(",") for line in raw.splitlines()]
    return [item for item in items if item]


T = TypeVar("T")


def _chunked(rows: list[T], size: int) -> Iterable[list[T]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


async def _run(ids: list[str], apply: bool) -> dict:
    service = get_memory_ui_service()
    supabase = service._get_supabase()

    candidate_rows: list[dict] = []
    for chunk in _chunked(ids, 200):
        response = await supabase._exec(
            lambda: supabase.client.table("memories")
            .select(
                "id,confidence_score,created_at,updated_at,reviewed_by,metadata,review_status"
            )
            .in_("id", chunk)
            .execute()
        )
        if response.data:
            candidate_rows.extend(response.data)

    deletable, protected = await service.partition_cleanup_delete_candidates(
        candidate_rows,
        min_confidence=CLEANUP_PROTECTED_MIN_CONFIDENCE,
    )

    deleted_relationships = 0
    deleted_memories = 0
    if apply and deletable:
        deletable_ids = [row["id"] for row in deletable if row.get("id")]
        for chunk in _chunked(deletable_ids, 200):
            rpc_resp = await supabase._exec(
                lambda: supabase.rpc(
                    DELETE_RPC_NAME,
                    {"p_memory_ids": chunk},
                ).execute()
            )
            rpc_rows = rpc_resp.data or []
            rpc_row = rpc_rows[0] if rpc_rows else {}
            deleted_relationships += int(rpc_row.get("deleted_relationships") or 0)
            deleted_memories += int(rpc_row.get("deleted_memories") or 0)

    return {
        "input_ids": len(ids),
        "existing_candidates": len(candidate_rows),
        "deletable_count": len(deletable),
        "protected_count": len(protected),
        "protected_ids": [row.get("id") for row in protected if row.get("id")],
        "applied": bool(apply),
        "deleted_relationships": deleted_relationships,
        "deleted_memories": deleted_memories,
        "guard_min_confidence": CLEANUP_PROTECTED_MIN_CONFIDENCE,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded cleanup for memory IDs")
    parser.add_argument(
        "--ids-file",
        required=True,
        type=Path,
        help="Path to newline-delimited memory IDs",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply deletes. Omit for dry-run.",
    )
    args = parser.parse_args()

    ids = _read_ids(args.ids_file)
    result = asyncio.run(_run(ids=ids, apply=args.apply))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
