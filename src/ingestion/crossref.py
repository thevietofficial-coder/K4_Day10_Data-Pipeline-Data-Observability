from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from core.config import Settings
from core.utils import ensure_parent, normalize_whitespace, read_json, write_json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DOI_PREFIX_RE = re.compile(
    r"^https?://(doi\.org|dx\.doi\.org)/",
    re.IGNORECASE,
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def normalize_doi(raw: str) -> str:
    """Lowercase, strip common URL prefixes and whitespace from a DOI string."""
    cleaned = _DOI_PREFIX_RE.sub("", raw.strip())
    return cleaned.strip().lower()


def parse_date_parts(date_obj: dict[str, Any] | None) -> str:
    """Convert a Crossref ``date-parts`` object to an ISO date string.

    Crossref dates look like ``{"date-parts": [[2023, 5, 14]]}``.  The inner
    list may contain 1 (year only), 2 (year-month), or 3 (full date) elements.
    Returns ``""`` when *date_obj* is ``None`` or has no usable parts.
    """
    if not date_obj:
        return ""
    parts_list = date_obj.get("date-parts")
    if not parts_list or not parts_list[0]:
        return ""
    parts = parts_list[0]
    year = int(parts[0])
    month = int(parts[1]) if len(parts) > 1 else 1
    day = int(parts[2]) if len(parts) > 2 else 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def _extract_authors(item: dict[str, Any]) -> list[str]:
    """Build a list of ``"Given Family"`` author names from a Crossref item."""
    authors: list[str] = []
    for author in item.get("author", []):
        given = author.get("given", "").strip()
        family = author.get("family", "").strip()
        name = f"{given} {family}".strip()
        if name:
            authors.append(name)
    return authors


def _extract_pdf_url(item: dict[str, Any]) -> str:
    """Return the first PDF link from a Crossref item, or ``""``."""
    for link in item.get("link", []):
        if link.get("content-type") == "application/pdf":
            url = link.get("URL", "")
            if url:
                return url
    return ""


def _best_published_date(item: dict[str, Any]) -> str:
    """Pick the most informative published date from a Crossref item."""
    for key in ("published-print", "published-online", "published", "created"):
        result = parse_date_parts(item.get(key))
        if result:
            return result
    return ""


def _strip_html(text: str) -> str:
    """Remove HTML/XML tags (e.g. ``<jats:p>``) and normalise whitespace."""
    return normalize_whitespace(_HTML_TAG_RE.sub(" ", text))


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_crossref_payload(payload: dict[str, Any]) -> list[PaperRecord]:
    """Parse a Crossref ``/works`` API response into a list of PaperRecord.

    Iterates ``payload["message"]["items"]``, extracts fields with safe
    ``.get()`` access, and skips any item that has no DOI (logging a warning).
    """
    message = payload.get("message", {})
    items: list[dict[str, Any]] = message.get("items", [])
    records: list[PaperRecord] = []

    for idx, item in enumerate(items):
        raw_doi = item.get("DOI", "")
        if not raw_doi:
            logger.warning("Skipping item at index %d: no DOI field.", idx)
            continue

        paper_id = normalize_doi(raw_doi)

        # Title — Crossref stores as a list of strings
        title_list = item.get("title", [])
        title = normalize_whitespace(title_list[0]) if title_list else ""
        if not title:
            logger.warning("Item %s has no title.", paper_id)

        # Abstract
        abstract_raw = item.get("abstract", "")
        summary = _strip_html(abstract_raw) if abstract_raw else ""
        if not summary:
            logger.warning("Item %s has no abstract.", paper_id)

        # Authors
        authors = _extract_authors(item)
        if not authors:
            logger.warning("Item %s has no authors.", paper_id)

        # Categories / subjects
        categories: list[str] = item.get("subject", [])
        primary_category = categories[0] if categories else ""

        # Dates
        published = _best_published_date(item)
        updated = parse_date_parts(item.get("deposited"))

        # URLs
        abs_url = f"https://doi.org/{paper_id}"
        pdf_url = _extract_pdf_url(item)

        # Comment — use funder info or empty
        funders = item.get("funder", [])
        if funders:
            funder_names = [f.get("name", "") for f in funders if f.get("name")]
            comment = f"Funded by: {', '.join(funder_names)}" if funder_names else ""
        else:
            comment = ""

        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=summary,
                authors=authors,
                categories=categories,
                primary_category=primary_category,
                published=published,
                updated=updated,
                abs_url=abs_url,
                pdf_url=pdf_url,
                comment=comment,
            )
        )

    logger.info(
        "Parsed %d records from %d items (%d skipped).",
        len(records),
        len(items),
        len(items) - len(records),
    )
    return records


