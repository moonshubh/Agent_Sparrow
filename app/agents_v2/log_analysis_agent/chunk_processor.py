"""Multiprocessing chunking utilities for large Mailbird log files."""
from __future__ import annotations

import multiprocessing as mp
from datetime import datetime
from typing import List, Dict, Any

from .parsers import parse_log_content

DEFAULT_LINES_PER_CHUNK = 10_000  # Tune as required based on memory/CPU trade-offs


def _parse_chunk(chunk_lines: List[str]) -> Dict[str, Any]:
    """Worker helper to parse a chunk of log lines."""
    chunk_content = "\n".join(chunk_lines)
    return parse_log_content(chunk_content)


def process_log_content_multiprocessing(
    log_content: str, *, lines_per_chunk: int = DEFAULT_LINES_PER_CHUNK
) -> Dict[str, Any]:
    """Parse *log_content* using a pool of processes.

    Splits the input into *lines_per_chunk* segments, processes them in parallel,
    then aggregates the resulting parsed structures.
    """
    lines = log_content.splitlines()

    # Small files can be parsed in-process to avoid overhead.
    if len(lines) <= lines_per_chunk:
        return parse_log_content(log_content)

    chunks: List[List[str]] = [
        lines[i : i + lines_per_chunk] for i in range(0, len(lines), lines_per_chunk)
    ]

    with mp.Pool() as pool:
        partial_results: List[Dict[str, Any]] = pool.map(_parse_chunk, chunks)

    # Aggregate entries and compute combined metadata.
    all_entries: List[Dict[str, Any]] = []
    for res in partial_results:
        all_entries.extend(res["entries"])

    aggregated_metadata = {
        "total_lines_processed": sum(r["metadata"]["total_lines_processed"] for r in partial_results),
        "total_entries_parsed": sum(r["metadata"]["total_entries_parsed"] for r in partial_results),
        "parsed_at": datetime.utcnow().isoformat(),
        "parser_version": "1.1.0",
        "parser_notes": "Aggregated via multiprocessing chunk_processor",
    }

    return {"entries": all_entries, "metadata": aggregated_metadata}
