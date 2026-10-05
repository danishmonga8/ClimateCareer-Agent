# Contributing

Thank you for your interest in improving ClimateCareer-Agent.

## Development setup

1. Create and activate a Python 3.12 virtual environment.
2. Install the project with `python -m pip install -e ".[dev]"`.
3. Run `python -m ruff check .`.
4. Run `python -m pytest -q`.

## Change guidelines

- Keep the workflow human-supervised and preserve the no-submission boundary.
- Never add real candidate data, credentials, private application artifacts, or generated private outputs.
- Add or update tests when behavior changes.
- Keep errors and logs free of private content and local artifact paths.
- Prefer focused pull requests with a clear explanation of the user-visible effect.

By contributing, you agree that your contribution will be licensed under the
repository's MIT License.

