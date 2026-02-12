from app.agents.unified.agent_sparrow import _fast_classify_task


def test_outage_plaintext_not_forced_to_log_analysis() -> None:
    message = (
        "Customer reports full outage after release: email sync fails, attachments "
        "timeout, dashboard blank. Need customer response and rollback criteria."
    )
    classification = _fast_classify_task(message)
    assert classification != "log_analysis"


def test_explicit_log_context_routes_to_log_analysis() -> None:
    message = (
        "Please analyze this debug log snippet and traceback from app.log. "
        "[ERROR] 2026-02-12 12:33:00 connection timeout."
    )
    assert _fast_classify_task(message) == "log_analysis"


def test_data_retrieval_pattern_still_matches() -> None:
    message = "Query database table for duplicate charge records and retrieve stats."
    assert _fast_classify_task(message) == "data_retrieval"
