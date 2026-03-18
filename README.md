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

## Roadmap

### Now (in progress / next engineering tasks)

- [ ] Web route integration tests
- [ ] CLI tests for `mem` and `link` command groups
- [ ] Retrieval unit tests (tokenizer, embedding cache, ranking fusion)
- [ ] Static type checking in CI with mypy
- [ ] Expand CI static analysis (full Ruff rule set + Bandit)

### Next

- [ ] Backup and restore commands (`agent backup` / `agent restore`)
- [ ] PDF/DOCX extraction pipeline on import
- [ ] Agent prompt/config versioning commands (`ArtifactKind.CONFIG`)
- [ ] SQLite FTS5 full-text search index
- [ ] Runtime input validation hardening for all CLI and web entry points
- [ ] Structured logging with error IDs (observability baseline)
- [ ] Dependency lockfile strategy for reproducible builds
- [ ] Release workflow (version tagging + changelog generation)

### Later

- [ ] Scheduled memory summarisation (local LLM / Ollama)
- [ ] LLM-assisted conflict merge suggestions
- [ ] Multi-kind artifact linking (doc ↔ memory ↔ config)
- [ ] Device sync via shared folder (Git, Dropbox, etc.)
- [ ] Web UI authentication (passphrase/token for networked use)
- [ ] Plugin/extension system for custom artifact kinds
- [ ] Structured entity extraction (NLP auto-tagging)
- [ ] Calendar/task integration (local planner layer)
- [ ] Interactive TUI (textual / prompt_toolkit dashboard)
- [ ] Export to Markdown vault (Obsidian/Logseq interop)

See [CONTRIBUTING.md](CONTRIBUTING.md) to pick up a task and contribute.
