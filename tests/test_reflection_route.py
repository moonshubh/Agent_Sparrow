from app.agents_v2.reflection.node import reflection_route
from app.agents_v2.reflection.schema import ReflectionFeedback


def make_state(conf: float, retries: int = 0):
    return {
        "reflection_feedback": ReflectionFeedback(
            confidence_score=conf,
            is_sufficient=conf > 0.7,
            correction_suggestions="fix",
        ),
        "qa_retry_count": retries,
    }


def test_route_refine():
    assert reflection_route(make_state(0.6, 0)) == "refine"


def test_route_escalate():
    assert reflection_route(make_state(0.3, 0)) == "escalate"


def test_route_post_process():
    assert reflection_route(make_state(0.9, 0)) == "post_process"
