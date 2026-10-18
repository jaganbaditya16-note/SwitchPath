"""FalkorDB access for SwitchPath. All demo data is synthetic."""

import json
import os
from typing import Any

from falkordb import FalkorDB


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
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


class GraphStore:
    def __init__(self) -> None:
        host = os.getenv("FALKORDB_HOST", "127.0.0.1")
        port = int(os.getenv("FALKORDB_PORT", "6379"))
        name = os.getenv("SWITCHPATH_GRAPH", "switchpath_demo")
        self.graph_name = name
        self.client = FalkorDB(host=host, port=port)
        self.graph = self.client.select_graph(name)

    def _query(self, query: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
        if params is None:
            result = self.graph.query(query)
        else:
            result = self.graph.query(query, params)
        return result.result_set

    def ensure_seeded(self) -> None:
        rows = self._query("MATCH (n:Model) RETURN count(n) AS total")
        if not rows or int(rows[0][0]) == 0:
            self.seed_demo()

    def seed_demo(self) -> None:
        models = [
            {
                "id": "model-a",
                "name": "Atlas Text v2",
                "vendor": "Atlas AI (fictional)",
                "supports_tools": True,
                "supports_structured_output": True,
                "max_context_tokens": 64000,
                "is_active": True,
            },
            {
                "id": "model-b",
                "name": "Nova Lite",
                "vendor": "Nova Labs (fictional)",
                "supports_tools": True,
                "supports_structured_output": False,
                "max_context_tokens": 32000,
                "is_active": False,
            },
        ]
        for model in models:
            self._query(
                """
                MERGE (m:Model {id: $id})
                SET m.name = $name,
                    m.vendor = $vendor,
                    m.supports_tools = $supports_tools,
                    m.supports_structured_output = $supports_structured_output,
                    m.max_context_tokens = $max_context_tokens,
                    m.is_active = $is_active
                """,
                model,
            )

        workflows = [
            {
                "id": "customer-support",
                "name": "Customer Support Triage",
                "team": "Customer Experience",
                "criticality": "high",
                "description": "Classifies tickets and prepares tool-assisted resolutions.",
                "agent_id": "support-agent",
                "agent_name": "Support Agent",
                "agent_type": "support",
                "tools": [
                    {"id": "tool-crm", "name": "CRM Connector", "kind": "business_tool"}
                ],
                "contracts": [
                    {
                        "id": "contract-support-tools",
                        "name": "Tool-call shape",
                        "required_capability": "tools",
                        "min_context_tokens": 0,
                        "description": "The agent must produce valid tool-call requests.",
                        "evaluation_id": "eval-support-tools",
                        "evaluation_name": "Support tool-call contract",
                        "evaluation_description": "A defined check for expected tool-call behavior.",
                    }
                ],
            },
            {
                "id": "invoice-extraction",
                "name": "Invoice Extraction",
                "team": "Finance Operations",
                "criticality": "high",
                "description": "Extracts invoice fields for a downstream structured workflow.",
                "agent_id": "invoice-agent",
                "agent_name": "Invoice Agent",
                "agent_type": "document_extraction",
                "tools": [
                    {"id": "tool-invoice-parser", "name": "Document Parser", "kind": "data_tool"}
                ],
                "contracts": [
                    {
                        "id": "contract-invoice-json",
                        "name": "Invoice JSON schema",
                        "required_capability": "structured_output",
                        "min_context_tokens": 0,
                        "description": "Required invoice fields must conform to a structured contract.",
                        "evaluation_id": "eval-invoice-json",
                        "evaluation_name": "Invoice schema contract",
                        "evaluation_description": "A defined check for required invoice fields and schema compatibility.",
                    }
                ],
            },
            {
                "id": "research-assistant",
                "name": "Research Assistant",
                "team": "Product Research",
                "criticality": "medium",
                "description": "Uses search tools and a large context window to synthesize findings.",
                "agent_id": "research-agent",
                "agent_name": "Research Agent",
                "agent_type": "research",
                "tools": [
                    {"id": "tool-search", "name": "Search Connector", "kind": "retrieval_tool"}
                ],
                "contracts": [
                    {
                        "id": "contract-research-tools",
                        "name": "Research tool calls",
                        "required_capability": "tools",
                        "min_context_tokens": 0,
                        "description": "The agent must retain tool-calling capability.",
                        "evaluation_id": "eval-research-tools",
                        "evaluation_name": "Research tool-call contract",
                        "evaluation_description": "A defined check for research tool compatibility.",
                    },
                    {
                        "id": "contract-research-context",
                        "name": "Research context window",
                        "required_capability": "long_context",
                        "min_context_tokens": 48000,
                        "description": "The workflow requires at least 48,000 context tokens.",
                        "evaluation_id": "eval-research-context",
                        "evaluation_name": "Research context contract",
                        "evaluation_description": "A defined check for the required context-window capacity.",
                    },
                ],
            },
        ]

        for workflow in workflows:
            self._query(
                """
                MERGE (w:Workflow {id: $id})
                SET w.name = $name, w.team = $team,
                    w.criticality = $criticality, w.description = $description
                """,
                {
                    "id": workflow["id"],
                    "name": workflow["name"],
                    "team": workflow["team"],
                    "criticality": workflow["criticality"],
                    "description": workflow["description"],
                },
            )
            self._query(
                """
                MERGE (a:Agent {id: $agent_id})
                SET a.name = $agent_name, a.kind = $agent_type
                """,
                workflow,
            )
            self._query(
                """
                MATCH (w:Workflow {id: $workflow_id}),
                      (a:Agent {id: $agent_id}),
                      (m:Model {id: $model_id})
                MERGE (w)-[:RUNS_AGENT]->(a)
                MERGE (a)-[:USES_MODEL]->(m)
                """,
                {
                    "workflow_id": workflow["id"],
                    "agent_id": workflow["agent_id"],
                    "model_id": "model-a",
                },
            )

            for tool in workflow["tools"]:
                self._query(
                    """
                    MERGE (t:Tool {id: $id})
                    SET t.name = $name, t.kind = $kind
                    """,
                    tool,
                )
                self._query(
                    """
                    MATCH (a:Agent {id: $agent_id}), (t:Tool {id: $tool_id})
                    MERGE (a)-[:CALLS_TOOL]->(t)
                    """,
                    {"agent_id": workflow["agent_id"], "tool_id": tool["id"]},
                )

            for contract in workflow["contracts"]:
                self._query(
                    """
                    MERGE (c:Contract {id: $id})
                    SET c.name = $name,
                        c.required_capability = $required_capability,
                        c.min_context_tokens = $min_context_tokens,
                        c.description = $description
                    """,
                    contract,
                )
                self._query(
                    """
                    MERGE (e:Evaluation {id: $evaluation_id})
                    SET e.name = $evaluation_name,
                        e.kind = 'contract_definition',
                        e.status = 'defined',
                        e.description = $evaluation_description
                    """,
                    contract,
                )
                self._query(
                    """
                    MATCH (w:Workflow {id: $workflow_id}),
                          (c:Contract {id: $contract_id}),
                          (e:Evaluation {id: $evaluation_id})
                    MERGE (w)-[:REQUIRES_CONTRACT]->(c)
                    MERGE (c)-[:VERIFIED_BY]->(e)
                    """,
                    {
                        "workflow_id": workflow["id"],
                        "contract_id": contract["id"],
                        "evaluation_id": contract["evaluation_id"],
                    },
                )

    def reset_demo(self) -> None:
        # This deletes only nodes in the configured SwitchPath graph.
        self._query("MATCH (n) DETACH DELETE n")
        self.seed_demo()

    def count_nodes(self) -> int:
        rows = self._query("MATCH (n) RETURN count(n) AS total")
        return int(rows[0][0]) if rows else 0

    @staticmethod
    def _model_dict(row: list[Any]) -> dict[str, Any]:
        return {
            "id": row[0],
            "name": row[1],
            "vendor": row[2],
            "supports_tools": _as_bool(row[3]),
            "supports_structured_output": _as_bool(row[4]),
            "max_context_tokens": int(row[5]) if row[5] is not None else None,
            "is_active": _as_bool(row[6]),
        }

    def get_model(self, model_id: str) -> dict[str, Any] | None:
        rows = self._query(
            """
            MATCH (m:Model {id: $id})
            RETURN m.id, m.name, m.vendor, m.supports_tools,
                   m.supports_structured_output, m.max_context_tokens, m.is_active
            """,
            {"id": model_id},
        )
        return self._model_dict(rows[0]) if rows else None

    def list_models(self) -> list[dict[str, Any]]:
        rows = self._query(
            """
            MATCH (m:Model)
            RETURN m.id, m.name, m.vendor, m.supports_tools,
                   m.supports_structured_output, m.max_context_tokens, m.is_active
            ORDER BY m.is_active DESC, m.name
            """
        )
        return [self._model_dict(row) for row in rows]

    def count_label(self, label: str) -> int:
        # Only fixed internal labels are passed to this method.
        rows = self._query(f"MATCH (n:{label}) RETURN count(n) AS total")
        return int(rows[0][0]) if rows else 0

    def counts(self) -> dict[str, int]:
        return {
            "models": self.count_label("Model"),
            "workflows": self.count_label("Workflow"),
            "agents": self.count_label("Agent"),
            "contracts": self.count_label("Contract"),
            "migration_checks": self.count_label("MigrationCheck"),
        }

    def get_impacted_workflows(self, model_id: str) -> list[dict[str, Any]]:
        rows = self._query(
            """
            MATCH (w:Workflow)-[:RUNS_AGENT]->(a:Agent)-[:USES_MODEL]->(m:Model {id: $model_id})
            RETURN w.id, w.name, w.team, w.criticality, w.description, a.id, a.name
            ORDER BY w.name
            """,
            {"model_id": model_id},
        )
        criticality_order = {"high": 0, "medium": 1, "low": 2}
        workflows = [
            {
                "id": row[0],
                "name": row[1],
                "team": row[2],
                "criticality": row[3],
                "description": row[4],
                "agent_id": row[5],
                "agent_name": row[6],
            }
            for row in rows
        ]
        return sorted(
            workflows,
            key=lambda item: (
                criticality_order.get(str(item["criticality"]).lower(), 3),
                str(item["name"]),
            ),
        )

    def get_contracts(self, workflow_id: str) -> list[dict[str, Any]]:
        rows = self._query(
            """
            MATCH (w:Workflow {id: $workflow_id})-[:REQUIRES_CONTRACT]->(c:Contract)
            OPTIONAL MATCH (c)-[:VERIFIED_BY]->(e:Evaluation)
            RETURN c.id, c.name, c.required_capability,
                   c.min_context_tokens, c.description, e.name
            ORDER BY c.name
            """,
            {"workflow_id": workflow_id},
        )
        return [
            {
                "id": row[0],
                "name": row[1],
                "required_capability": row[2],
                "min_context_tokens": int(row[3] or 0),
                "description": row[4],
                "evaluation_name": row[5],
            }
            for row in rows
        ]

    def get_tools(self, workflow_id: str) -> list[str]:
        rows = self._query(
            """
            MATCH (w:Workflow {id: $workflow_id})-[:RUNS_AGENT]->(a:Agent)-[:CALLS_TOOL]->(t:Tool)
            RETURN DISTINCT t.name
            ORDER BY t.name
            """,
            {"workflow_id": workflow_id},
        )
        return [str(row[0]) for row in rows]

    def save_check(
        self,
        *,
        check_id: str,
        workflow: dict[str, Any],
        current_model_id: str,
        candidate_model_id: str,
        assessment: dict[str, Any],
        created_at: str,
    ) -> None:
        self._query(
            """
            MERGE (c:MigrationCheck {id: $id})
            SET c.workflow_id = $workflow_id,
                c.workflow_name = $workflow_name,
                c.current_model_id = $current_model_id,
                c.candidate_model_id = $candidate_model_id,
                c.status = $status,
                c.summary = $summary,
                c.passed = $passed,
                c.failed = $failed,
                c.review = $review,
                c.details_json = $details_json,
                c.created_at = $created_at
            """,
            {
                "id": check_id,
                "workflow_id": workflow["id"],
                "workflow_name": workflow["name"],
                "current_model_id": current_model_id,
                "candidate_model_id": candidate_model_id,
                "status": assessment["status"],
                "summary": assessment["summary"],
                "passed": assessment["passed"],
                "failed": assessment["failed"],
                "review": assessment["review"],
                "details_json": json.dumps(assessment["checks"]),
                "created_at": created_at,
            },
        )
        self._query(
            """
            MATCH (w:Workflow {id: $workflow_id}), (c:MigrationCheck {id: $check_id})
            MERGE (w)-[:HAS_MIGRATION_CHECK]->(c)
            """,
            {"workflow_id": workflow["id"], "check_id": check_id},
        )
        self._query(
            """
            MATCH (c:MigrationCheck {id: $check_id}), (m:Model {id: $candidate_model_id})
            MERGE (c)-[:TESTED_AGAINST]->(m)
            """,
            {"check_id": check_id, "candidate_model_id": candidate_model_id},
        )

    def recent_checks(self, limit: int = 6) -> list[dict[str, Any]]:
        rows = self._query(
            """
            MATCH (c:MigrationCheck)
            RETURN c.id, c.workflow_name, c.status, c.passed, c.failed,
                   c.review, c.created_at, c.candidate_model_id
            ORDER BY c.created_at DESC
            LIMIT $limit
            """,
            {"limit": limit},
        )
        return [
            {
                "id": row[0],
                "workflow_name": row[1],
                "status": row[2],
                "passed": int(row[3] or 0),
                "failed": int(row[4] or 0),
                "review": int(row[5] or 0),
                "created_at": row[6],
                "candidate_model_id": row[7],
            }
            for row in rows
        ]
