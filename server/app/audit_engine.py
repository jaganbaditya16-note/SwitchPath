"""Local, read-only project inventory and evidence matching for SwitchPath."""

from __future__ import annotations

import hashlib
import json
import math
import re
import tomllib
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

MAX_FILES = 500
MAX_FILE_BYTES = 200_000
MAX_TOTAL_BYTES = 3_000_000

SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".next", "dist", "build",
    ".idea", ".vscode", "vendor", "backups", "backup",
}

TEXT_EXTENSIONS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf",
    ".md", ".txt", ".html", ".css", ".scss", ".sql", ".sh",
    ".ps1", ".bat", ".xml", ".gradle", ".properties", ".go",
    ".rs", ".java", ".kt", ".cs", ".php", ".rb", ".swift",
    ".dockerfile", ".lock",
}

STOP_WORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this",
    "are", "was", "were", "will", "would", "could", "should",
    "can", "have", "has", "had", "not", "but", "use", "using",
    "used", "make", "made", "build", "create", "add", "implement",
    "feature", "project", "code", "system", "application", "app",
    "please", "want", "need", "show", "tell", "check", "review",
    "all", "any", "what", "when", "where", "which", "who", "how",
    "its", "their", "they", "them", "our", "you", "your", "into",
    "support", "supports", "without", "possible", "possibility",
    "possibilities", "impossible", "unknown", "requirements",
}

TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{2,}")


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_PATTERN.findall(text)
        if token.lower() not in STOP_WORDS
    }


def _skip_file(path: Path) -> bool:
    name = path.name.lower()
    if any(part.lower() in SKIP_DIRS for part in path.parts):
        return True
    if name == ".env" or name.startswith(".env."):
        return True
    if any(term in name for term in ("secret", "credential", "private_key")):
        return True
    if path.suffix.lower() in {".pem", ".p12", ".pfx", ".key", ".der"}:
        return True
    if path.suffix.lower() not in TEXT_EXTENSIONS and name != "dockerfile":
        return True
    return False


def _dependency_name(line: str) -> str | None:
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", line)
    if not match:
        return None
    name = match.group(1)
    if name.startswith("#"):
        return None
    return name


def _collect_manifest_data(
    relative_path: str,
    content: str,
    dependencies: dict[str, set[str]],
    build_scripts: list[str],
    manifest_names: set[str],
) -> None:
    name = Path(relative_path).name.lower()
    supported_manifests = {
        "package.json", "requirements.txt", "pyproject.toml",
        "cargo.toml", "go.mod", "pom.xml", "build.gradle",
    }
    if name not in supported_manifests:
        return
    manifest_names.add(relative_path)

    if name == "package.json":
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return

        for section in ("dependencies", "devDependencies", "optionalDependencies"):
            values = data.get(section, {})
            if isinstance(values, dict):
                for package in values:
                    dependencies.setdefault(str(package), set()).add(relative_path)

        scripts = data.get("scripts", {})
        if isinstance(scripts, dict):
            for script_name, command in scripts.items():
                if script_name.lower() in {"build", "test", "lint", "typecheck", "check"}:
                    build_scripts.append(
                        f"{relative_path}: {script_name} = {command}"
                    )

    elif name == "requirements.txt":
        for line in content.splitlines():
            package = _dependency_name(line)
            if package:
                dependencies.setdefault(package, set()).add(relative_path)

    elif name == "pyproject.toml":
        try:
            data = tomllib.loads(content)
        except (tomllib.TOMLDecodeError, ValueError):
            return

        project = data.get("project", {})
        values = project.get("dependencies", [])
        if isinstance(values, list):
            for value in values:
                package = _dependency_name(str(value))
                if package:
                    dependencies.setdefault(package, set()).add(relative_path)

        scripts = data.get("tool", {}).get("pytest", {})
        if scripts:
            build_scripts.append(f"{relative_path}: pytest configuration detected")

    elif name in {"cargo.toml", "go.mod", "pom.xml", "build.gradle"}:
        build_scripts.append(f"{relative_path}: build/dependency manifest detected")


