"""Bounded, read-only job-board connectors and provenance-aware imports.

The provider adapters deliberately map into a small model similar to JobSpy's
public ``JobPost`` output (source, title, company, location, URL, description
and source ID) without depending on that scraping package.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit

from .db import audit, connect, deserialize, now, one, serialize
from .services import ValidationError, clean_url, source_key


HTTP_TIMEOUT_SECONDS = 15
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_FETCH_LIMIT = 1000
MAX_IMPORT_RECORDS = 10_000
_BOARD_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,98}[A-Za-z0-9])?$")
_AVAILABILITY = {"unknown", "listed", "closed"}
_PROVIDERS = {
    "greenhouse": "boards-api.greenhouse.io",
    "lever": "api.lever.co",
}


class SourceError(ValueError):
    """A safe, user-facing provider or payload error."""


def ensure_source_schema(db=None):
    """Create the immutable source snapshot table, using ``db`` if supplied."""
    owns_connection = db is None
    if owns_connection:
        with connect() as connection:
            _ensure_source_schema(connection)
        return
    _ensure_source_schema(db)


def _ensure_source_schema(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS job_source_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
            source_key TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            data TEXT NOT NULL,
            retrieved_at TEXT NOT NULL,
            availability TEXT NOT NULL CHECK (availability IN ('unknown','listed','closed')),
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_job_source_snapshots_job
            ON job_source_snapshots(job_id, id)
        """
    )
    db.execute(
        """
        CREATE TRIGGER IF NOT EXISTS job_source_snapshots_no_update
        BEFORE UPDATE ON job_source_snapshots
        BEGIN
            SELECT RAISE(ABORT, 'job source snapshots are immutable');
        END
        """
    )
    db.execute(
        """
        CREATE TRIGGER IF NOT EXISTS job_source_snapshots_no_delete
        BEFORE DELETE ON job_source_snapshots
        BEGIN
            SELECT RAISE(ABORT, 'job source snapshots are immutable');
        END
        """
    )


