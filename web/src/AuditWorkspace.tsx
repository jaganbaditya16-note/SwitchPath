import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  CircleHelp,
  Database,
  FileCode2,
  FileSearch,
  GitBranch,
  LoaderCircle,
  RefreshCw,
  ScanSearch,
  ShieldCheck,
  Workflow,
} from "lucide-react";

const API_BASE = "http://127.0.0.1:8000";

type Health = {
  ok: boolean;
  database?: string;
  graph?: string;
  node_count?: number;
};

type Finding = {
  id: string;
  status: string;
  message: string;
};

type ProjectFile = {
  path: string;
  sha256: string;
  extension: string;
  line_count: number;
  bytes: number;
  is_test_file: boolean;
};

type Inventory = {
  file_count?: number;
  extension_counts?: Record<string, number>;
  test_files?: string[];
  manifests?: string[];
  files?: ProjectFile[];
};

type Dependency = {
  name: string;
  sources: string[];
};

type Evidence = {
  path: string;
  sha256: string;
  matched_terms: string[];
  matching_lines: number[];
  evidence_type: string;
  status: string;
};

type ConstraintCheck = {
  constraint: string;
  status: string;
  basis: string;
};

type AuditReport = {
  audit_id: string;
  project_name: string;
  feature_request: string;
  constraints: string[];
  constraint_checks?: ConstraintCheck[];
  overall_status: string;
  scope?: {
    read_only?: boolean;
    executed_project_code?: boolean;
    scanned_file_count?: number;
    total_bytes_read?: number;
  };
  inventory: Inventory;
  build_signals?: string[];
  dependencies?: Dependency[];
  evidence_candidates?: Evidence[];
  findings?: Finding[];
  graph_persistence?: {
    graph?: string;
    audit_id?: string;
    files?: number;
    dependencies?: number;
    evidence?: number;
    findings?: number;
  };
  limitation?: string;
};

type EvidencePath = {
  finding_id: string;
  finding_status: string;
  source_path: string;
  matched_terms: string[];
  matching_lines: number[];
  sha256: string;
  status: string;
};

type DependencyPath = {
  finding_id: string;
  dependency: string;
  declared_in: string;
  sha256: string;
};

type AuditTrace = {
  audit_id: string;
  graph: string;
  evidence_paths: EvidencePath[];
  dependency_paths: DependencyPath[];
};

async function requestJson<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  const body = (await response.json().catch(() => ({}))) as Record<
    string,
    unknown
  >;

  if (!response.ok) {
    const detail = body.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : `Request failed with HTTP ${response.status}.`,
    );
  }

  return body as T;
}

function statusClass(status: string): string {
  return status.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

function shortHash(value: string): string {
  return value ? value.slice(0, 12) : "Not available";
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="audit-error" role="alert">
      <AlertCircle size={17} />
      <span>{message}</span>
    </div>
  );
}

