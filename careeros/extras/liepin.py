"""Optional extension: bounded job-search-only client for Liepin's open endpoint.

This module is NOT loaded by default. It only runs after the caller sets
``CAREEROS_ENABLE_LIEPIN=1``; see ``careeros/extras/__init__.py`` and
``docs/LIEPIN_INTEGRATION.md``.

Scope is deliberately narrow:

- Only the search endpoint is exposed. No resume read, no resume edit, no application.
- The user's own credential comes from the environment and never appears in output.
- Search cards are leads, never full JDs; an HTTP 200 is not treated as success.

Using a platform endpoint from a third-party client is governed by that platform's
own terms. Enabling this extension is the user's decision and the user's
responsibility; the project makes no claim that such use is permitted.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.parse import urlsplit, urlunsplit

from ..db import PROJECT_ROOT
from ..services import ValidationError

ENDPOINT = "https://open-agent.liepin.com/mcp/search-job"
MAX_BYTES = 2 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward the account token to another URL.


def normalize(data, query, fetched_at):
    if not isinstance(data, dict) or type(data.get("code")) is not int or data["code"] != 0:
        return None
    payload = data.get("data")
    rows = payload.get("list") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) > 1000:
        return None
    records = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        if any(not isinstance(row.get(k), str) or not row[k].strip() for k in ("jobName", "company", "jobDetailUrl")):
            return None
        try:
            url = urlsplit(row["jobDetailUrl"])
            if url.scheme != "https" or url.hostname != "www.liepin.com" or url.username or url.password or url.port:
                return None
        except ValueError:
            return None
        if not url.path.startswith("/job/") or not url.path.endswith(".shtml"):
            return None
        fields = ("location", "salary", "education", "workYears", "industry")
        if any(not isinstance(row.get(k, ""), str) for k in fields):
            return None
        records.append({"provider": "liepin", "title": row["jobName"], "company": row["company"],
                        "url": urlunsplit((url.scheme, url.netloc, url.path, "", "")),
                        "location": row.get("location", ""), "query": query,
                        "summary": "；".join(row.get(k, "") for k in fields[1:] if row.get(k)),
                        "discovery_method": "official_api", "discovered_at": fetched_at,
                        "salary": row.get("salary", ""), "education": row.get("education", ""),
                        "experience": row.get("workYears", "")})
    return records


def validated_result(data, metadata, limit):
    records = normalize(data, metadata["query"], metadata["fetched_at"])
    if records is None:
        return metadata
    return {**metadata, "executed": True, "status": "SEARCH_VERIFIED", "returned_count": len(records),
            "records": records[:limit], "note": "Official search cards, not full JDs or exact keyword matches. Availability unknown."}


def search(query, location="", limit=10, refresh=False):
    if not isinstance(query, str) or not query.strip() or len(query) > 120:
        raise ValidationError("query must be nonempty text of at most 120 characters")
    if not isinstance(location, str) or len(location) > 80:
        raise ValidationError("location must be text of at most 80 characters")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValidationError("limit must be 1..100")
    token = os.environ.get("LIEPIN_USER_TOKEN", "").strip()
    if not token:
        return {"provider": "liepin", "executed": False, "status": "AUTH_REQUIRED",
                "auth_url": "https://www.liepin.com/mcp/auth",
                "setup": "scripts/liepin.ps1 -Setup", "scope": "job_search_only"}
    if len(token) > 8192 or not token.isascii() or any(ord(c) < 33 for c in token):
        raise ValidationError("Invalid credential format; re-enter locally")
    payload = {"jobName": query.strip(), "page": 0}
    if location.strip():
        payload["address"] = location.strip()
    # Account-separated cache; no credential or hash of the credential is output.
    key = hashlib.sha256((token + json.dumps(payload, sort_keys=True)).encode()).hexdigest()
    root = Path(os.environ.get("CAREEROS_LIEPIN_CACHE", PROJECT_ROOT / "data/private/liepin-search"))
    cache = root / (key + ".json")
    stamp = datetime.now(timezone.utc)
    if not refresh and cache.is_file() and 0 <= stamp.timestamp() - cache.stat().st_mtime < 900:
        metadata = json.loads(cache.read_text(encoding="utf-8"))["metadata"]
        data = json.loads(Path(metadata["response_path"]).read_text(encoding="utf-8"))
        return validated_result(data, {**metadata, "cache_hit": True, "requested_local_limit": limit}, limit)
    request = Request(ENDPOINT, data=json.dumps(payload).encode("utf-8"), method="POST",
                      headers={"x-user-token": token, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValidationError("Liepin response exceeds 2 MiB")
            if "application/json" not in response.headers.get("Content-Type", "").lower():
                raise ValidationError("Liepin did not return JSON; no jobs imported")
        data = json.loads(raw)
    except HTTPError as exc:
        status = "AUTH_REQUIRED" if exc.code in (401, 403) else "REQUEST_FAILED"
        return {"provider": "liepin", "executed": False, "status": status, "http_status": exc.code}
    except (URLError, TimeoutError, OSError, ValueError):
        # Server bodies / exception details can echo credentials. Never print them.
        raise ValidationError("Liepin request failed or returned invalid data; no jobs imported") from None
    # Do not mistake HTTP 200 (possibly a business error) for valid job results.
    root.mkdir(parents=True, exist_ok=True)
    response_path = root / (key + ".response.json")
    response_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = {"provider": "liepin", "executed": False, "request_sent": True,
                "status": "RESPONSE_REQUIRES_VALIDATION", "cache_hit": False,
                "fetched_at": stamp.isoformat(timespec="seconds"), "response_path": str(response_path.resolve()),
                "query": query.strip(), "location": location.strip(), "scope": "first_result_page",
                "requested_local_limit": limit, "imported": 0,
                "note": "HTTP response received; validate business status and result schema before importing. No pagination performed."}
    cache.write_text(json.dumps({"metadata": metadata}), encoding="utf-8")
    return validated_result(data, metadata, limit)
