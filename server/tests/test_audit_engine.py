import json
from pathlib import Path

import pytest

from app.audit_engine import scan_project


def test_missing_project_path_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="existing directory"):
        scan_project(str(tmp_path / "missing"), "Add an evidence report")


def test_empty_feature_request_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="feature request"):
        scan_project(str(tmp_path), "  ")


def test_scanner_finds_request_terms_and_line_numbers(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    file = source / "evidence.py"
    file.write_text(
        "def create_report():\n    return 'evidence report'\n",
        encoding="utf-8",
    )

    result = scan_project(str(tmp_path), "Create an evidence report")

    assert result["scope"]["read_only"] is True
    assert result["scope"]["executed_project_code"] is False
    assert any(item["path"] == "src/evidence.py"
               for item in result["evidence_candidates"])
    assert result["overall_status"] == "review"


def test_scanner_detects_package_dependencies_and_scripts(tmp_path):
    manifest = {
        "name": "demo",
        "scripts": {"build": "vite build", "test": "pytest"},
        "dependencies": {"react": "^19.0.0"},
        "devDependencies": {"vite": "^7.0.0"},
    }
    (tmp_path / "package.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    result = scan_project(str(tmp_path), "Add a component")

    names = {item["name"] for item in result["dependencies"]}
    assert names == {"react", "vite"}
    assert any("build" in item for item in result["build_signals"])
    assert any("test" in item for item in result["build_signals"])


def test_scanner_skips_environment_secrets_and_generated_folders(tmp_path):
    (tmp_path / ".env").write_text("TOKEN=do-not-read", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def run(): pass", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "hidden.js").write_text(
        "hidden generated file", encoding="utf-8"
    )

    result = scan_project(str(tmp_path), "Review application code")
    paths = {item["path"] for item in result["inventory"]["files"]}

    assert ".env" not in paths
    assert not any("node_modules" in path for path in paths)
    assert "src/app.py" in paths


def test_no_test_files_remains_unknown_not_proven_absent(tmp_path):
    (tmp_path / "app.py").write_text("print('hello')", encoding="utf-8")

    result = scan_project(str(tmp_path), "Add a dashboard")

    test_finding = next(
        finding for finding in result["findings"] if finding["id"] == "tests"
    )
    assert test_finding["status"] == "unknown"
    assert "does not prove tests are absent" in test_finding["message"]

def test_constraint_terms_do_not_inflate_feature_evidence(tmp_path):
    (tmp_path / "constraint_notes.py").write_text(
        "local only paid services subscriptions",
        encoding="utf-8",
    )

    result = scan_project(
        str(tmp_path),
        "Export invoices as CSV",
        ["local only; no paid services"],
    )

    evidence_paths = {
        item["path"] for item in result["evidence_candidates"]
    }
    assert "constraint_notes.py" not in evidence_paths


def test_constraints_distinguish_verified_checks_from_unknown(tmp_path):
    (tmp_path / "app.py").write_text(
        "def placeholder():\n    return None\n",
        encoding="utf-8",
    )

    no_execution = "Read project files only; do not execute inspected code"
    no_cost = "Zero-cost local prototype; no paid services or subscriptions"
    custom = "Must support Kubernetes deployment"

    result = scan_project(
        str(tmp_path),
        "Add invoice export",
        [no_execution, no_cost, custom],
    )

    checks = {
        item["constraint"]: item
        for item in result["constraint_checks"]
    }
    assert checks[no_execution]["status"] == "verified"
    assert checks[no_cost]["status"] == "unknown"
    assert checks[custom]["status"] == "unknown"
    assert result["overall_status"] == "review"


def test_backup_directory_is_excluded_from_inventory(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    (backup_dir / "old_app.py").write_text(
        "export invoices as CSV",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text(
        "def unrelated():\n    return None\n",
        encoding="utf-8",
    )

    result = scan_project(str(tmp_path), "Export invoices as CSV")
    paths = {item["path"] for item in result["inventory"]["files"]}

    assert not any(path.startswith("backups/") for path in paths)



def test_evidence_ranks_specific_terms_above_common_terms(tmp_path):
    (tmp_path / "feature.py").write_text(
        "invoice dashboard\\n", encoding="utf-8"
    )
    (tmp_path / "page.py").write_text(
        "dashboard layout\\n", encoding="utf-8"
    )
    (tmp_path / "overview.py").write_text(
        "dashboard overview\\n", encoding="utf-8"
    )

    result = scan_project(str(tmp_path), "invoice dashboard")
    evidence = result["evidence_candidates"]

    assert evidence
    assert evidence[0]["path"] == "feature.py"
    assert evidence[0]["relevance_score"] > next(
        item["relevance_score"]
        for item in evidence
        if item["path"] == "page.py"
    )
    assert "not confidence or proof" in evidence[0]["relevance_basis"]
    assert all(item["status"] == "candidate_evidence" for item in evidence)


def test_dependency_request_surfaces_recognized_manifests(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"react": "^19.0.0"}}),
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text(
        "fastapi\\npytest\\n",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text(
        "def start_application():\\n    return True\\n",
        encoding="utf-8",
    )

    result = scan_project(
        str(tmp_path),
        "Display declared package dependencies with the manifest file "
        "where each package is declared",
    )
    by_path = {
        item["path"]: item for item in result["evidence_candidates"]
    }

    expected = {"package.json", "requirements.txt"}
    assert expected.issubset(by_path)
    for path in expected:
        assert by_path[path]["evidence_type"] == (
            "manifest_dependency_declaration"
        )
        assert by_path[path]["relevance_score"] >= 12
        assert by_path[path]["status"] == "candidate_evidence"


def test_manifest_evidence_ranks_before_keyword_noise(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"react": "^19.0.0"}}),
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text(
        "fastapi\\npytest\\n", encoding="utf-8"
    )
    (tmp_path / "notes.py").write_text(
        "# Display declared package dependencies with the manifest file "
        "where each package is declared\\n",
        encoding="utf-8",
    )

    result = scan_project(
        str(tmp_path),
        "Display declared package dependencies with the manifest file "
        "where each package is declared",
    )
    paths = [item["path"] for item in result["evidence_candidates"]]

    assert set(paths[:2]) == {"package.json", "requirements.txt"}
    assert all(
        item["status"] == "candidate_evidence"
        for item in result["evidence_candidates"]
    )