def _parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("retrieved_at must be a non-empty ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError("retrieved_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValidationError("retrieved_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def _content_hash(record: dict) -> str:
    content = {
        key: value
        for key, value in record.items()
        if key not in {"retrieved_at", "imported_at", "content_hash", "cache_hit"}
    }
    try:
        encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Job record must contain JSON-compatible values") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalize_published(value, field: str = "published_at") -> str | None:
    """Accept a date or a timezone-aware ISO timestamp; keep the given precision."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be an ISO-8601 date or timestamp string")
    text = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError as exc:
            raise ValidationError(f"{field} must be an ISO-8601 date") from exc
        return text
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field} must be an ISO-8601 date or timestamp") from exc
    if parsed.tzinfo is None:
        raise ValidationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _normalize_record(raw, imported_at: str, default_retrieved_at: str | None = None) -> dict:
    if not isinstance(raw, dict):
        raise ValidationError("Expected JSON object")
    record = dict(raw)
    for field in ("source", "title", "company", "description"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"Missing required field: {field}")
        record[field] = value.strip()

    source_id = record.get("source_id", "")
    if source_id is None:
        source_id = ""
    if isinstance(source_id, bool) or not isinstance(source_id, (str, int)):
        raise ValidationError("source_id must be a string or integer")
    record["source_id"] = str(source_id).strip()

    for field in ("url", "location"):
        value = record.get(field, "")
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ValidationError(f"{field} must be a string")
        record[field] = value.strip()
    record["url"] = clean_url(record["url"])

    availability = record.get("availability", "unknown")
    if availability not in _AVAILABILITY:
        raise ValidationError("availability must be unknown|listed|closed")
    record["availability"] = availability

    # Publication time belongs to the employer's posting, not to our retrieval.
    # Missing values stay absent so "unknown" can never masquerade as fresh.
    record["published_at"] = _normalize_published(record.get("published_at"))
    if "listed_at" in record:
        listed = _normalize_published(record.get("listed_at"), "listed_at")
        if listed:
            record["listed_at"] = listed
        else:
            record.pop("listed_at", None)

    retrieved_at = record.get("retrieved_at", default_retrieved_at)
    if retrieved_at is None or (isinstance(retrieved_at, str) and not retrieved_at.strip()):
        record["retrieved_at"] = None
    else:
        parsed = _parse_timestamp(retrieved_at)
        if parsed > datetime.now(timezone.utc):
            raise ValidationError("retrieved_at cannot be in the future")
        record["retrieved_at"] = parsed.isoformat(timespec="seconds")
    record["imported_at"] = imported_at
    record["content_hash"] = _content_hash(record)
    # Validate arbitrary provider-specific fields before any transaction starts.
    try:
        serialize(record)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Job record must contain JSON-compatible values") from exc
    return record


def import_records(records: list[dict]) -> dict:
    """Validate and atomically add, update, or re-observe normalized jobs.

    ``duplicate`` means the content hash was unchanged. Its ``retrieved_at`` is
    still advanced in the current jobs row, but no immutable snapshot is added.
    ``job_ids`` follows input order and therefore may contain repeated IDs.
    """
    if not isinstance(records, list):
        raise ValidationError("records must be a list")
    if len(records) > MAX_IMPORT_RECORDS:
        raise ValidationError(f"Limit {MAX_IMPORT_RECORDS:,} jobs per import")
    batch_time = now()
    normalized = []
    for index, record in enumerate(records, start=1):
        try:
            normalized.append(_normalize_record(record, batch_time))
        except ValueError as exc:
            raise ValidationError(f"Record {index}: {exc}") from exc

    result = {"added": 0, "updated": 0, "duplicate": 0, "job_ids": []}
    with connect() as db:
        ensure_source_schema(db)
        for record_index, record in enumerate(normalized, start=1):
            key = source_key(record)
            existing = db.execute("SELECT * FROM jobs WHERE source_key=?", (key,)).fetchone()
            if existing is None:
                cursor = db.execute(
                    "INSERT INTO jobs(source_key,title,company,url,data,created_at) VALUES (?,?,?,?,?,?)",
                    (key, record["title"], record["company"], record["url"], serialize(record), now()),
                )
                job_id = cursor.lastrowid
                _insert_snapshot(db, job_id, key, record)
                result["added"] += 1
                audit(db, "jobs.imported", "jobs", job_id, record["source"])
            else:
                job_id = existing["id"]
                previous = deserialize(existing["data"])
                previous_retrieved = previous.get("retrieved_at")
                incoming_retrieved = record.get("retrieved_at")
                if previous_retrieved:
                    previous_time = _parse_timestamp(previous_retrieved)
                    incoming_time = _parse_timestamp(incoming_retrieved) if incoming_retrieved else None
                    if incoming_time is None or incoming_time < previous_time:
                        raise ValidationError(
                            f"Record {record_index}: stale or undated source observation for {key}; "
                            f"current retrieved_at is {previous['retrieved_at']}"
                        )
                previous_hash = previous.get("content_hash") or _content_hash(previous)
                changed = previous_hash != record["content_hash"]
                db.execute(
                    "UPDATE jobs SET title=?,company=?,url=?,data=? WHERE id=?",
                    (record["title"], record["company"], record["url"], serialize(record), job_id),
                )
                if changed:
                    _insert_snapshot(db, job_id, key, record)
                    result["updated"] += 1
                    audit(db, "jobs.source_updated", "jobs", job_id, record["source"])
                else:
                    result["duplicate"] += 1
                    audit(db, "jobs.source_retrieved", "jobs", job_id, record["source"])
            result["job_ids"].append(job_id)
    return result


def _insert_snapshot(db, job_id: int, key: str, record: dict):
    db.execute(
        """INSERT INTO job_source_snapshots
           (job_id,source_key,content_hash,data,retrieved_at,availability,created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (
            job_id,
            key,
            record["content_hash"],
            serialize(record),
            record["retrieved_at"] or "",
            record["availability"],
            now(),
        ),
    )


def list_snapshots(job_id: int) -> list[dict]:
    """Return immutable snapshots oldest first for one existing job."""
    with connect() as db:
        ensure_source_schema(db)
        one(db, "jobs", int(job_id))
        rows = db.execute(
            "SELECT * FROM job_source_snapshots WHERE job_id=? ORDER BY id", (int(job_id),)
        ).fetchall()
        return [
            {
                "id": row["id"],
                "job_id": row["job_id"],
                "source_key": row["source_key"],
                "content_hash": row["content_hash"],
                "data": deserialize(row["data"]),
                "retrieved_at": row["retrieved_at"],
                "availability": row["availability"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]


def freshness(job_data: dict, max_age_days: float = 30) -> dict:
    """Classify source recency without implying that an absent job is closed."""
    if not isinstance(job_data, dict):
        raise ValidationError("job_data must be an object")
    if isinstance(max_age_days, bool) or not isinstance(max_age_days, (int, float)) or max_age_days < 0:
        raise ValidationError("max_age_days must be a non-negative number")
    value = job_data.get("retrieved_at")
    if not value:
        return {"status": "unknown", "retrieved_at": None, "age_days": None, "max_age_days": max_age_days}
    retrieved = _parse_timestamp(value)
    current = datetime.now(timezone.utc)
    if retrieved > current:
        return {
            "status": "unknown",
            "retrieved_at": retrieved.isoformat(timespec="seconds"),
            "age_days": None,
            "max_age_days": max_age_days,
            "reason": "future_timestamp",
        }
    age_days = (current - retrieved).total_seconds() / 86400
    return {
        "status": "fresh" if age_days <= max_age_days else "stale",
        "retrieved_at": retrieved.isoformat(timespec="seconds"),
        "age_days": round(age_days, 3),
        "max_age_days": max_age_days,
    }


class _ExactHostRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_host: str):
        super().__init__()
        self.allowed_host = allowed_host

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urlsplit(newurl)
        if parts.scheme != "https" or parts.netloc.casefold() != self.allowed_host:
            raise SourceError("Provider redirect left the approved HTTPS host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _http_json(url: str, allowed_host: str):
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc.casefold() != allowed_host:
        raise SourceError("Provider URL is outside the approved HTTPS host")
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "CareerOS/0.1 public-job-reader"},
        method="GET",
    )
    opener = urllib.request.build_opener(_ExactHostRedirectHandler(allowed_host))
    try:
        with opener.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            final = urlsplit(final_url)
            if final.scheme != "https" or final.netloc.casefold() != allowed_host:
                raise SourceError("Provider response came from an unapproved host")
            length = response.headers.get("Content-Length")
            if length:
                try:
                    declared_length = int(length)
                except ValueError:
                    declared_length = None
                if declared_length is not None and declared_length > MAX_RESPONSE_BYTES:
                    raise SourceError("Provider response exceeds 5 MB")
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except SourceError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceError(f"Provider request failed: {getattr(exc, 'reason', exc)}") from exc
    if len(payload) > MAX_RESPONSE_BYTES:
        raise SourceError("Provider response exceeds 5 MB")
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceError("Provider returned invalid JSON") from exc


def _validate_fetch_args(provider, board, company, limit):
    if not isinstance(provider, str) or provider.strip().casefold() not in _PROVIDERS:
        raise ValidationError("provider must be greenhouse or lever")
    provider = provider.strip().casefold()
    if not isinstance(board, str) or not _BOARD_RE.fullmatch(board):
        raise ValidationError("board must be a 1-100 character slug using letters, digits, _ or -")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_FETCH_LIMIT:
        raise ValidationError("limit must be an integer from 1 to 1000")
    if company is None:
        company = board
    if not isinstance(company, str) or not company.strip():
        raise ValidationError("company must be a non-empty string")
    return provider, board, company.strip(), limit


class _PlainTextHTMLParser(HTMLParser):
    _BLOCK_TAGS = {"br", "div", "p", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6"}
    _IGNORED_TAGS = {"script", "style"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._IGNORED_TAGS:
            self.ignored_depth += 1
        elif not self.ignored_depth and tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._IGNORED_TAGS and self.ignored_depth:
            self.ignored_depth -= 1
        elif not self.ignored_depth and tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.ignored_depth:
            self.parts.append(data)


def _plain_text(value) -> str:
    """Convert trusted-as-data provider HTML/entities into readable text."""
    if not isinstance(value, str):
        return ""
    parser = _PlainTextHTMLParser()
    try:
        parser.feed(html.unescape(html.unescape(value)))
        parser.close()
    except (ValueError, AssertionError):
        return " ".join(html.unescape(value).split())
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _greenhouse_records(payload, board: str, company: str, retrieved_at: str, limit: int):
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise SourceError("Greenhouse payload must contain a jobs array")
    records = []
    for index, item in enumerate(payload["jobs"][:limit], start=1):
        if not isinstance(item, dict):
            raise SourceError(f"Greenhouse job {index} must be an object")
        location = item.get("location") or {}
        if not isinstance(location, dict):
            raise SourceError(f"Greenhouse job {index} location must be an object")
        raw_description = item.get("content")
        records.append(
            {
                "source": "greenhouse",
                "source_id": item.get("id"),
                "source_board": board,
                "title": item.get("title"),
                "company": company,
                "description": _plain_text(raw_description),
                "description_raw_html": raw_description,
                "url": item.get("absolute_url") or "",
                "location": location.get("name") or "",
                "availability": "listed",
                "retrieved_at": retrieved_at,
                "provider_updated_at": item.get("updated_at"),
                "language": item.get("language"),
            }
        )
    return records


def _lever_description(item: dict, index: int) -> tuple[str, str]:
    raw_parts = []
    plain_parts = []
    description_raw = item.get("description")
    description_plain = item.get("descriptionPlain")
    if description_raw is not None and not isinstance(description_raw, str):
        raise SourceError(f"Lever job {index} description must be a string")
    if description_plain is not None and not isinstance(description_plain, str):
        raise SourceError(f"Lever job {index} descriptionPlain must be a string")
    if description_raw:
        raw_parts.append(description_raw)
    base = description_plain.strip() if description_plain else _plain_text(description_raw)
    if base:
        plain_parts.append(base)

    lists = item.get("lists") or []
    if not isinstance(lists, list):
        raise SourceError(f"Lever job {index} lists must be an array")
    for list_index, section in enumerate(lists, start=1):
        if not isinstance(section, dict):
            raise SourceError(f"Lever job {index} list {list_index} must be an object")
        heading = section.get("text") or ""
        content = section.get("content") or ""
        if not isinstance(heading, str) or not isinstance(content, str):
            raise SourceError(f"Lever job {index} list {list_index} fields must be strings")
        if content:
            raw_parts.append(content)
        section_text = _plain_text(content)
        combined = "\n".join(part for part in (heading.strip(), section_text) if part)
        if combined:
            plain_parts.append(combined)

    additional_raw = item.get("additional")
    additional_plain = item.get("additionalPlain")
    if additional_raw is not None and not isinstance(additional_raw, str):
        raise SourceError(f"Lever job {index} additional must be a string")
    if additional_plain is not None and not isinstance(additional_plain, str):
        raise SourceError(f"Lever job {index} additionalPlain must be a string")
    if additional_raw:
        raw_parts.append(additional_raw)
    closing = additional_plain.strip() if additional_plain else _plain_text(additional_raw)
    if closing:
        plain_parts.append(closing)
    return "\n\n".join(plain_parts), "\n".join(raw_parts)


def _lever_records(payload, board: str, company: str, retrieved_at: str, limit: int):
    if not isinstance(payload, list):
        raise SourceError("Lever payload must be an array")
    records = []
    for index, item in enumerate(payload[:limit], start=1):
        if not isinstance(item, dict):
            raise SourceError(f"Lever job {index} must be an object")
        categories = item.get("categories") or {}
        if not isinstance(categories, dict):
            raise SourceError(f"Lever job {index} categories must be an object")
        description, raw_description = _lever_description(item, index)
        records.append(
            {
                "source": "lever",
                "source_id": item.get("id"),
                "source_board": board,
                "title": item.get("text"),
                "company": company,
                "description": description,
                "description_raw_html": raw_description,
                "url": item.get("hostedUrl") or "",
                "location": categories.get("location") or "",
                "availability": "listed",
                "retrieved_at": retrieved_at,
                "workplace_type": item.get("workplaceType"),
                "employment_type": categories.get("commitment"),
                "team": categories.get("team"),
                "department": categories.get("department"),
                "all_locations": categories.get("allLocations"),
            }
        )
    return records


def fetch_jobs(provider, board, company=None, limit=100) -> dict:
    """Fetch and normalize public listings without writing to the database."""
    provider, board, company, limit = _validate_fetch_args(provider, board, company, limit)
    retrieved_at = now()
    host = _PROVIDERS[provider]
    if provider == "greenhouse":
        url = f"https://{host}/v1/boards/{board}/jobs?content=true"
        payload = _http_json(url, host)
        records = _greenhouse_records(payload, board, company, retrieved_at, limit)
        available_count = payload.get("meta", {}).get("total") if isinstance(payload.get("meta"), dict) else None
        if not isinstance(available_count, int):
            available_count = len(payload["jobs"])
    else:
        query = urlencode({"mode": "json", "limit": limit})
        url = f"https://{host}/v0/postings/{board}?{query}"
        payload = _http_json(url, host)
        records = _lever_records(payload, board, company, retrieved_at, limit)
        available_count = len(payload)

    # Run the same strict checks as import while remaining read-only.
    normalized = []
    for index, record in enumerate(records, start=1):
        try:
            normalized.append(_normalize_record(record, retrieved_at, default_retrieved_at=retrieved_at))
        except ValueError as exc:
            raise SourceError(f"{provider} job {index}: {exc}") from exc
    return {
        "provider": provider,
        "board": board,
        "company": company,
        "request_url": url,
        "retrieved_at": retrieved_at,
        "available_count": available_count,
        "returned_count": len(normalized),
        "limit": limit,
        "records": normalized,
    }


def sync_jobs(provider, board, company=None, limit=100) -> dict:
    """Fetch a public board and atomically import the returned records."""
    fetched = fetch_jobs(provider, board, company=company, limit=limit)
    imported = import_records(fetched["records"])
    retrieval = {key: value for key, value in fetched.items() if key != "records"}
    return {**imported, "retrieval": retrieval}
