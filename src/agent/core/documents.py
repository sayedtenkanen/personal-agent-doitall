"""
Document lifecycle service.

Coordinates create/update/view/list workflows for documents (and config
artifacts) on top of the lower-level artifact, versioning, and conflict layers.

Markdown documents are stored natively as content.
PDF/DOCX imports are metadata-only: extracted text is stored for search/recall
but the original file path is recorded; no in-place editing of the binary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agent.core.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactVersion,
    _sha256,
    create_artifact,
    get_artifact_by_slug,
    get_artifact_by_id,
    get_current_version,
    list_artifacts,
    list_versions,
)
from agent.core.conflicts import ConflictRecord, check_and_record_conflict, is_stale
from agent.core.versioning import BumpKind, bump_version, get_version_content


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class WriteResult:
    artifact: Artifact
    version: ArtifactVersion
    is_conflict: bool = False
    conflict_record: Optional[ConflictRecord] = None


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create_document(
    session,
    *,
    title: str,
    slug: str,
    content: str,
    changelog: str = "Initial version",
    content_type: str = "text/markdown",
) -> WriteResult:
    """
    Create a new document artifact at v1.0.0.
    Raises ValueError if a document with the same slug already exists.
    """
    existing = get_artifact_by_slug(session, ArtifactKind.DOCUMENT, slug)
    if existing is not None:
        raise ValueError(
            f"A document with slug {slug!r} already exists (id={existing.id}). "
            "Use update_document() to create a new version."
        )

    artifact, version = create_artifact(
        session,
        kind=ArtifactKind.DOCUMENT,
        title=title,
        slug=slug,
        content=content,
        content_type=content_type,
        changelog=changelog,
    )
    return WriteResult(artifact=artifact, version=version)


# ---------------------------------------------------------------------------
# Update (version bump or conflict copy)
# ---------------------------------------------------------------------------


def update_document(
    session,
    *,
    slug: str,
    new_content: str,
    bump_kind: BumpKind,
    changelog: str,
    base_version_id: str,
    content_type: str = "text/markdown",
) -> WriteResult:
    """
    Update an existing document.

    If base_version_id matches the current version → bump to next semver.
    If stale → create a conflict copy and return WriteResult(is_conflict=True).

    Does NOT commit.  Caller controls the transaction.
    """
    artifact = get_artifact_by_slug(session, ArtifactKind.DOCUMENT, slug)
    if artifact is None:
        raise ValueError(f"No document found with slug {slug!r}.")

    if is_stale(artifact, base_version_id, session):
        record = check_and_record_conflict(
            session,
            artifact=artifact,
            base_version_id=base_version_id,
            incoming_content=new_content,
            content_type=content_type,
        )
        current_ver = get_current_version(session, artifact)
        return WriteResult(
            artifact=artifact,
            version=current_ver,  # type: ignore[arg-type]
            is_conflict=True,
            conflict_record=record,
        )

    version = bump_version(
        session,
        artifact=artifact,
        new_content=new_content,
        bump_kind=bump_kind,
        changelog=changelog,
        content_type=content_type,
    )
    return WriteResult(artifact=artifact, version=version)


# ---------------------------------------------------------------------------
# Import external file (metadata only)
# ---------------------------------------------------------------------------


def import_external_document(
    session,
    *,
    file_path: Path,
    title: Optional[str] = None,
    slug: Optional[str] = None,
    extracted_text: str = "",
    changelog: str = "Imported external document",
) -> WriteResult:
    """
    Register a PDF/DOCX (or any external file) as a metadata-only artifact.

    *extracted_text* (e.g. from pdfminer / python-docx) is stored as the
    snapshot content for search and linking purposes.
    The original *file_path* is embedded in the changelog for traceability.
    No content is edited in place.
    """
    file_path = Path(file_path).resolve()
    resolved_title = title or file_path.name
    resolved_slug = slug or _slug_from_name(file_path.stem)
    full_changelog = f"{changelog} | source={file_path}"
    content = extracted_text or f"[Imported: {file_path}]"

    return create_document(
        session,
        title=resolved_title,
        slug=resolved_slug,
        content=content,
        changelog=full_changelog,
        content_type="text/plain",
    )


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def get_document_content(
    session, slug: str, semver: Optional[str] = None
) -> Optional[str]:
    artifact = get_artifact_by_slug(session, ArtifactKind.DOCUMENT, slug)
    if artifact is None:
        return None
    return get_version_content(session, artifact, semver)


def list_documents(session, include_archived: bool = False) -> list[Artifact]:
    return list_artifacts(
        session, kind=ArtifactKind.DOCUMENT, include_archived=include_archived
    )


def get_document_history(session, slug: str) -> list[ArtifactVersion]:
    artifact = get_artifact_by_slug(session, ArtifactKind.DOCUMENT, slug)
    if artifact is None:
        return []
    return list_versions(session, artifact.id)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _slug_from_name(name: str) -> str:
    """Convert a filename stem into a safe ASCII slug."""
    import re

    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "document"
