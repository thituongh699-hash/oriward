"""Bounded public-HTML job leads from the zhiye.page aggregator.

This module never logs in, calls private board APIs, or visits an employer URL.
Search results are deliberately small leads; full descriptions are retrieved
only when a caller explicitly requests one aggregate detail page.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit

from .db import database_path, now
from .sources import SourceError


HOST = "zhiye.page"
BASE_URL = f"https://{HOST}"
ROBOTS_URL = f"{BASE_URL}/robots.txt"
HTTP_TIMEOUT_SECONDS = 15
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MIN_REQUEST_INTERVAL_SECONDS = 2.0
SEARCH_TTL = timedelta(minutes=15)
DETAIL_TTL = timedelta(hours=24)
ROBOTS_TTL = timedelta(hours=24)
USER_AGENT = "Oriward/0.2.0 public-job-reader"
_JOB_PATH_RE = re.compile(r"^/jobs/(job_[A-Za-z0-9]+)$")
_CHALLENGE_MARKERS = (
    "cf-chl-",
    "captcha",
    "verify you are human",
    "checking your browser",
    "人机验证",
    "访问验证",
    "安全验证",
)
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_last_request_at = 0.0
_rate_lock = threading.Lock()


class _SameHostRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_origin(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _validate_origin(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname is None or parts.hostname.casefold() != HOST:
        raise SourceError("zhiye.page request left the approved HTTPS host")
    if parts.port not in (None, 443) or parts.username is not None or parts.password is not None:
        raise SourceError("zhiye.page URL contains an unapproved authority")


def _cache_root() -> Path:
    from .legacy import environment
    configured = environment("ORIWARD_CACHE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return database_path().parent / "cache" / "public-search"


def _cache_paths(kind: str, url: str) -> tuple[Path, Path]:
    key = hashlib.sha256(f"{kind}\0{url}".encode("utf-8")).hexdigest()
    root = _cache_root()
    return root / f"{kind}-{key}.html", root / f"{kind}-{key}.json"


def _read_cache(kind: str, url: str, ttl: timedelta) -> tuple[str, str, str] | None:
    body_path, meta_path = _cache_paths(kind, url)
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        body_bytes = body_path.read_bytes()
        fetched = datetime.fromisoformat(str(meta["fetched_at"]).replace("Z", "+00:00"))
        current = datetime.now(timezone.utc)
        if fetched.tzinfo is None:
            return None
        fetched = fetched.astimezone(timezone.utc)
        if fetched > current or current - fetched > ttl:
            return None
        if meta.get("url") != url or len(body_bytes) > MAX_RESPONSE_BYTES:
            return None
        digest = hashlib.sha256(body_bytes).hexdigest()
        if digest != meta.get("sha256"):
            return None
        return body_bytes.decode("utf-8"), meta["fetched_at"], digest
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False)
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _write_cache(kind: str, url: str, body: str, fetched_at: str) -> str:
    body_path, meta_path = _cache_paths(kind, url)
    encoded = body.encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    meta = json.dumps(
        {"url": url, "fetched_at": fetched_at, "sha256": digest},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    _atomic_write(body_path, encoded)
    _atomic_write(meta_path, meta)
    return digest


def _download(url: str, accept: str) -> str:
    global _last_request_at
    _validate_origin(url)
    with _rate_lock:
        wait = MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        request = urllib.request.Request(
            url,
            headers={"Accept": accept, "User-Agent": USER_AGENT},
            method="GET",
        )
        opener = urllib.request.build_opener(_SameHostRedirectHandler())
        try:
            with opener.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                _validate_origin(response.geturl())
                declared = response.headers.get("Content-Length")
                if declared:
                    try:
                        declared_length = int(declared)
                    except ValueError:
                        declared_length = None
                    if declared_length is not None and declared_length > MAX_RESPONSE_BYTES:
                        raise SourceError("zhiye.page response exceeds 2 MB")
                payload = response.read(MAX_RESPONSE_BYTES + 1)
        except SourceError:
            raise
        except urllib.error.HTTPError as exc:
            raise SourceError(f"zhiye.page request failed with HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SourceError(f"zhiye.page request failed: {getattr(exc, 'reason', exc)}") from exc
        finally:
            _last_request_at = time.monotonic()
    if len(payload) > MAX_RESPONSE_BYTES:
        raise SourceError("zhiye.page response exceeds 2 MB")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceError("zhiye.page returned non-UTF-8 text") from exc


def _robots_allows(url: str) -> None:
    cached = _read_cache("robots", ROBOTS_URL, ROBOTS_TTL)
    if cached is None:
        body = _download(ROBOTS_URL, "text/plain")
        fetched_at = now()
    else:
        body = cached[0]
    lowered = body.casefold()
    looks_html = re.search(r"<(?:!doctype\s+html|html|head|body|title)\b", lowered) is not None
    if looks_html or any(marker in lowered for marker in _CHALLENGE_MARKERS):
        raise SourceError("zhiye.page robots.txt returned HTML or a challenge page")
    if cached is None:
        _write_cache("robots", ROBOTS_URL, body, fetched_at)
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(ROBOTS_URL)
    parser.parse(body.splitlines())
    if not parser.can_fetch(USER_AGENT, url):
        raise SourceError("zhiye.page robots.txt disallows this request")


def _get_page(url: str, kind: str, ttl: timedelta, refresh: bool) -> tuple[str, str, str, bool]:
    if not refresh:
        cached = _read_cache(kind, url, ttl)
        if cached is not None:
            if any(marker in cached[0].casefold() for marker in _CHALLENGE_MARKERS):
                raise SourceError("zhiye.page returned a challenge page; manual access may be required")
            return cached[0], cached[1], cached[2], True
    _robots_allows(url)
    body = _download(url, "text/html,application/xhtml+xml")
    lowered = body.casefold()
    if any(marker in lowered for marker in _CHALLENGE_MARKERS):
        raise SourceError("zhiye.page returned a challenge page; manual access may be required")
    fetched_at = now()
    digest = _write_cache(kind, url, body, fetched_at)
    return body, fetched_at, digest, False


def _classes(attrs) -> set[str]:
    values = dict(attrs).get("class", "")
    return {part.casefold() for part in values.split()}


def _clean(parts: list[str]) -> str:
    return " ".join(" ".join(parts).split())


class _SearchParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cards: list[dict] = []
        self.card: dict | None = None
        self.card_depth = 0
        self.capture: str | None = None
        self.capture_depth = 0
        self.parts: list[str] = []
        self.saw_search_form = False
        self.saw_query_input = False

    def handle_starttag(self, tag, attrs):
        classes = _classes(attrs)
        attr = dict(attrs)
        if tag == "form" and "filter-form" in classes:
            self.saw_search_form = True
        if tag == "input" and attr.get("name") == "q":
            self.saw_query_input = True
        if self.card is None and tag == "a" and "job-card" in classes:
            self.card = {"href": attr.get("href", ""), "tags": [], "all": []}
            self.card_depth = 1
            return
        if self.card is None:
            return
        if tag in _VOID_TAGS:
            return
        self.card_depth += 1
        field = None
        if tag == "h2":
            field = "title"
        elif "freshness" in classes:
            field = "freshness"
        elif "tag" in classes:
            field = "tag"
        elif any(name in classes for name in ("company-label", "company-name", "company-title")):
            field = "company"
        elif any(name in classes for name in ("summary", "description", "job-summary")):
            field = "summary"
        if field and self.capture is None:
            self.capture, self.capture_depth, self.parts = field, self.card_depth, []

    def handle_data(self, data):
        if self.card is not None:
            self.card["all"].append(data)
        if self.capture is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if self.card is None:
            return
        if self.capture is not None and self.card_depth == self.capture_depth:
            value = _clean(self.parts)
            if self.capture == "tag":
                if value:
                    self.card["tags"].append(value)
            elif value:
                self.card[self.capture] = value
            self.capture, self.parts = None, []
        self.card_depth -= 1
        if self.card_depth == 0:
            self.card["all_text"] = _clean(self.card.pop("all"))
            self.cards.append(self.card)
            self.card = None

    def handle_startendtag(self, tag, attrs):
        return


def _search_records(body: str, location: str, limit: int) -> tuple[list[dict], bool]:
    parser = _SearchParser()
    try:
        parser.feed(body)
        parser.close()
    except (AssertionError, ValueError) as exc:
        raise SourceError("zhiye.page returned malformed search HTML") from exc
    if not parser.cards and not (parser.saw_search_form and parser.saw_query_input):
        raise SourceError("zhiye.page search page did not contain the expected public result structure")
    records = []
    for card in parser.cards:
        href = card.get("href", "")
        url = urljoin(BASE_URL, href)
        try:
            _validate_detail_url(url)
        except (SourceError, ValueError):
            continue
        title = card.get("title", "").strip()
        if not title:
            continue
        tags = [item for item in card.get("tags", []) if item]
        found_location = tags[0] if tags else ""
        if location and location.casefold() not in found_location.casefold():
            continue
        company = re.sub(r"\s*[→↗]\s*$", "", card.get("company", "")).strip() or "未披露（zhiye.page）"
        summary = card.get("summary", "").strip() or " · ".join(tags[1:])
        records.append(
            {
                "title": title,
                "company": company,
                "location": found_location,
                "url": url,
                "summary": summary,
                "source_verified_label": card.get("freshness", "").strip(),
            }
        )
    return records[:limit], len(records) > limit


class _DetailParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fields: dict[str, list[str]] = {}
        self.capture: str | None = None
        self.capture_depth = 0
        self.depth = 0
        self.heading_parts: list[str] | None = None
        self.heading_depth = 0
        self.after_description_heading = False
        self.official_url = ""
        self.nodes: list[dict] = []
        self.node_stack: list[dict] = []

    def handle_starttag(self, tag, attrs):
        if tag in _VOID_TAGS:
            return
        self.depth += 1
        classes = _classes(attrs)
        attr = dict(attrs)
        self.node_stack.append({"tag": tag, "classes": classes, "href": attr.get("href", ""), "parts": []})
        text_hint = (attr.get("aria-label", "") + " " + attr.get("title", "")).casefold()
        if tag == "a" and not self.official_url:
            href = attr.get("href", "")
            if href and (any(x in " ".join(classes) for x in ("official", "apply", "external")) or "官方" in text_hint):
                candidate = urljoin(BASE_URL, href)
                if urlsplit(candidate).scheme in {"http", "https"}:
                    self.official_url = candidate
        field = None
        if tag == "h1":
            field = "title"
        elif any(name in classes for name in ("job-description", "description", "job-content")):
            field = "description_explicit"
        elif any(name in classes for name in ("company-label", "company-name", "company-title")):
            field = "company"
        elif any(any(hint in name for hint in ("location", "city", "region")) for name in classes):
            field = "location"
        elif any(any(hint in name for hint in ("freshness", "verified", "verification")) for name in classes):
            field = "verified"
        elif self.after_description_heading and tag not in {"h1", "h2", "h3"}:
            field = "description_fallback"
        if field and self.capture is None:
            self.capture, self.capture_depth = field, self.depth
            self.fields.setdefault(field, [])
        if tag in {"h2", "h3"}:
            self.heading_parts, self.heading_depth = [], self.depth

    def handle_data(self, data):
        for node in self.node_stack:
            node["parts"].append(data)
        if self.capture:
            self.fields[self.capture].append(data)
        if self.heading_parts is not None:
            self.heading_parts.append(data)

    def handle_endtag(self, tag):
        if self.heading_parts is not None and self.depth == self.heading_depth:
            heading = _clean(self.heading_parts)
            self.after_description_heading = "职位说明" in heading
            self.heading_parts = None
        if self.capture and self.depth == self.capture_depth:
            self.capture = None
        if self.node_stack:
            node = self.node_stack.pop()
            node["text"] = _clean(node.pop("parts"))
            self.nodes.append(node)
            if node["tag"] == "a" and not self.official_url:
                hint = (node["text"] + " " + " ".join(node["classes"])).casefold()
                if any(word in hint for word in ("官方", "官网", "投递", "申请", "official", "apply")):
                    candidate = urljoin(BASE_URL, node["href"])
                    if urlsplit(candidate).scheme in {"http", "https"}:
                        self.official_url = candidate
        self.depth -= 1

    def handle_startendtag(self, tag, attrs):
        return


def _field(parser: _DetailParser, name: str) -> str:
    return _clean(parser.fields.get(name, []))


def _node_value(parser: _DetailParser, class_hints: tuple[str, ...]) -> str:
    candidates = []
    for node in parser.nodes:
        if node["text"] and any(hint in name for name in node["classes"] for hint in class_hints):
            if not any("label" in name for name in node["classes"]):
                candidates.append(node["text"])
    return min(candidates, key=len) if candidates else ""


def _labeled_value(parser: _DetailParser, labels: tuple[str, ...]) -> str:
    nodes = parser.nodes
    for index, node in enumerate(nodes):
        text = node["text"].strip()
        for label in labels:
            match = re.fullmatch(rf"{re.escape(label)}\s*[：:]\s*(.+)", text)
            if match:
                return match.group(1).strip()
            if text == label:
                for candidate in nodes[index + 1 : index + 4]:
                    value = candidate["text"].strip()
                    if value and value not in labels and not value.startswith(label):
                        return value
    return ""


def _labeled_link(parser: _DetailParser, labels: tuple[str, ...]) -> str:
    for index, node in enumerate(parser.nodes):
        if node["text"].strip() not in labels:
            continue
        for candidate in parser.nodes[index + 1 : index + 6]:
            if candidate["tag"] != "a" or not candidate["href"]:
                continue
            url = urljoin(BASE_URL, candidate["href"])
            if urlsplit(url).scheme in {"http", "https"}:
                return url
    return ""


def _first_detail_tag(parser: _DetailParser) -> str:
    for node in parser.nodes:
        if node["text"] and "tag" in node["classes"] and "warning" not in node["classes"]:
            return node["text"].strip()
    return ""


def _verified_label(parser: _DetailParser) -> str:
    explicit = _field(parser, "verified")
    if explicit:
        return explicit
    candidates = [
        node["text"].strip()
        for node in parser.nodes
        if "验证" in node["text"] and len(node["text"].strip()) <= 80
    ]
    return min(candidates, key=len) if candidates else ""


def _detail_record(body: str, url: str, retrieved_at: str, digest: str) -> dict:
    parser = _DetailParser()
    try:
        parser.feed(body)
        parser.close()
    except (AssertionError, ValueError) as exc:
        raise SourceError("zhiye.page returned malformed detail HTML") from exc
    title = _field(parser, "title")
    description = _field(parser, "description_explicit") or _field(parser, "description_fallback")
    if not title or not description:
        raise SourceError("zhiye.page detail page is missing a title or job description")
    verified_label = _verified_label(parser)
    verified_at = _labeled_value(parser, ("最近验证",))
    if not verified_at:
        verified_match = re.search(r"\d{4}[/-]\d{1,2}[/-]\d{1,2}(?:\s+\d{1,2}:\d{2})?", verified_label)
        verified_at = verified_match.group(0) if verified_match else ""
    if verified_at and verified_at not in verified_label:
        verified_label = f"最近验证 {verified_at}"
    source_id = _validate_detail_url(url)
    company = _field(parser, "company") or _node_value(parser, ("company",)) or _labeled_value(parser, ("公司", "公司名称", "招聘公司"))
    company = re.sub(r"\s*[→↗]\s*$", "", company).strip() or "未披露（zhiye.page）"
    return {
        "source": "zhiye",
        "source_id": source_id,
        "url": url,
        "official_url": parser.official_url or _labeled_link(parser, ("官方来源",)),
        "description": description,
        "title": title,
        "company": company,
        "location": _field(parser, "location") or _node_value(parser, ("location", "city", "region")) or _labeled_value(parser, ("工作地点", "地点", "城市")) or _first_detail_tag(parser),
        "retrieved_at": retrieved_at,
        "availability": "unknown",
        "upstream_verified_at": verified_at,
        "upstream_verified_label": verified_label,
        "content_digest": digest,
    }


def _validate_search_args(query, location, limit, refresh) -> tuple[str, str, int, bool]:
    if not isinstance(query, str) or not query.strip() or len(query.strip()) > 200:
        raise ValueError("query must be a non-empty string of at most 200 characters")
    if not isinstance(location, str) or len(location.strip()) > 100:
        raise ValueError("location must be a string of at most 100 characters")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError("limit must be an integer from 1 to 50")
    if not isinstance(refresh, bool):
        raise ValueError("refresh must be a boolean")
    return query.strip(), location.strip(), limit, refresh


def _validate_detail_url(url) -> str:
    if not isinstance(url, str):
        raise ValueError("url must be a string")
    _validate_origin(url)
    match = _JOB_PATH_RE.fullmatch(urlsplit(url).path)
    if not match or urlsplit(url).query or urlsplit(url).fragment:
        raise SourceError("detail URL must be a zhiye.page /jobs/job_* page")
    return match.group(1)


def search_zhiye(query, location="", limit=10, refresh=False) -> dict:
    """Return small public leads without fetching any aggregate detail page."""
    query, location, limit, refresh = _validate_search_args(query, location, limit, refresh)
    combined = " ".join(part for part in (query, location) if part)
    search_url = f"{BASE_URL}/jobs?{urlencode({'q': combined})}"
    body, fetched_at, digest, cache_hit = _get_page(search_url, "search", SEARCH_TTL, refresh)
    records, has_more = _search_records(body, location, limit)
    return {
        "provider": "zhiye",
        "query": query,
        "location": location,
        "records": records,
        "fetched_at": fetched_at,
        "cache_hit": cache_hit,
        "search_url": search_url,
        "has_more": has_more,
        "content_digest": digest,
    }


def fetch_zhiye_detail(url, refresh=False) -> dict:
    """Fetch one public aggregate detail page; never follow its employer link."""
    source_id = _validate_detail_url(url)
    if not isinstance(refresh, bool):
        raise ValueError("refresh must be a boolean")
    canonical_url = f"{BASE_URL}/jobs/{source_id}"
    body, fetched_at, digest, _cache_hit = _get_page(canonical_url, "detail", DETAIL_TTL, refresh)
    return _detail_record(body, canonical_url, fetched_at, digest)
