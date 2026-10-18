"""SwitchPath: graph-backed AI workflow migration preflight."""

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.engine import evaluate_compatibility
from app.graph_store import GraphStore

app = FastAPI(
    title="SwitchPath API",
    description="Graph-backed AI workflow migration readiness using synthetic demo data.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class MigrationRequest(BaseModel):
    current_model_id: str = "model-a"
    candidate_model_id: str = "model-b"


def get_ready_store() -> GraphStore:
    try:
        store = GraphStore()
        store.ensure_seeded()
        return store
    except Exception as exc:
        # Avoid exposing connection strings or internal details in API responses.
        raise HTTPException(
            status_code=503,
            detail=(
                "FalkorDB is unavailable. Start it from the project root with "
                "'docker compose up -d falkordb', then refresh this page."
            ),
        ) from exc


def build_impact(
    store: GraphStore,
    current_model_id: str,
    candidate_model_id: str,
) -> dict[str, Any]:
    if current_model_id == candidate_model_id:
        raise HTTPException(status_code=400, detail="Choose two different models.")

    current_model = store.get_model(current_model_id)
    candidate_model = store.get_model(candidate_model_id)
    if current_model is None:
        raise HTTPException(status_code=404, detail="Current model was not found in the graph.")
    if candidate_model is None:
        raise HTTPException(status_code=404, detail="Candidate model was not found in the graph.")

    impacted = store.get_impacted_workflows(current_model_id)
    workflows: list[dict[str, Any]] = []

    for workflow in impacted:
        contracts = store.get_contracts(workflow["id"])
        tools = store.get_tools(workflow["id"])
        assessment = evaluate_compatibility(workflow, contracts, candidate_model)
        workflows.append({
            **workflow,
            "tools": tools,
            "contracts": contracts,
            "path": [workflow["name"], workflow["agent_name"], current_model["name"]],
            "assessment": assessment,
        })

    summary = {
        "total": len(workflows),
        "ready": sum(item["assessment"]["status"] == "ready" for item in workflows),
        "blocked": sum(item["assessment"]["status"] == "blocked" for item in workflows),
        "review": sum(item["assessment"]["status"] == "review" for item in workflows),
    }

    if summary["blocked"] or summary["review"]:
        recommendation = (
            "Do not switch all workflows yet. Resolve blocked requirements and review unknowns, "
            "then run representative candidate-model evaluations before production use."
        )
    else:
        recommendation = (
            "All declared capability preflight checks passed. Run output-quality and end-to-end "
            "staging evaluations before approving a production switch."
        )

    return {
        "current_model": current_model,
        "candidate_model": candidate_model,
        "workflows": workflows,
        "summary": summary,
        "recommendation": recommendation,
        "saved": False,
        "assessment_scope": "Synthetic capability metadata only; not a live model-quality evaluation.",
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    store = get_ready_store()
    return {
        "ok": True,
        "database": "connected",
        "graph": store.graph_name,
        "node_count": store.count_nodes(),
    }


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    store = get_ready_store()
    return {
        "models": store.list_models(),
        "counts": store.counts(),
        "recent_checks": store.recent_checks(),
    }


@app.get("/api/impact")
def impact(
    current_model_id: str = Query(default="model-a"),
    candidate_model_id: str = Query(default="model-b"),
) -> dict[str, Any]:
    store = get_ready_store()
    return build_impact(store, current_model_id, candidate_model_id)


@app.post("/api/migrations/run-checks")
def run_checks(request: MigrationRequest) -> dict[str, Any]:
    store = get_ready_store()
    result = build_impact(store, request.current_model_id, request.candidate_model_id)
    created_at = datetime.now(timezone.utc).isoformat()

    for workflow in result["workflows"]:
        check_id = (
            f"{request.current_model_id}--{request.candidate_model_id}--{workflow['id']}"
        )
        store.save_check(
            check_id=check_id,
            workflow=workflow,
            current_model_id=request.current_model_id,
            candidate_model_id=request.candidate_model_id,
            assessment=workflow["assessment"],
            created_at=created_at,
        )

    result["saved"] = True
    result["saved_check_count"] = len(result["workflows"])
    return result


@app.post("/api/demo/reset")
def reset_demo() -> dict[str, Any]:
    store = get_ready_store()
    try:
        store.reset_demo()
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not reset the synthetic demo graph.") from exc
    return {
        "ok": True,
        "message": "Synthetic SwitchPath graph reset.",
        "counts": store.counts(),
    }

# ---------- Evidence-backed project audits ----------

from pydantic import Field
from app.audit_engine import scan_project
from app.audit_graph import persist_audit, load_audit, load_audit_trace


class ProjectAuditRequest(BaseModel):
    project_path: str
    feature_request: str
    constraints: list[str] = Field(default_factory=list, max_length=20)


@app.post("/api/audits/scan")
def create_project_audit(request: ProjectAuditRequest) -> dict[str, Any]:
    """Perform a bounded read-only scan and store its evidence graph."""
    try:
        report = scan_project(
            request.project_path,
            request.feature_request,
            request.constraints,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Could not scan the selected project directory.",
        ) from exc

    try:
        stored = persist_audit(report)
    except Exception as exc:
        # Avoid exposing graph connection details in the HTTP response.
        raise HTTPException(
            status_code=503,
            detail="The local audit graph could not persist this report.",
        ) from exc

    return {
        "audit_id": report["audit_id"],
        "project_name": report["project_name"],
        "feature_request": report["feature_request"],
        "constraints": report["constraints"],
        "constraint_checks": report["constraint_checks"],
        "overall_status": report["overall_status"],
        "scope": report["scope"],
        "inventory": {
            "file_count": len(report["inventory"]["files"]),
            "extension_counts": report["inventory"]["extension_counts"],
            "test_files": report["inventory"]["test_files"],
            "manifests": report["inventory"]["manifests"],
        },
        "build_signals": report["build_signals"],
        "dependencies": report["dependencies"],
        "evidence_candidates": report["evidence_candidates"],
        "findings": report["findings"],
        "graph_persistence": stored,
        "limitation": report["limitation"],
    }


@app.get("/api/audits/{audit_id}")
def read_project_audit(audit_id: str) -> dict[str, Any]:
    """Load a prior audit and its connected evidence from FalkorDB."""
    try:
        report = load_audit(audit_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="The audit graph could not be queried.",
        ) from exc

    if report is None:
        raise HTTPException(status_code=404, detail="Audit was not found.")

    return report


@app.get("/api/audits/{audit_id}/trace")
def trace_project_audit(audit_id: str) -> dict[str, Any]:
    """Return evidence and dependency paths obtained through graph queries."""
    try:
        result = load_audit_trace(audit_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="The audit graph trace could not be queried.",
        ) from exc

    if result is None:
        raise HTTPException(status_code=404, detail="Audit was not found.")

    return result
