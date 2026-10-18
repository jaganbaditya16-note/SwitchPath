from app.engine import evaluate_compatibility


def candidate(**overrides):
    model = {
        "id": "model-b",
        "name": "Nova Lite",
        "supports_tools": True,
        "supports_structured_output": False,
        "max_context_tokens": 32000,
    }
    model.update(overrides)
    return model


def workflow():
    return {"id": "demo-workflow", "name": "Demo workflow"}


def contract(capability, minimum=0):
    return {
        "id": f"contract-{capability}",
        "name": f"{capability} contract",
        "required_capability": capability,
        "min_context_tokens": minimum,
    }


def test_structured_output_requirement_blocks_candidate():
    result = evaluate_compatibility(
        workflow(), [contract("structured_output")], candidate()
    )
    assert result["status"] == "blocked"
    assert result["failed"] == 1
    assert result["checks"][0]["status"] == "fail"


def test_tool_requirement_passes_when_candidate_supports_tools():
    result = evaluate_compatibility(workflow(), [contract("tools")], candidate())
    assert result["status"] == "ready"
    assert result["passed"] == 1
    assert result["failed"] == 0


def test_insufficient_context_blocks_candidate():
    result = evaluate_compatibility(
        workflow(), [contract("long_context", 48000)], candidate()
    )
    assert result["status"] == "blocked"
    assert "below the required" in result["checks"][0]["message"]


def test_unknown_capability_requires_review():
    result = evaluate_compatibility(
        workflow(), [contract("unimplemented_capability")], candidate()
    )
    assert result["status"] == "review"
    assert result["review"] == 1


def test_missing_contracts_do_not_get_a_false_ready_status():
    result = evaluate_compatibility(workflow(), [], candidate())
    assert result["status"] == "review"
    assert result["failed"] == 0
    assert result["review"] == 1


def test_unknown_candidate_capability_requires_review():
    result = evaluate_compatibility(
        workflow(), [contract("tools")], candidate(supports_tools=None)
    )
    assert result["status"] == "review"
