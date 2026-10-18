"""Deterministic migration preflight checks for synthetic demo data."""

from typing import Any


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _check_capability(
    capability: str,
    minimum: int,
    candidate: dict[str, Any],
) -> tuple[bool | None, str]:
    if capability == "tools":
        supported = _optional_bool(candidate.get("supports_tools"))
        if supported is True:
            return True, "Candidate declares tool-calling support."
        if supported is False:
            return False, "Candidate does not support required tool calling."
        return None, "Tool-calling support is unknown; verify before switching."

    if capability == "structured_output":
        supported = _optional_bool(candidate.get("supports_structured_output"))
        if supported is True:
            return True, "Candidate declares structured-output support."
        if supported is False:
            return False, "Candidate does not support required structured output."
        return None, "Structured-output support is unknown; verify before switching."

    if capability == "long_context":
        raw_limit = candidate.get("max_context_tokens")
        if raw_limit is None:
            return None, "Candidate context limit is unknown."
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return None, "Candidate context limit is invalid or unknown."
        if limit >= minimum:
            return True, f"Context limit {limit:,} meets the required {minimum:,} tokens."
        return False, f"Context limit {limit:,} is below the required {minimum:,} tokens."

    if capability == "text":
        return True, "Text output is assumed by this demo contract."

    return None, f"Capability '{capability}' has no evaluation rule yet."


def evaluate_compatibility(
    workflow: dict[str, Any],
    contracts: list[dict[str, Any]],
    candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    """Check declared capabilities, not live model quality."""
    workflow_name = str(workflow.get("name", "Unnamed workflow"))

    if candidate is None:
        return {
            "status": "review",
            "summary": "Candidate model details are unavailable.",
            "passed": 0,
            "failed": 0,
            "review": 1,
            "checks": [{
                "contract_id": None,
                "contract_name": "Candidate availability",
                "capability": "candidate",
                "status": "review",
                "message": "Load candidate metadata before assessing compatibility.",
            }],
        }

    if not contracts:
        return {
            "status": "review",
            "summary": f"{workflow_name} has no declared compatibility contracts.",
            "passed": 0,
            "failed": 0,
            "review": 1,
            "checks": [{
                "contract_id": None,
                "contract_name": "Contract completeness",
                "capability": "unknown",
                "status": "review",
                "message": "Declare requirements and tests before marking this workflow ready.",
            }],
        }

    checks = []
    for contract in contracts:
        capability = str(contract.get("required_capability", "unknown"))
        minimum = int(contract.get("min_context_tokens") or 0)
        passed, message = _check_capability(capability, minimum, candidate)
        status = "pass" if passed is True else "fail" if passed is False else "review"

        checks.append({
            "contract_id": contract.get("id"),
            "contract_name": contract.get("name", capability),
            "capability": capability,
            "status": status,
            "message": message,
        })

    passed_count = sum(item["status"] == "pass" for item in checks)
    failed_count = sum(item["status"] == "fail" for item in checks)
    review_count = sum(item["status"] == "review" for item in checks)

    if failed_count:
        overall = "blocked"
        summary = f"{failed_count} requirement(s) failed; migration is blocked."
    elif review_count:
        overall = "review"
        summary = f"{review_count} requirement(s) need evidence or human review."
    else:
        overall = "ready"
        summary = "All declared capability preflight checks passed."

    return {
        "status": overall,
        "summary": summary,
        "passed": passed_count,
        "failed": failed_count,
        "review": review_count,
        "checks": checks,
    }
