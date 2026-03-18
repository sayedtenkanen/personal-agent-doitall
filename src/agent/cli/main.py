"""
CLI entry point — `agent` command.

Command groups
--------------
  agent doc       — document lifecycle (create, update, view, history, list)
  agent mem       — memory capture and search
  agent link      — topic-link suggestion and confirmation
  agent conflict  — list and resolve conflict copies
  agent web       — start the FastAPI web server
  agent init      — bootstrap data directory and database
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich import print as rprint

console = Console()
error_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _get_session():
    """Lazy import to avoid loading SQLAlchemy on every --help call."""
    from agent.core.storage import get_session, init_db

    init_db()
    return get_session()


def _require_arg(value, name: str):
    if not value:
        raise click.UsageError(f"{name} is required.")
    return value


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(package_name="personal-agent")
def cli():
    """Personal Work Agent — local-first, cross-platform."""


# ===========================================================================
# agent init
# ===========================================================================


@cli.command()
def init():
    """Bootstrap the data directory and database (idempotent)."""
    from agent.core.config import settings
    from agent.core.storage import init_db

    settings.ensure_dirs()
    init_db()
    console.print(f"[green]✓[/green] Data directory: {settings.data_dir}")
    console.print(f"[green]✓[/green] Database:       {settings.db_path}")
    console.print("[green]✓[/green] Ready.")


# ===========================================================================
# agent doc
# ===========================================================================


@cli.group()
def doc():
    """Document lifecycle commands."""


@doc.command("create")
@click.option(
    "--slug", "-s", required=True, help="Short unique identifier (e.g. onboarding-v1)"
)
@click.option("--title", "-t", required=True, help="Human-readable title")
@click.option(
    "--file",
    "-f",
    "file_path",
    type=click.Path(exists=True, path_type=Path),
    help="Read initial content from this file (markdown)",
)
@click.option("--message", "-m", default="Initial version", help="Changelog message")
def doc_create(slug: str, title: str, file_path: Path | None, message: str):
    """Create a new document artifact at v1.0.0."""
    if file_path:
        content = file_path.read_text(encoding="utf-8")
    else:
        # Open $EDITOR for inline authoring.
        content = click.edit("", require_save=True) or ""
        if not content.strip():
            raise click.UsageError("No content provided.")

    from agent.core.documents import create_document

    with _get_session() as session:
        result = create_document(
            session, title=title, slug=slug, content=content, changelog=message
        )
    console.print(
        f"[green]Created[/green] {slug!r} "
        f"v{result.version.semver} (id={result.artifact.id[:8]})"
    )


@doc.command("update")
@click.option("--slug", "-s", required=True, help="Document slug")
@click.option(
    "--file",
    "-f",
    "file_path",
    type=click.Path(exists=True, path_type=Path),
    help="New content from file",
)
@click.option(
    "--bump",
    "-b",
    type=click.Choice(["major", "minor", "patch"], case_sensitive=False),
    default=None,
    help="SemVer bump kind (prompted if omitted)",
)
@click.option("--message", "-m", default=None, help="Changelog (prompted if omitted)")
@click.option(
    "--base-version-id",
    "--base",
    "base_version_id",
    required=True,
    help="Version ID you are basing this update on (from `agent doc view --slug <slug>`)",
)
def doc_update(
    slug: str,
    file_path: Path | None,
    bump: str | None,
    message: str | None,
    base_version_id: str,
):
    """Update an existing document (create new version or flag conflict)."""
    if file_path:
        new_content = file_path.read_text(encoding="utf-8")
    else:
        # Load current content as editor seed.
        from agent.core.documents import get_document_content

        with _get_session() as session:
            current = get_document_content(session, slug)
        new_content = click.edit(current or "", require_save=True) or ""
        if not new_content.strip():
            raise click.UsageError("No content provided.")

    if bump is None:
        bump = click.prompt(
            "Bump kind",
            type=click.Choice(["major", "minor", "patch"], case_sensitive=False),
            default="minor",
        )
    if message is None:
        message = click.prompt("Changelog message")

    from agent.core.documents import update_document

    with _get_session() as session:
        result = update_document(
            session,
            slug=slug,
            new_content=new_content,
            bump_kind=bump,  # type: ignore[arg-type]
            changelog=message,
            base_version_id=base_version_id,
        )

    if result.is_conflict:
        console.print(
            f"[yellow]⚠ Conflict detected[/yellow] — your changes were saved as a conflict copy.\n"
            f"  Conflict record id: {result.conflict_record.id}\n"
            f"  Run [bold]agent conflict list[/bold] to review and merge."
        )
    else:
        console.print(f"[green]Updated[/green] {slug!r} → v{result.version.semver}")


@doc.command("view")
@click.option("--slug", "-s", required=True)
@click.option("--version", "-v", "semver", default=None, help="Specific semver to view")
def doc_view(slug: str, semver: str | None):
    """Print document content and metadata."""
    from agent.core.documents import get_document_content, get_document_history
    from agent.core.artifacts import (
        get_artifact_by_slug,
        ArtifactKind,
        get_current_version,
    )

    with _get_session() as session:
        artifact = get_artifact_by_slug(session, ArtifactKind.DOCUMENT, slug)
        if artifact is None:
            error_console.print(f"[red]Not found:[/red] {slug!r}")
            sys.exit(1)

        current_ver = get_current_version(session, artifact)
        content = get_document_content(session, slug, semver)

    console.print(f"[bold]{artifact.title}[/bold]  (slug={slug})")
    console.print(
        f"Current version : v{artifact.current_version}  id={current_ver.id if current_ver else '—'}"
    )
    console.rule()
    console.print(content or "[dim](no content)[/dim]")


@doc.command("history")
@click.option("--slug", "-s", required=True)
def doc_history(slug: str):
    """Show version history for a document."""
    from agent.core.documents import get_document_history
    from agent.core.artifacts import get_artifact_by_slug, ArtifactKind

    with _get_session() as session:
        artifact = get_artifact_by_slug(session, ArtifactKind.DOCUMENT, slug)
        if artifact is None:
            error_console.print(f"[red]Not found:[/red] {slug!r}")
            sys.exit(1)
        versions = get_document_history(session, slug)

    table = Table(title=f"History — {slug}")
    table.add_column("SemVer", style="cyan")
    table.add_column("Bump", style="magenta")
    table.add_column("Changelog")
    table.add_column("Version ID", style="dim")
    table.add_column("Date", style="dim")

    for v in versions:
        table.add_row(
            v.semver,
            v.bump_kind or "—",
            v.changelog or "—",
            v.id[:8],
            str(v.created_at)[:19],
        )
    console.print(table)


@doc.command("list")
def doc_list():
    """List all documents."""
    from agent.core.documents import list_documents

    with _get_session() as session:
        docs = list_documents(session)

    table = Table(title="Documents")
    table.add_column("Slug", style="cyan")
    table.add_column("Title")
    table.add_column("Version", style="green")
    table.add_column("Updated", style="dim")

    for d in docs:
        table.add_row(d.slug, d.title, d.current_version or "—", str(d.updated_at)[:19])
    console.print(table)


# ===========================================================================
# agent mem
# ===========================================================================


@cli.group()
def mem():
    """Memory capture and search commands."""


@mem.command("add")
@click.argument("text")
@click.option("--tags", "-t", default="", help="Comma-separated tags")
@click.option("--entities", "-e", default="", help="Comma-separated entity names")
def mem_add(text: str, tags: str, entities: str):
    """Capture a memory entry."""
    from agent.core.memory import add_memory

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    ent_list = [e.strip() for e in entities.split(",") if e.strip()]
    with _get_session() as session:
        entry = add_memory(session, text=text, tags=tag_list, entities=ent_list)
    console.print(f"[green]Memory saved[/green] id={entry.id[:8]}")


@mem.command("search")
@click.argument("query")
@click.option("--top", "-k", default=5, show_default=True, help="Number of results")
def mem_search(query: str, top: int):
    """Search memory with hybrid BM25 + semantic retrieval."""
    from agent.core.retrieval import search

    with _get_session() as session:
        results = search(session, query, top_k=top)

    if not results:
        console.print("[dim]No results found.[/dim]")
        return

    table = Table(title=f"Memory search: {query!r}")
    table.add_column("#", style="dim")
    table.add_column("Text")
    table.add_column("Tags", style="cyan")
    table.add_column("BM25", style="yellow")
    table.add_column("Sem", style="magenta")
    table.add_column("RRF", style="green")

    for r in results:
        table.add_row(
            str(r.rank),
            r.entry.text[:80],
            r.entry.tags[:40] or "—",
            f"{r.bm25_score:.3f}",
            f"{r.semantic_score:.3f}",
            f"{r.rrf_score:.4f}",
        )
    console.print(table)


@mem.command("list")
@click.option("--limit", "-n", default=20, show_default=True)
def mem_list(limit: int):
    """List recent memory entries."""
    from agent.core.memory import list_memory

    with _get_session() as session:
        entries = list_memory(session, limit=limit)

    table = Table(title="Memory entries")
    table.add_column("ID", style="dim")
    table.add_column("Text")
    table.add_column("Tags", style="cyan")
    table.add_column("Created", style="dim")

    for e in entries:
        table.add_row(e.id[:8], e.text[:80], e.tags[:40] or "—", str(e.created_at)[:19])
    console.print(table)


# ===========================================================================
# agent link
# ===========================================================================


@cli.group()
def link():
    """Topic-link suggestion and confirmation commands."""


@link.command("suggest")
@click.option("--artifact-id", "-a", required=True, help="Source artifact ID")
@click.option("--top", "-k", default=5, show_default=True)
def link_suggest(artifact_id: str, top: int):
    """Generate link suggestions for an artifact (does NOT persist until confirmed)."""
    from agent.core.linking import suggest_links

    with _get_session() as session:
        suggestions = suggest_links(session, source_artifact_id=artifact_id, top_k=top)

    if not suggestions:
        console.print("[dim]No suggestions generated.[/dim]")
        return

    table = Table(title="Link suggestions (pending confirmation)")
    table.add_column("Suggestion ID", style="dim")
    table.add_column("Target ID", style="cyan")
    table.add_column("Relation")
    table.add_column("Confidence", style="green")
    table.add_column("Evidence")

    for s in suggestions:
        table.add_row(
            s.id[:8],
            s.target_id[:8],
            s.relation,
            f"{s.confidence:.4f}",
            s.evidence or "—",
        )
    console.print(table)
    console.print(
        "\nRun [bold]agent link confirm --id <suggestion-id>[/bold] to accept."
    )


@link.command("pending")
def link_pending():
    """List all pending link suggestions."""
    from agent.core.linking import list_pending_suggestions

    with _get_session() as session:
        suggestions = list_pending_suggestions(session)

    if not suggestions:
        console.print("[dim]No pending suggestions.[/dim]")
        return

    table = Table(title="Pending link suggestions")
    table.add_column("ID", style="dim")
    table.add_column("Source", style="cyan")
    table.add_column("Target", style="cyan")
    table.add_column("Confidence", style="green")

    for s in suggestions:
        table.add_row(s.id[:8], s.source_id[:8], s.target_id[:8], f"{s.confidence:.4f}")
    console.print(table)


@link.command("confirm")
@click.option("--id", "suggestion_id", required=True, help="Suggestion ID (8+ chars)")
def link_confirm(suggestion_id: str):
    """Confirm a suggested link (persists the TopicLink)."""
    from agent.core.linking import confirm_suggestion, SuggestedLink
    from sqlalchemy import select

    with _get_session() as session:
        # Look up by prefix if short ID was given.
        from sqlalchemy import select

        stmt = select(SuggestedLink).where(SuggestedLink.id.startswith(suggestion_id))
        sug = session.execute(stmt).scalar_one_or_none()
        if sug is None:
            error_console.print(f"[red]Not found:[/red] {suggestion_id!r}")
            sys.exit(1)
        link_obj = confirm_suggestion(session, sug.id)

    if link_obj:
        console.print(
            f"[green]Link confirmed[/green] {link_obj.source_id[:8]}→{link_obj.target_id[:8]}"
        )
    else:
        console.print("[yellow]Already actioned or not found.[/yellow]")


@link.command("reject")
@click.option("--id", "suggestion_id", required=True)
def link_reject(suggestion_id: str):
    """Reject a suggested link."""
    from agent.core.linking import reject_suggestion, SuggestedLink
    from sqlalchemy import select

    with _get_session() as session:
        stmt = select(SuggestedLink).where(SuggestedLink.id.startswith(suggestion_id))
        sug = session.execute(stmt).scalar_one_or_none()
        if sug is None:
            error_console.print(f"[red]Not found:[/red] {suggestion_id!r}")
            sys.exit(1)
        ok = reject_suggestion(session, sug.id)

    console.print(
        "[green]Rejected.[/green]" if ok else "[yellow]Already actioned.[/yellow]"
    )


# ===========================================================================
# agent conflict
# ===========================================================================


@cli.group()
def conflict():
    """Conflict detection and resolution commands."""


@conflict.command("list")
def conflict_list():
    """List all open (unresolved) conflict copies."""
    from agent.core.conflicts import list_open_conflicts

    with _get_session() as session:
        records = list_open_conflicts(session)

    if not records:
        console.print("[dim]No open conflicts.[/dim]")
        return

    table = Table(title="Open conflicts")
    table.add_column("ID", style="dim")
    table.add_column("Original Artifact", style="cyan")
    table.add_column("Conflict Copy", style="yellow")
    table.add_column("Base Version ID", style="dim")
    table.add_column("Created", style="dim")

    for r in records:
        table.add_row(
            r.id[:8],
            r.original_artifact_id[:8],
            r.conflict_artifact_id[:8],
            r.base_version_id[:8],
            str(r.created_at)[:19],
        )
    console.print(table)
    console.print(
        "\nUse [bold]agent conflict resolve --id <id>[/bold] after merging manually."
    )


@conflict.command("resolve")
@click.option("--id", "conflict_id", required=True)
@click.option("--note", "-n", default="", help="Resolution note")
def conflict_resolve(conflict_id: str, note: str):
    """Mark a conflict record as resolved."""
    from agent.core.conflicts import ConflictRecord, resolve_conflict
    from sqlalchemy import select

    with _get_session() as session:
        stmt = select(ConflictRecord).where(ConflictRecord.id.startswith(conflict_id))
        record = session.execute(stmt).scalar_one_or_none()
        if record is None:
            error_console.print(f"[red]Not found:[/red] {conflict_id!r}")
            sys.exit(1)
        resolve_conflict(session, conflict_record=record, resolution_note=note)

    console.print(f"[green]Conflict {conflict_id[:8]} marked resolved.[/green]")


# ===========================================================================
# agent web
# ===========================================================================


@cli.command()
@click.option("--host", default=None, help="Bind host (default: 127.0.0.1)")
@click.option("--port", default=None, type=int, help="Port (default: 8000)")
@click.option(
    "--reload", is_flag=True, default=False, help="Auto-reload on code changes"
)
def web(host: str | None, port: int | None, reload: bool):
    """Start the FastAPI web server (localhost only)."""
    import uvicorn
    from agent.core.config import settings
    from agent.core.storage import init_db

    init_db()

    bind_host = host or settings.host
    bind_port = port or settings.port

    if bind_host not in ("127.0.0.1", "localhost"):
        raise click.UsageError(
            f"Web server must bind to localhost only for security. Got: {bind_host!r}"
        )

    console.print(
        f"[green]Starting web server[/green] → http://{bind_host}:{bind_port}"
    )
    uvicorn.run(
        "agent.web.app:app",
        host=bind_host,
        port=bind_port,
        reload=reload,
        log_level=settings.log_level,
    )