export default function AuditWorkspace() {
  const [projectPath, setProjectPath] = useState(
    "C:\\Users\\Jagan\\Projects\\switchpath",
  );
  const [featureRequest, setFeatureRequest] = useState("");
  const [constraintsText, setConstraintsText] = useState(
    "Zero-cost local prototype; no paid services or subscriptions\nRead project files only; do not execute inspected code",
  );
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState("");
  const [report, setReport] = useState<AuditReport | null>(null);
  const [trace, setTrace] = useState<AuditTrace | null>(null);
  const [error, setError] = useState("");
  const [traceError, setTraceError] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("Overview");

  const refreshHealth = useCallback(async () => {
    setHealthError("");
    try {
      const result = await requestJson<Health>("/api/health");
      setHealth(result);
    } catch (err) {
      setHealth(null);
      setHealthError(
        err instanceof Error
          ? err.message
          : "Could not connect to the local API.",
      );
    }
  }, []);

  useEffect(() => {
    void refreshHealth();
  }, [refreshHealth]);

  const runAudit = async () => {
    const path = projectPath.trim();
    const feature = featureRequest.trim();
    const constraints = constraintsText
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean)
      .slice(0, 20);

    if (!path || !feature) {
      setError("Enter a project path and describe the feature to review.");
      return;
    }

    setLoading(true);
    setError("");
    setTraceError("");
    setTrace(null);
    setReport(null);
    setActiveTab("Overview");

    try {
      const scan = await requestJson<AuditReport>("/api/audits/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_path: path,
          feature_request: feature,
          constraints,
        }),
      });

      setReport(scan);

      try {
        const recovered = await requestJson<Partial<AuditReport>>(
          `/api/audits/${encodeURIComponent(scan.audit_id)}`,
        );
        setReport({
          ...scan,
          ...recovered,
          inventory: {
            ...scan.inventory,
            ...(recovered.inventory ?? {}),
          },
        });
      } catch {
        setTraceError(
          "The scan was saved, but the separate audit-retrieval request failed.",
        );
      }

      try {
        const graphTrace = await requestJson<AuditTrace>(
          `/api/audits/${encodeURIComponent(scan.audit_id)}/trace`,
        );
        setTrace(graphTrace);
      } catch (err) {
        setTraceError(
          err instanceof Error
            ? `Audit saved, but graph tracing failed: ${err.message}`
            : "Audit saved, but graph tracing could not be loaded.",
        );
      }

      await refreshHealth();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "The project audit failed. Check the local API logs.",
      );
    } finally {
      setLoading(false);
    }
  };

  const findings = report?.findings ?? [];
  const evidence = report?.evidence_candidates ?? [];
  const dependencies = report?.dependencies ?? [];
  const evidencePaths = trace?.evidence_paths ?? [];
  const dependencyPaths = trace?.dependency_paths ?? [];
  const files = report?.inventory?.files ?? [];

  return (
    <div className="audit-shell">
      <aside className="audit-sidebar">
        <a className="audit-brand" href="#workspace" aria-label="SwitchPath home">
          <span className="audit-brand-mark"><GitBranch size={23} /></span>
          <span>
            <strong>SwitchPath</strong>
            <small>PROJECT INTELLIGENCE</small>
          </span>
        </a>

        <div className="audit-nav-caption">WORKSPACE</div>
        <nav className="audit-nav">
          {[
            { label: "Overview", icon: Activity },
            { label: "Evidence", icon: FileSearch },
            { label: "Dependencies", icon: Workflow },
            { label: "Project files", icon: FileCode2 },
          ].map(({ label, icon: Icon }) => (
            <button
              type="button"
              key={label}
              className={`audit-nav-item ${activeTab === label ? "active" : ""}`}
              onClick={() => setActiveTab(label)}
            >
              <Icon size={17} />
              <span>{label}</span>
              {label === "Evidence" && evidence.length > 0 && (
                <span className="audit-nav-count">{evidence.length}</span>
              )}
            </button>
          ))}
        </nav>

        <div className="audit-sidebar-bottom">
          <div className="audit-local-icon"><ShieldCheck size={19} /></div>
          <strong>Local-first analysis</strong>
          <p>Read-only inventory. No inspected project code is executed by the scanner.</p>
          <div className="audit-local-status">
            <span className="audit-status-dot" />
            Zero-cost prototype
          </div>
        </div>
      </aside>

      <main id="workspace" className="audit-main">
        <header className="audit-topbar">
          <div className="audit-breadcrumb">
            <span>Workspace</span><ArrowRight size={14} /><strong>Project audit</strong>
          </div>
          <div className={`audit-connection ${health?.ok ? "connected" : "offline"}`}>
            <span className="audit-status-dot" />
            {health?.ok ? "API connected" : "API unavailable"}
            <button
              type="button"
              className="audit-icon-button"
              onClick={() => void refreshHealth()}
              aria-label="Refresh API status"
              title="Refresh API status"
            >
              <RefreshCw size={14} />
            </button>
          </div>
        </header>

        <section className="audit-page-heading">
          <div>
            <div className="audit-eyebrow"><ScanSearch size={14} /> GRAPH-BACKED PROJECT REVIEW</div>
            <h1>Know what your project can support.</h1>
            <p>
              Trace feature requests to source-file evidence, declared dependencies
              and project signals — before treating an assumption as a fact.
            </p>
          </div>
          <div className="audit-heading-mark"><GitBranch size={32} /></div>
        </section>

        {healthError && (
          <ErrorBanner
            message={`Cannot reach the local API at ${API_BASE}. Start the backend and retry. Details: ${healthError}`}
          />
        )}

        <section className="audit-layout">
          <div className="audit-panel audit-form-panel">
            <div className="audit-panel-heading">
              <span className="audit-step-number">01</span>
              <div>
                <h2>Configure audit</h2>
                <p>Choose the project and define the goal.</p>
              </div>
            </div>

            <label className="audit-label" htmlFor="project-path">Local project path</label>
            <input
              id="project-path"
              className="audit-input"
              value={projectPath}
              onChange={(event) => setProjectPath(event.target.value)}
              placeholder="C:\Projects\my-project"
              spellCheck={false}
            />
            <div className="audit-field-hint">The API reads files from the machine running the backend.</div>

            <label className="audit-label" htmlFor="feature-request">Feature or decision to review</label>
            <textarea
              id="feature-request"
              className="audit-input audit-textarea"
              rows={4}
              value={featureRequest}
              onChange={(event) => setFeatureRequest(event.target.value)}
              placeholder="Example: Add CSV export for invoice records"
            />

            <label className="audit-label" htmlFor="constraints">Constraints <span>one per line · up to 20</span></label>
            <textarea
              id="constraints"
              className="audit-input audit-textarea audit-constraints"
              rows={4}
              value={constraintsText}
              onChange={(event) => setConstraintsText(event.target.value)}
              placeholder={"Budget: ₹0\nNo external services\nDo not execute project code"}
            />

            {error && <ErrorBanner message={error} />}

            <button
              className="audit-primary-button"
              type="button"
              onClick={() => void runAudit()}
              disabled={loading}
            >
              {loading ? (
                <><LoaderCircle className="audit-spin" size={17} /> Scanning project…</>
              ) : (
                <><ScanSearch size={17} /> Run project audit <ArrowRight size={16} /></>
              )}
            </button>
            <div className="audit-form-footnote">
              <ShieldCheck size={14} /> Static scan · bounded file reading · graph persistence
            </div>
          </div>

          <div className="audit-results-column">
            <div className="audit-panel audit-hero-panel">
              <div className="audit-hero-top">
                <span className="audit-hero-kicker">AUDIT STATUS</span>
                <span className={`audit-status-pill ${statusClass(report?.overall_status ?? "waiting")}`}>
                  <CircleHelp size={14} />
                  {report?.overall_status ?? "Awaiting audit"}
                </span>
              </div>
              <h2>{report ? report.project_name : "Your next decision, evidence-backed."}</h2>
              <p>
                {report
                  ? report.feature_request
                  : "Run an audit to inventory files, identify project signals, and map candidate evidence through FalkorDB."}
              </p>
              <div className="audit-hero-footer">
                <div>
                  <span>Graph</span>
                  <strong><Database size={14} /> {trace?.graph ?? report?.graph_persistence?.graph ?? health?.graph ?? "switchpath_demo"}</strong>
                </div>
                <div>
                  <span>Audit ID</span>
                  <strong className="audit-mono">{report ? shortHash(report.audit_id) : "Not created yet"}</strong>
                </div>
              </div>
            </div>

            <div className="audit-metric-grid">
              <div className="audit-panel audit-metric">
                <span className="audit-metric-icon teal"><FileCode2 size={17} /></span>
                <span className="audit-metric-label">Files inventoried</span>
                <strong>{report?.inventory?.file_count ?? report?.scope?.scanned_file_count ?? "—"}</strong>
                <small>Readable source files</small>
              </div>
              <div className="audit-panel audit-metric">
                <span className="audit-metric-icon blue"><Workflow size={17} /></span>
                <span className="audit-metric-label">Declared packages</span>
                <strong>{dependencies.length || report?.graph_persistence?.dependencies || "—"}</strong>
                <small>From detected manifests</small>
              </div>
              <div className="audit-panel audit-metric">
                <span className="audit-metric-icon violet"><GitBranch size={17} /></span>
                <span className="audit-metric-label">Evidence candidates</span>
                <strong>{evidence.length || report?.graph_persistence?.evidence || "—"}</strong>
                <small>Require human review</small>
              </div>
            </div>

            {traceError && <ErrorBanner message={traceError} />}

            {report?.limitation && (
              <div className="audit-limitation">
                <AlertCircle size={17} />
                <div><strong>Interpret results carefully</strong><p>{report.limitation}</p></div>
              </div>
            )}

            {report?.constraint_checks && report.constraint_checks.length > 0 && (
              <div className="audit-panel audit-constraint-results">
                <div className="audit-table-intro">
                  <strong>Constraint assessment</strong>
                  <p>
                    Verified labels apply only to checks this scanner can establish.
                    Cost and unsupported requirements remain unknown.
                  </p>
                </div>
                {report.constraint_checks.map((check, index) => (
                  <article
                    className="audit-constraint-result"
                    key={`${check.constraint}-${index}`}
                  >
                    <span className={`audit-status-pill ${statusClass(check.status)}`}>
                      {check.status}
                    </span>
                    <div className="audit-constraint-result-body">
                      <strong>{check.constraint}</strong>
                      <p>{check.basis}</p>
                    </div>
                  </article>
                ))}
              </div>
            )}

            <div className="audit-section-heading">
              <div>
                <span className="audit-eyebrow">TRACEABLE RESULTS</span>
                <h2>{activeTab === "Overview" ? "Audit findings" : activeTab}</h2>
              </div>
              {report && (
                <span className="audit-subtle-count">{findings.length} findings</span>
              )}
            </div>

            {!report && (
              <div className="audit-panel audit-empty-state">
                <div className="audit-empty-icon"><ScanSearch size={26} /></div>
                <h3>Start with a project question</h3>
                <p>
                  Audit results, trace paths, dependency declarations and source hashes
                  will appear here after your first scan.
                </p>
              </div>
            )}

            {report && activeTab === "Overview" && (
              <div className="audit-findings-list">
                {findings.map((finding) => (
                  <article className="audit-panel audit-finding" key={finding.id}>
                    <div className={`audit-finding-icon ${statusClass(finding.status)}`}>
                      {finding.status === "observed" ? <CheckCircle2 size={17} /> : <CircleHelp size={17} />}
                    </div>
                    <div className="audit-finding-body">
                      <div className="audit-finding-title-row">
                        <h3>{finding.id.replaceAll("_", " ")}</h3>
                        <span className={`audit-status-pill ${statusClass(finding.status)}`}>
                          {finding.status.replaceAll("_", " ")}
                        </span>
                      </div>
                      <p>{finding.message}</p>
                      {finding.id === "feature_trace" && (
                        <button type="button" className="audit-text-button" onClick={() => setActiveTab("Evidence")}>
                          Inspect source candidates <ArrowRight size={14} />
                        </button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            )}

            {report && activeTab === "Evidence" && (
              <div className="audit-panel audit-table-panel">
                <div className="audit-table-intro">
                  <strong>Candidate evidence</strong>
                  <p>Keyword overlap helps locate files; it does not prove a feature works.</p>
                </div>
                {evidence.length === 0 && <p className="audit-empty-inline">No evidence candidates were returned.</p>}
                {evidence.map((item, index) => (
                  <article className="audit-evidence-row" key={`${item.path}-${index}`}>
                    <FileSearch size={17} />
                    <div className="audit-evidence-main">
                      <strong>{item.path}</strong>
                      <p>Terms: {item.matched_terms.join(", ") || "None listed"}</p>
                      <p>Lines: {item.matching_lines.join(", ") || "Not available"}</p>
                      <small>SHA-256 · {shortHash(item.sha256)}</small>
                    </div>
                    <span className={`audit-status-pill ${statusClass(item.status)}`}>candidate</span>
                  </article>
                ))}
                {trace && <div className="audit-trace-summary">Graph traversal returned {evidencePaths.length} evidence paths.</div>}
              </div>
            )}

            {report && activeTab === "Dependencies" && (
              <div className="audit-panel audit-table-panel">
                <div className="audit-table-intro">
                  <strong>Declared dependencies</strong>
                  <p>Package declarations and source manifests captured during scanning.</p>
                </div>
                {dependencies.length === 0 && <p className="audit-empty-inline">No package dependencies were detected.</p>}
                {dependencies.map((dependency) => (
                  <div className="audit-dependency-row" key={`${dependency.name}-${dependency.sources.join(",")}`}>
                    <span className="audit-dependency-icon"><Workflow size={16} /></span>
                    <div><strong>{dependency.name}</strong><small>{dependency.sources.join(", ") || "Manifest not specified"}</small></div>
                    <span className="audit-source-tag">DECLARED</span>
                  </div>
                ))}
                {trace && dependencyPaths.length > 0 && (
                  <div className="audit-trace-summary">Graph traversal confirmed {dependencyPaths.length} dependency-to-manifest paths.</div>
                )}
              </div>
            )}

            {report && activeTab === "Project files" && (
              <div className="audit-panel audit-table-panel">
                <div className="audit-table-intro">
                  <strong>Inventoried project files</strong>
                  <p>File metadata and hashes from the read-only scan.</p>
                </div>
                {files.length === 0 && <p className="audit-empty-inline">File detail is unavailable in this response.</p>}
                {files.map((file) => (
                  <div className="audit-file-row" key={file.path}>
                    <FileCode2 size={16} />
                    <div><strong>{file.path}</strong><small>{file.line_count} lines · {file.bytes.toLocaleString()} bytes{file.is_test_file ? " · test-like file" : ""}</small></div>
                    <code>{shortHash(file.sha256)}</code>
                  </div>
                ))}
              </div>
            )}

            {report && trace && traceError === "" && (
              <div className="audit-graph-footer">
                <div className="audit-graph-icon"><GitBranch size={19} /></div>
                <div>
                  <strong>Graph trace connected</strong>
                  <p>
                    {evidencePaths.length} evidence path(s) and {dependencyPaths.length} dependency path(s)
                    {" "}were returned for this audit.
                  </p>
                </div>
                <CheckCircle2 size={19} className="audit-graph-check" />
              </div>
            )}
          </div>
        </section>

        <footer className="audit-footer">
          <span>SWITCHPATH · EVIDENCE-FIRST PROJECT REVIEW</span>
          <span><ShieldCheck size={13} /> Local prototype · no paid API required</span>
        </footer>
      </main>
    </div>
  );
}
