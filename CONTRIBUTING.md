# Contributing to personal-agent-doitall

Thanks for your interest! This is a local-first personal work agent built in Python.
Everything runs offline on your machine — no cloud services required.

---

## Development Setup

**Prerequisites:** Python 3.11+, Git

```bash
git clone https://github.com/sayedtenkanen/personal-agent-doitall.git
cd personal-agent-doitall
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
agent init                         # create ~/.agent/ data directory and DB
agent --help
```

---

## Project Layout

```
src/agent/
  core/         — config, storage, artifacts, versioning, documents,
                  memory, retrieval, linking, conflicts
  cli/          — Click command groups (agent <command>)
  web/          — FastAPI app + Jinja2 templates (localhost only)
tests/          — pytest suite, one file per module
.github/
  workflows/    — CI: static-analysis.yml
```

All file paths go through `pathlib.Path`. The SQLite database lives at
`~/.agent/agent.db` (override with `AGENT_DATA_DIR` env var).

---

## Running Tests

```bash
pytest                              # all tests
pytest -q                           # quiet
pytest --cov=src/agent tests/       # with coverage report
```

All tests use a temp directory via `monkeypatch` — no shared state, no network calls.

---

## Code Style

- Formatter: none enforced yet (Ruff is in CI for critical checks).
- Type hints used throughout; aim to keep new code fully annotated.
- No bare `except:` — catch specific exceptions and log them.
- No `os.path` — use `pathlib.Path` everywhere.

---

## Where to Start

Good first contributions are marked in the **Now** tier of the [Roadmap](README.md#roadmap):

| Task                                    | Skill area        | File(s) to touch                                        |
| --------------------------------------- | ----------------- | ------------------------------------------------------- |
| CLI tests for `mem` and `link` commands | Testing           | `tests/test_cli.py`                                     |
| Retrieval unit tests                    | Testing           | `tests/test_retrieval.py` (new)                         |
| Web route integration tests             | Testing / FastAPI | `tests/test_web.py` (new), `src/agent/web/app.py`       |
| Static type checking (mypy)             | CI / types        | `.github/workflows/`, `pyproject.toml`                  |
| Backup & restore commands               | Feature / CLI     | `src/agent/cli/main.py`, new `src/agent/core/backup.py` |
| PDF/DOCX import extraction              | Feature / core    | `src/agent/core/documents.py`                           |

Pick one, create a branch, and open a pull request against `main`.

---

## Pull Request Guidelines

1. **Branch naming:** `feat/<name>`, `fix/<name>`, or `test/<name>`.
2. **Tests:** every code change should come with matching tests.
3. **Security:** run `bandit -r src` before pushing — no new issues.
4. **Deps:** run `pip-audit` if you add a new dependency.
5. **Commits:** clear, present-tense messages (`Add backup command`, not `added backup`).

---

## Security

- Web server must bind to `127.0.0.1` only (no external exposure in MVP).
- No credentials or secrets in committed files — use env vars.
- Report security concerns privately by opening a GitHub issue marked **[security]**.
