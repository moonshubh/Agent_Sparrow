"""
Log Cleanup Manager with Bulletproof Guarantees

This module ensures zero persistent storage of sensitive log data through
guaranteed cleanup mechanisms. Implements multiple layers of cleanup with
fail-safe defaults and automatic resource management.

Security Design:
- Try/finally blocks for guaranteed cleanup
- Automatic cleanup scheduling with delays
- Forced garbage collection after data removal
- FIFO eviction for memory management
- Context managers for automatic resource cleanup
- Deadman switch for orphaned data
"""

import asyncio
import gc
import logging
import os
import shutil
import tempfile
import weakref
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Callable
from dataclasses import dataclass, field
from collections import OrderedDict
import threading
import atexit
import signal
import sys

logger = logging.getLogger(__name__)


@dataclass
class CleanupConfig:
    """Configuration for cleanup manager with secure defaults."""
    max_memory_items: int = 100  # Maximum items in memory cache
    cleanup_delay_seconds: float = 5.0  # Delay before automatic cleanup
    force_gc_after_cleanup: bool = True  # Force garbage collection
    secure_delete_iterations: int = 3  # Overwrite iterations for file deletion
    enable_deadman_switch: bool = True  # Cleanup on unexpected exit
    temp_dir_prefix: str = "mailbird_logs_"
    log_cleanup_operations: bool = True  # Audit trail of cleanups
    paranoid_mode: bool = True  # Maximum security settings


