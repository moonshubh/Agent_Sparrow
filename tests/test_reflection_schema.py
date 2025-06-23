from app.agents_v2.reflection.schema import ReflectionFeedback


def test_schema_validation():
    data = {
        "confidence_score": 0.5,
        "is_sufficient": False,
        "correction_suggestions": "Add steps for IMAP setup.",
        "reasoning": "Answer missed key configuration instructions.",
    }
    obj = ReflectionFeedback.model_validate(data)
    assert obj.confidence_score == 0.5
    assert not obj.is_sufficient
