"""LangGraph BaseStore adapter for Agent Sparrow memory service.

This module provides a LangGraph-compatible BaseStore implementation that wraps
our existing mem0-based MemoryService. It enables LangGraph's built-in memory
patterns while leveraging our proven infrastructure.

Following LangGraph patterns:
- Namespace-based key organization (agent_id, collection)
- Key-value storage with metadata
- Semantic search when configured
- Async-first with sync fallbacks

Usage:
    from app.agents.harness.store import SparrowMemoryStore

    store = SparrowMemoryStore()
    await store.aput(("sparrow",), "fact_001", {"text": "User prefers dark mode"})
    results = await store.asearch(("sparrow",), query="user preferences")
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from loguru import logger

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
    # Graceful degradation when langgraph.store not available
    _LANGGRAPH_STORE_AVAILABLE = False
    BaseStore = object  # type: ignore
    Item = SearchItem = MatchCondition = None  # type: ignore
    Op = Result = GetOp = PutOp = SearchOp = ListNamespacesOp = None  # type: ignore


# Sentinel for import failure detection
_IMPORT_FAILED = object()


class SparrowMemoryStore(BaseStore if _LANGGRAPH_STORE_AVAILABLE else object):
    """LangGraph BaseStore implementation backed by Sparrow's MemoryService.

    Maps LangGraph's namespace/key/value model to our mem0-based storage:
    - Namespace tuple[0] -> agent_id (e.g., ("sparrow",) -> agent_id="sparrow")
    - Namespace tuple[1:] -> additional scoping (user_id, session_id)
    - Key -> unique identifier within namespace
    - Value -> dict stored as memory with metadata

    This store supports:
    - Key-value CRUD operations via get/put/delete
    - Semantic search via search() when memory service is configured
    - Namespace listing for organizational queries
    - TTL is NOT supported (supports_ttl = False)

    Example:
        store = SparrowMemoryStore()

        # Store user preference
        await store.aput(
            namespace=("sparrow", "user_123"),
            key="pref_theme",
            value={"text": "User prefers dark mode", "category": "preference"}
        )

        # Search memories
        results = await store.asearch(
            namespace_prefix=("sparrow",),
            query="user preferences"
        )

        # Get specific item
        item = await store.aget(("sparrow", "user_123"), "pref_theme")
    """

    supports_ttl = False

    def __init__(self) -> None:
        """Initialize the memory store.

        The actual MemoryService is lazy-loaded to avoid circular imports.
        """
        self._memory_service = None
        # Local cache for items (namespace -> key -> Item)
        # Used for get/put operations since mem0 is search-focused
        self._cache: Dict[Tuple[str, ...], Dict[str, Item]] = defaultdict(dict)

    @property
    def memory_service(self):
        """Lazy-load the memory service.

        Returns None if import failed or service unavailable.
        """
        if self._memory_service is _IMPORT_FAILED:
            return None

        if self._memory_service is None:
            try:
                from app.memory import memory_service

                self._memory_service = memory_service
            except ImportError:
                logger.warning("MemoryService not available - operating in cache-only mode")
                self._memory_service = _IMPORT_FAILED
                return None

        return self._memory_service

    # -------------------------------------------------------------------------
    # Required BaseStore methods
    # -------------------------------------------------------------------------

    def batch(self, ops: Iterable[Op]) -> List[Result]:
        """Execute a batch of operations synchronously.

        Args:
            ops: Iterable of GetOp, PutOp, SearchOp, or ListNamespacesOp.

        Returns:
            List of results corresponding to each operation.
        """
        if not _LANGGRAPH_STORE_AVAILABLE:
            raise RuntimeError("langgraph.store not available")

        # Use asyncio.run() for Python 3.10+ compatibility (avoids deprecated get_event_loop())
        try:
            loop = asyncio.get_running_loop()
            # If there's already a running loop, create a task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, self.abatch(ops)).result()
        except RuntimeError:
            # No running loop - safe to use asyncio.run()
            return asyncio.run(self.abatch(ops))

    async def abatch(self, ops: Iterable[Op]) -> List[Result]:
        """Execute a batch of operations asynchronously.

        Args:
            ops: Iterable of GetOp, PutOp, SearchOp, or ListNamespacesOp.

        Returns:
            List of results corresponding to each operation.
        """
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
                # Unknown op type - return None
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

        # Try to retrieve from memory service
        if self.memory_service and len(namespace) > 0:
            agent_id = namespace[0]
            try:
                results = await self.memory_service.retrieve(
                    agent_id=agent_id,
                    query=key,  # Use key as query for exact match attempt
                    top_k=1,
                )
                if results:
                    # Check if we have an exact key match in metadata
                    for result in results:
                        metadata = result.get("metadata", {})
                        if metadata.get("store_key") == key:
                            item = Item(
                                value={
                                    "text": result.get("memory", ""),
                                    "score": result.get("score"),
                                    **metadata,
                                },
                                key=key,
                                namespace=namespace,
                                created_at=datetime.now(timezone.utc),
                                updated_at=datetime.now(timezone.utc),
                            )
                            # Cache the item
                            self._cache[namespace][key] = item
                            return item
            except Exception as exc:
                logger.warning("memory_store_get_error", error=str(exc), key=key)

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

        # Create the Item
        item = Item(
            value=value,
            key=key,
            namespace=namespace,
            created_at=self._cache.get(namespace, {}).get(key, Item(
                value={}, key=key, namespace=namespace,
                created_at=now, updated_at=now
            )).created_at if namespace in self._cache and key in self._cache[namespace] else now,
            updated_at=now,
        )

        # Store in local cache
        self._cache[namespace][key] = item

        # Persist to memory service if available
        if self.memory_service and len(namespace) > 0:
            agent_id = namespace[0]
            # Extract text content for memory storage
            text = value.get("text", "")
            if not text and isinstance(value, dict):
                # Try to construct text from value fields
                text = " | ".join(
                    f"{k}: {v}" for k, v in value.items()
                    if isinstance(v, (str, int, float, bool))
                )

            if text:
                # Build metadata with store key for retrieval
                meta = {
                    "store_key": key,
                    "namespace": "/".join(namespace),
                    **({"user_id": namespace[1]} if len(namespace) > 1 else {}),
                    **({"session_id": namespace[2]} if len(namespace) > 2 else {}),
                }

                try:
                    await self.memory_service.add_facts(
                        agent_id=agent_id,
                        facts=[text],
                        meta=meta,
                    )
                except Exception as exc:
                    logger.warning("memory_store_put_error", error=str(exc), key=key)

    async def _execute_search(
        self,
        namespace_prefix: Tuple[str, ...],
        query: Optional[str] = None,
        filter_dict: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> List[SearchItem]:
        """Search for items matching query within namespace prefix."""
        results: List[SearchItem] = []

        # Use memory service for semantic search if available
        if self.memory_service and query and len(namespace_prefix) > 0:
            agent_id = namespace_prefix[0]
            try:
                # Fetch enough results to account for offset (pagination applied at end)
                memories = await self.memory_service.retrieve(
                    agent_id=agent_id,
                    query=query,
                    top_k=limit + offset,
                )

                # Don't slice here - let final pagination handle offset/limit
                for memory in memories:
                    metadata = memory.get("metadata", {})
                    ns_str = metadata.get("namespace", agent_id)
                    namespace = tuple(ns_str.split("/")) if ns_str else (agent_id,)

                    results.append(
                        SearchItem(
                            value={
                                "text": memory.get("memory", ""),
                                **metadata,
                            },
                            key=metadata.get("store_key", memory.get("id", str(uuid.uuid4()))),
                            namespace=namespace,
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc),
                            score=memory.get("score", 0.0),
                        )
                    )
            except Exception as exc:
                logger.warning("memory_store_search_error", error=str(exc), query=query)

        # Also search local cache for matching items
        for ns, items in self._cache.items():
            # Check if namespace matches prefix
            if len(ns) >= len(namespace_prefix):
                if ns[: len(namespace_prefix)] == namespace_prefix:
                    for key, item in items.items():
                        # Apply filter if provided
                        if filter_dict:
                            match = all(
                                item.value.get(k) == v
                                for k, v in filter_dict.items()
                            )
                            if not match:
                                continue

                        # Add to results if not already present
                        if not any(r.key == key and r.namespace == ns for r in results):
                            results.append(
                                SearchItem(
                                    value=item.value,
                                    key=item.key,
                                    namespace=item.namespace,
                                    created_at=item.created_at,
                                    updated_at=item.updated_at,
                                    score=0.5,  # Default score for cache hits
                                )
                            )

        # Apply offset and limit
        return results[offset : offset + limit]

    async def _execute_list_namespaces(
        self,
        match_conditions: Optional[Tuple] = None,
        max_depth: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Tuple[str, ...]]:
        """List all namespaces matching criteria.

        Args:
            match_conditions: Tuple of MatchCondition for prefix/suffix filtering.
            max_depth: Maximum namespace depth to return.
            limit: Maximum number of namespaces to return.
            offset: Number of namespaces to skip.

        Returns:
            List of matching namespace tuples.
        """
        all_namespaces = set(self._cache.keys())

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

        # Sort and apply pagination
        sorted_ns = sorted(all_namespaces)
        return sorted_ns[offset : offset + limit]

    # -------------------------------------------------------------------------
    # Convenience methods (delegating to batch/abatch)
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
        if namespace in self._cache and key in self._cache[namespace]:
            del self._cache[namespace][key]

    async def adelete(self, namespace: Tuple[str, ...], key: str) -> None:
        """Delete a single item asynchronously."""
        if namespace in self._cache and key in self._cache[namespace]:
            del self._cache[namespace][key]

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

    def list_namespaces(
        self,
        *,
        prefix: Optional[Tuple[str, ...]] = None,
        suffix: Optional[Tuple[str, ...]] = None,
        max_depth: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Tuple[str, ...]]:
        """List namespaces synchronously."""
        if not _LANGGRAPH_STORE_AVAILABLE:
            raise RuntimeError("langgraph.store not available")
        # Build match conditions from prefix/suffix
        match_conditions = self._build_match_conditions(prefix, suffix)
        results = self.batch([
            ListNamespacesOp(
                match_conditions=match_conditions,
                max_depth=max_depth,
                limit=limit,
                offset=offset,
            )
        ])
        return results[0] if results else []

    async def alist_namespaces(
        self,
        *,
        prefix: Optional[Tuple[str, ...]] = None,
        suffix: Optional[Tuple[str, ...]] = None,
        max_depth: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Tuple[str, ...]]:
        """List namespaces asynchronously."""
        if not _LANGGRAPH_STORE_AVAILABLE:
            raise RuntimeError("langgraph.store not available")
        # Build match conditions from prefix/suffix
        match_conditions = self._build_match_conditions(prefix, suffix)
        results = await self.abatch([
            ListNamespacesOp(
                match_conditions=match_conditions,
                max_depth=max_depth,
                limit=limit,
                offset=offset,
            )
        ])
        return results[0] if results else []

    def _build_match_conditions(
        self,
        prefix: Optional[Tuple[str, ...]] = None,
        suffix: Optional[Tuple[str, ...]] = None,
    ) -> Optional[Tuple[MatchCondition, ...]]:
        """Build match conditions from prefix/suffix parameters."""
        conditions = []
        if prefix:
            conditions.append(MatchCondition(match_type="prefix", path=prefix))
        if suffix:
            conditions.append(MatchCondition(match_type="suffix", path=suffix))
        return tuple(conditions) if conditions else None


# Global singleton for easy access
sparrow_memory_store = SparrowMemoryStore()
