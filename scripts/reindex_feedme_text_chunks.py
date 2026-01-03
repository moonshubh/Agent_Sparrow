from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, AsyncIterator

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.settings import settings
from app.db.embedding.utils import get_embedding_model
from app.db.embedding_config import assert_dim
from app.db.supabase.client import get_supabase_client


logger = logging.getLogger("feedme_reindex")


def _build_contextual_embedding_input(
    *,
    chunks: list[str],
    index: int,
    window_before: int,
    window_after: int,
    max_chars: int,
) -> str:
    start = max(0, index - max(0, int(window_before)))
    end = min(len(chunks) - 1, index + max(0, int(window_after)))
    parts = [chunks[i].strip() for i in range(start, end + 1) if chunks[i].strip()]
    merged = "\n\n---\n\n".join(parts).strip()
    if len(merged) <= max_chars:
        return merged

    keep = max(256, int(max_chars))
    if keep >= len(merged):
        return merged
    head = merged[: keep // 2].rstrip()
    tail = merged[-(keep - len(head)) :].lstrip()
    return f"{head}\n\n...\n\n{tail}".strip()


async def _iter_conversation_ids(
    *,
    supa: Any,
    conversation_ids: list[int] | None,
    folder_id: int | None,
    limit: int,
) -> AsyncIterator[int]:
    if conversation_ids:
        for cid in conversation_ids[:limit]:
            yield cid
        return

    if folder_id is None:
        raise SystemExit("Provide --conversation-id or --folder-id to scope reindexing.")

    resp = await supa._exec(
        lambda: supa.client.table("feedme_conversations")
        .select("id")
        .eq("folder_id", folder_id)
        .order("id")
        .limit(limit)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    for row in rows:
        try:
            yield int(row.get("id"))
        except Exception:
            continue


async def reindex_feedme_text_chunks(
    *,
    conversation_ids: list[int] | None,
    folder_id: int | None,
    limit_conversations: int,
    window_before: int,
    window_after: int,
    max_embedding_chars: int,
    dry_run: bool,
) -> int:
    supa = get_supabase_client()
    emb_model = get_embedding_model()

    updated = 0
    async for conversation_id in _iter_conversation_ids(
        supa=supa,
        conversation_ids=conversation_ids,
        folder_id=folder_id,
        limit=limit_conversations,
    ):
        resp = await supa._exec(
            lambda cid=conversation_id: supa.client.table("feedme_text_chunks")
            .select("id, chunk_index, content")
            .eq("conversation_id", cid)
            .order("chunk_index")
            .execute()
        )
        rows = getattr(resp, "data", None) or []
        if not rows:
            logger.info("conversation=%s chunks=0", conversation_id)
            continue

        chunk_texts: list[str] = [str(row.get("content") or "") for row in rows]
        logger.info("conversation=%s chunks=%s dry_run=%s", conversation_id, len(rows), dry_run)

        for row_idx, row in enumerate(rows):
            chunk_id = row.get("id")
            try:
                chunk_index = int(row.get("chunk_index"))
            except Exception:
                continue
            if chunk_id is None:
                continue

            embed_input = _build_contextual_embedding_input(
                chunks=chunk_texts,
                index=row_idx,
                window_before=window_before,
                window_after=window_after,
                max_chars=max_embedding_chars,
            )
            if not embed_input.strip():
                continue

            if dry_run:
                updated += 1
                continue

            vec = emb_model.embed_query(embed_input)
            assert_dim(vec, "feedme_text_chunks.embedding")
            await supa._exec(
                lambda v=vec, cid=chunk_id: supa.client.table("feedme_text_chunks")
                .update({"embedding": v})
                .eq("id", cid)
                .execute()
            )
            updated += 1
            logger.debug(
                "conversation=%s chunk_index=%s chunk_id=%s updated=%s",
                conversation_id,
                chunk_index,
                chunk_id,
                updated,
            )

    return updated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reindex FeedMe chunk embeddings with contextual windows (Phase 6 late chunking approximation)."
    )
    parser.add_argument(
        "--conversation-id",
        action="append",
        type=int,
        dest="conversation_ids",
        help="Conversation id to reindex (repeatable).",
    )
    parser.add_argument(
        "--folder-id",
        type=int,
        default=None,
        help="Reindex all conversations in this folder (use with --limit-conversations).",
    )
    parser.add_argument(
        "--limit-conversations",
        type=int,
        default=25,
        help="Max conversations to process when using --folder-id.",
    )
    parser.add_argument(
        "--window-before",
        type=int,
        default=1,
        help="Chunks to include before each chunk for contextual embedding input.",
    )
    parser.add_argument(
        "--window-after",
        type=int,
        default=1,
        help="Chunks to include after each chunk for contextual embedding input.",
    )
    parser.add_argument(
        "--max-embedding-chars",
        type=int,
        default=8000,
        help="Max characters sent to the embedding model per chunk update.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write embeddings to Supabase (default is dry-run).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if not getattr(settings, "supabase_url", None) or not getattr(
        settings, "supabase_service_key", None
    ):
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in environment.")

    dry_run = not bool(args.apply)
    updated = asyncio.run(
        reindex_feedme_text_chunks(
            conversation_ids=args.conversation_ids,
            folder_id=args.folder_id,
            limit_conversations=max(1, int(args.limit_conversations)),
            window_before=int(args.window_before),
            window_after=int(args.window_after),
            max_embedding_chars=max(512, int(args.max_embedding_chars)),
            dry_run=dry_run,
        )
    )
    logger.info("completed updated=%s dry_run=%s", updated, dry_run)


if __name__ == "__main__":
    main()
