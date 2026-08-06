from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from core.utils import read_json, write_json
from evaluation.testset import load_frozen_test_set


def _read_chroma_collection_count(chroma_dir: Path, collection_name: str) -> int:
    """Read Chroma's SQLite catalog in read-only mode to avoid index mutation."""
    database_path = chroma_dir / "chroma.sqlite3"
    if not database_path.is_file():
        raise FileNotFoundError(f"Chroma catalog does not exist: {database_path}")

    connection = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        collection_row = connection.execute(
            "SELECT id FROM collections WHERE name = ?",
            (collection_name,),
        ).fetchone()
        if collection_row is None:
            raise ValueError(f"Chroma collection does not exist: {collection_name}")
        count_row = connection.execute(
            """
            SELECT COUNT(*)
            FROM embeddings AS e
            JOIN segments AS s ON s.id = e.segment_id
            WHERE s.collection = ? AND s.scope = 'METADATA'
            """,
            (collection_row[0],),
        ).fetchone()
        return int(count_row[0])
    finally:
        connection.close()


def audit_embedding_manifest(
    manifest_path: Path,
    expected_collection_name: str,
    expected_doc_ids: Iterable[str] | None = None,
    chroma_dir: Path | None = None,
) -> dict[str, Any]:
    """Audit manifest metadata and, when available, the persisted collection."""
    manifest_path = Path(manifest_path)
    payload = read_json(manifest_path)
    documents = payload.get("documents")
    if not isinstance(documents, list):
        raise ValueError(f"Embedding manifest has no valid documents list: {manifest_path}")
    if any(not isinstance(document, dict) for document in documents):
        raise ValueError(f"Embedding manifest contains a non-object document: {manifest_path}")

    document_ids = [str(document.get("paper_id", "")).strip() for document in documents]
    blank_document_ids = sum(not paper_id for paper_id in document_ids)
    duplicate_document_ids = len(document_ids) - len(set(document_ids))
    collection_name = str(payload.get("collection_name", ""))
    manifest_document_count = len(documents)

    expected_ids = {str(doc_id) for doc_id in expected_doc_ids} if expected_doc_ids is not None else None
    manifest_ids = {paper_id for paper_id in document_ids if paper_id}
    missing_expected_ids = sorted(expected_ids.difference(manifest_ids)) if expected_ids is not None else []
    unexpected_ids = sorted(manifest_ids.difference(expected_ids)) if expected_ids is not None else []

    errors: list[str] = []
    warnings: list[str] = []
    if collection_name != expected_collection_name:
        errors.append(
            f"collection_name={collection_name!r}, expected {expected_collection_name!r}"
        )
    if blank_document_ids:
        errors.append(f"{blank_document_ids} manifest documents have blank paper_id")
    if duplicate_document_ids:
        errors.append(f"{duplicate_document_ids} duplicate paper_id entries in manifest")
    if missing_expected_ids:
        errors.append(f"{len(missing_expected_ids)} cleaned paper IDs are missing from manifest")
    if unexpected_ids:
        errors.append(f"{len(unexpected_ids)} manifest paper IDs are absent from cleaned data")

    recorded_persist_value = str(payload.get("persist_path", "")).strip()
    recorded_persist_path = Path(recorded_persist_value) if recorded_persist_value else None
    runtime_persist_path = Path(chroma_dir) if chroma_dir is not None else recorded_persist_path
    if chroma_dir is not None:
        if recorded_persist_path is None:
            warnings.append("manifest persist_path is blank; the runtime Chroma path was used")
        else:
            try:
                paths_differ = recorded_persist_path.resolve() != runtime_persist_path.resolve()
            except OSError:
                paths_differ = True
                warnings.append("manifest persist_path could not be resolved on this machine")
            if paths_differ:
                warnings.append(
                    "manifest persist_path differs from the runtime Chroma path; "
                    "the runtime path was used for collection audit"
                )

    collection_document_count: int | None = None
    collection_error: str | None = None
    if runtime_persist_path is not None and runtime_persist_path.exists():
        try:
            collection_document_count = _read_chroma_collection_count(
                runtime_persist_path,
                collection_name,
            )
            if collection_document_count != manifest_document_count:
                errors.append(
                    "collection document count does not match manifest: "
                    f"{collection_document_count} != {manifest_document_count}"
                )
        except Exception as exc:  # pragma: no cover - backend-specific failure
            collection_error = str(exc)
            errors.append(f"could not audit Chroma collection: {exc}")
    else:
        collection_error = f"Chroma path does not exist: {runtime_persist_path}"
        errors.append(collection_error)

    return {
        "status": "pass" if not errors else "fail",
        "manifest_path": str(manifest_path),
        "backend": payload.get("backend"),
        "embedding_model": payload.get("embedding_model"),
        "collection_name": collection_name,
        "expected_collection_name": expected_collection_name,
        "collection_name_matches": collection_name == expected_collection_name,
        "manifest_document_count": manifest_document_count,
        "expected_document_count": len(expected_ids) if expected_ids is not None else None,
        "manifest_ids_match_expected": expected_ids is not None
        and manifest_ids == expected_ids,
        "collection_document_count": collection_document_count,
        "unique_manifest_document_ids": len(manifest_ids),
        "blank_document_ids": blank_document_ids,
        "duplicate_document_ids": duplicate_document_ids,
        "missing_expected_doc_ids": missing_expected_ids,
        "unexpected_doc_ids": unexpected_ids,
        "recorded_persist_path": str(recorded_persist_path) if recorded_persist_path else None,
        "runtime_persist_path": str(runtime_persist_path),
        "collection_error": collection_error,
        "errors": errors,
        "warnings": warnings,
    }


def build_baseline_artifact_audit(
    manifest_path: Path,
    test_set_path: Path,
    output_path: Path,
    expected_collection_name: str,
    expected_doc_ids: Iterable[str],
    chroma_dir: Path,
) -> dict[str, Any]:
    """Persist one baseline audit joining clean IDs, index, and frozen test set."""
    expected_ids = {str(doc_id) for doc_id in expected_doc_ids}
    index_audit = audit_embedding_manifest(
        manifest_path=manifest_path,
        expected_collection_name=expected_collection_name,
        expected_doc_ids=expected_ids,
        chroma_dir=chroma_dir,
    )
    manifest = read_json(Path(manifest_path))
    manifest_doc_ids = {
        str(document["paper_id"])
        for document in manifest.get("documents", [])
        if document.get("paper_id")
    }
    _, test_set_audit = load_frozen_test_set(
        Path(test_set_path),
        available_doc_ids=manifest_doc_ids,
    )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "pass" if index_audit["status"] == "pass" else "fail",
        "clean_document_count": len(expected_ids),
        "index": index_audit,
        "test_set": test_set_audit,
    }
    write_json(Path(output_path), payload)
    return payload
