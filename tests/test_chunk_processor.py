"""Benchmark tests for multiprocessing chunk processor."""
import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from app.agents_v2.log_analysis_agent.chunk_processor import process_log_content_multiprocessing

SAMPLE_LOG = "\n".join(
    [
        "2019-05-02 20:10:28.6967|INFO|1|42|2|Logger Initialized [2.5.45.0]|"
    ]
    * 50_000
)  # 50k lines generates ~5 chunks (given 10k default)


def test_large_log_processing_benchmark(benchmark: BenchmarkFixture):
    result = benchmark(process_log_content_multiprocessing, SAMPLE_LOG)
    # Basic sanity checks
    assert result["metadata"]["total_lines_processed"] == 50_000
    assert result["metadata"]["total_entries_parsed"] == 50_000
