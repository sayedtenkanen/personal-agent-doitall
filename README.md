# Personal Work Agent

Local-first personal all-purpose work agent. Runs identically on Windows and Linux.

## Features

- **Long-term memory** — captures conversation context; recalls prior topics automatically
- **Topic linking** — agent suggests related topics; you confirm before links are persisted
- **Versioned documents** — markdown-native lifecycle with user-controlled SemVer bumps (MAJOR/MINOR/PATCH)
- **Conflict detection** — stale concurrent edits become conflict copies for manual merge
- **Hybrid retrieval** — lexical (BM25) + semantic (local embeddings) ranked recall
- **CLI + Web UI** — full feature parity; web binds to `127.0.0.1` only
- **Artifact versioning** — documents, memory entries, and agent prompts/config all versioned
- **Optional backup** — sync-folder export/import with integrity checksums

## Quick Start

```bash
pip install -e ".[dev]"
agent --help
agent web       # starts FastAPI UI at http://127.0.0.1:8000
```

## Data Location

All data lives in `~/.agent/` by default. Override with `AGENT_DATA_DIR` environment variable.

```
~/.agent/
  agent.db        — SQLite database (all artifacts, versions, memory, links)
  snapshots/      — immutable content snapshots per version
  backup/         — sync-folder export bundles
```

## Environment Variables

| Variable            | Default            | Description                |
| ------------------- | ------------------ | -------------------------- |
| `AGENT_DATA_DIR`    | `~/.agent`         | Root data directory        |
| `AGENT_EMBED_MODEL` | `all-MiniLM-L6-v2` | Local embedding model name |
| `AGENT_HOST`        | `127.0.0.1`        | Web server bind address    |
| `AGENT_PORT`        | `8000`             | Web server port            |

## Architecture

```
src/agent/
  core/        — config, storage, artifacts, versioning, documents,
                 memory, retrieval, linking, conflicts
  cli/         — Click command groups
  web/         — FastAPI app + Jinja2 templates
tests/         — pytest suite per module
```

## Running Tests

```bash
pytest
pytest --cov=agent tests/
```
