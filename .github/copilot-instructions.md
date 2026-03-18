# Copilot Instructions — Personal Work Agent

## Project Overview

Local-first personal all-purpose work agent. Python stack, runs identically on Windows and Linux.
Core capabilities: long-term memory, topic linking, versioned documents, CLI and web interfaces.

## Stack

- Python 3.11+
- FastAPI + Jinja2 (web UI, localhost-only)
- Click (CLI)
- SQLAlchemy + SQLite (storage)
- sentence-transformers (local embeddings, offline)
- rank-bm25 (lexical retrieval)
- pathlib throughout (cross-platform paths)

## Architecture

```
src/agent/
  core/        — config, storage, artifacts, versioning, documents, memory, retrieval, linking, conflicts
  cli/         — Click command groups
  web/         — FastAPI app + Jinja2 templates
tests/         — pytest suite per module
```

## Key Conventions

- All file paths via `pathlib.Path`; never `os.path.join` or string concatenation
- SQLite DB lives in `~/.agent/agent.db` (or `AGENT_DATA_DIR` env override)
- Every artifact has a UUID, a SemVer string, and an immutable snapshot per version
- All writes require a `base_version_id`; stale writes produce a conflict copy
- Memory retention is indefinite — only archive flag, no hard deletes
- Topic links are only persisted after explicit user confirmation
- Web UI binds to `127.0.0.1` only (no auth in MVP = no external exposure)

## Completed Steps

- [x] .github/copilot-instructions.md created
