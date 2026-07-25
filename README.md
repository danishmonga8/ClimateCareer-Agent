# ClimateCareer-Agent

ClimateCareer-Agent is a human-supervised AI system for evaluating climate, environmental, sustainability, and AI-related job opportunities.

It converts a candidate CV into structured, traceable evidence; parses job descriptions; calculates an explainable relevance score; and generates private recommendation and application-personalization outputs.

The system does not submit applications automatically. Personalization, review, approval, and final application decisions remain under human control.

## Core principles

- Use only evidence supported by the candidate’s CV.
- Never invent qualifications, skills, employment, or experience.
- Keep candidate and application information private.
- Explain why a candidate matches or does not match a role.
- Route uncertain and sensitive information to human review.
- Require explicit human approval.
- Exclude automatic job-application submission.

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
11. Approve the application explicitly when all review items are resolved.
12. Complete any external application manually.

ClimateCareer-Agent stops at approval. It does not submit the application.

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

### 4. Create the private configuration file

```powershell
Copy-Item .env.example .env
```

### 5. Configure the OpenAI API key

Add the real OpenAI API key only to `.env`.

Never place the API key directly in source code, test files, command history, or committed configuration.

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

These help commands display the required item identifiers and resolution arguments supported by the current CLI.

### Approve the application

After every required review item has been resolved:

```powershell
python review_cli.py approve `
    --application .\documents\private\personalized_application.json
```

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

These files can contain personal, professional, scoring, and application information and must never be committed.

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

## Quality checks

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

## Planned development

- LangGraph workflow orchestration.
- Additional quality-control and approval commands.
- Controlled application-field autofill after explicit approval.
- Expanded audit logging and review visibility.

Any future autofill capability must remain human-supervised and must not introduce automatic submission.
