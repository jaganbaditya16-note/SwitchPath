# SwitchPath



**Trace the evidence. Follow the dependencies. Keep decisions reviewable.**



SwitchPath is a local-first, graph-backed project audit prototype built with Python, FastAPI, React, TypeScript, and FalkorDB.



It inventories eligible project files, extracts declared dependencies, ranks source-linked evidence candidates for a feature request, assesses constraints, and stores relationships in FalkorDB so users can trace evidence back to project files.



**Competition:** Graph Hacks 2026 - WeMakeDevs x FalkorDB

**Intended track:** Track 01 - Agents That Act on Connected Data

**Status:** Local prototype

**Demo video:** Add the public video URL before submitting.



## The problem



A keyword match is not proof that a feature is implemented or feasible. Engineers need to inspect the source files, identify declared dependencies, understand relationships between findings and evidence, and recognize uncertainty.



SwitchPath aims to make this evidence traceable rather than automatically approving a proposed feature.



## Features



- Bounded, read-only inventory of eligible project files.

- SHA-256 fingerprints for inspected files.

- Dependency extraction from `package.json` and `requirements.txt`.

- Keyword evidence candidates with matched terms and line numbers.

- Heuristic ranking that prioritizes dependency manifests for dependency-focused requests.

- Conservative constraint assessments, including `verified` and `unknown`.

- Persistent FalkorDB relationships for audits, source files, evidence candidates, and dependencies.

- FastAPI endpoints for audits and graph traces.

- React and TypeScript web interface.



## Architecture



React + Vite frontend â†’ FastAPI backend â†’ static audit and dependency extraction â†’ FalkorDB graph persistence and traversal.



The static scanner finds files, dependencies, and candidate evidence. FalkorDB stores relationships that can be traversed to connect findings with evidence files and declared dependencies.



## Graph data model



Key relationships include:



- `INSPECTED_FILE`: project audit to inspected file.

- `CANDIDATE_EVIDENCE`: finding to candidate evidence.

- `POINTS_TO`: evidence to its source file.

- `LISTS_DEPENDENCY`: finding to declared dependency.

- `DECLARED_IN`: dependency to its manifest file.



The graph trace API traverses these relationships to return evidence paths and dependency-to-manifest paths. See `server/app/audit_graph.py` for the implementation.



### Representative Cypher traversals



Trace inspected files:



```cypher

MATCH (audit:ProjectAudit {id: $id})-[:INSPECTED_FILE]->(file:ProjectFile)

RETURN audit, file

```



Trace evidence to source files:



```cypher

MATCH (audit:ProjectAudit {id: $id})-[:HAS_FINDING]->(finding:AuditFinding)-[:CANDIDATE_EVIDENCE]->

      (evidence:AuditEvidence)-[:POINTS_TO]->(file:ProjectFile)

RETURN finding, evidence, file

```



Trace dependencies to manifest files:



```cypher

MATCH (audit:ProjectAudit {id: $id})-[:HAS_FINDING]->(finding:AuditFinding)-[:LISTS_DEPENDENCY]->

      (dependency)-[:DECLARED_IN]->(manifest:ProjectFile)

RETURN finding, dependency, manifest

```



These are representative traversal patterns; check the actual graph implementation before treating them as the exact queries executed by the application.



## Technology stack



- Frontend: React, TypeScript, Vite

- Backend: Python, FastAPI, Uvicorn

- Graph database: FalkorDB

- Tests: pytest

- Local orchestration: Docker Compose



## Local setup



Requirements: Windows, PowerShell, Python 3.11 or newer, Node.js/npm, and Docker Desktop.



Create the Python environment:



```powershell

py -3 -m venv .venv

.\\.venv\\Scripts\\python.exe -m pip install -r server\\requirements.txt

```



Install frontend packages:



```powershell

Set-Location .\\web

npm ci

Set-Location ..

```



Start FalkorDB:



```powershell

docker compose up -d

docker compose ps

```



Start the API in one terminal:



```powershell

Set-Location .\\server

\& ..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

```



Start the frontend in another terminal:



```powershell

Set-Location .\\web

npm run dev -- --host 127.0.0.1

```



Open `http://127.0.0.1:5173/`. API health is available at `http://127.0.0.1:8000/api/health`.



## Tests and build



Run backend tests:



```powershell

Set-Location .\\server

\& ..\\.venv\\Scripts\\python.exe -m pytest .\\tests -q

Set-Location ..

```



Build the frontend:



```powershell

Set-Location .\\web

npm run build

Set-Location ..

```



The current development session recorded 18 passing Python tests and a successful frontend build. These results apply to that test run and do not prove the absence of all defects.



## API routes



- `GET /api/health` â€” service and database health.

- `POST /api/audits/scan` â€” create a project audit.

- `GET /api/audits/{audit_id}` â€” retrieve an audit.

- `GET /api/audits/{audit_id}/trace` â€” trace evidence and dependency relationships.



## Interpreting results



**Candidate evidence is not proof of feature support.** Matching terms identify leads for human review. The relevance score is a heuristic, not a confidence percentage or probability.



A static scan cannot prove the total running cost of a project. Such constraints remain `unknown` without sufficient evidence. The overall audit status remains `review`; a completed scan is not automatic approval.



## Limitations



- Evidence matching uses keyword overlap and heuristic ranking, not full semantic program analysis.

- The scanner does not execute inspected project code or automatically run its tests.

- Inventory limits and excluded files can affect completeness.

- Graph traversal demonstrates saved relationships but does not prove a feature works.

- External conditions, such as total operating costs, cannot all be verified from source files.



## Cost and privacy



SwitchPath is intended for local execution without requiring a paid AI service. Actual costs depend on the machine and infrastructure used; zero cost is not guaranteed for every deployment.



Only inspect projects you are authorized to access. Never publish credentials, API keys, or private project data.



## AI coding-assistant disclosure



OpenAI ChatGPT was used as a coding assistant during development. Assistance included project planning, architecture discussions, proposing and refining code changes, writing and refining regression tests, diagnosing problems from terminal output, and preparing documentation.



The participant applied the changes in the local environment and ran the documented automated tests, frontend builds, API health checks, and graph-trace checks. These checks establish only the results observed; they do not independently prove the complete correctness of the software.



The participant remains responsible for reviewing and understanding the submitted code, explaining design decisions, and accurately disclosing AI assistance as required by the competition rules.



## Demo plan



The demo should show:



1\. Starting the database, API, and frontend.

2\. Submitting a dependency-focused audit.

3\. Finding the declared dependencies and their source manifests.

4\. Reviewing the ranked evidence candidates.

5\. Following graph paths back to evidence files and dependency manifests.

6\. Examining constraint statuses and explaining uncertainty.

7\. Explaining the limitations of keyword-based ranking.



**Before submitting:** insert the actual public demo video URL, add the public repository URL where appropriate, and verify all submission requirements and the selected track.



## Project status



SwitchPath is a working local prototype under active development. It is not yet a production-ready code-review or feasibility-verification system.
