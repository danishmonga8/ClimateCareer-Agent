# ClimateCareer-Agent

ClimateCareer-Agent is a human-supervised AI system for evaluating climate, environmental, sustainability, and AI-related job opportunities.

It converts a candidate CV into structured evidence, parses job descriptions, calculates an explainable relevance score, and generates a private recommendation report. It does not submit applications automatically.

## Phase 1 capabilities

- Parse PDF and DOCX CV files.
- Extract and validate a candidate profile.
- Build a traceable CV evidence bank.
- Parse manually supplied job descriptions.
- Evaluate mandatory and preferred requirements.
- Calculate explainable category-level scores.
- Identify strengths and missing evidence.
- Generate a private Markdown recommendation report.
- Keep application decisions under human control.

## Workflow

1. Parse the master CV.
2. Extract the candidate profile.
3. Build the evidence bank.
4. Parse a job description.
5. Score candidate-job relevance.
6. Generate the recommendation report.
7. Review the recommendation manually.

## Installation

Requires Python 3.12 or later.

1. Create the environment: `py -3.12 -m venv .venv`
2. Activate it: `.\.venv\Scripts\Activate.ps1`
3. Install dependencies: `python -m pip install -e ".[dev]"`
4. Create the private configuration: `Copy-Item .env.example .env`
5. Add the real OpenAI API key only to `.env`.

## Usage

- Candidate profile and evidence: `python main.py --cv .\documents\private\master_cv.pdf --extract-profile --build-evidence`
- Parse a job: `python job_cli.py --file .\documents\private\job_description.txt --url "https://example.com/job"`
- Score the job: `python score_cli.py`
- Score a pure AI role: `python score_cli.py --pure-ai-role`
- Generate the report: `python report_cli.py`

Private outputs are stored under `documents/private/`.

## Quality checks

- Lint: `python -m ruff check .`
- Tests: `python -m pytest -q`

## Privacy and safety

The `.env` file and `documents/private/` directory are excluded from Git. Never commit API keys, CVs, candidate profiles, evidence banks, job data, scoring results, or recommendation reports.

The system provides recommendations only. It must not invent candidate experience or replace human review.

## Planned development

- Unified workflow orchestration.
- Application-document personalization.
- Quality-control and approval stages.
- Streamlit user interface.