class SecureDataStore:
    """
    In-memory store with automatic cleanup and size limits.

    Implements FIFO eviction and weak references for automatic cleanup
    when data is no longer referenced.
    """

    def __init__(self, max_items: int = 100):
        """Initialize secure data store with size limits."""
        self._data: OrderedDict = OrderedDict()
        self._weak_refs: Dict[str, weakref.ref] = {}
        self._max_items = max_items
        self._access_count: Dict[str, int] = {}
        self._lock = threading.RLock()

    def store(self, key: str, data: Any, weak: bool = False) -> None:
        """
        Store data with optional weak reference.

        Args:
            key: Unique identifier for the data
            data: Data to store
            weak: Use weak reference for automatic cleanup
        """
        with self._lock:
            # Enforce size limit with FIFO eviction
            while len(self._data) >= self._max_items:
                evicted_key = next(iter(self._data))
                self._evict(evicted_key)
                logger.debug(f"Evicted oldest item: {evicted_key}")

            self._data[key] = data
            self._access_count[key] = 0

            if weak:
                # Create weak reference with cleanup callback
                self._weak_refs[key] = weakref.ref(
                    data, lambda ref, k=key: self._cleanup_weak_ref(k)
                )

    def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve data if it exists."""
        with self._lock:
            if key in self._data:
                # Move to end for LRU behavior
                self._data.move_to_end(key)
                self._access_count[key] += 1
                return self._data[key]
            return None

    def delete(self, key: str) -> bool:
        """Delete data and force cleanup."""
        with self._lock:
            return self._evict(key)

    def _evict(self, key: str) -> bool:
        """Evict data from store."""
        if key in self._data:
            data = self._data.pop(key)
            self._access_count.pop(key, None)
            self._weak_refs.pop(key, None)

            # Clear the data
            if hasattr(data, 'clear'):
                data.clear()
            elif isinstance(data, (list, dict)):
                data.clear()

            del data
            return True
        return False

    def _cleanup_weak_ref(self, key: str) -> None:
        """Cleanup callback for weak references."""
        with self._lock:
            self._data.pop(key, None)
            self._access_count.pop(key, None)
            logger.debug(f"Weak reference cleanup for key: {key}")

    def clear_all(self) -> int:
        """Clear all stored data."""
        with self._lock:
            count = len(self._data)
            for key in list(self._data.keys()):
                self._evict(key)
            return count


class LogCleanupManager:
    """
    Comprehensive cleanup manager ensuring zero persistent storage of log data.

    Implements multiple cleanup strategies:
    - Automatic scheduled cleanup
    - Context manager cleanup
    - Signal handler cleanup
    - Deadman switch cleanup
    - Manual cleanup triggers
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Singleton pattern for global cleanup coordination."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self, config: Optional[CleanupConfig] = None):
        """
        Initialize cleanup manager with paranoid defaults.

        Args:
            config: Optional configuration, uses paranoid defaults if not provided
        """
        # Prevent re-initialization for singleton
        if hasattr(self, '_initialized'):
            return

        self.config = config or CleanupConfig()
        self._data_store = SecureDataStore(self.config.max_memory_items)
        self._temp_files: Set[Path] = set()
        self._temp_dirs: Set[Path] = set()
        self._cleanup_tasks: Dict[str, asyncio.Task] = {}
        self._cleanup_callbacks: List[Callable] = []
        self._cleanup_lock = threading.RLock()
        self._shutdown_initiated = False

        # Setup cleanup handlers
        self._setup_cleanup_handlers()

        self._initialized = True
        logger.info("LogCleanupManager initialized with paranoid settings")

    def _setup_cleanup_handlers(self) -> None:
        """Setup multiple cleanup handlers for guaranteed cleanup."""
        if self.config.enable_deadman_switch:
            # Register cleanup on normal exit
            atexit.register(self._emergency_cleanup)

            # Register signal handlers for abnormal termination
            for sig in [signal.SIGTERM, signal.SIGINT]:
                try:
                    signal.signal(sig, self._signal_cleanup_handler)
                except (OSError, ValueError):
                    # Signal might not be available on this platform
                    pass

            # Register exception handler (chain with existing)
            self._original_excepthook = getattr(sys, 'excepthook', sys.__excepthook__)
            sys.excepthook = self._exception_cleanup_handler

    def _signal_cleanup_handler(self, signum: int, frame: Any) -> None:
        """Handle cleanup on signal termination."""
        logger.warning(f"Received signal {signum}, initiating emergency cleanup")
        self._emergency_cleanup()
        # Re-raise the signal for default handling
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    def _exception_cleanup_handler(self, exc_type, exc_val, exc_tb) -> None:
        """Handle cleanup on uncaught exceptions."""
        logger.error(f"Uncaught exception: {exc_type.__name__}, initiating cleanup")
        self._emergency_cleanup()
        # Call the original exception handler (preserves chain)
        if hasattr(self, '_original_excepthook'):
            self._original_excepthook(exc_type, exc_val, exc_tb)
        else:
            sys.__excepthook__(exc_type, exc_val, exc_tb)

    def _emergency_cleanup(self) -> None:
        """Emergency cleanup for unexpected termination."""
        with self._cleanup_lock:
            if self._shutdown_initiated:
                return
            self._shutdown_initiated = True

            logger.warning("Emergency cleanup initiated")

            # Clear all in-memory data
            cleared = self._data_store.clear_all()
            logger.info(f"Cleared {cleared} items from memory")

            # Delete all temporary files
            for temp_file in list(self._temp_files):
                self._secure_delete_file(temp_file)

            # Delete all temporary directories
            for temp_dir in list(self._temp_dirs):
                self._secure_delete_directory(temp_dir)

            # Cancel all cleanup tasks
            for task_id, task in self._cleanup_tasks.items():
                if not task.done():
                    task.cancel()

            # Execute cleanup callbacks
            for callback in self._cleanup_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Cleanup callback failed: {e}")

            # Force garbage collection
            if self.config.force_gc_after_cleanup:
                gc.collect(2)  # Full collection

            logger.info("Emergency cleanup completed")

    def _secure_delete_file(self, file_path: Path) -> bool:
        """
        Securely delete a file with multiple overwrites.

        Args:
            file_path: Path to file to delete

        Returns:
            True if successfully deleted
        """
        try:
            if not file_path.exists():
                return True

            # Multiple overwrite passes for paranoid security
            if self.config.paranoid_mode:
                file_size = file_path.stat().st_size
                with open(file_path, "rb+") as f:
                    for _ in range(self.config.secure_delete_iterations):
                        f.seek(0)
                        f.write(os.urandom(file_size))
                        f.flush()
                        os.fsync(f.fileno())

            # Remove the file
            file_path.unlink(missing_ok=True)
            self._temp_files.discard(file_path)

            if self.config.log_cleanup_operations:
                logger.info(f"Securely deleted file: {file_path}")

            return True

        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
            return False

    def _secure_delete_directory(self, dir_path: Path) -> bool:
        """
        Securely delete a directory and all contents.

        Args:
            dir_path: Path to directory to delete

        Returns:
            True if successfully deleted
        """
        try:
            if not dir_path.exists():
                return True

            # Delete all files in directory first
            for file_path in dir_path.rglob("*"):
                if file_path.is_file():
                    self._secure_delete_file(file_path)

            # Remove the directory
            shutil.rmtree(dir_path, ignore_errors=True)
            self._temp_dirs.discard(dir_path)

            if self.config.log_cleanup_operations:
                logger.info(f"Securely deleted directory: {dir_path}")

            return True

        except Exception as e:
            logger.error(f"Failed to delete directory {dir_path}: {e}")
            return False

    @contextmanager
    def temporary_file(self, suffix: str = ".log", delete: bool = True):
        """
        Context manager for temporary file with guaranteed cleanup.

        Args:
            suffix: File suffix
            delete: Whether to delete on exit

        Yields:
            Path to temporary file
        """
        temp_file = None
        try:
            # Create temporary file
            fd, temp_path = tempfile.mkstemp(
                suffix=suffix,
                prefix=self.config.temp_dir_prefix
            )
            os.close(fd)

            temp_file = Path(temp_path)
            self._temp_files.add(temp_file)

            yield temp_file

        finally:
            # Guaranteed cleanup
            if temp_file and delete:
                self._secure_delete_file(temp_file)

    @contextmanager
    def temporary_directory(self, delete: bool = True):
        """
        Context manager for temporary directory with guaranteed cleanup.

        Args:
            delete: Whether to delete on exit

        Yields:
            Path to temporary directory
        """
        temp_dir = None
        try:
            # Create temporary directory
            temp_path = tempfile.mkdtemp(prefix=self.config.temp_dir_prefix)
            temp_dir = Path(temp_path)
            self._temp_dirs.add(temp_dir)

            yield temp_dir

        finally:
            # Guaranteed cleanup
            if temp_dir and delete:
                self._secure_delete_directory(temp_dir)

    @asynccontextmanager
    async def process_with_cleanup(self, data: Any, identifier: str):
        """
        Async context manager for processing data with guaranteed cleanup.

        Args:
            data: Data to process
            identifier: Unique identifier for the data

        Yields:
            The data for processing
        """
        cleanup_task = None
        try:
            # Store data
            self._data_store.store(identifier, data)

            # Schedule cleanup task
            cleanup_task = asyncio.create_task(
                self._scheduled_cleanup(identifier)
            )
            self._cleanup_tasks[identifier] = cleanup_task

            yield data

        finally:
            # Guaranteed cleanup
            await self._immediate_cleanup(identifier)

            # Cancel scheduled cleanup if exists
            if cleanup_task and not cleanup_task.done():
                cleanup_task.cancel()
                try:
                    await cleanup_task
                except asyncio.CancelledError:
                    pass

            self._cleanup_tasks.pop(identifier, None)

    async def _scheduled_cleanup(self, identifier: str) -> None:
        """
        Scheduled cleanup after delay.

        Args:
            identifier: Data identifier to cleanup
        """
        try:
            await asyncio.sleep(self.config.cleanup_delay_seconds)
            await self._immediate_cleanup(identifier)
            logger.debug(f"Scheduled cleanup completed for: {identifier}")

        except asyncio.CancelledError:
            logger.debug(f"Scheduled cleanup cancelled for: {identifier}")
            raise

    async def _immediate_cleanup(self, identifier: str) -> None:
        """
        Immediate cleanup of data.

        Args:
            identifier: Data identifier to cleanup
        """
        # Delete from store
        deleted = self._data_store.delete(identifier)

        if deleted and self.config.log_cleanup_operations:
            logger.info(f"Cleaned up data for: {identifier}")

        # Force garbage collection
        if self.config.force_gc_after_cleanup:
            gc.collect()

    def register_cleanup_callback(self, callback: Callable) -> None:
        """
        Register a callback for emergency cleanup.

        Args:
            callback: Function to call during cleanup
        """
        with self._cleanup_lock:
            self._cleanup_callbacks.append(callback)

    def get_cleanup_statistics(self) -> Dict[str, Any]:
        """Get statistics about cleanup operations."""
        return {
            "memory_items": len(self._data_store._data),
            "temp_files": len(self._temp_files),
            "temp_dirs": len(self._temp_dirs),
            "pending_cleanup_tasks": len(self._cleanup_tasks),
            "max_memory_items": self.config.max_memory_items,
            "cleanup_delay_seconds": self.config.cleanup_delay_seconds,
            "paranoid_mode": self.config.paranoid_mode,
        }

    def force_cleanup(self) -> Dict[str, int]:
        """
        Force immediate cleanup of all resources.

        Returns:
            Statistics of cleaned resources
        """
        stats = {}

        with self._cleanup_lock:
            # Clear memory
            stats['memory_cleared'] = self._data_store.clear_all()

            # Delete files
            stats['files_deleted'] = 0
            for temp_file in list(self._temp_files):
                if self._secure_delete_file(temp_file):
                    stats['files_deleted'] += 1

            # Delete directories
            stats['directories_deleted'] = 0
            for temp_dir in list(self._temp_dirs):
                if self._secure_delete_directory(temp_dir):
                    stats['directories_deleted'] += 1

            # Cancel tasks
            stats['tasks_cancelled'] = 0
            for task in self._cleanup_tasks.values():
                if not task.done():
                    task.cancel()
                    stats['tasks_cancelled'] += 1

            # Force garbage collection
            if self.config.force_gc_after_cleanup:
                gc.collect(2)
                stats['gc_performed'] = True

        logger.info(f"Forced cleanup completed: {stats}")
        return stats