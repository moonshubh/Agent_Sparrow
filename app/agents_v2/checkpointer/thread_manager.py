from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List


logger = logging.getLogger(__name__)


class ThreadManager:
    """Minimal thread manager that uses the checkpointer's DB pool.

    Methods mirror the signatures used by the test suite and rely on mocked
    connection methods provided by fixtures.
    """

    def __init__(self, checkpointer):
        self.checkpointer = checkpointer
        self.pool = checkpointer.pool

    @staticmethod
    def _ensure_dict(value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.warning("Failed to decode JSON field: %s", value)
                return {}
        return dict(value) if hasattr(value, "items") else {}

    @staticmethod
    def _rows_to_dicts(cursor: Any, rows: List[Any]) -> List[Dict[str, Any]]:
        if not rows:
            return []
        first = rows[0]
        if isinstance(first, dict):
            return [dict(row) for row in rows]

        columns: List[str] = []
        if hasattr(cursor, "description") and cursor.description:
            columns = [getattr(col, "name", col[0]) for col in cursor.description]

        results: List[Dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                item = dict(row)
            elif columns:
                item = {columns[idx]: row[idx] for idx in range(min(len(columns), len(row)))}
            else:
                item = {"value": row}

            if "state" in item:
                item["state"] = ThreadManager._decode_json(item["state"], {})
            if "metadata" in item:
                item["metadata"] = ThreadManager._decode_json(item["metadata"], {})
            results.append(item)
        return results

    @staticmethod
    def _get_value(row: Any, key: str, index: int) -> Any:
        if row is None:
            return None
        if isinstance(row, dict):
            return row.get(key)
        if hasattr(row, key):
            return getattr(row, key)
        return row[index]

    @staticmethod
    def _decode_json(value: Any, default: Any) -> Any:
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.warning("Failed to decode JSON payload: %s", value)
                return default
        return default

    async def get_or_create_thread(self, user_id: str, session_id: int) -> str:
        async with self.pool.connection() as conn:
            select_query = (
                """
                SELECT id
                FROM langgraph_threads
                WHERE user_id = %s AND session_id = %s
                LIMIT 1
                """
            )
            insert_query = (
                """
                INSERT INTO langgraph_threads (
                    user_id,
                    session_id,
                    parent_thread_id,
                    title,
                    status,
                    thread_type,
                    metadata,
                    config
                )
                VALUES (%s, %s, NULL, %s, 'active', 'conversation', %s::jsonb, %s::jsonb)
                ON CONFLICT (user_id, session_id) DO UPDATE SET
                    updated_at = NOW()
                RETURNING id
                """
            )
            async with conn.transaction():
                cursor = await conn.execute(select_query, (user_id, session_id))
                row = await cursor.fetchone()
                existing_id = self._get_value(row, "id", 0)
                if existing_id:
                    return str(existing_id)

                metadata_json = json.dumps({"session_id": session_id})
                config_json = json.dumps({})
                title = f"Session {session_id}"
                cursor = await conn.execute(
                    insert_query,
                    (user_id, session_id, title, metadata_json, config_json),
                )
                inserted = await cursor.fetchone()
                new_id = self._get_value(inserted, "id", 0)
                if not new_id:
                    raise RuntimeError("Failed to create thread record")
                return str(new_id)

    async def switch_thread(self, user_id: str, thread_id: str) -> Dict[str, Any]:
        async with self.pool.connection() as conn:
            select_query = (
                """
                SELECT id, metadata, config, last_checkpoint_id
                FROM langgraph_threads
                WHERE id = %s AND user_id = %s
                LIMIT 1
                """
            )
            cursor = await conn.execute(select_query, (thread_id, user_id))
            row = await cursor.fetchone()
            if row:
                thread_metadata = self._ensure_dict(self._get_value(row, "metadata", 1))
                thread_config = self._ensure_dict(self._get_value(row, "config", 2))
                last_checkpoint_id = self._get_value(row, "last_checkpoint_id", 3)
                checkpoint_payload: Dict[str, Any]
                if last_checkpoint_id:
                    checkpoint_payload = {"id": str(last_checkpoint_id)}
                else:
                    checkpoint_payload = {"v": 1}
                return {
                    "id": str(self._get_value(row, "id", 0)),
                    "checkpoint": checkpoint_payload,
                    "metadata": thread_metadata,
                    "config": thread_config,
                }

            metadata_json = json.dumps({})
            config_json = json.dumps({})
            insert_query = (
                """
                INSERT INTO langgraph_threads (
                    id,
                    user_id,
                    session_id,
                    parent_thread_id,
                    title,
                    status,
                    thread_type,
                    metadata,
                    config,
                    last_activity_at
                )
                VALUES (%s, %s, NULL, NULL, %s, 'active', 'conversation', %s::jsonb, %s::jsonb, NOW())
                ON CONFLICT (id) DO NOTHING
                RETURNING id
                """
            )
            cursor = await conn.execute(
                insert_query,
                (thread_id, user_id, f"Thread {thread_id}", metadata_json, config_json),
            )
            inserted = await cursor.fetchone()
            if inserted:
                return {
                    "id": thread_id,
                    "checkpoint": {"v": 1},
                    "metadata": {},
                    "config": {},
                }
            if not inserted:
                # The insert failed due to a concurrent write; fetch the row again.
                cursor = await conn.execute(select_query, (thread_id, user_id))
                row = await cursor.fetchone()
                if row:
                    thread_metadata = self._ensure_dict(self._get_value(row, "metadata", 1))
                    thread_config = self._ensure_dict(self._get_value(row, "config", 2))
                    last_checkpoint_id = self._get_value(row, "last_checkpoint_id", 3)
                    checkpoint_payload = {"id": str(last_checkpoint_id)} if last_checkpoint_id else {"v": 1}
                    return {
                        "id": str(self._get_value(row, "id", 0)),
                        "checkpoint": checkpoint_payload,
                        "metadata": thread_metadata,
                        "config": thread_config,
                    }
            return {
                "id": thread_id,
                "checkpoint": {"v": 1},
                "metadata": {},
                "config": {},
            }

    async def fork_thread(self, source_thread_id: str, checkpoint_id: str, note: str) -> str:
        new_thread_id = str(uuid.uuid4())
        async with self.pool.connection() as conn:
            try:
                async with conn.transaction():
                    source_query = (
                        """
                        SELECT id, user_id, session_id, title, status, thread_type, metadata, config
                        FROM langgraph_threads
                        WHERE id = %s
                        LIMIT 1
                        """
                    )
                    source_cursor = await conn.execute(source_query, (source_thread_id,))
                    source_row = await source_cursor.fetchone()
                    if not source_row:
                        raise ValueError(f"Source thread {source_thread_id} not found")

                    source_user_id = self._get_value(source_row, "user_id", 1)
                    source_session_id = self._get_value(source_row, "session_id", 2)
                    source_title = self._get_value(source_row, "title", 3) or "Forked Thread"
                    source_status = self._get_value(source_row, "status", 4) or "active"
                    source_type = self._get_value(source_row, "thread_type", 5) or "conversation"
                    source_metadata = self._ensure_dict(self._get_value(source_row, "metadata", 6))
                    source_config = self._ensure_dict(self._get_value(source_row, "config", 7))

                    checkpoint_query = (
                        """
                        SELECT id, state, metadata, version, channel, checkpoint_type
                        FROM langgraph_checkpoints
                        WHERE id = %s AND thread_id = %s
                        LIMIT 1
                        """
                    )
                    checkpoint_cursor = await conn.execute(
                        checkpoint_query, (checkpoint_id, source_thread_id)
                    )
                    checkpoint_row = await checkpoint_cursor.fetchone()
                    if not checkpoint_row:
                        raise ValueError(
                            f"Checkpoint {checkpoint_id} not found for thread {source_thread_id}"
                        )

                    checkpoint_state = self._decode_json(
                        self._get_value(checkpoint_row, "state", 1), {}
                    )
                    checkpoint_metadata = self._ensure_dict(
                        self._get_value(checkpoint_row, "metadata", 2)
                    )
                    checkpoint_version = self._get_value(checkpoint_row, "version", 3) or 1
                    checkpoint_channel = self._get_value(checkpoint_row, "channel", 4) or "main"
                    checkpoint_type = self._get_value(checkpoint_row, "checkpoint_type", 5) or "delta"

                    fork_metadata = dict(source_metadata)
                    fork_metadata.update(
                        {
                            "forked_from_thread_id": source_thread_id,
                            "forked_from_checkpoint_id": checkpoint_id,
                        }
                    )
                    if note:
                        fork_metadata["fork_note"] = note

                    new_checkpoint_id = str(uuid.uuid4())

                    insert_thread_query = (
                        """
                        INSERT INTO langgraph_threads (
                            id,
                            user_id,
                            session_id,
                            parent_thread_id,
                            title,
                            status,
                            thread_type,
                            checkpoint_count,
                            last_checkpoint_id,
                            last_checkpoint_at,
                            metadata,
                            config
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s::jsonb, %s::jsonb)
                        """
                    )
                    await conn.execute(
                        insert_thread_query,
                        (
                            new_thread_id,
                            source_user_id,
                            source_session_id,
                            source_thread_id,
                            f"{source_title} (Fork)",
                            source_status,
                            source_type,
                            1,
                            new_checkpoint_id,
                            json.dumps(fork_metadata),
                            json.dumps(source_config),
                        ),
                    )

                    insert_checkpoint_query = (
                        """
                        INSERT INTO langgraph_checkpoints (
                            id,
                            thread_id,
                            parent_checkpoint_id,
                            version,
                            channel,
                            checkpoint_type,
                            state,
                            metadata,
                            is_latest
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, TRUE)
                        """
                    )
                    merged_metadata = dict(checkpoint_metadata)
                    merged_metadata.update({"forked_from_checkpoint": checkpoint_id})
                    await conn.execute(
                        insert_checkpoint_query,
                        (
                            new_checkpoint_id,
                            new_thread_id,
                            checkpoint_id,
                            checkpoint_version,
                            checkpoint_channel,
                            checkpoint_type,
                            json.dumps(checkpoint_state),
                            json.dumps(merged_metadata),
                        ),
                    )

                return new_thread_id
            except Exception:
                logger.exception(
                    "Failed to fork thread %s using checkpoint %s", source_thread_id, checkpoint_id
                )
                raise

    async def get_thread_history(self, thread_id: str) -> List[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            history_query = (
                """
                SELECT id, version, checkpoint_type, channel, state, metadata, created_at
                FROM langgraph_checkpoints
                WHERE thread_id = %s
                ORDER BY created_at DESC
                """
            )
            cursor = await conn.execute(history_query, (thread_id,))
            rows = await cursor.fetchall()
            return self._rows_to_dicts(cursor, rows)

    async def cleanup_old_checkpoints(self, days: int = 30, dry_run: bool = True) -> int:
        async with self.pool.connection() as conn:
            interval_param = f"{max(days, 0)} days"
            if dry_run:
                query = (
                    """
                    SELECT COUNT(*) AS deleted_count
                    FROM langgraph_checkpoints
                    WHERE created_at < NOW() - %s::interval
                    """
                )
                cursor = await conn.execute(query, (interval_param,))
                row = await cursor.fetchone()
                deleted_count = self._get_value(row, "deleted_count", 0) or 0
                return int(deleted_count)

            delete_query = (
                """
                DELETE FROM langgraph_checkpoints
                WHERE created_at < NOW() - %s::interval
                RETURNING id
                """
            )
            cursor = await conn.execute(delete_query, (interval_param,))
            rows = await cursor.fetchall()
            deleted_count = len(rows)
            return int(deleted_count)
