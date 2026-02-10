# mypy: ignore-errors
"""LangGraph BaseStore adapter for Deep Agent workspace files.

This module provides a LangGraph-compatible BaseStore implementation backed by
Supabase for persistent workspace storage. It's designed for the context engineering
pattern from DeepAgents, storing:

**Persistence Scopes:**
- GLOBAL: /playbooks/ - shared across all sessions (read-only for agents)
- CUSTOMER: /customer/{id}/, /shared/ - per-customer, survives across tickets
- SESSION: /scratch/, /knowledge/, /context/, /handoff/, /progress/, /goals/, /evidence/, /reports/ - per-ticket

Usage:
    from app.agents.harness.store import SparrowWorkspaceStore

    # Session-only access
    store = SparrowWorkspaceStore(session_id="abc123")

    # With customer scope (for Zendesk tickets)
    store = SparrowWorkspaceStore(
        session_id="zendesk-12345",
        customer_id="hash_of_email",
    )

    await store.aput(("progress",), "notes.md", {"content": "Progress so far..."})
    item = await store.aget(("progress",), "notes.md")
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, TYPE_CHECKING

from loguru import logger

# =============================================================================
# Persistence Scope Configuration
# =============================================================================


class PersistenceScope(Enum):
    """Persistence scope for workspace files."""

    GLOBAL = "global"  # /playbooks/ - shared across all sessions
    USER = "user"  # /user/ - per-user internal metadata (not exposed to agents)
    CUSTOMER = "customer"  # /customer/{id}/ - per-customer, cross-ticket
    SESSION = "session"  # /scratch/, /knowledge/ - per-ticket ephemeral


# Path-to-scope routing rules
SCOPE_ROUTING: Dict[str, PersistenceScope] = {
    "playbooks": PersistenceScope.GLOBAL,
    "user": PersistenceScope.USER,
    "customer": PersistenceScope.CUSTOMER,
    "shared": PersistenceScope.CUSTOMER,
    "scratch": PersistenceScope.SESSION,
    "knowledge": PersistenceScope.SESSION,
    "context": PersistenceScope.SESSION,
    "handoff": PersistenceScope.SESSION,
    "progress": PersistenceScope.SESSION,
    "goals": PersistenceScope.SESSION,
    "evidence": PersistenceScope.SESSION,
    "reports": PersistenceScope.SESSION,
}

# Allowed path roots for validation
ALLOWED_ROOTS: Set[str] = set(SCOPE_ROUTING.keys())

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

    Provides persistent storage for workspace files using Supabase backend with
    **three persistence scopes**:

    - **GLOBAL** (`/playbooks/`): Shared across all sessions, read-only for agents
    - **CUSTOMER** (`/customer/{id}/`): Per-customer, survives across tickets
    - **SESSION** (`/scratch/`, `/knowledge/`, etc.): Per-ticket ephemeral

    Namespace tuple maps to scope-aware prefix:
    - Global: `workspace:global:{path}`
    - Customer: `workspace:customer:{customer_id}:{path}`
    - Session: `workspace:session:{session_id}:{path}`

    This store supports:
    - Key-value CRUD operations via get/put/delete
    - Namespace listing for organizational queries
    - Path validation to prevent traversal attacks
    - TTL is NOT supported (supports_ttl = False)

    Example:
        # Session-only access
        store = SparrowWorkspaceStore(session_id="session123")

        # With customer scope (for Zendesk tickets)
        store = SparrowWorkspaceStore(
            session_id="zendesk-12345",
            customer_id="abc123hash",
        )

        # Store progress notes (SESSION scope)
        await store.aput(
            namespace=("progress",),
            key="notes.md",
            value={"content": "Made progress on feature X..."}
        )

        # Access customer history (CUSTOMER scope - requires customer_id)
        await store.aput(
            namespace=("customer", "abc123hash", "history"),
            key="ticket_12345.md",
            value={"content": "Ticket summary..."}
        )

        # Read playbooks (GLOBAL scope - typically read-only)
        item = await store.aget(("playbooks",), "sync_auth.md")
    """

    supports_ttl = False

    def __init__(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        supabase_client: Optional["SupabaseClient"] = None,
    ) -> None:
        """Initialize the workspace store.

        Args:
            session_id: The session ID for scoping workspace files (required).
            user_id: Optional authenticated user id for user-scoped metadata (e.g.
                     /user/* session registries). Session-scoped workspace prefixes
                     remain keyed by session_id for backward compatibility.
            customer_id: Optional customer ID for customer-scoped paths.
                         Required if accessing /customer/ paths.
            supabase_client: Optional Supabase client. If not provided,
                             will be lazy-loaded from app.db.supabase.
        """
        self.session_id = session_id
        self.user_id = user_id
        self.customer_id = customer_id
        self._client = supabase_client
        # Local cache for faster reads within same request
        self._cache: Dict[Tuple[str, ...], Dict[str, Item]] = defaultdict(dict)
        # Per-path locks to serialize append operations within this process
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

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
                logger.warning(
                    "Supabase client not available - operating in cache-only mode"
                )
                self._client = _IMPORT_FAILED  # type: ignore
                return None
            except Exception as exc:
                logger.warning("Supabase client initialization failed", error=str(exc))
                self._client = _IMPORT_FAILED  # type: ignore
                return None

        return self._client

    def _get_scope_for_path(self, path: str) -> PersistenceScope:
        """Determine persistence scope from path root.

        Args:
            path: Virtual path (e.g., "/scratch/notes.md", "playbooks/sync.md")

        Returns:
            PersistenceScope for this path.

        Example:
            "/playbooks/sync.md" -> PersistenceScope.GLOBAL
            "/customer/abc/history.md" -> PersistenceScope.CUSTOMER
            "/scratch/notes.md" -> PersistenceScope.SESSION
        """
        normalized = path.lstrip("/").split("/")[0] if path else ""
        return SCOPE_ROUTING.get(normalized, PersistenceScope.SESSION)

    def _validate_and_normalize_path(self, path: str) -> str:
        """Validate and normalize virtual path.

        Args:
            path: Virtual path to validate.

        Returns:
            Normalized path (stripped of leading/trailing slashes).

        Raises:
            ValueError: If path is invalid or attempts traversal.
        """
        # Normalize slashes
        normalized = path.replace("\\", "/").strip("/")

        # Reject empty paths
        if not normalized:
            raise ValueError("Empty path not allowed")

        # Reject path traversal
        if ".." in normalized:
            raise ValueError(f"Path traversal not allowed: {path}")

        # Validate root
        root = normalized.split("/")[0]
        if root not in ALLOWED_ROOTS:
            raise ValueError(
                f"Invalid path root '{root}'. Allowed: {sorted(ALLOWED_ROOTS)}"
            )

        return normalized

    def _path_to_namespace_key(self, path: str) -> Tuple[Tuple[str, ...], str]:
        """Convert virtual path to (namespace, key) tuple.

        Args:
            path: Virtual path (e.g., "/scratch/notes.md")

        Returns:
            Tuple of (namespace_tuple, key).

        Example:
            "/scratch/notes.md" -> (("scratch",), "notes.md")
            "/customer/abc123/history/ticket_1.md" -> (("customer", "abc123", "history"), "ticket_1.md")
            "/playbooks" -> (("playbooks",), "index")
        """
        normalized = self._validate_and_normalize_path(path)
        parts = normalized.split("/")

        if len(parts) == 1:
            # Single-level path like "/scratch" -> ("scratch",), "index"
            return (parts[0],), "index"

        # Multi-level path: all but last part is namespace, last is key
        return tuple(parts[:-1]), parts[-1]

    def _namespace_to_prefix(self, namespace: Tuple[str, ...]) -> str:
        """Convert namespace tuple to scope-aware prefix for store table.

        Routes to different prefixes based on path root:
        - Global: `workspace:global:{path}`
        - Customer: `workspace:customer:{customer_id}:{path}`
        - Session: `workspace:session:{session_id}:{path}`

        Example:
            ("playbooks",) -> "workspace:global:playbooks"
            ("user", "sessions") -> "workspace:user:{user_id}:sessions"
            ("customer", "abc", "history") -> "workspace:customer:abc:history"
            ("progress",) -> "workspace:session:{session_id}:progress"
        """
        if not namespace:
            raise ValueError("Empty namespace not allowed")

        path = "/".join(namespace)
        scope = self._get_scope_for_path(path)

        if scope == PersistenceScope.GLOBAL:
            return f"workspace:global:{path}"
        elif scope == PersistenceScope.USER:
            if not self.user_id:
                raise ValueError("user_id is required for user-scoped paths (/user/*)")
            rest = (
                namespace[1:]
                if len(namespace) > 1 and namespace[0] == "user"
                else namespace
            )
            rest_path = "/".join(rest)
            if not rest_path:
                raise ValueError(
                    "user-scoped namespace must include a sub-namespace (e.g. ('user','sessions'))"
                )
            return f"workspace:user:{self.user_id}:{rest_path}"
        elif scope == PersistenceScope.CUSTOMER:
            # For customer scope, extract customer_id from namespace or use stored one
            # Namespace format: ("customer", "{customer_id}", ...)
            if len(namespace) >= 2 and namespace[0] == "customer":
                customer_id = namespace[1]
            elif self.customer_id:
                customer_id = self.customer_id
            else:
                raise ValueError(
                    "customer_id required for customer-scoped paths. "
                    'Either include it in namespace ("customer", "id", ...) '
                    "or initialize store with customer_id parameter."
                )

            rest = namespace[2:] if len(namespace) > 2 else ()
            rest_path = "/".join(rest)
            prefix = f"workspace:customer:{customer_id}"
            if rest_path:
                prefix = f"{prefix}:{rest_path}"
            return prefix
        else:  # SESSION
            return f"workspace:session:{self.session_id}:{path}"

    def _prefix_key_to_namespace(
        self, prefix: str, key: str
    ) -> Tuple[Tuple[str, ...], str]:
        """Convert prefix and key back to namespace tuple and key.

        Handles all scope formats:
        - "workspace:global:playbooks" -> (("playbooks",), key)
        - "workspace:user:{user_id}:sessions" -> (("user","sessions"), key)
        - "workspace:customer:abc:history" -> (("customer", "abc", "history"), key)
        - "workspace:session:{user_id}:sess123:progress" -> (("progress",), key)
        - "workspace:session:sess123:progress" -> (("progress",), key)  (legacy)

        Example:
            "workspace:session:sess123:progress", "notes.md" -> (("progress",), "notes.md")
        """
        parts = prefix.split(":")
        if len(parts) < 3 or parts[0] != "workspace":
            return (), key

        scope = parts[1]

        if scope == "global":
            # Format: workspace:global:{path}
            path = ":".join(parts[2:])
            namespace = tuple(path.split("/"))
        elif scope == "user":
            # Format: workspace:user:{user_id}:{path}
            path = ":".join(parts[3:]) if len(parts) >= 4 else ""
            path_parts = path.split("/") if path else []
            namespace = ("user", *path_parts) if path_parts else ()
        elif scope == "customer":
            # Format: workspace:customer:{customer_id}:{path}
            customer_id = parts[2] if len(parts) >= 3 else ""
            path = ":".join(parts[3:]) if len(parts) >= 4 else ""
            path_parts = path.split("/") if path else []
            namespace = ("customer", customer_id, *path_parts) if customer_id else ()
        else:  # session
            # Formats:
            # - workspace:session:{user_id}:{session_id}:{path}
            # - workspace:session:{session_id}:{path} (legacy)
            if len(parts) >= 5:
                path = ":".join(parts[4:])
                namespace = tuple(path.split("/"))
            elif len(parts) >= 4:
                path = ":".join(parts[3:])
                namespace = tuple(path.split("/"))
            else:
                namespace = ()

        return namespace, key

    # -------------------------------------------------------------------------
    # Required BaseStore methods
    # -------------------------------------------------------------------------

    def batch(self, ops: Iterable[Op]) -> List[Result]:
        """Execute a batch of operations synchronously."""
        if not _LANGGRAPH_STORE_AVAILABLE:
            raise RuntimeError("langgraph.store not available")

        try:
            asyncio.get_running_loop()
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
            item = self._cache[namespace][key]
            # Observability: log cache hits
            path = "/".join(namespace)
            scope = self._get_scope_for_path(path)
            content_size = len(json.dumps(item.value).encode("utf-8"))
            logger.debug(
                "workspace_read",
                scope=scope.value,
                namespace=":".join(namespace),
                key=key,
                content_size_bytes=content_size,
                session_id=self.session_id,
                cache_hit=True,
            )
            return item

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
                        created_at=(
                            datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                            if created_at
                            else datetime.now(timezone.utc)
                        ),
                        updated_at=(
                            datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                            if updated_at
                            else datetime.now(timezone.utc)
                        ),
                    )
                    # Cache the item
                    self._cache[namespace][key] = item

                    # Observability: log workspace reads with scope and size
                    path = "/".join(namespace)
                    scope = self._get_scope_for_path(path)
                    content_size = len(json.dumps(value).encode("utf-8"))
                    logger.info(
                        "workspace_read",
                        scope=scope.value,
                        namespace=":".join(namespace),
                        key=key,
                        content_size_bytes=content_size,
                        session_id=self.session_id,
                        customer_id=self.customer_id,
                        cache_hit=False,
                    )
                    return item

            except Exception as exc:
                logger.debug(
                    "workspace_store_get_error", prefix=prefix, key=key, error=str(exc)
                )

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

        # Determine scope for observability
        path = "/".join(namespace)
        scope = self._get_scope_for_path(path)
        content_size = len(json.dumps(value).encode("utf-8"))

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

                # Observability: log workspace writes with scope and size
                logger.info(
                    "workspace_write",
                    scope=scope.value,
                    namespace=":".join(namespace),
                    key=key,
                    content_size_bytes=content_size,
                    session_id=self.session_id,
                    customer_id=self.customer_id,
                )
            except Exception as exc:
                logger.warning(
                    "workspace_store_put_error", prefix=prefix, key=key, error=str(exc)
                )

    async def _execute_search(
        self,
        namespace_prefix: Tuple[str, ...],
        query: Optional[str] = None,
        filter_dict: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> List[SearchItem]:
        """Search for items within namespace prefix.

        If query is provided, performs content search using the GIN index
        on the content_text generated column (uses ILIKE for case-insensitive matching).

        Args:
            namespace_prefix: Namespace tuple to search within.
            query: Optional search query for content search.
            filter_dict: Optional filter for exact value matches.
            limit: Maximum results to return.
            offset: Number of results to skip.

        Returns:
            List of matching SearchItems.
        """
        results: List[SearchItem] = []

        # Search Supabase (store table: prefix, key, value, content_text)
        if self.client:
            prefix_pattern = (
                None
                if not namespace_prefix
                else self._namespace_to_prefix(namespace_prefix)
            )
            try:

                def _append_row(row: Dict[str, Any]) -> None:
                    namespace, key = self._prefix_key_to_namespace(
                        row["prefix"], row["key"]
                    )
                    value = row.get("value", {})
                    if isinstance(value, str):
                        try:
                            value = json.loads(value)
                        except json.JSONDecodeError:
                            value = {"content": value}

                    # Apply filter if provided
                    if filter_dict:
                        match = all(value.get(k) == v for k, v in filter_dict.items())
                        if not match:
                            return

                    created_at = row.get("created_at")
                    updated_at = row.get("updated_at")

                    results.append(
                        SearchItem(
                            value=value,
                            key=key,
                            namespace=namespace,
                            created_at=(
                                datetime.fromisoformat(
                                    created_at.replace("Z", "+00:00")
                                )
                                if created_at
                                else datetime.now(timezone.utc)
                            ),
                            updated_at=(
                                datetime.fromisoformat(
                                    updated_at.replace("Z", "+00:00")
                                )
                                if updated_at
                                else datetime.now(timezone.utc)
                            ),
                            score=1.0,  # No semantic search, exact match
                        )
                    )

                # Root search: query all accessible scopes (session/global/customer/user)
                if prefix_pattern is None:
                    prefix_patterns: list[str] = [
                        f"workspace:session:{self.session_id}:",
                        "workspace:global:",
                    ]
                    if self.user_id:
                        prefix_patterns.append(f"workspace:user:{self.user_id}:")
                        # Forward-compat: tolerate session prefixes that include user_id.
                        prefix_patterns.append(
                            f"workspace:session:{self.user_id}:{self.session_id}:"
                        )
                    if self.customer_id:
                        prefix_patterns.append(
                            f"workspace:customer:{self.customer_id}:"
                        )

                    fetched_rows: list[Dict[str, Any]] = []
                    per_prefix_limit = min(200, max(limit + max(offset, 0), limit))

                    for base in prefix_patterns:
                        # Build query with optional content search
                        db_query = (
                            self.client.table(WORKSPACE_TABLE)
                            .select("prefix, key, value, created_at, updated_at")
                            .like("prefix", f"{base}%")
                        )
                        if query:
                            db_query = db_query.ilike("content_text", f"%{query}%")

                        response = db_query.limit(per_prefix_limit).execute()
                        fetched_rows.extend(list(response.data or []))

                    # Deterministic order across scopes (best-effort).
                    fetched_rows.sort(
                        key=lambda row: (
                            row.get("updated_at") or row.get("created_at") or ""
                        ),
                        reverse=True,
                    )

                    for row in fetched_rows:
                        _append_row(row)
                else:
                    # Build query with optional content search
                    db_query = (
                        self.client.table(WORKSPACE_TABLE)
                        .select("prefix, key, value, created_at, updated_at")
                        .like("prefix", f"{prefix_pattern}%")
                    )

                    # Add content search if query provided (uses GIN index via ILIKE)
                    if query:
                        # Note: ilike uses the GIN index on content_text column
                        db_query = db_query.ilike("content_text", f"%{query}%")

                    # Apply pagination at DB level (not client-side)
                    response = db_query.limit(limit).offset(offset).execute()

                    for row in response.data or []:
                        _append_row(row)

            except Exception as exc:
                logger.warning(
                    "workspace_store_search_error",
                    prefix=prefix_pattern,
                    error=str(exc),
                )

        # Also search local cache (for items not yet persisted)
        for ns, items in self._cache.items():
            if len(ns) >= len(namespace_prefix):
                if ns[: len(namespace_prefix)] == namespace_prefix:
                    for key, item in items.items():
                        # Apply content search filter if query provided
                        if query:
                            content = item.value.get("content", "")
                            if query.lower() not in content.lower():
                                continue

                        # Apply filter if provided
                        if filter_dict:
                            match = all(
                                item.value.get(k) == v for k, v in filter_dict.items()
                            )
                            if not match:
                                continue

                        # Skip if already in results from DB
                        if not any(r.key == key and r.namespace == ns for r in results):
                            results.append(
                                SearchItem(
                                    value=item.value,
                                    key=item.key,
                                    namespace=item.namespace,
                                    created_at=item.created_at,
                                    updated_at=item.updated_at,
                                    score=0.5,  # Cache items scored lower than DB results
                                )
                            )

        # Pagination already applied at DB level for scoped searches; only limit total results
        # (cache items are extras, so we may have slightly more than limit). Root searches
        # span multiple scopes, so apply the offset after merging.
        safe_offset = max(offset, 0)
        if namespace_prefix:
            final_results = results[:limit]
        else:
            final_results = results[safe_offset : safe_offset + limit]

        # Observability: log workspace searches with scope and result count
        path = "/".join(namespace_prefix)
        scope = self._get_scope_for_path(path)
        logger.info(
            "workspace_search",
            scope=scope.value,
            namespace=":".join(namespace_prefix),
            query=query[:50] if query else None,  # Truncate long queries
            has_filter=filter_dict is not None,
            result_count=len(final_results),
            limit=limit,
            offset=offset,
            session_id=self.session_id,
            customer_id=self.customer_id,
        )

        return final_results

    async def _execute_list_namespaces(
        self,
        match_conditions: Optional[Tuple] = None,
        max_depth: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Tuple[str, ...]]:
        """List all namespaces matching criteria.

        Queries all accessible scopes:
        - Session scope (session_id)
        - Customer scope (if customer_id is set)
        - Global scope (always accessible)
        """
        all_namespaces = set(self._cache.keys())

        # Add namespaces from Supabase for all accessible scopes
        if self.client:
            # Build list of prefix patterns to query
            prefix_patterns = [
                f"workspace:session:{self.session_id}%",  # Session scope
                "workspace:global:%",  # Global scope (always accessible)
                (
                    f"workspace:user:{self.user_id}:%" if self.user_id else None
                ),  # User scope
            ]

            # Add customer scope if customer_id is set
            if self.customer_id:
                prefix_patterns.append(f"workspace:customer:{self.customer_id}%")

            for pattern in [p for p in prefix_patterns if p]:
                try:
                    response = (
                        self.client.table(WORKSPACE_TABLE)
                        .select("prefix, key")
                        .like("prefix", pattern)
                        .execute()
                    )

                    for row in response.data or []:
                        namespace, _ = self._prefix_key_to_namespace(
                            row["prefix"], row["key"]
                        )
                        if namespace:
                            all_namespaces.add(namespace)

                except Exception as exc:
                    logger.warning(
                        "workspace_store_list_ns_error", pattern=pattern, error=str(exc)
                    )

        # Apply match conditions
        if match_conditions:
            for condition in match_conditions:
                match_type = condition.match_type
                path = condition.path

                if match_type == "prefix":
                    all_namespaces = {
                        ns
                        for ns in all_namespaces
                        if len(ns) >= len(path) and ns[: len(path)] == path
                    }
                elif match_type == "suffix":
                    all_namespaces = {
                        ns
                        for ns in all_namespaces
                        if len(ns) >= len(path) and ns[-len(path) :] == path
                    }

        # Filter by max_depth
        if max_depth is not None:
            all_namespaces = {ns for ns in all_namespaces if len(ns) <= max_depth}

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
        await self.abatch(
            [PutOp(namespace=namespace, key=key, value=value, index=index)]
        )

    def delete(self, namespace: Tuple[str, ...], key: str) -> None:
        """Delete a single item synchronously."""
        # Remove from cache
        if namespace in self._cache and key in self._cache[namespace]:
            del self._cache[namespace][key]

        # Remove from Supabase (store table: prefix, key)
        if self.client:
            prefix = self._namespace_to_prefix(namespace)
            try:
                self.client.table(WORKSPACE_TABLE).delete().eq("prefix", prefix).eq(
                    "key", key
                ).execute()
            except Exception as exc:
                logger.warning(
                    "workspace_store_delete_error",
                    prefix=prefix,
                    key=key,
                    error=str(exc),
                )

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
        results = self.batch(
            [
                SearchOp(
                    namespace_prefix=namespace_prefix,
                    query=query,
                    filter=filter,
                    limit=limit,
                    offset=offset,
                )
            ]
        )
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
        results = await self.abatch(
            [
                SearchOp(
                    namespace_prefix=namespace_prefix,
                    query=query,
                    filter=filter,
                    limit=limit,
                    offset=offset,
                )
            ]
        )
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

    # -------------------------------------------------------------------------
    # File-like convenience methods (path-based API)
    # -------------------------------------------------------------------------

    async def read_file(self, path: str) -> Optional[str]:
        """Read content from a workspace file by path.

        Args:
            path: Virtual path (e.g., "/scratch/notes.md")

        Returns:
            File content as string, or None if not found.

        Example:
            content = await store.read_file("/scratch/notes.md")
        """
        namespace, key = self._path_to_namespace_key(path)
        item = await self.aget(namespace, key)
        if item and item.value:
            return item.value.get("content", "")
        return None

    async def write_file(
        self,
        path: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Write content to a workspace file by path.

        Args:
            path: Virtual path (e.g., "/scratch/notes.md")
            content: Content to write.
            metadata: Optional metadata to store alongside content.

        Example:
            await store.write_file("/scratch/notes.md", "My notes...")
        """
        namespace, key = self._path_to_namespace_key(path)
        value = {
            "content": content,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if metadata:
            value["metadata"] = metadata
        await self.aput(namespace, key, value)

    async def append_file(
        self,
        path: str,
        content: str,
        max_size_bytes: int,
    ) -> int:
        """Append content to a workspace file with per-path locking.

        Returns the new file size in bytes.
        """
        namespace, key = self._path_to_namespace_key(path)
        lock_key = "/".join(namespace + (key,))
        lock = self._locks[lock_key]

        async with lock:
            existing = await self.read_file(path)
            new_content = (existing or "") + content

            new_size = len(new_content.encode("utf-8"))
            if new_size > max_size_bytes:
                current_size = len((existing or "").encode("utf-8"))
                raise ValueError(
                    f"Append would exceed {max_size_bytes} bytes "
                    f"(current: {current_size}, new total: {new_size}). "
                    "Archive old entries first."
                )

            await self.write_file(path, new_content)
            return new_size

    async def delete_file(self, path: str) -> None:
        """Delete a workspace file by path.

        Args:
            path: Virtual path (e.g., "/scratch/notes.md")
        """
        namespace, key = self._path_to_namespace_key(path)
        await self.adelete(namespace, key)

    async def list_files(self, path: str = "/", depth: int = 2) -> List[Dict[str, Any]]:
        """List files in a workspace directory.

        Args:
            path: Virtual directory path (e.g., "/scratch")
            depth: Maximum depth to traverse (default: 2)

        Returns:
            List of file info dicts with keys: path, key, updated_at

        Example:
            files = await store.list_files("/scratch")
        """
        normalized = path.strip("/")
        if normalized:
            namespace_prefix = tuple(normalized.split("/"))
        else:
            # Root listing: show a shallow view of all accessible scopes.
            # Implemented as a multi-scope query because empty namespace prefixes
            # cannot be routed via _namespace_to_prefix().
            return await self._list_root_files(depth=depth)

        # Search with depth limit
        items = await self.asearch(namespace_prefix, limit=100)

        results = []
        for item in items:
            # Filter by depth
            if len(item.namespace) > len(namespace_prefix) + depth:
                continue

            file_path = "/" + "/".join(item.namespace) + "/" + item.key
            results.append(
                {
                    "path": file_path,
                    "key": item.key,
                    "namespace": item.namespace,
                    "updated_at": (
                        item.updated_at.isoformat() if item.updated_at else None
                    ),
                }
            )

        return results

    async def _list_root_files(self, depth: int = 2) -> List[Dict[str, Any]]:
        """List files from the workspace root across all accessible scopes."""
        results: List[Dict[str, Any]] = []

        # Prefer Supabase for authoritative listing.
        if self.client:
            prefix_patterns: list[str] = []
            prefix_patterns.append(f"workspace:session:{self.session_id}:")
            if self.user_id:
                prefix_patterns.append(f"workspace:user:{self.user_id}:")
            prefix_patterns.append("workspace:global:")
            if self.customer_id:
                prefix_patterns.append(f"workspace:customer:{self.customer_id}:")

            for base in prefix_patterns:
                try:
                    response = (
                        self.client.table(WORKSPACE_TABLE)
                        .select("prefix, key, value, created_at, updated_at")
                        .like("prefix", f"{base}%")
                        .limit(200)
                        .execute()
                    )
                except Exception as exc:
                    logger.warning(
                        "workspace_store_root_list_error", base=base, error=str(exc)
                    )
                    continue

                for row in response.data or []:
                    namespace, key = self._prefix_key_to_namespace(
                        row["prefix"], row["key"]
                    )
                    created_at = row.get("created_at")
                    updated_at = row.get("updated_at")

                    # Filter by depth relative to root.
                    if depth is not None and len(namespace) > depth:
                        continue

                    file_path = (
                        "/" + "/".join(namespace) + "/" + key
                        if namespace
                        else "/" + key
                    )
                    results.append(
                        {
                            "path": file_path,
                            "key": key,
                            "namespace": namespace,
                            "updated_at": updated_at,
                            "created_at": created_at,
                        }
                    )

        # Include cache entries not yet persisted.
        for ns, items in self._cache.items():
            if depth is not None and len(ns) > depth:
                continue
            for key, item in items.items():
                file_path = "/" + "/".join(ns) + "/" + key if ns else "/" + key
                if any(r["path"] == file_path for r in results):
                    continue
                results.append(
                    {
                        "path": file_path,
                        "key": key,
                        "namespace": item.namespace,
                        "updated_at": (
                            item.updated_at.isoformat() if item.updated_at else None
                        ),
                        "created_at": (
                            item.created_at.isoformat() if item.created_at else None
                        ),
                    }
                )

        results.sort(key=lambda r: (r.get("path") or ""))
        return results

    # -------------------------------------------------------------------------
    # Phase 1: Per-user session registry + pruning (keep N sessions per user)
    # -------------------------------------------------------------------------

    async def register_session(self) -> None:
        """Register/update this session in the per-user session index."""
        if not self.user_id:
            return
        now = datetime.now(timezone.utc).isoformat()
        path = f"/user/sessions/{self.session_id}.json"
        try:
            existing = await self.read_file(path)
            created_at = None
            if existing:
                try:
                    parsed = json.loads(existing)
                    if isinstance(parsed, dict):
                        created_at = parsed.get("created_at")
                except Exception:
                    created_at = None
            payload: Dict[str, Any] = {
                "session_id": self.session_id,
                "user_id": self.user_id,
                "last_used_at": now,
                "created_at": created_at or now,
            }
            await self.write_file(
                path, json.dumps(payload, ensure_ascii=False, indent=2)
            )
        except Exception as exc:
            logger.warning(
                "workspace_register_session_failed",
                session_id=self.session_id,
                error=str(exc),
            )

    async def prune_user_sessions(self, *, keep: int = 10) -> None:
        """Prune session-scoped workspace data to keep only the newest N sessions per user."""
        if not self.user_id:
            return
        keep = max(1, int(keep))
        if not self.client:
            return

        entries: list[Any] = []
        try:
            page_size = 200
            offset = 0
            while True:
                batch = await self.asearch(
                    ("user", "sessions"), limit=page_size, offset=offset
                )
                if not batch:
                    break
                entries.extend(batch)
                if len(batch) < page_size:
                    break
                offset += len(batch)
        except Exception as exc:
            logger.warning("workspace_list_user_sessions_failed", error=str(exc))
            return

        parsed: list[tuple[str, str]] = []
        for item in entries or []:
            session_key = item.key
            session_id = (
                session_key[:-5] if session_key.endswith(".json") else session_key
            )
            last_used_at = None
            try:
                value = item.value or {}
                if isinstance(value, dict):
                    last_used_at = value.get("last_used_at")
            except Exception:
                last_used_at = None
            if not isinstance(last_used_at, str) or not last_used_at:
                last_used_at = (
                    item.updated_at.isoformat()
                    if getattr(item, "updated_at", None)
                    else ""
                )
            parsed.append((session_id, last_used_at))

        parsed.sort(key=lambda pair: pair[1], reverse=True)
        to_delete = parsed[keep:]
        if not to_delete:
            return

        for session_id, _ in to_delete:
            await self._delete_session_workspace(session_id=session_id)
            try:
                await self.delete_file(f"/user/sessions/{session_id}.json")
            except Exception as exc:
                logger.warning(
                    "workspace_session_index_delete_failed",
                    session_id=session_id,
                    error=str(exc),
                )

    async def _delete_session_workspace(self, *, session_id: str) -> None:
        """Delete all session-scoped workspace rows for a specific session_id."""
        if not self.client:
            return

        patterns: list[str] = []
        if self.user_id:
            patterns.append(f"workspace:session:{self.user_id}:{session_id}:")
        # Legacy pattern (pre user_id scoping)
        patterns.append(f"workspace:session:{session_id}:")

        for base in patterns:
            try:
                self.client.table(WORKSPACE_TABLE).delete().like(
                    "prefix", f"{base}%"
                ).execute()
            except Exception as exc:
                logger.warning(
                    "workspace_delete_session_failed", base=base, error=str(exc)
                )

    # -------------------------------------------------------------------------
    # Session cleanup methods
    # -------------------------------------------------------------------------

    async def cleanup_session_data(self) -> int:
        """Delete all session-scoped data for this session.

        Called after ticket resolution or session timeout.
        Only deletes SESSION scope data; CUSTOMER and GLOBAL data are preserved.

        Returns:
            Number of items deleted.
        """
        if not self.client:
            # Clear cache only
            count = sum(len(items) for items in self._cache.values())
            self._cache.clear()
            return count

        prefix_patterns = [f"workspace:session:{self.session_id}%"]
        # Forward-compat: tolerate session prefixes that include user_id.
        if self.user_id:
            prefix_patterns.append(
                f"workspace:session:{self.user_id}:{self.session_id}%"
            )

        try:
            deleted_rows = []
            for prefix_pattern in prefix_patterns:
                response = (
                    self.client.table(WORKSPACE_TABLE)
                    .delete()
                    .like("prefix", prefix_pattern)
                    .execute()
                )
                deleted_rows.extend(list(response.data or []))

            count = len(deleted_rows)

            # Also clear local cache
            self._cache.clear()

            logger.info(
                "session_cleanup",
                session_id=self.session_id,
                items_deleted=count,
            )
            return count

        except Exception as exc:
            logger.warning(
                "session_cleanup_error",
                session_id=self.session_id,
                error=str(exc),
            )
            return 0

    async def file_exists(self, path: str) -> bool:
        """Check if a workspace file exists.

        Args:
            path: Virtual path (e.g., "/scratch/notes.md")

        Returns:
            True if file exists, False otherwise.
        """
        content = await self.read_file(path)
        return content is not None
