"""
Simple in-process daily + per-minute pacing for Gemini requests.
Not a global distributed limiter; intended to keep within free-tier limits
on a single worker and provide best-effort pacing with backoff.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Optional


class GeminiRateTracker:
    def __init__(self, daily_limit: int, rpm_limit: int, tpm_limit: int | None = None):
        self.daily_limit = daily_limit
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit or 0
        self._lock = threading.Lock()
        self._count_today = 0
        self._day_key = self._current_day_key()
        self._window_start = time.monotonic()
        self._calls_in_window = 0
        self._token_window_start = time.monotonic()
        self._tokens_in_window = 0

    def _current_day_key(self) -> str:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%d")

    def _reset_if_new_day(self):
        day_key = self._current_day_key()
        if day_key != self._day_key:
            self._day_key = day_key
            self._count_today = 0
            self._window_start = time.monotonic()
            self._calls_in_window = 0
            self._token_window_start = time.monotonic()
            self._tokens_in_window = 0

    def can_request(self) -> bool:
        with self._lock:
            self._reset_if_new_day()
            return self._count_today < self.daily_limit

    def record(self):
        with self._lock:
            self._reset_if_new_day()
            self._count_today += 1
            # per-minute window accounting
            now = time.monotonic()
            if now - self._window_start >= 60.0:
                self._window_start = now
                self._calls_in_window = 0
            self._calls_in_window += 1

    def record_tokens(self, n_tokens: int):
        if self.tpm_limit <= 0:
            return
        with self._lock:
            now = time.monotonic()
            if now - self._token_window_start >= 60.0:
                self._token_window_start = now
                self._tokens_in_window = 0
            self._tokens_in_window += max(0, int(n_tokens))

    def throttle(self):
        """Block until we're under RPM. Best-effort pacing (sleep)."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._window_start
            if elapsed >= 60.0:
                # start a fresh window
                self._window_start = now
                self._calls_in_window = 0
                return
            # if we're at or above rpm_limit, sleep for remainder of the minute
            if self._calls_in_window >= self.rpm_limit:
                sleep_for = 60.0 - elapsed + 0.05
            else:
                # light spacing between requests to smooth bursts
                sleep_for = 0.05
        if sleep_for > 0:
            time.sleep(sleep_for)

    def throttle_tokens(self, needed_tokens: int):
        """Block until token window allows the required tokens."""
        if self.tpm_limit <= 0:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._token_window_start
                if elapsed >= 60.0:
                    self._token_window_start = now
                    self._tokens_in_window = 0
                capacity_left = self.tpm_limit - self._tokens_in_window
                if capacity_left >= needed_tokens:
                    return
                # sleep until window resets or enough capacity accrues
                sleep_for = max(0.05, 60.0 - elapsed + 0.01)
            time.sleep(sleep_for)

    def info(self) -> dict:
        with self._lock:
            self._reset_if_new_day()
            now = time.monotonic()
            elapsed = now - self._window_start
            window_remaining = max(0.0, 60.0 - elapsed)
            token_elapsed = now - self._token_window_start
            token_window_remaining = max(0.0, 60.0 - token_elapsed)
            return {
                "day": self._day_key,
                "daily_used": self._count_today,
                "daily_limit": self.daily_limit,
                "rpm_limit": self.rpm_limit,
                "calls_in_window": self._calls_in_window,
                "window_seconds_remaining": window_remaining,
                "tpm_limit": self.tpm_limit,
                "tokens_in_window": self._tokens_in_window,
                "token_window_seconds_remaining": token_window_remaining,
                "utilization": {
                    "daily": self._count_today / max(1, self.daily_limit),
                    "rpm": self._calls_in_window / max(1, self.rpm_limit),
                    "tpm": (
                        (self._tokens_in_window / float(self.tpm_limit))
                        if self.tpm_limit > 0
                        else 0.0
                    ),
                },
            }


_tracker: Optional[GeminiRateTracker] = None
_embed_tracker: Optional[GeminiRateTracker] = None
_tracker_lock = threading.Lock()
_embed_tracker_lock = threading.Lock()


def get_tracker(daily_limit: int, rpm_limit: int) -> GeminiRateTracker:
    global _tracker
    if _tracker is None:
        with _tracker_lock:
            if _tracker is None:  # Double-check pattern
                _tracker = GeminiRateTracker(
                    daily_limit=daily_limit, rpm_limit=rpm_limit
                )
    return _tracker


def get_tracker_info(daily_limit: int, rpm_limit: int) -> dict:
    return get_tracker(daily_limit, rpm_limit).info()


def get_embed_tracker(
    daily_limit: int, rpm_limit: int, tpm_limit: int
) -> GeminiRateTracker:
    global _embed_tracker
    if _embed_tracker is None:
        with _embed_tracker_lock:
            if _embed_tracker is None:  # Double-check pattern
                _embed_tracker = GeminiRateTracker(
                    daily_limit=daily_limit, rpm_limit=rpm_limit, tpm_limit=tpm_limit
                )
    return _embed_tracker


def get_embed_tracker_info(daily_limit: int, rpm_limit: int, tpm_limit: int) -> dict:
    return get_embed_tracker(daily_limit, rpm_limit, tpm_limit).info()
