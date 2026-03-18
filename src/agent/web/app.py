"""
FastAPI web application — localhost-only personal work agent UI.

Binds to 127.0.0.1 by default. No authentication in MVP.
Routes:
  GET  /                     — dashboard / home
  GET  /documents            — document list
  GET  /documents/{slug}     — view document (current version)
  GET  /documents/{slug}/history — version history
  POST /documents/create     — create new document
  POST /documents/{slug}/update — update existing document
  GET  /memory               — memory list + search
  POST /memory/add           — capture a memory entry
  GET  /links                — pending link suggestions
  POST /links/{id}/confirm   — confirm a suggestion
  POST /links/{id}/reject    — reject a suggestion
  GET  /conflicts            — open conflict records
  POST /conflicts/{id}/resolve — resolve a conflict
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agent.core.storage import init_db, get_session

# Initialise DB at startup.
init_db()

app = FastAPI(title="Personal Work Agent", docs_url=None, redoc_url=None)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(request: Request, **extra) -> dict:
    return {"request": request, **extra}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    with get_session() as session:
        from agent.core.documents import list_documents
        from agent.core.conflicts import list_open_conflicts
        from agent.core.linking import list_pending_suggestions
        from agent.core.memory import list_memory

        docs = list_documents(session)
        open_conflicts = list_open_conflicts(session)
        pending_links = list_pending_suggestions(session)
        recent_memory = list_memory(session, limit=5)

    return templates.TemplateResponse(
        "index.html",
        _ctx(
            request,
            doc_count=len(docs),
            conflict_count=len(open_conflicts),
            pending_link_count=len(pending_links),
            recent_memory=recent_memory,
        ),
    )


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


@app.get("/documents", response_class=HTMLResponse)
async def documents_list(request: Request):
    with get_session() as session:
        from agent.core.documents import list_documents

        docs = list_documents(session)
    return templates.TemplateResponse("documents.html", _ctx(request, docs=docs))


@app.get("/documents/new", response_class=HTMLResponse)
async def documents_new_form(request: Request):
    return templates.TemplateResponse("document_create.html", _ctx(request))


@app.post("/documents/create")
async def documents_create(
    request: Request,
    title: str = Form(...),
    slug: str = Form(...),
    content: str = Form(...),
    changelog: str = Form("Initial version"),
):
    from agent.core.documents import create_document

    try:
        with get_session() as session:
            create_document(
                session, title=title, slug=slug, content=content, changelog=changelog
            )
    except ValueError as exc:
        return templates.TemplateResponse(
            "document_create.html",
            _ctx(request, error=str(exc), title=title, slug=slug, content=content),
            status_code=400,
        )
    return RedirectResponse(f"/documents/{slug}", status_code=303)


@app.get("/documents/{slug}", response_class=HTMLResponse)
async def document_view(request: Request, slug: str, version: str | None = None):
    from agent.core.artifacts import (
        get_artifact_by_slug,
        ArtifactKind,
        get_current_version,
    )
    from agent.core.documents import get_document_content
    from agent.core.linking import list_confirmed_links

    with get_session() as session:
        artifact = get_artifact_by_slug(session, ArtifactKind.DOCUMENT, slug)
        if artifact is None:
            raise HTTPException(status_code=404, detail=f"Document {slug!r} not found")
        current_ver = get_current_version(session, artifact)
        content = get_document_content(session, slug, version)
        links = list_confirmed_links(session, artifact.id)

    return templates.TemplateResponse(
        "document_view.html",
        _ctx(
            request,
            artifact=artifact,
            current_ver=current_ver,
            content=content,
            links=links,
            viewing_version=version,
        ),
    )


@app.get("/documents/{slug}/history", response_class=HTMLResponse)
async def document_history(request: Request, slug: str):
    from agent.core.artifacts import get_artifact_by_slug, ArtifactKind
    from agent.core.documents import get_document_history

    with get_session() as session:
        artifact = get_artifact_by_slug(session, ArtifactKind.DOCUMENT, slug)
        if artifact is None:
            raise HTTPException(status_code=404, detail=f"Document {slug!r} not found")
        versions = get_document_history(session, slug)

    return templates.TemplateResponse(
        "document_history.html",
        _ctx(request, artifact=artifact, versions=versions),
    )


@app.get("/documents/{slug}/edit", response_class=HTMLResponse)
async def document_edit_form(request: Request, slug: str):
    from agent.core.artifacts import (
        get_artifact_by_slug,
        ArtifactKind,
        get_current_version,
    )
    from agent.core.documents import get_document_content

    with get_session() as session:
        artifact = get_artifact_by_slug(session, ArtifactKind.DOCUMENT, slug)
        if artifact is None:
            raise HTTPException(status_code=404, detail=f"Document {slug!r} not found")
        current_ver = get_current_version(session, artifact)
        content = get_document_content(session, slug)

    return templates.TemplateResponse(
        "document_edit.html",
        _ctx(request, artifact=artifact, current_ver=current_ver, content=content),
    )


@app.post("/documents/{slug}/update")
async def document_update(
    request: Request,
    slug: str,
    content: str = Form(...),
    bump_kind: str = Form(...),
    changelog: str = Form(...),
    base_version_id: str = Form(...),
):
    from agent.core.documents import update_document

    with get_session() as session:
        result = update_document(
            session,
            slug=slug,
            new_content=content,
            bump_kind=bump_kind,  # type: ignore[arg-type]
            changelog=changelog,
            base_version_id=base_version_id,
        )

    if result.is_conflict:
        return RedirectResponse("/conflicts?flash=conflict", status_code=303)
    return RedirectResponse(f"/documents/{slug}", status_code=303)


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


@app.get("/memory", response_class=HTMLResponse)
async def memory_list(request: Request, q: str = ""):
    from agent.core.memory import list_memory
    from agent.core.retrieval import search

    with get_session() as session:
        if q.strip():
            results = search(session, q, top_k=20)
            entries = [r.entry for r in results]
        else:
            entries = list_memory(session, limit=50)

    return templates.TemplateResponse(
        "memory.html", _ctx(request, entries=entries, query=q)
    )


@app.post("/memory/add")
async def memory_add(
    request: Request,
    text: str = Form(...),
    tags: str = Form(""),
    entities: str = Form(""),
):
    from agent.core.memory import add_memory

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    ent_list = [e.strip() for e in entities.split(",") if e.strip()]
    with get_session() as session:
        add_memory(session, text=text, tags=tag_list, entities=ent_list)
    return RedirectResponse("/memory", status_code=303)


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------


@app.get("/links", response_class=HTMLResponse)
async def links_list(request: Request):
    from agent.core.linking import list_pending_suggestions

    with get_session() as session:
        suggestions = list_pending_suggestions(session)

    return templates.TemplateResponse(
        "links.html", _ctx(request, suggestions=suggestions)
    )


@app.post("/links/{suggestion_id}/confirm")
async def links_confirm(suggestion_id: str):
    from agent.core.linking import confirm_suggestion, SuggestedLink
    from sqlalchemy import select

    with get_session() as session:
        stmt = select(SuggestedLink).where(SuggestedLink.id.startswith(suggestion_id))
        sug = session.execute(stmt).scalar_one_or_none()
        if sug is None:
            raise HTTPException(status_code=404)
        confirm_suggestion(session, sug.id)

    return RedirectResponse("/links", status_code=303)


@app.post("/links/{suggestion_id}/reject")
async def links_reject(suggestion_id: str):
    from agent.core.linking import reject_suggestion, SuggestedLink
    from sqlalchemy import select

    with get_session() as session:
        stmt = select(SuggestedLink).where(SuggestedLink.id.startswith(suggestion_id))
        sug = session.execute(stmt).scalar_one_or_none()
        if sug is None:
            raise HTTPException(status_code=404)
        reject_suggestion(session, sug.id)

    return RedirectResponse("/links", status_code=303)


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------


@app.get("/conflicts", response_class=HTMLResponse)
async def conflicts_list(request: Request, flash: str = ""):
    from agent.core.conflicts import list_open_conflicts

    with get_session() as session:
        records = list_open_conflicts(session)

    return templates.TemplateResponse(
        "conflicts.html",
        _ctx(request, records=records, flash=flash),
    )


@app.post("/conflicts/{conflict_id}/resolve")
async def conflicts_resolve(conflict_id: str, note: str = Form("")):
    from agent.core.conflicts import ConflictRecord, resolve_conflict
    from sqlalchemy import select

    with get_session() as session:
        stmt = select(ConflictRecord).where(ConflictRecord.id.startswith(conflict_id))
        record = session.execute(stmt).scalar_one_or_none()
        if record is None:
            raise HTTPException(status_code=404)
        resolve_conflict(session, conflict_record=record, resolution_note=note)

    return RedirectResponse("/conflicts", status_code=303)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


@app.get("/chat", response_class=HTMLResponse)
async def chat_list(request: Request):
    from agent.core.chat import list_sessions
    from agent.core.llm import is_available
    from agent.core import config as _config

    with get_session() as session:
        sessions = list_sessions(session)

    return templates.TemplateResponse(
        "chat.html",
        _ctx(
            request,
            sessions=sessions,
            llm_available=is_available(),
            llm_provider=_config.settings.llm_provider,
            llm_model=_config.settings.llm_model,
        ),
    )


@app.post("/chat/new")
async def chat_new(title: str = Form("New Chat")):
    from agent.core.chat import create_session

    with get_session() as session:
        chat_session = create_session(session, title=title)
        session_id = chat_session.id

    return RedirectResponse(f"/chat/{session_id}", status_code=303)


@app.get("/chat/{session_id}", response_class=HTMLResponse)
async def chat_session_view(request: Request, session_id: str):
    from agent.core.chat import get_session_by_id, get_messages
    from agent.core.llm import is_available
    from agent.core import config as _config

    with get_session() as session:
        chat_session = get_session_by_id(session, session_id)
        if chat_session is None:
            raise HTTPException(status_code=404, detail="Chat session not found")
        messages = get_messages(session, session_id)

    return templates.TemplateResponse(
        "chat_session.html",
        _ctx(
            request,
            chat_session=chat_session,
            messages=messages,
            llm_available=is_available(),
            llm_provider=_config.settings.llm_provider,
            llm_model=_config.settings.llm_model,
        ),
    )


@app.post("/chat/{session_id}/send")
async def chat_send(request: Request, session_id: str):
    """Receive a user message, call the LLM, persist both, return JSON."""
    from fastapi.responses import JSONResponse
    from agent.core.chat import get_session_by_id, add_message
    from agent.core.llm import get_reply, build_system_prompt, LLMError, is_available
    from agent.core.chat import get_messages

    body = await request.json()
    user_text: str = (body.get("message") or "").strip()
    if not user_text:
        return JSONResponse({"error": "Empty message."}, status_code=400)

    if not is_available():
        return JSONResponse(
            {"error": "No LLM provider configured. Set AGENT_LLM_PROVIDER."},
            status_code=503,
        )

    with get_session() as session:
        chat_session = get_session_by_id(session, session_id)
        if chat_session is None:
            raise HTTPException(status_code=404)

        # Persist user message.
        add_message(session, session_id=session_id, role="user", content=user_text)

        # Build messages list for LLM.
        history = get_messages(session, session_id)
        system_prompt = build_system_prompt(session)

        llm_messages = [{"role": "system", "content": system_prompt}]
        llm_messages += [{"role": m.role, "content": m.content} for m in history]

        try:
            reply = get_reply(llm_messages)
        except LLMError as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)

        # Persist assistant reply.
        add_message(session, session_id=session_id, role="assistant", content=reply)

        # Update session title from first user message if still default.
        if chat_session.title == "New Chat":
            chat_session.title = user_text[:60]
            session.add(chat_session)

    return JSONResponse({"reply": reply})


@app.post("/chat/{session_id}/delete")
async def chat_delete(session_id: str):
    from agent.core.chat import delete_session

    with get_session() as session:
        delete_session(session, session_id)

    return RedirectResponse("/chat", status_code=303)
