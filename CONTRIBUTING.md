# Contributing

Thanks for your interest in contributing to AutoShorts!

## Reporting Issues

- Search [existing issues](../../issues) before opening a new one
- Include your OS, Python version, and relevant error output
- For Veo-related issues, include your prompt JSON (redact any personal info)

## Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make your changes
4. Run tests: `uv run python -m pytest tests/ -q`
5. Ensure coverage stays above 90%: `uv run python -m pytest --cov --cov-fail-under=90`
6. Commit with a descriptive message
7. Open a PR against `main`

## Development Setup

```bash
git clone https://github.com/your-username/AutoShorts.git
cd AutoShorts
uv sync --group dev
cp .env.example .env
```

### Running Tests

```bash
uv run python -m pytest tests/ -q           # All tests
uv run python -m pytest tests/test_veo.py   # Single file
uv run python -m pytest --cov               # With coverage
```

### Code Style

- Python: 4-space indent, `snake_case`, type hints on signatures
- Use `pathlib.Path` for filesystem operations
- External I/O (APIs, files, network) must be mocked in unit tests

## Project Structure

- `Backend/` — Active Veo pipeline code
- `Backend/legacy/` — Stock footage pipeline (maintained but not actively developed)
- `tests/` — pytest test suite
- `docs/` — Documentation
