# Personal Agent - The Agent DoItAll

Local-first personal all-purpose work agent. Runs identically on Windows and Linux.

## Features

- **Long-term memory** — captures conversation context; recalls prior topics automatically
- **Topic linking** — agent suggests related topics; you confirm before links are persisted
- **Versioned documents** — markdown-native lifecycle with user-controlled SemVer bumps (MAJOR/MINOR/PATCH)
- **Conflict detection** — stale concurrent edits become conflict copies for manual merge
- **Hybrid retrieval** — lexical (BM25) + semantic (local embeddings) ranked recall
- **CLI + Web UI** — full feature parity; web binds to `127.0.0.1` only
- **LLM chat** — interactive chat sessions backed by Ollama (local) or any OpenAI-compatible API; memory context injected automatically
- **Artifact versioning** — documents, memory entries, and agent prompts/config all versioned

## Quick Start

```bash
pip install -e ".[dev]"
cp .env.example .env    # optional: configure LLM provider etc.
agent init      # create ~/.agent/ data directory and database
agent --help
agent web       # starts FastAPI UI at http://127.0.0.1:8000
```

### Using the LLM chat

```bash
# Local Ollama (install from https://ollama.com)
AGENT_LLM_PROVIDER=ollama AGENT_LLM_MODEL=llama3.2 agent chat

# OpenAI or any compatible API
AGENT_LLM_PROVIDER=openai \
  AGENT_LLM_BASE_URL=https://api.openai.com/v1 \
  AGENT_LLM_API_KEY=sk-... \
  agent chat

# Resume an existing session
agent chat --session-id <id>

# Or use the web UI: http://127.0.0.1:8000/chat
```

## Data Location

All data lives in `~/.agent/` by default. Override with `AGENT_DATA_DIR` environment variable.

```
~/.agent/
  agent.db     — SQLite database (artifacts, versions, memory, links, chat)
  snapshots/   — immutable content snapshots per version
```

## Environment Variables

| Variable             | Default                  | Description                            |
| -------------------- | ------------------------ | -------------------------------------- |
| `AGENT_DATA_DIR`     | `~/.agent`               | Root data directory                    |
| `AGENT_EMBED_MODEL`  | `all-MiniLM-L6-v2`       | Local embedding model name             |
| `AGENT_HOST`         | `127.0.0.1`              | Web server bind address                |
| `AGENT_PORT`         | `8000`                   | Web server port                        |
| `AGENT_LLM_PROVIDER` | `none`                   | `none` \| `ollama` \| `openai`         |
| `AGENT_LLM_MODEL`    | `llama3.2`               | Model name (e.g. `gpt-4o-mini`)        |
| `AGENT_LLM_BASE_URL` | `http://localhost:11434` | Ollama or OpenAI-compatible base URL   |
| `AGENT_LLM_API_KEY`  | _(empty)_                | API key — required for OpenAI provider |

## Architecture

```
src/agent/
  core/        — config, storage, artifacts, versioning, documents,
                 memory, retrieval, linking, conflicts, chat, llm
  cli/         — Click command groups
  web/         — FastAPI app + Jinja2 templates
tests/         — pytest suite per module
```

## Running Tests

```bash
pytest                              # all tests
pytest --cov=src/agent tests/       # with coverage report
```

## Roadmap

### Now (in progress / next engineering tasks)

- [ ] Web route integration tests (`httpx.AsyncClient`)
- [ ] CLI tests for `mem` and `link` command groups
- [ ] LLM provider tests (mocked HTTP for `_ollama_chat` / `_openai_chat`)
- [ ] Static type checking in CI with mypy
- [ ] Expand CI: add Bandit security checks and full Ruff rule set

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

- [ ] Scheduled memory summarization (local LLM / Ollama)
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
