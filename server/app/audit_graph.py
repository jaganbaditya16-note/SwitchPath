"""Persistent, evidence-linked project audits in FalkorDB."""

import json
import os
from datetime import datetime, timezone
from typing import Any

from falkordb import FalkorDB


def _graph():
    host = os.getenv("FALKORDB_HOST", "127.0.0.1")
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    name = os.getenv("SWITCHPATH_GRAPH", "switchpath_demo")
    client = FalkorDB(host=host, port=port)
    return name, client.select_graph(name)


def _query(graph: Any, query: str, params: dict | None = None) -> list[list]:
    if params is None:
        result = graph.query(query)
    else:
        result = graph.query(query, params)
    return result.result_set


def persist_audit(report: dict) -> dict:
    """Save the audit and its evidence as connected graph nodes."""
    graph_name, graph = _graph()
    audit_id = report["audit_id"]
    inventory = report.get("inventory", {})
    file_items = inventory.get("files", [])

    _query(
        graph,
        """
        MERGE (a:ProjectAudit {id: $id})
        SET a.project_name = $project_name,
            a.feature_request = $feature_request,
            a.overall_status = $status,
            a.created_at = $created_at,
            a.constraints_json = $constraints_json,
            a.limitation = $limitation,
            a.scanned_file_count = $file_count
        """,
        {
            "id": audit_id,
            "project_name": report["project_name"],
            "feature_request": report["feature_request"],
            "status": report["overall_status"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "constraints_json": json.dumps(report.get("constraints", [])),
            "limitation": report.get("limitation", ""),
            "file_count": len(file_items),
        },
    )

    graph_files = [
        {
            "id": f"{audit_id}:file:{item['path']}",
            "path": item["path"],
            "sha256": item["sha256"],
            "extension": item["extension"],
            "line_count": item["line_count"],
            "bytes": item["bytes"],
            "is_test_file": item["is_test_file"],
        }
        for item in file_items
    ]

    if graph_files:
        _query(
            graph,
            """
            UNWIND $rows AS row
            MERGE (f:ProjectFile {id: row.id})
            SET f.audit_id = $audit_id,
                f.path = row.path,
                f.sha256 = row.sha256,
                f.extension = row.extension,
                f.line_count = row.line_count,
                f.bytes = row.bytes,
                f.is_test_file = row.is_test_file
            """,
            {"audit_id": audit_id, "rows": graph_files},
        )
        _query(
            graph,
            """
            MATCH (a:ProjectAudit {id: $audit_id})
            UNWIND $rows AS row
            MATCH (f:ProjectFile {id: row.id})
            MERGE (a)-[:INSPECTED_FILE]->(f)
            """,
            {"audit_id": audit_id, "rows": graph_files},
        )

    graph_dependencies = []
    for item in report.get("dependencies", []):
        graph_dependencies.append({
            "id": f"{audit_id}:dependency:{item['name']}",
            "name": item["name"],
            "sources_json": json.dumps(item.get("sources", [])),
        })

    if graph_dependencies:
        _query(
            graph,
            """
            UNWIND $rows AS row
            MERGE (d:AuditDependency {id: row.id})
            SET d.audit_id = $audit_id,
                d.name = row.name,
                d.sources_json = row.sources_json
            """,
            {"audit_id": audit_id, "rows": graph_dependencies},
        )
        _query(
            graph,
            """
            MATCH (a:ProjectAudit {id: $audit_id})
            UNWIND $rows AS row
            MATCH (d:AuditDependency {id: row.id})
            MERGE (a)-[:DECLARES_DEPENDENCY]->(d)
            """,
            {"audit_id": audit_id, "rows": graph_dependencies},
        )

        dependency_source_links = []
        for item in report.get("dependencies", []):
            dependency_id = f"{audit_id}:dependency:{item['name']}"
            for source_path in item.get("sources", []):
                dependency_source_links.append({
                    "dependency_id": dependency_id,
                    "file_id": f"{audit_id}:file:{source_path}",
                })

        if dependency_source_links:
            _query(
                graph,
                """
                UNWIND $rows AS row
                MATCH (d:AuditDependency {id: row.dependency_id})
                MATCH (f:ProjectFile {id: row.file_id})
                MERGE (d)-[:DECLARED_IN]->(f)
                """,
                {"rows": dependency_source_links},
            )

    graph_evidence = []
    for index, item in enumerate(report.get("evidence_candidates", [])):
        path = item["path"]
        graph_evidence.append({
            "id": f"{audit_id}:evidence:{index}",
            "path": path,
            "file_id": f"{audit_id}:file:{path}",
            "sha256": item["sha256"],
            "matched_terms_json": json.dumps(item.get("matched_terms", [])),
            "matching_lines_json": json.dumps(item.get("matching_lines", [])),
            "evidence_type": item.get("evidence_type", "unknown"),
            "status": item.get("status", "candidate_evidence"),
        })

    if graph_evidence:
        _query(
            graph,
            """
            UNWIND $rows AS row
            MERGE (e:AuditEvidence {id: row.id})
            SET e.audit_id = $audit_id,
                e.path = row.path,
                e.sha256 = row.sha256,
                e.matched_terms_json = row.matched_terms_json,
                e.matching_lines_json = row.matching_lines_json,
                e.evidence_type = row.evidence_type,
                e.status = row.status
            """,
            {"audit_id": audit_id, "rows": graph_evidence},
        )
        _query(
            graph,
            """
            MATCH (a:ProjectAudit {id: $audit_id})
            UNWIND $rows AS row
            MATCH (e:AuditEvidence {id: row.id})
            MERGE (a)-[:HAS_EVIDENCE]->(e)
            WITH row, e
            MATCH (f:ProjectFile {id: row.file_id})
            MERGE (e)-[:POINTS_TO]->(f)
            """,
            {"audit_id": audit_id, "rows": graph_evidence},
        )

    graph_findings = [
        {
            "id": f"{audit_id}:finding:{item['id']}",
            "finding_id": item["id"],
            "status": item["status"],
            "message": item["message"],
        }
        for item in report.get("findings", [])
    ]

    if graph_findings:
        _query(
            graph,
            """
            UNWIND $rows AS row
            MERGE (f:AuditFinding {id: row.id})
            SET f.audit_id = $audit_id,
                f.finding_id = row.finding_id,
                f.status = row.status,
                f.message = row.message
            """,
            {"audit_id": audit_id, "rows": graph_findings},
        )
        _query(
            graph,
            """
            MATCH (a:ProjectAudit {id: $audit_id})
            UNWIND $rows AS row
            MATCH (f:AuditFinding {id: row.id})
            MERGE (a)-[:HAS_FINDING]->(f)
            """,
            {"audit_id": audit_id, "rows": graph_findings},
        )

    file_paths = [
        item["path"] for item in file_items
    ]
    test_paths = [
        item["path"] for item in file_items if item["is_test_file"]
    ]
    manifest_paths = inventory.get("manifests", [])

    finding_file_links = []
    finding_evidence_links = []
    finding_dependency_links = []

    for finding in report.get("findings", []):
        finding_id = f"{audit_id}:finding:{finding['id']}"

        paths = []
        if finding["id"] == "inventory":
            paths = file_paths
        elif finding["id"] == "tests":
            paths = test_paths
        elif finding["id"] in {"build", "dependencies"}:
            paths = manifest_paths

        for path in paths:
            finding_file_links.append({
                "finding_id": finding_id,
                "file_id": f"{audit_id}:file:{path}",
            })

        if finding["id"] == "feature_trace":
            for index, item in enumerate(
                report.get("evidence_candidates", [])[:40]
            ):
                finding_evidence_links.append({
                    "finding_id": finding_id,
                    "evidence_id": f"{audit_id}:evidence:{index}",
                })

        if finding["id"] == "dependencies":
            for item in report.get("dependencies", []):
                finding_dependency_links.append({
                    "finding_id": finding_id,
                    "dependency_id": (
                        f"{audit_id}:dependency:{item['name']}"
                    ),
                })

    if finding_file_links:
        _query(
            graph,
            """
            UNWIND $rows AS row
            MATCH (f:AuditFinding {id: row.finding_id})
            MATCH (p:ProjectFile {id: row.file_id})
            MERGE (f)-[:REFERENCES_FILE]->(p)
            """,
            {"rows": finding_file_links},
        )

    if finding_evidence_links:
        _query(
            graph,
            """
            UNWIND $rows AS row
            MATCH (f:AuditFinding {id: row.finding_id})
            MATCH (e:AuditEvidence {id: row.evidence_id})
            MERGE (f)-[:CANDIDATE_EVIDENCE]->(e)
            """,
            {"rows": finding_evidence_links},
        )

    if finding_dependency_links:
        _query(
            graph,
            """
            UNWIND $rows AS row
            MATCH (f:AuditFinding {id: row.finding_id})
            MATCH (d:AuditDependency {id: row.dependency_id})
            MERGE (f)-[:LISTS_DEPENDENCY]->(d)
            """,
            {"rows": finding_dependency_links},
        )

    return {
        "graph": graph_name,
        "audit_id": audit_id,
        "files": len(graph_files),
        "dependencies": len(graph_dependencies),
        "evidence": len(graph_evidence),
        "findings": len(graph_findings),
    }


def load_audit(audit_id: str) -> dict | None:
    """Read an audit report back from the persistent graph."""
    graph_name, graph = _graph()

    rows = _query(
        graph,
        """
        MATCH (a:ProjectAudit {id: $id})
        RETURN a.id, a.project_name, a.feature_request,
               a.overall_status, a.created_at, a.constraints_json,
               a.limitation, a.scanned_file_count
        """,
        {"id": audit_id},
    )
    if not rows:
        return None

    row = rows[0]
    file_rows = _query(
        graph,
        """
        MATCH (a:ProjectAudit {id: $id})-[:INSPECTED_FILE]->(f:ProjectFile)
        RETURN f.path, f.sha256, f.extension, f.line_count, f.bytes,
               f.is_test_file
        ORDER BY f.path
        """,
        {"id": audit_id},
    )
    dependency_rows = _query(
        graph,
        """
        MATCH (a:ProjectAudit {id: $id})-[:DECLARES_DEPENDENCY]->(d:AuditDependency)
        RETURN d.name, d.sources_json
        ORDER BY d.name
        """,
        {"id": audit_id},
    )
    evidence_rows = _query(
        graph,
        """
        MATCH (a:ProjectAudit {id: $id})-[:HAS_EVIDENCE]->(e:AuditEvidence)
        RETURN e.path, e.sha256, e.matched_terms_json,
               e.matching_lines_json, e.evidence_type, e.status
        ORDER BY e.path
        """,
        {"id": audit_id},
    )
    finding_rows = _query(
        graph,
        """
        MATCH (a:ProjectAudit {id: $id})-[:HAS_FINDING]->(f:AuditFinding)
        RETURN f.finding_id, f.status, f.message
        ORDER BY f.finding_id
        """,
        {"id": audit_id},
    )

    return {
        "audit_id": row[0],
        "project_name": row[1],
        "feature_request": row[2],
        "overall_status": row[3],
        "created_at": row[4],
        "constraints": json.loads(row[5] or "[]"),
        "limitation": row[6],
        "graph": graph_name,
        "inventory": {
            "file_count": len(file_rows),
            "files": [
                {
                    "path": item[0], "sha256": item[1],
                    "extension": item[2], "line_count": item[3],
                    "bytes": item[4], "is_test_file": item[5],
                }
                for item in file_rows
            ],
        },
        "dependencies": [
            {"name": item[0], "sources": json.loads(item[1] or "[]")}
            for item in dependency_rows
        ],
        "evidence_candidates": [
            {
                "path": item[0],
                "sha256": item[1],
                "matched_terms": json.loads(item[2] or "[]"),
                "matching_lines": json.loads(item[3] or "[]"),
                "evidence_type": item[4],
                "status": item[5],
            }
            for item in evidence_rows
        ],
        "findings": [
            {"id": item[0], "status": item[1], "message": item[2]}
            for item in finding_rows
        ],
    }

def load_audit_trace(audit_id: str) -> dict | None:
    """Return source-evidence and dependency paths traversed in FalkorDB."""
    graph_name, graph = _graph()

    audit_rows = _query(
        graph,
        "MATCH (a:ProjectAudit {id: $id}) RETURN a.id",
        {"id": audit_id},
    )
    if not audit_rows:
        return None

    evidence_rows = _query(
        graph,
        """
        MATCH (a:ProjectAudit {id: $id})-[:HAS_FINDING]->(f:AuditFinding)
              -[:CANDIDATE_EVIDENCE]->(e:AuditEvidence)
              -[:POINTS_TO]->(p:ProjectFile)
        RETURN f.finding_id, f.status, e.path,
               e.matched_terms_json, e.matching_lines_json, p.sha256
        ORDER BY f.finding_id, e.path
        """,
        {"id": audit_id},
    )

    dependency_rows = _query(
        graph,
        """
        MATCH (a:ProjectAudit {id: $id})-[:HAS_FINDING]->(f:AuditFinding)
              -[:LISTS_DEPENDENCY]->(d:AuditDependency)
              -[:DECLARED_IN]->(p:ProjectFile)
        RETURN f.finding_id, d.name, p.path, p.sha256
        ORDER BY d.name, p.path
        """,
        {"id": audit_id},
    )

    return {
        "audit_id": audit_id,
        "graph": graph_name,
        "evidence_paths": [
            {
                "finding_id": row[0],
                "finding_status": row[1],
                "source_path": row[2],
                "matched_terms": json.loads(row[3] or "[]"),
                "matching_lines": json.loads(row[4] or "[]"),
                "sha256": row[5],
                "status": "candidate_evidence",
            }
            for row in evidence_rows
        ],
        "dependency_paths": [
            {
                "finding_id": row[0],
                "dependency": row[1],
                "declared_in": row[2],
                "sha256": row[3],
            }
            for row in dependency_rows
        ],
    }
