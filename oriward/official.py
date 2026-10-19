"""Employer official-site channel: one bounded read of one public posting page.

This is the only channel where the vacancy and the application entry point both
come from the employer, so it is also the only channel that can claim the
posting is currently open. Everything here is read-only: no login, no form
submission, no following the apply button.
"""
from __future__ import annotations

import hashlib
import html
import ipaddress
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
from urllib.parse import urljoin, urlsplit, urlunsplit

from .db import database_path, now
from .services import ValidationError
from .sources import SourceError


HTTP_TIMEOUT_SECONDS = 15
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MIN_REQUEST_INTERVAL_SECONDS = 2.0
PAGE_TTL = timedelta(hours=1)
ROBOTS_TTL = timedelta(hours=24)
USER_AGENT = "Oriward/0.2.0 official-job-reader"
MIN_HEURISTIC_JD_CHARS = 400
_MIN_JD_KEYWORD = re.compile(
    r"岗位职责|职位描述|工作职责|职位职责|任职要求|任职资格|岗位要求|"
    r"responsibilit|qualification|requirement|what you.ll do|about the role",
    re.IGNORECASE,
)
_BLOCKED_SUFFIXES = (".local", ".internal", ".localhost", ".lan", ".home", ".corp", ".test", ".invalid", ".example", ".onion")
_BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "metadata"}
_last_request_at: dict[str, float] = {}
_rate_lock = threading.Lock()


def _cache_root() -> Path:
    from .legacy import environment
    configured = environment("ORIWARD_OFFICIAL_CACHE")
    if configured:
        return Path(configured).expanduser().resolve()
    return database_path().parent / "cache" / "official"


