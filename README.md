# ClimateCareer-Agent

[![CI](https://github.com/danishmonga8/ClimateCareer-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/danishmonga8/ClimateCareer-Agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)

ClimateCareer-Agent is a human-supervised AI system for evaluating climate, environmental, sustainability, and AI-related job opportunities.

It converts a candidate CV into structured, traceable evidence; parses job descriptions; calculates an explainable relevance score; and generates private recommendation and application-personalization outputs.

The system does not submit applications automatically. Personalization, review,
approval, controlled local field entry, and final application decisions remain
under human control.

> **Project status:** Local/offline v1 is complete and covered by automated
> tests. External application submission is deliberately outside the project scope.

## Core principles

- Use only evidence supported by the candidate’s CV.
- Never invent qualifications, skills, employment, or experience.
- Keep candidate and application information private.
- Explain why a candidate matches or does not match a role.
- Route uncertain and sensitive information to human review.
- Require explicit human approval.
- Exclude automatic job-application submission.
- Keep command-line status and recovery output free of private artifact paths,
  review-note text, reviewer labels, and application content.

## Phase 1 capabilities

- Parse PDF and DOCX CV files.
- Extract and validate a candidate profile.
- Build a traceable CV evidence bank.
- Parse manually supplied job descriptions.
- Separate mandatory and preferred requirements.
- Evaluate candidate-job relevance.
- Calculate explainable category-level scores.
- Identify strengths, gaps, and missing evidence.
- Generate a private Markdown recommendation report.
- Keep application decisions under human control.

## Phase 2 capabilities

- Generate an evidence-backed tailored resume draft.
- Generate an evidence-backed cover-letter draft.
- Assess optional application questions.
- Route uncertain or sensitive answers to human review.
- Store personalized applications as validated private JSON.
- Start a structured human-review process.
- Resolve review items and confirm uncertain answers manually.
- Require explicit human approval.
- Prevent approval while unresolved review items remain.
- Maintain a strict no-submission boundary.

## Phase 3 capabilities

- Collect published jobs from public Greenhouse, Lever, and Ashby job boards.
- Normalize ATS-specific fields into one validated discovery model.
- Filter listings locally by keyword, location, work arrangement, and employment type.
- Deduplicate exact and cross-source copies while retaining the richer record.
- Store normalized listings as private, validated JSON snapshots.
- Pass selected listings into the existing job parser and relevance scorer.
- Use read-only public endpoints without credentials or application submission.

## Workflow

1. Parse the master CV.
2. Extract the candidate profile.
3. Build the CV evidence bank.
4. Parse the job description.
5. Score candidate-job relevance.
6. Generate the recommendation report.
7. Review the recommendation manually.
8. Optionally generate personalized application documents.
9. Optionally begin structured human review.
10. Resolve uncertain answers and other review items.
11. Run the current local quality gate and record internal approval only when
    all review items are resolved.
12. Optionally prepare a controlled local field-entry session through an
    explicitly configured fictional/mock adapter.
13. Confirm that specific session, then separately confirm the exact selected
    field identifiers before any local population status is recorded.
14. Review populated fields manually in the external target context.
15. Use the selected-job audit timeline to inspect sanitized local history.
16. Complete any external application manually, outside this system.

ClimateCareer-Agent stops before external application action. Internal approval
and any mock-only local field-entry status never submit the application.

## Installation

Python 3.12 or later is required.

### 1. Create a virtual environment

```powershell
py -3.12 -m venv .venv
```

### 2. Activate the environment

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Install the project and development dependencies

```powershell
python -m pip install -e ".[dev]"
```

### 4. Create the private configuration file for optional live model commands

```powershell
Copy-Item .env.example .env
```

### 5. Configure the OpenAI API key only when using live model commands

Add the real OpenAI API key only to `.env`.

Never place the API key directly in source code, test files, command history, or committed configuration.

The local dashboard, review, quality-control, workflow, controlled field-entry,
audit-timeline, and offline test paths do not call the OpenAI API. The original
profile-extraction, job-parsing, scoring, and personalization commands use a
configured model only when a user explicitly invokes them. The repository's
offline verification uses fictional fixtures and mocked model responses.

## Phase 1 usage

### Extract the candidate profile and evidence bank

```powershell
python main.py `
    --cv .\documents\private\master_cv.pdf `
    --extract-profile `
    --build-evidence
```

### Parse a job description

```powershell
python job_cli.py `
    --file .\documents\private\job_description.txt `
    --url "https://example.com/job"
```

### Score candidate-job relevance

```powershell
python score_cli.py
```

For a primarily AI-focused role:

```powershell
python score_cli.py --pure-ai-role
```

### Generate the recommendation report

```powershell
python report_cli.py
```

## Phase 2 usage

Phase 2 requires the Phase 1 candidate, evidence, job, and scoring outputs.

### Generate a personalized application

```powershell
python personalization_cli.py
```

To include application questions:

```powershell
python personalization_cli.py `
    --questions .\documents\private\application_questions.json
```

The personalized application is saved as:

```text
documents/private/personalized_application.json
```

### Begin human review

```powershell
python review_cli.py begin `
    --application .\documents\private\personalized_application.json
```

Beginning review does not approve the application.

### Check review status

```powershell
python review_cli.py status `
    --application .\documents\private\personalized_application.json
```

### Resolve review items

Use the dedicated review commands for uncertain application answers and general review items.

```powershell
python review_cli.py resolve-answer --help
python review_cli.py resolve-item --help
```

The status command intentionally shows only safe counts and generic indicators.
Inspect the private application artifact locally to identify a review-item field
path or question index before using a resolution command; those private details
are never echoed by the CLI.

### Approve the application

After every required review item has been resolved, use the authoritative
workspace-based approval command. The legacy application-only approval command
is intentionally unsupported:

```powershell
python review_cli.py approve `
    --workspace .\documents\private\dashboard_workspace.json `
    --job-key "manual:example-board:example-job-001" `
    --expected-revision 0 `
    --reviewer-label "Local reviewer" `
    --confirm `
    --evidence .\documents\private\evidence_bank.json `
    --approval-note "Internal approval recorded."
```

Use `--workflow-checkpoints .\documents\private\workflow_checkpoints` when
the selected review is workflow-enabled. `review_cli.py quality-check` accepts
the same workspace, job, revision, and evidence context and returns `0` for
PASS or WARNING, `3` for BLOCKED, and `2` for invalid command input. Approval
always recomputes the quality report from freshly loaded authoritative artifacts;
a prior PASS result is never authorization.

Approval fails when:

- The application has not entered human review.
- Required review items remain unresolved.
- An uncertain answer has not been confirmed by the user.
- The application data are missing or invalid.

Approval records the user’s decision only. It does not submit an application.

## Phase 3 usage

Collect a Greenhouse public board:

```powershell
python discovery_cli.py `
    --company "Example Climate" `
    --include climate `
    greenhouse `
    --board example
```

Collect a Lever public site:

```powershell
python discovery_cli.py `
    --company "Example Climate" `
    --work-arrangement remote `
    lever `
    --site example
```

Collect an Ashby public board:

```powershell
python discovery_cli.py `
    --company "Example Climate" `
    ashby `
    --board example
```

The default private output is:

```text
documents/private/discovered_jobs.json
```

The collectors make unauthenticated GET requests only. LinkedIn is not scraped;
only permitted public links may be recorded for manual discovery. The system does
not access logged-in pages, bypass controls, automate Easy Apply, or submit an
application.

## Unified workflow

### Complete Phase 1 workflow

```powershell
python workflow_cli.py `
    --cv .\documents\private\master_cv.pdf `
    --job-file .\documents\private\job_description.txt `
    --job-url "https://example.com/job"
```

### Complete workflow with personalization

```powershell
python workflow_cli.py `
    --cv .\documents\private\master_cv.pdf `
    --job-file .\documents\private\job_description.txt `
    --job-url "https://example.com/job" `
    --personalize
```

### Include application questions

```powershell
python workflow_cli.py `
    --cv .\documents\private\master_cv.pdf `
    --job-file .\documents\private\job_description.txt `
    --job-url "https://example.com/job" `
    --personalize `
    --questions .\documents\private\application_questions.json
```

### Generate personalization and begin human review

```powershell
python workflow_cli.py `
    --cv .\documents\private\master_cv.pdf `
    --job-file .\documents\private\job_description.txt `
    --job-url "https://example.com/job" `
    --personalize `
    --begin-review
```

### Combine personalization, questions, and review

```powershell
python workflow_cli.py `
    --cv .\documents\private\master_cv.pdf `
    --job-file .\documents\private\job_description.txt `
    --job-url "https://example.com/job" `
    --personalize `
    --questions .\documents\private\application_questions.json `
    --begin-review
```

For a primarily AI-focused job, add:

```text
--pure-ai-role
```

The following rules are enforced:

- `--questions` requires `--personalize`.
- `--begin-review` requires `--personalize`.
- Beginning review does not approve the application.
- Approval remains a separate manual command.

## Private outputs

Generated private files are stored under `documents/private/`.

Depending on the workflow, these include:

```text
candidate_profile.json
evidence_bank.json
structured_job.json
scoring_result.json
recommendation_report.md
personalized_application.json
discovered_jobs.json
```

These files can contain personal, professional, scoring, and application
information and must never be committed. Keep any configured workflow
checkpoints, autofill sessions, audit records, and private artifact registries
under an ignored private directory as well. CLI success and recovery output
deliberately reports only local status and counts, not private locations or
content.

## Application-question format

Application questions are supplied as a JSON array.

Example:

```json
[
  "Why are you interested in this role?",
  "Do you have the legal right to work in this location?"
]
```

Questions requiring uncertain, sensitive, or candidate-confirmed information must be routed to human review. The system must not infer or invent answers.

## Human-review safeguards

The review workflow enforces the following controls:

- A newly personalized application cannot be approved directly.
- Human review must begin before approval.
- Unresolved review items block approval.
- Uncertain answers require explicit human confirmation.
- Sensitive candidate information is never assumed.
- Approved applications cannot be returned to review improperly.
- No application-submission state or command exists.

## Phase 4: Human Approval Dashboard

Launch the local dashboard from the repository root:

```powershell
python -m streamlit run dashboard.py
```

The dashboard reads one private workspace JSON file. It contains review metadata
and references to existing discovery, scoring, and personalized-application JSON
artifacts; it never copies, regenerates, or changes their content. The default
private location is `documents/private/dashboard_workspace.json`.

Use paths relative to the workspace file where practical. This redacted example
uses only placeholder data:

```json
{
  "records": [
    {
      "source": "manual",
      "source_board": "example-board",
      "source_job_id": "example-job-001",
      "artifacts": {
        "discovery_snapshot": "discovered_jobs.json",
        "scoring_result": "example_score.json",
        "personalized_application": "example_application.json"
      }
    }
  ],
  "audit_events": [],
  "schema_version": "1.0"
}
```

Dashboard statuses are internal only:

- **Awaiting review**: no decision has been recorded.
- **Revision requested**: a reviewer recorded instructions before another review.
- **Approved for manual next step**: the internal package is approved for a
  human-led next step. It does **not** mean submitted.
- **Rejected**: the internal decision is final in the dashboard.

Every dashboard decision records an append-only local audit event. Rejection and
revision requests require a reason; approval is blocked when linked application
review items remain unresolved. The dashboard never submits an application,
opens an Apply flow, sends messages, logs in, starts browser automation, or
changes any external service.

## Phase 6: Local LangGraph orchestration

Phase 6 coordinates existing validated artifacts through a local LangGraph flow:

```text
input validation -> job processing -> scoring -> personalization -> human review interrupt
                                                                    -> approved for manual next step
                                                                    -> revision requested
                                                                    -> rejected
```

The graph state and restart-safe JSON checkpoint contain artifact references,
stable job identity, review revision, internal stage, timestamps, and sanitized
warnings only. They do not duplicate candidate or application content. Live
interrupts use LangGraph's local in-memory checkpointer; an atomic JSON snapshot
under `workflow_checkpoints/` enables a later local resume after restart.

The dashboard displays a matching local workflow stage when a checkpoint is
available. Streamlit refreshes never start graph nodes automatically. This
orchestration records internal approval only: it has no submission node,
external-action route, browser action, upload, email, or autofill capability.

## Quality control

`review_cli.py quality-check` reports **PASS**, **WARNING**, or **BLOCKED** using
sanitized finding codes and recovery guidance. PASS and WARNING exit `0`;
BLOCKED exits `3`; invalid command input exits `2`. Internal approval now requires
`--workspace`, `--job-key`, `--expected-revision`, `--reviewer-label`,
`--confirm`, `--evidence`, and `--approval-note`; the former application-only
approval invocation is intentionally unsupported. Approval remains only
**Approved for manual next step** and never submits an application.

## Phase 8 controlled field entry

Phase 8 provides a local, mock-adapter-only field-entry session after a package
is **Approved for manual next step**. It never opens a browser or external
application. It records controlled local population status only, after which a
human must manually review the target context.

Sessions and LangGraph checkpoints contain opaque workspace, profile, evidence,
material-version, and workflow references; identifiers; classifications;
revisions; statuses; and sanitized counts only. A trusted, externally configured
`workspace_id -> approved root` mapping resolves opaque private-registry records
locally. Registry entries contain only an opaque ID, workspace binding, kind,
relative path, and SHA-256 digest. Resolution rejects malformed references,
wrong kinds or workspaces, missing files, directories and other non-regular
files, symlinks, containment escapes, and digest mismatches. Resolved paths and
field values are transient and never enter dashboard models, sessions,
checkpoints, audit events, errors, or logs.

Eligible identifiers are limited to verified profile/application data for a full
name, approved email or telephone, explicitly mapped professional links, and
only other allow-listed categories when an exact deterministic mapping exists.
The current profile schema leaves ambiguous location, employment, education,
and skill aggregates manual until an exact field-level mapping is available.
Passwords, authentication, CAPTCHA/MFA, payments, legal declarations, sensitive
or demographic questions, work authorization, compensation, references,
free-text answers, and attachments always remain manual.

Every session preparation, start confirmation, and population confirmation
reloads authoritative artifacts and reruns approval, Phase 7 quality, revision,
material-version, workflow-checkpoint, evidence, and profile-completeness gates.
Two deliberate confirmations are required: first for the prepared session, then
for the exact selected eligible field identifiers. Cancellation and skips are
explicit, safe, and idempotent. Local reference-only snapshots use atomic writes;
sanitized audit events are append-only and idempotent.

The dashboard is read-only by default. It shows sanitized session metadata,
counts, classifications, compatibility indicators, the last fresh quality
outcome, and interruption stage. Rendering and refresh do not create, resolve,
validate, migrate, confirm, populate, skip, cancel, or advance a session.
An explicitly injected trusted local session service is required before the
deliberate controls are available; the dashboard never infers or creates that
configuration. Controls always re-enter the controller-backed LangGraph flow.

Only fictional offline adapters and fixtures are supplied. There is no browser
adapter, HTTP/API action, upload, download, email, authentication, CAPTCHA/MFA,
payment, consent, Apply, Send, or Submit capability. Population never means an
application was submitted.

## Expanded audit logging and review visibility

The dashboard now provides a local, selected-job, read-only audit timeline. It
projects existing dashboard-review audit events and, when an explicitly
configured local session repository is available, Phase 8 autofill audit events.
It does not create a unified audit ledger, copy history into a new store, repair
source data, or mutate review, workflow, session, or audit state during loading,
filtering, pagination, or refresh.

Timeline entries expose only structured internal metadata: source, category,
action, internal status transition, timestamp, and a deterministic opaque source
key. Existing review notes and reviewer labels are never rendered; the dashboard
shows only the generic indicators **Review note recorded** and **Reviewer
recorded**. Autofill field values, candidate data, evidence, application
materials, paths, roots, registry records, checkpoint payloads, credentials, and
raw exceptions are not included in the projection.

Entries are ordered newest first with stable tie-breakers. Source, category,
action, status, and time-range filters operate only on structured metadata. Pages
use bounded opaque cursors. A malformed or stale cursor produces a sanitized
read-only warning and does not change history. Current local session checkpoint
metadata, if available, is explicitly labelled **Current checkpoint summary**;
it is not historical audit evidence.

The view exposes sanitized integrity warnings for unavailable or malformed
sources, duplicate identifiers/source keys, invalid linkage, conflicting
transitions, invalid timestamps, malformed cursors, and inconsistent current
checkpoint metadata. These warnings are visible and non-blocking: they do not
change approval, revision, rejection, workflow, or autofill decisions.

The audit view is local/offline and has no export or download, retention or
deletion automation, cryptographic tamper-evidence, browser, upload, email,
authentication, external-service, or submission capability.

## Local/offline v1 scope

The documented local/offline v1 scope is complete when used with existing local
artifacts or the supplied fictional, mocked test fixtures. It provides a
connected human-controlled journey from local artifact review through
quality-gated internal approval, optional mock-only controlled field entry,
mandatory manual review, and sanitized selected-job audit visibility.

All stateful local controls use stable job identity, expected revisions,
material-version and evidence compatibility, fresh validation, append-only
authoritative audit sources, reference-only snapshots, and idempotent retries.
Dashboard rendering, status inspection, filters, pagination, and refresh are
read-only. Recovery messages are sanitized and direct the user to reload the
relevant local state rather than exposing a private path or raw exception.

The mock adapter records local field-population status only. It never opens or
controls a browser, and every populated field still requires manual human review
in its target context. No component interprets approval or local population as
an application submission.

### Lint

```powershell
python -m ruff check .
```

### Tests

```powershell
python -m pytest -v
```

For concise test output:

```powershell
python -m pytest -q
```

### Offline end-to-end verification

Run the Phase 5 fictional, offline integration checks without an OpenAI API call
or live job-board request:

```powershell
python -m pytest -q tests/test_e2e_verification.py tests/test_dashboard_app.py
```

### Formatting and Git checks

```powershell
git diff --check
git status --short
```

## Privacy and security

The `.env` file and `documents/private/` directory are excluded from Git.

Never commit:

- API keys or credentials
- CVs or resumes
- Candidate profiles
- Evidence banks
- Job-description data
- Scoring results
- Recommendation reports
- Personalized applications
- Application-question answers
- Human-review decisions containing private information
- Private workflow checkpoints, session records, audit records, or artifact
  registries

Before committing, always inspect:

```powershell
git status --short
git diff --cached
```

## Safety limitations

ClimateCareer-Agent provides decision support only.

It must not:

- Invent candidate experience or qualifications.
- Use unverified evidence in application documents.
- Answer sensitive questions without human confirmation.
- Approve an application with unresolved review items.
- Automatically submit applications.
- Scrape logged-in LinkedIn pages or bypass access controls.
- Automate LinkedIn Easy Apply or any other application submission.
- Replace final human judgment.

## Optional future enhancements

No later required roadmap item is currently documented. The following are
deliberately outside local/offline v1 and require separate design and approval:

- A real browser or target adapter, if ever considered, with an independent
  safety review; it must not introduce automatic submission.
- Audit export/download, retention or deletion automation, or cryptographic
  tamper-evidence.
- Any live external integration beyond an explicitly user-invoked existing
  model or public-discovery command.