def scan_project(
    project_path: str,
    feature_request: str,
    constraints: list[str] | None = None,
) -> dict[str, Any]:
    """Inventory a local project and return source-linked evidence candidates.

    This function never executes project code and never writes into the
    scanned directory. Matches are leads for review, not proof of feasibility.
    """
    root = Path(project_path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Project path must point to an existing directory.")

    if not feature_request or not feature_request.strip():
        raise ValueError("A non-empty feature request is required.")

    request = feature_request.strip()
    clean_constraints = [
        str(item).strip() for item in (constraints or []) if str(item).strip()
    ][:20]
    # Constraints are assessed separately; they must not inflate feature matches.
    query_terms = _tokens(request)

    files: list[dict[str, Any]] = []
    dependencies: dict[str, set[str]] = {}
    build_scripts: list[str] = []
    manifests: set[str] = set()
    extensions: Counter[str] = Counter()
    total_bytes = 0
    skipped_large_files = 0
    test_files: list[str] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or _skip_file(path):
            continue
        if len(files) >= MAX_FILES:
            break

        try:
            size = path.stat().st_size
        except OSError:
            continue

        if size > MAX_FILE_BYTES or total_bytes + size > MAX_TOTAL_BYTES:
            skipped_large_files += 1
            continue

        try:
            raw = path.read_bytes()
            content = raw.decode("utf-8", errors="replace")
        except OSError:
            continue

        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(raw).hexdigest()
        suffix = path.suffix.lower() or ("dockerfile" if path.name.lower() == "dockerfile" else "[none]")
        total_bytes += len(raw)
        extensions[suffix] += 1

        lower_path = relative.lower()
        is_test = (
            "/tests/" in f"/{lower_path}/"
            or "/test/" in f"/{lower_path}/"
            or Path(relative).name.lower().startswith("test_")
            or ".test." in lower_path
            or ".spec." in lower_path
        )
        if is_test:
            test_files.append(relative)

        _collect_manifest_data(
            relative, content, dependencies, build_scripts, manifests
        )

        content_terms = _tokens(content)
        path_terms = _tokens(relative)
        matched_terms = sorted(query_terms & (content_terms | path_terms))
        matching_lines: list[int] = []

        for line_number, line in enumerate(content.splitlines(), start=1):
            line_terms = _tokens(line)
            if query_terms & line_terms:
                matching_lines.append(line_number)
                if len(matching_lines) >= 8:
                    break

        files.append({
            "path": relative,
            "extension": suffix,
            "bytes": len(raw),
            "line_count": len(content.splitlines()),
            "sha256": digest,
            "is_test_file": is_test,
            "matched_terms": matched_terms,
            "matching_lines": matching_lines,
        })

    # Rank candidate evidence using term specificity across inventoried files.
    # This is a relevance heuristic, not a probability or proof of support.
    term_document_frequency = Counter(
        term
        for item in files
        for term in set(item["matched_terms"])
    )
    document_count = max(len(files), 1)
    manifest_intent_terms = {
        "package", "packages", "dependency", "dependencies",
        "manifest", "declared", "declaration", "declarations",
    }
    manifest_intent = bool(query_terms & manifest_intent_terms)

    def _relevance_score(item: dict[str, Any]) -> float:
        score = sum(
            math.log(
                (document_count + 1)
                / (term_document_frequency[term] + 1)
            ) + 1
            for term in set(item["matched_terms"])
        )
        # Recognized manifests are especially relevant to dependency requests.
        manifest_bonus = (
            25.0
            if manifest_intent and item["path"] in manifests
            else 0.0
        )
        return round(score + manifest_bonus, 3)

    evidence = [
        {
            "path": item["path"],
            "sha256": item["sha256"],
            "matched_terms": item["matched_terms"],
            "matching_lines": item["matching_lines"],
            "relevance_score": _relevance_score(item),
            "relevance_basis": (
                "Recognized dependency manifest for a package/dependency request; "
                "heuristic, not proof."
                if manifest_intent and item["path"] in manifests
                else "Term-specificity keyword heuristic; not confidence or proof."
            ),
            "evidence_type": (
                "manifest_dependency_declaration"
                if manifest_intent and item["path"] in manifests
                else "keyword_match"
            ),
            "status": "candidate_evidence",
        }
        for item in files
        if item["matched_terms"]
        or (manifest_intent and item["path"] in manifests)
    ]
    evidence.sort(
        key=lambda item: (
            -item["relevance_score"],
            -len(item["matched_terms"]),
            -len(item["matching_lines"]),
            item["path"].lower(),
        )
    )

    dependency_list = [
        {
            "name": name,
            "sources": sorted(sources),
        }
        for name, sources in sorted(
            dependencies.items(), key=lambda pair: pair[0].lower()
        )
    ]

    constraint_checks: list[dict[str, str]] = []
    for constraint in clean_constraints:
        normalized = re.sub(r"[^a-z0-9]+", " ", constraint.lower()).strip()

        cost_required = any(
            phrase in normalized
            for phrase in (
                "zero cost", "no paid", "no subscription", "no spending",
                "free prototype", "free service", "free services",
            )
        )
        no_execution = any(
            phrase in normalized
            for phrase in (
                "do not execute", "dont execute", "never execute",
                "no code execution", "without executing", "without running",
            )
        )
        read_only = any(
            phrase in normalized
            for phrase in (
                "read only", "read project files only", "no writes",
                "do not modify", "without modifying",
            )
        )

        # Static inventory cannot prove that an entire project has no costs.
        if cost_required:
            status = "unknown"
            basis = (
                "A static file inventory cannot prove total running costs "
                "or the absence of all paid services."
            )
        elif no_execution and read_only:
            status = "verified"
            basis = (
                "This scan reads a bounded set of project files, does not "
                "execute inspected project code, and does not write into "
                "the inspected project directory."
            )
        elif no_execution:
            status = "verified"
            basis = (
                "This scanner does not execute inspected project code."
            )
        elif read_only:
            status = "verified"
            basis = (
                "This scanner reads project files without writing into "
                "the inspected project directory."
            )
        else:
            status = "unknown"
            basis = (
                "No specific deterministic check is implemented for this "
                "constraint; manual verification is still required."
            )

        constraint_checks.append({
            "constraint": constraint,
            "status": status,
            "basis": basis,
        })

    findings = [
        {
            "id": "inventory",
            "status": "observed" if files else "unknown",
            "message": f"Inventoried {len(files)} readable project files.",
        },
        {
            "id": "tests",
            "status": "observed" if test_files else "unknown",
            "message": (
                f"Found {len(test_files)} file(s) with test-like names or paths."
                if test_files
                else "No recognizable test files were found; this does not prove tests are absent."
            ),
        },
        {
            "id": "build",
            "status": "observed" if build_scripts else "unknown",
            "message": (
                f"Found {len(build_scripts)} build/check script or manifest signal(s)."
                if build_scripts
                else "No recognized build/check signal was found in the inspected manifests."
            ),
        },
        {
            "id": "dependencies",
            "status": "observed" if dependency_list else "unknown",
            "message": (
                f"Collected {len(dependency_list)} declared package dependencies."
                if dependency_list
                else "No supported dependency manifest yielded dependencies."
            ),
        },
        {
            "id": "feature_trace",
            "status": "candidate_evidence" if evidence else "unknown",
            "message": (
                f"Found {len(evidence)} file(s) with request/constraint keyword matches. "
                "Review the exact paths and lines before treating a match as evidence."
                if evidence
                else "No keyword-linked file evidence was found. Semantic support is unknown."
            ),
        },
    ]

    return {
        "audit_id": uuid.uuid4().hex,
        "project_name": root.name,
        "feature_request": request,
        "constraints": clean_constraints,
        "scope": {
            "read_only": True,
            "executed_project_code": False,
            "scanned_file_count": len(files),
            "total_bytes_read": total_bytes,
            "oversized_files_skipped": skipped_large_files,
            "max_files": MAX_FILES,
            "max_file_bytes": MAX_FILE_BYTES,
        },
        "inventory": {
            "files": files,
            "extension_counts": dict(sorted(extensions.items())),
            "test_files": test_files,
            "manifests": sorted(manifests),
        },
        "build_signals": sorted(set(build_scripts)),
        "dependencies": dependency_list,
        "constraint_checks": constraint_checks,
        "evidence_candidates": evidence[:40],
        "findings": findings,
        "overall_status": "review",
        "limitation": (
            "Preliminary static inventory only. Keyword overlap is not proof of support. "
            "This version does not execute tests, infer all project semantics, or prove "
            "that a feature is universally possible or impossible."
        ),
    }