# ---------------------------------------------------------------------------
# HTTP fetch with retry / backoff
# ---------------------------------------------------------------------------

class _RetryableHTTPError(Exception):
    """Raised when the Crossref API returns a retryable status code."""

    def __init__(self, status_code: int, retry_after: float | None = None):
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(f"HTTP {status_code}")


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, _RetryableHTTPError)


def _wait_with_retry_after(retry_state: RetryCallState) -> float:
    """Use Retry-After header if available, otherwise fall back to exponential."""
    exc = retry_state.outcome and retry_state.outcome.exception()
    if isinstance(exc, _RetryableHTTPError) and exc.retry_after is not None:
        return exc.retry_after
    # Exponential backoff: 1s, 2s, 4s, ... capped at 60s, plus jitter
    exp = min(2 ** (retry_state.attempt_number - 1), 60)
    return exp + (time.monotonic() % 1)  # simple jitter


def _build_retry(max_retries: int):
    """Build a tenacity retry decorator configured for Crossref HTTP calls."""
    return retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(max_retries),
        wait=_wait_with_retry_after,
        reraise=True,
    )


def _do_fetch(settings: Settings) -> requests.Response:
    """Perform the actual HTTP GET to Crossref, raising retryable errors."""
    params: dict[str, Any] = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
        "mailto": settings.crossref_mailto,
    }
    headers = {
        "User-Agent": f"Day10-DataPipeline-Lab/0.1 (mailto:{settings.crossref_mailto})",
    }

    logger.info(
        "Fetching Crossref: %s  params=%s",
        settings.crossref_base_url,
        {k: v for k, v in params.items() if k != "mailto"},
    )

    resp = requests.get(
        settings.crossref_base_url,
        params=params,
        headers=headers,
        timeout=settings.crossref_timeout,
    )

    if resp.status_code in (429, 503):
        retry_after_raw = resp.headers.get("Retry-After")
        retry_after = float(retry_after_raw) if retry_after_raw else None
        logger.warning(
            "Crossref returned %d. Retry-After: %s",
            resp.status_code,
            retry_after_raw,
        )
        raise _RetryableHTTPError(resp.status_code, retry_after)

    resp.raise_for_status()
    return resp


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch papers from Crossref, persist raw response, and parse into records.

    When ``settings.refresh_source`` is ``False`` and a cached raw-records
    snapshot already exists, the cached version is loaded instead of calling
    the API. If it does not exist, a RuntimeError is raised to guarantee no live
    fetch happens mid-run.
    """
    # Use cache when available and refresh not forced
    if not settings.refresh_source:
        if settings.paths.raw_records_json.exists():
            logger.info("Loading cached raw records from %s", settings.paths.raw_records_json)
            return load_raw_records(settings.paths.raw_records_json)
        else:
            raise RuntimeError(
                f"Frozen snapshot not found at {settings.paths.raw_records_json}. "
                "Live fetch is disabled when refresh_source is False to guarantee consistent evaluation."
            )

    # Wrap _do_fetch with retry configured from settings
    retryable_fetch = _build_retry(settings.crossref_max_retries)(_do_fetch)
    resp: requests.Response = retryable_fetch(settings)

    # Persist raw response BEFORE parsing (exact bytes from the wire)
    ensure_parent(settings.paths.raw_api_response)
    settings.paths.raw_api_response.write_bytes(resp.content)
    logger.info("Saved raw API response to %s", settings.paths.raw_api_response)

    # Parse
    payload: dict[str, Any] = resp.json()
    records = parse_crossref_payload(payload)

    # Persist parsed records
    write_json(
        settings.paths.raw_records_json,
        [asdict(r) for r in records],
    )
    logger.info("Saved %d parsed records to %s", len(records), settings.paths.raw_records_json)

    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Load a previously-saved JSON snapshot and reconstruct PaperRecord objects."""
    data = read_json(path)
    records: list[PaperRecord] = []
    for entry in data:
        records.append(
            PaperRecord(
                paper_id=entry["paper_id"],
                title=entry["title"],
                summary=entry["summary"],
                authors=entry["authors"],
                categories=entry["categories"],
                primary_category=entry["primary_category"],
                published=entry["published"],
                updated=entry["updated"],
                abs_url=entry["abs_url"],
                pdf_url=entry["pdf_url"],
                comment=entry["comment"],
            )
        )
    logger.info("Loaded %d records from %s", len(records), path)
    return records