def require_public_https(url) -> str:
    """Reject anything that is not a public HTTPS host; return the hostname.

    Refusing IP literals, credentials, non-standard ports and internal suffixes
    keeps a user-supplied URL from turning into an internal network request.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValidationError("A posting URL is required")
    parts = urlsplit(url.strip())
    if parts.scheme != "https":
        raise ValidationError("Official-site reads require an https URL")
    if parts.username or parts.password:
        raise ValidationError("Posting URL must not contain credentials")
    if parts.port not in (None, 443):
        raise ValidationError("Posting URL must use the default HTTPS port")
    host = (parts.hostname or "").casefold().rstrip(".")
    if not host or "." not in host:
        raise ValidationError("Posting URL must use a public provider hostname")
    if host in _BLOCKED_HOSTS or host.endswith(_BLOCKED_SUFFIXES):
        raise ValidationError("Posting URL points at a local or reserved hostname")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    raise ValidationError("IP-literal hosts are not accepted")


def _canonical(url: str) -> str:
    parts = urlsplit(url.strip())
    path = parts.path or "/"
    return urlunsplit(("https", parts.netloc.casefold(), path, parts.query, ""))


def _cache_paths(url: str) -> tuple[Path, Path]:
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    root = _cache_root()
    return root / f"page-{key}.html", root / f"page-{key}.json"


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


class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, host: str):
        super().__init__()
        self.host = host

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if (urlsplit(newurl).hostname or "").casefold() != self.host:
            raise SourceError("Official-site redirect left the approved host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _throttle(host: str) -> None:
    with _rate_lock:
        wait = MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - _last_request_at.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        _last_request_at[host] = time.monotonic()


def _get(url: str, accept: str) -> str:
    host = require_public_https(url)
    _throttle(host)
    request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT}, method="GET")
    opener = urllib.request.build_opener(_SameHostRedirect(host))
    try:
        with opener.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            if (urlsplit(response.geturl()).hostname or "").casefold() != host:
                raise SourceError("Official-site response came from an unapproved host")
            declared = response.headers.get("Content-Length")
            if declared:
                try:
                    if int(declared) > MAX_RESPONSE_BYTES:
                        raise SourceError("Official page exceeds 2 MB")
                except ValueError:
                    pass
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except SourceError:
        raise
    except urllib.error.HTTPError as exc:
        raise SourceError(f"Official page request failed with HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceError(f"Official page request failed: {getattr(exc, 'reason', exc)}") from exc
    if len(payload) > MAX_RESPONSE_BYTES:
        raise SourceError("Official page exceeds 2 MB")
    try:
        return payload.decode("utf-8", errors="replace")
    except UnicodeDecodeError as exc:
        raise SourceError("Official page is not readable text") from exc


def _robots_allows(url: str) -> None:
    host = require_public_https(url)
    robots_url = f"https://{host}/robots.txt"
    body = None
    try:
        body = _get(robots_url, "text/plain")
    except SourceError as exc:
        if "HTTP 404" in str(exc) or "HTTP 410" in str(exc):
            return
        raise SourceError(f"Cannot verify robots policy for {host}; refusing to read") from exc
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(body.splitlines())
    if not parser.can_fetch(USER_AGENT, url):
        raise SourceError(f"robots.txt on {host} disallows this posting read")


class _TextExtractor(HTMLParser):
    _BLOCK = {"br", "div", "p", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article"}
    _IGNORE = {"script", "style", "noscript", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._IGNORE:
            self.depth += 1
        elif not self.depth and tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._IGNORE and self.depth:
            self.depth -= 1
        elif not self.depth and tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.depth:
            self.parts.append(data)


def _plain_text(value) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(html.unescape(html.unescape(value)))
        parser.close()
    except (AssertionError, ValueError):
        return " ".join(html.unescape(value).split())
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line).strip()


class _PageScan(HTMLParser):
    """Collect the few page-level facts a fallback read needs."""

    _IGNORE = {"script", "style", "noscript", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ld_json: list[str] = []
        self.title = ""
        self.h1: list[str] = []
        self.meta: dict[str, str] = {}
        self.body_parts: list[str] = []
        self.ignore_depth = 0
        self._capture: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attr = {k.casefold(): (v or "") for k, v in attrs}
        if tag in self._IGNORE:
            self.ignore_depth += 1
            if tag == "script" and "ld+json" in attr.get("type", "").casefold():
                self._capture, self._parts = "ld", []
            return
        if tag == "meta":
            key = (attr.get("property") or attr.get("name") or "").casefold()
            if key and attr.get("content"):
                self.meta.setdefault(key, attr["content"])
        elif tag == "title":
            self._capture, self._parts = "title", []
        elif tag == "h1":
            self._capture, self._parts = "h1", []

    def handle_endtag(self, tag):
        if tag in self._IGNORE:
            if self.ignore_depth:
                self.ignore_depth -= 1
            if tag == "script" and self._capture == "ld":
                self.ld_json.append("".join(self._parts))
                self._capture = None
            return
        if self._capture in {"title", "h1"} and tag == self._capture:
            text = " ".join("".join(self._parts).split())
            if self._capture == "title":
                self.title = text
            elif text:
                self.h1.append(text)
            self._capture = None

    def handle_data(self, data):
        if self._capture:
            self._parts.append(data)
            return
        if not self.ignore_depth:
            self.body_parts.append(data)


def _ld_objects(blocks: list[str]) -> list[dict]:
    found: list[dict] = []

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            types = node.get("@type")
            names = [types] if isinstance(types, str) else types if isinstance(types, list) else []
            if any(str(name).casefold() == "jobposting" for name in names):
                found.append(node)
            for key in ("@graph", "itemListElement", "mainEntity"):
                if key in node:
                    walk(node[key])

    for block in blocks:
        try:
            walk(json.loads(block))
        except (json.JSONDecodeError, TypeError):
            continue
    return found


def _address_location(value) -> str:
    node = value[0] if isinstance(value, list) and value else value
    if not isinstance(node, dict):
        return ""
    address = node.get("address") if isinstance(node.get("address"), dict) else node
    parts = [address.get("addressLocality"), address.get("addressRegion"), address.get("addressCountry")]
    parts = [str(part).strip() for part in parts if isinstance(part, (str, int)) and str(part).strip()]
    return "、".join(parts)


def _organization(value) -> str:
    if isinstance(value, list) and value:
        value = value[0]
    if isinstance(value, dict):
        name = value.get("name")
        return name.strip() if isinstance(name, str) else ""
    return value.strip() if isinstance(value, str) else ""


def _record_from_json_ld(node: dict, url: str, company: str) -> dict:
    description = _plain_text(node.get("description"))
    title = node.get("title") if isinstance(node.get("title"), str) else ""
    if not title.strip() or not description:
        return {}
    published = node.get("datePosted") if isinstance(node.get("datePosted"), str) else ""
    apply_url = node.get("url") if isinstance(node.get("url"), str) else ""
    if apply_url:
        apply_url = urljoin(url, apply_url)
    record = {
        "source": "official",
        "source_id": url,
        "url": url,
        "apply_url": apply_url or url,
        "title": title.strip(),
        "company": (_organization(node.get("hiringOrganization")) or company).strip(),
        "location": _address_location(node.get("jobLocation")),
        "description": description,
        "published_at": published.strip() or None,
        "valid_through": node.get("validThrough") if isinstance(node.get("validThrough"), str) else "",
        "employment_type": node.get("employmentType") if isinstance(node.get("employmentType"), (str, list)) else "",
        "direct_apply": bool(node.get("directApply")) if isinstance(node.get("directApply"), bool) else None,
        "availability": "listed",
        "parser": "json_ld",
        "evidence_level": "full_jd",
    }
    return record


def _record_from_page(scan: _PageScan, url: str, company: str) -> dict:
    body = _plain_text("".join(scan.body_parts))
    title = scan.h1[0] if scan.h1 else (scan.meta.get("og:title") or scan.title)
    title = " ".join(str(title or "").split())
    if not title or len(body) < MIN_HEURISTIC_JD_CHARS or not _MIN_JD_KEYWORD.search(body):
        return {}
    apply_url = urljoin(url, scan.meta.get("og:url", "")) if scan.meta.get("og:url") else url
    return {
        "source": "official",
        "source_id": url,
        "url": url,
        "apply_url": apply_url,
        "title": title,
        "company": (scan.meta.get("og:site_name") or company).strip(),
        "location": "",
        "description": body,
        "published_at": None,
        "availability": "listed",
        "parser": "html_heuristic",
        "evidence_level": "full_jd",
    }


def fetch(url, company="", refresh=False) -> dict:
    """Read one public employer posting. Never follows the apply button."""
    canonical = _canonical(url)
    host = require_public_https(canonical)
    if not isinstance(company, str) or len(company) > 200:
        raise ValidationError("company must be text of at most 200 characters")
    if not isinstance(refresh, bool):
        raise ValidationError("refresh must be a boolean")

    body_path, meta_path = _cache_paths(canonical)
    page = None
    if not refresh:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            page = body_path.read_text(encoding="utf-8")
            stamp = datetime.fromisoformat(meta["fetched_at"])
            if stamp.tzinfo is None or datetime.now(timezone.utc) - stamp > PAGE_TTL:
                page = None
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            page = None

    cached = page is not None
    if page is None:
        _robots_allows(canonical)
        page = _get(canonical, "text/html,application/xhtml+xml")
        stamp = datetime.now(timezone.utc)
        digest = hashlib.sha256(page.encode("utf-8")).hexdigest()
        _atomic_write(body_path, page.encode("utf-8"))
        _atomic_write(meta_path, json.dumps(
            {"url": canonical, "fetched_at": stamp.isoformat(timespec="seconds"), "sha256": digest},
            ensure_ascii=False, sort_keys=True).encode("utf-8"))
    else:
        digest = hashlib.sha256(page.encode("utf-8")).hexdigest()

    scan = _PageScan()
    try:
        scan.feed(page)
        scan.close()
    except (AssertionError, ValueError) as exc:
        raise SourceError("Official page returned malformed HTML") from exc

    record = {}
    for node in _ld_objects(scan.ld_json):
        record = _record_from_json_ld(node, canonical, company.strip())
        if record:
            break
    if not record:
        record = _record_from_page(scan, canonical, company.strip())
    if not record:
        raise SourceError(
            "Official page did not expose a readable JD (no JobPosting structured data and "
            "no recognizable description); read it manually and import the text instead"
        )

    record["retrieved_at"] = now()
    record["content_digest"] = digest
    record["cache_hit"] = cached
    record["host"] = host
    record["read_method"] = "official_site_read"
    return record


def plan(company, query="", url="") -> dict:
    """Describe how to find the employer's own posting; performs no request."""
    if not isinstance(company, str) or not company.strip():
        raise ValidationError("A company name is required for official-site discovery")
    company = company.strip()
    if url:
        require_public_https(url)
    queries = []
    if query.strip():
        queries.append(f'"{company}" {query.strip()} 招聘')
        queries.append(f'"{company}" {query.strip()} 官网 职位')
    queries.append(f'"{company}" 招聘 官网 careers')
    queries.append(f'"{company}" 校园招聘 OR 社会招聘')
    return {
        "provider": "official",
        "company": company,
        "query": query.strip(),
        "entry_url": url,
        "executed": False,
        "status": "OFFICIAL_SITE_DISCOVERY",
        "search_queries": queries,
        "steps": [
            "用 search_queries 在东财/必应/百度定位企业招聘主页（路径多为 /careers、/jobs、/zhaopin）",
            "在岗位列表中找到目标单岗页面，复制该页面 URL（不是列表页）",
            "执行 official fetch --url <单岗URL> --company <公司>，本地解析 JD 与发布时间",
            "确认岗位仍在招后 application prepare --job-id <id> --channel official，在官网完成投递",
        ],
        "note": "官网是唯一能同时确认岗位开放与真实投递入口的渠道；本项目不代投、不点投递按钮。",
    }


def import_official(record: dict) -> dict:
    """Import one already-read official posting into the job table."""
    from . import sources, tracking
    result = sources.import_records([record])
    job_id = result["job_ids"][0]
    tracking.regroup()
    return {"job_id": job_id, "import": result, "next_command": f"jobs card --id {job_id}"}
