"""LangGraph BaseStore adapter for Deep Agent workspace files.

This module provides a LangGraph-compatible BaseStore implementation backed by
Supabase for persistent workspace storage. It's designed for the context engineering
pattern from DeepAgents, storing:
- /progress/ - Session progress notes
- /goals/ - Active goals and feature tracking
- /handoff/ - Session handoff context for resumption

Usage:
    from app.agents.harness.store import SparrowWorkspaceStore

    store = SparrowWorkspaceStore(session_id="abc123")
    await store.aput(("progress",), "notes.md", {"content": "Progress so far..."})
    item = await store.aget(("progress",), "notes.md")
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from supabase import Client as SupabaseClient

try:
    from langgraph.store.base import (
        BaseStore,
        GetOp,
        Item,
        ListNamespacesOp,
        MatchCondition,
        Op,
        PutOp,
        Result,
        SearchItem,
        SearchOp,
    )

    _LANGGRAPH_STORE_AVAILABLE = True
except ImportError:
    _LANGGRAPH_STORE_AVAILABLE = False
    BaseStore = object  # type: ignore
    Item = SearchItem = MatchCondition = None  # type: ignore
    Op = Result = GetOp = PutOp = SearchOp = ListNamespacesOp = None  # type: ignore


# Sentinel for import failure detection
_IMPORT_FAILED = object()

# Table name for workspace storage
# Using the existing LangGraph 'store' table (prefix/key/value structure)
WORKSPACE_TABLE = "store"


class SparrowWorkspaceStore(BaseStore if _LANGGRAPH_STORE_AVAILABLE else object):
    """LangGraph BaseStore implementation for Deep Agent workspace files.

    Provides persistent storage for workspace files using Supabase backend:
    - Namespace tuple maps to path prefix (e.g., ("progress", "session123") -> "/progress/session123/")
    - Key maps to filename within namespace
    - Value is stored as JSON in content field

    This store supports:
    - Key-value CRUD operations via get/put/delete
    - Namespace listing for organizational queries
    - TTL is NOT supported (supports_ttl = False)

    Example:
        store = SparrowWorkspaceStore(session_id="session123")

        # Store progress notes
        await store.aput(
            namespace=("progress",),
            key="notes.md",
            value={"content": "Made progress on feature X..."}
        )

        # Store goals
        await store.aput(
            namespace=("goals",),
            key="active.json",
            value={
                "features": [
                    {"name": "Auth", "status": "pass"},
                    {"name": "API", "status": "pending"}
                ]
            }
        )

        # Get handoff context
        item = await store.aget(("handoff",), "summary.json")
    """

    supports_ttl = False

    def __init__(
        self,
        session_id: str,
        supabase_client: Optional["SupabaseClient"] = None,
    ) -> None:
        """Initialize the workspace store.

        Args:
            session_id: The session ID for scoping workspace files.
            supabase_client: Optional Supabase client. If not provided,
                             will be lazy-loaded from app.db.supabase.
        """
        self.session_id = session_id
        self._client = supabase_client
        # Local cache for faster reads within same request
        self._cache: Dict[Tuple[str, ...], Dict[str, Item]] = defaultdict(dict)

    @property
    def client(self) -> Optional["SupabaseClient"]:
        """Lazy-load the Supabase client.

        Returns None if import failed or client unavailable.
        """
        if self._client is _IMPORT_FAILED:
            return None

        if self._client is None:
            try:
                from app.db.supabase.client import get_supabase_client

                self._client = get_supabase_client()
            except ImportError:
                logger.warning("Supabase client not available - operating in cache-only mode")
                self._client = _IMPORT_FAILED  # type: ignore
                return None
            except Exception as exc:
                logger.warning("Supabase client initialization failed", error=str(exc))
                self._client = _IMPORT_FAILED  # type: ignore
                return None

        return self._client

    def _namespace_to_prefix(self, namespace: Tuple[str, ...]) -> str:
        """Convert namespace tuple to prefix for store table.

        Example:
            ("progress",) -> "workspace:progress:{session_id}"
            ("goals",) -> "workspace:goals:{session_id}"
        """
        ns_path = ":".join(namespace)
        return f"workspace:{ns_path}:{self.session_id}"

    def _prefix_key_to_namespace(self, prefix: str, key: str) -> Tuple[Tuple[str, ...], str]:
        """Convert prefix and key back to namespace tuple and key.

        Example:
            "workspace:progress:session123", "notes.md" -> (("progress",), "notes.md")
        """
        parts = prefix.split(":")
        if len(parts) >= 3 and parts[0] == "workspace":
            namespace = (parts[1],)
            return namespace, key
        return (), key

    # -------------------------------------------------------------------------
    # Required BaseStore methods
    # -------------------------------------------------------------------------

    def batch(self, ops: Iterable[Op]) -> List[Result]:
        """Execute a batch of operations synchronously."""
        if not _LANGGRAPH_STORE_AVAILABLE:
            raise RuntimeError("langgraph.store not available")

        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, self.abatch(ops)).result()
        except RuntimeError:
            return asyncio.run(self.abatch(ops))

    async def abatch(self, ops: Iterable[Op]) -> List[Result]:
        """Execute a batch of operations asynchronously."""
        if not _LANGGRAPH_STORE_AVAILABLE:
            raise RuntimeError("langgraph.store not available")

        results: List[Result] = []
        ops_list = list(ops)

        for op in ops_list:
            if isinstance(op, GetOp):
                item = await self._execute_get(op.namespace, op.key)
                results.append(item)
            elif isinstance(op, PutOp):
                await self._execute_put(op.namespace, op.key, op.value, op.index)
                results.append(None)
            elif isinstance(op, SearchOp):
                items = await self._execute_search(
                    op.namespace_prefix,
                    query=op.query,
                    filter_dict=op.filter,
                    limit=op.limit,
                    offset=op.offset,
                )
                results.append(items)
            elif isinstance(op, ListNamespacesOp):
                namespaces = await self._execute_list_namespaces(
                    match_conditions=op.match_conditions,
                    max_depth=op.max_depth,
                    limit=op.limit,
                    offset=op.offset,
                )
                results.append(namespaces)
            else:
                results.append(None)

        return results

    # -------------------------------------------------------------------------
    # Internal execution methods
    # -------------------------------------------------------------------------

    async def _execute_get(
        self, namespace: Tuple[str, ...], key: str
    ) -> Optional[Item]:
        """Get an item by namespace and key."""
        # Check local cache first
        if namespace in self._cache and key in self._cache[namespace]:
            return self._cache[namespace][key]

        # Try to retrieve from Supabase (store table: prefix, key, value)
        if self.client:
            prefix = self._namespace_to_prefix(namespace)
            try:
                response = (
                    self.client.table(WORKSPACE_TABLE)
                    .select("value, created_at, updated_at")
                    .eq("prefix", prefix)
                    .eq("key", key)
                    .single()
                    .execute()
                )

                if response.data:
                    value = response.data.get("value", {})
                    if isinstance(value, str):
                        try:
                            value = json.loads(value)
                        except json.JSONDecodeError:
                            value = {"content": value}

                    created_at = response.data.get("created_at")
                    updated_at = response.data.get("updated_at")

                    item = Item(
                        value=value,
                        key=key,
                        namespace=namespace,
                        created_at=datetime.fromisoformat(created_at.replace("Z", "+00:00")) if created_at else datetime.now(timezone.utc),
                        updated_at=datetime.fromisoformat(updated_at.replace("Z", "+00:00")) if updated_at else datetime.now(timezone.utc),
                    )
                    # Cache the item
                    self._cache[namespace][key] = item
                    return item

            except Exception as exc:
                logger.debug("workspace_store_get_error", prefix=prefix, key=key, error=str(exc))

        return None

    async def _execute_put(
        self,
        namespace: Tuple[str, ...],
        key: str,
        value: Dict[str, Any],
        index: Optional[List[str]] = None,
    ) -> None:
        """Store an item with namespace and key."""
        now = datetime.now(timezone.utc)

        # Create the Item for cache
        existing = self._cache.get(namespace, {}).get(key)
        item = Item(
            value=value,
            key=key,
            namespace=namespace,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )

        # Store in local cache
        self._cache[namespace][key] = item

        # Persist to Supabase (store table: prefix, key, value)
        if self.client:
            prefix = self._namespace_to_prefix(namespace)

            data = {
                "prefix": prefix,
                "key": key,
                "value": value,  # JSONB column - pass dict directly
                "updated_at": now.isoformat(),
            }

            try:
                self.client.table(WORKSPACE_TABLE).upsert(
                    data, on_conflict="prefix,key"
                ).execute()
            except Exception as exc:
                logger.warning("workspace_store_put_error", prefix=prefix, key=key, error=str(exc))

    async def _execute_search(
        self,
        namespace_prefix: Tuple[str, ...],
        query: Optional[str] = None,
        filter_dict: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> List[SearchItem]:
        """Search for items within namespace prefix."""
        results: List[SearchItem] = []

        # Search Supabase (store table: prefix, key, value)
        if self.client:
            prefix_pattern = self._namespace_to_prefix(namespace_prefix)
            try:
                response = (
                    self.client.table(WORKSPACE_TABLE)
                    .select("prefix, key, value, created_at, updated_at")
                    .like("prefix", f"{prefix_pattern}%")
                    .limit(limit + offset)
                    .execute()
                )

                for row in response.data or []:
                    namespace, key = self._prefix_key_to_namespace(row["prefix"], row["key"])
                    value = row.get("value", {})
                    if isinstance(value, str):
                        try:
                            value = json.loads(value)
                        except json.JSONDecodeError:
                            value = {"content": value}

                    # Apply filter if provided
                    if filter_dict:
                        match = all(
                            value.get(k) == v
                            for k, v in filter_dict.items()
                        )
                        if not match:
                            continue

                    created_at = row.get("created_at")
                    updated_at = row.get("updated_at")

                    results.append(
                        SearchItem(
                            value=value,
                            key=key,
                            namespace=namespace,
                            created_at=datetime.fromisoformat(created_at.replace("Z", "+00:00")) if created_at else datetime.now(timezone.utc),
                            updated_at=datetime.fromisoformat(updated_at.replace("Z", "+00:00")) if updated_at else datetime.now(timezone.utc),
                            score=1.0,  # No semantic search, exact match
                        )
                    )

            except Exception as exc:
                logger.warning("workspace_store_search_error", prefix=prefix_pattern, error=str(exc))

        # Also search local cache
        for ns, items in self._cache.items():
            if len(ns) >= len(namespace_prefix):
                if ns[: len(namespace_prefix)] == namespace_prefix:
                    for key, item in items.items():
                        if filter_dict:
                            match = all(
                                item.value.get(k) == v
                                for k, v in filter_dict.items()
                            )
                            if not match:
                                continue

                        if not any(r.key == key and r.namespace == ns for r in results):
                            results.append(
                                SearchItem(
                                    value=item.value,
                                    key=item.key,
                                    namespace=item.namespace,
                                    created_at=item.created_at,
                                    updated_at=item.updated_at,
                                    score=0.5,
                                )
                            )

        return results[offset : offset + limit]

    async def _execute_list_namespaces(
        self,
        match_conditions: Optional[Tuple] = None,
        max_depth: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Tuple[str, ...]]:
        """List all namespaces matching criteria."""
        all_namespaces = set(self._cache.keys())

        # Add namespaces from Supabase (store table: prefix, key, value)
        if self.client:
            try:
                response = (
                    self.client.table(WORKSPACE_TABLE)
                    .select("prefix, key")
                    .like("prefix", f"workspace:%:{self.session_id}%")
                    .execute()
                )

                for row in response.data or []:
                    namespace, _ = self._prefix_key_to_namespace(row["prefix"], row["key"])
                    if namespace:
                        all_namespaces.add(namespace)

            except Exception as exc:
                logger.warning("workspace_store_list_ns_error", error=str(exc))

        # Apply match conditions
        if match_conditions:
            for condition in match_conditions:
                match_type = condition.match_type
                path = condition.path

                if match_type == "prefix":
                    all_namespaces = {
                        ns for ns in all_namespaces
                        if len(ns) >= len(path) and ns[: len(path)] == path
                    }
                elif match_type == "suffix":
                    all_namespaces = {
                        ns for ns in all_namespaces
                        if len(ns) >= len(path) and ns[-len(path) :] == path
                    }

        # Filter by max_depth
        if max_depth is not None:
            all_namespaces = {
                ns for ns in all_namespaces if len(ns) <= max_depth
            }

        sorted_ns = sorted(all_namespaces)
        return sorted_ns[offset : offset + limit]

    # -------------------------------------------------------------------------
    # Convenience methods
    # -------------------------------------------------------------------------

    def get(
        self,
        namespace: Tuple[str, ...],
        key: str,
        *,
        refresh_ttl: Optional[bool] = None,
    ) -> Optional[Item]:
        """Get a single item synchronously."""
        if not _LANGGRAPH_STORE_AVAILABLE:
            raise RuntimeError("langgraph.store not available")
        results = self.batch([GetOp(namespace=namespace, key=key)])
        return results[0] if results else None

    async def aget(
        self,
        namespace: Tuple[str, ...],
        key: str,
        *,
        refresh_ttl: Optional[bool] = None,
    ) -> Optional[Item]:
        """Get a single item asynchronously."""
        if not _LANGGRAPH_STORE_AVAILABLE:
            raise RuntimeError("langgraph.store not available")
        results = await self.abatch([GetOp(namespace=namespace, key=key)])
        return results[0] if results else None

    def put(
        self,
        namespace: Tuple[str, ...],
        key: str,
        value: Dict[str, Any],
        index: Optional[List[str]] = None,
        *,
        ttl: Optional[float] = None,
    ) -> None:
        """Store a single item synchronously."""
        if not _LANGGRAPH_STORE_AVAILABLE:
            raise RuntimeError("langgraph.store not available")
        self.batch([PutOp(namespace=namespace, key=key, value=value, index=index)])

    async def aput(
        self,
        namespace: Tuple[str, ...],
        key: str,
        value: Dict[str, Any],
        index: Optional[List[str]] = None,
        *,
        ttl: Optional[float] = None,
    ) -> None:
        """Store a single item asynchronously."""
        if not _LANGGRAPH_STORE_AVAILABLE:
            raise RuntimeError("langgraph.store not available")
        await self.abatch([PutOp(namespace=namespace, key=key, value=value, index=index)])

    def delete(self, namespace: Tuple[str, ...], key: str) -> None:
        """Delete a single item synchronously."""
        # Remove from cache
        if namespace in self._cache and key in self._cache[namespace]:
            del self._cache[namespace][key]

        # Remove from Supabase (store table: prefix, key)
        if self.client:
            prefix = self._namespace_to_prefix(namespace)
            try:
                self.client.table(WORKSPACE_TABLE).delete().eq("prefix", prefix).eq("key", key).execute()
            except Exception as exc:
                logger.warning("workspace_store_delete_error", prefix=prefix, key=key, error=str(exc))

    async def adelete(self, namespace: Tuple[str, ...], key: str) -> None:
        """Delete a single item asynchronously."""
        self.delete(namespace, key)

    def search(
        self,
        namespace_prefix: Tuple[str, ...],
        /,
        *,
        query: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        offset: int = 0,
        refresh_ttl: Optional[bool] = None,
    ) -> List[SearchItem]:
        """Search for items synchronously."""
        if not _LANGGRAPH_STORE_AVAILABLE:
            raise RuntimeError("langgraph.store not available")
        results = self.batch([
            SearchOp(
                namespace_prefix=namespace_prefix,
                query=query,
                filter=filter,
                limit=limit,
                offset=offset,
            )
        ])
        return results[0] if results else []

    async def asearch(
        self,
        namespace_prefix: Tuple[str, ...],
        /,
        *,
        query: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        offset: int = 0,
        refresh_ttl: Optional[bool] = None,
    ) -> List[SearchItem]:
        """Search for items asynchronously."""
        if not _LANGGRAPH_STORE_AVAILABLE:
            raise RuntimeError("langgraph.store not available")
        results = await self.abatch([
            SearchOp(
                namespace_prefix=namespace_prefix,
                query=query,
                filter=filter,
                limit=limit,
                offset=offset,
            )
        ])
        return results[0] if results else []

    # -------------------------------------------------------------------------
    # Workspace-specific convenience methods
    # -------------------------------------------------------------------------

    async def get_progress_notes(self) -> Optional[str]:
        """Get the current session's progress notes."""
        item = await self.aget(("progress",), "session_notes.md")
        if item and item.value:
            return item.value.get("content", "")
        return None

    async def set_progress_notes(self, content: str) -> None:
        """Set the current session's progress notes."""
        await self.aput(
            ("progress",),
            "session_notes.md",
            {"content": content, "updated_at": datetime.now(timezone.utc).isoformat()},
        )

    async def get_active_goals(self) -> Optional[Dict[str, Any]]:
        """Get the current session's active goals."""
        item = await self.aget(("goals",), "active.json")
        if item and item.value:
            return item.value
        return None

    async def set_active_goals(self, goals: Dict[str, Any]) -> None:
        """Set the current session's active goals."""
        goals["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.aput(("goals",), "active.json", goals)

    async def get_handoff_context(self) -> Optional[Dict[str, Any]]:
        """Get handoff context from previous session (if any)."""
        item = await self.aget(("handoff",), "summary.json")
        if item and item.value:
            return item.value
        return None

    async def set_handoff_context(self, context: Dict[str, Any]) -> None:
        """Set handoff context for session resumption."""
        context["captured_at"] = datetime.now(timezone.utc).isoformat()
        await self.aput(("handoff",), "summary.json", context)

    def clear_cache(self) -> None:
        """Clear the local cache (called at end of session)."""
        self._cache.clear()
