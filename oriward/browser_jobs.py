"""Optional visible-DOM collection from an explicitly connected job-search tab.

Uses normal browser pages and next-page controls. No cookies, hidden state,
network replay, login automation or model dependency.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from . import discovery
from .db import now
from .services import ValidationError

PROVIDERS = {
    "boss": {"domain": "zhipin.com", "path": r"^/job_detail/[^/]+\.html$"},
    "zhilian": {"domain": "zhaopin.com", "path": r"^/(?:cc[^/]+|jobdetail/[^/]+)\.(?:htm|html)$"},
    "liepin": {"domain": "liepin.com", "path": r"^/(?:job|a)/\d+\.shtml$"},
}

# Only rendered text and links. Broad card containers are fallbacks for modest
# site layout changes; missing title/company stays unknown rather than invented.
EXTRACT = r"""() => {
 const visible = e => !!(e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
 const first = (e, selectors) => {
   for (const s of selectors) { const n=e.querySelector(s); if(n && visible(n) && n.innerText.trim()) return n.innerText.trim(); }
   return '';
 };
 const links = Array.from(document.querySelectorAll('a[href]')).filter(visible).map(a => {
   const c=a.closest('.job-card-wrapper,.job-card-box,.joblist-box,.job-card-pc-container,.job-list-item,article,li') || a.parentElement;
   return {url:a.href, anchor:a.innerText.trim(),
     title:first(c,['.job-name','.jobinfo__name','.job-title','.job-title-box','.job-title-text']),
     company:first(c,['.company-name','.companyinfo__name','.company-info .company-name','.company-name-box']),
     location:first(c,['.job-area','.jobinfo__other-info-item','.job-area-wrapper','.job-dq-box']),
     salary:first(c,['.salary','.jobinfo__salary','.job-salary']), summary:c.innerText.trim().slice(0,1800)};
 });
 return {url:location.href, text:document.body.innerText.slice(0,100000), links,
   filters:Array.from(document.querySelectorAll('input')).filter(visible).map(e=>e.value).filter(Boolean)};
}"""


def validate_url(provider, url):
    if provider not in PROVIDERS:
        raise ValidationError("Browser provider must be boss, zhilian or liepin")
    parsed = urlsplit(url)
    domain = PROVIDERS[provider]["domain"]
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or not (parsed.hostname == domain or (parsed.hostname or "").endswith("." + domain))):
        raise ValidationError("Browser URL must belong to the selected provider")
    return url


def parse_snapshot(provider, snapshot, query="", location=""):
    """Convert observed DOM into preview leads; no source dates are inferred."""
    validate_url(provider, snapshot["url"])
    text = snapshot.get("text", "")
    if re.search(r"验证码|人机验证|验证连接安全性|安全验证|访问验证|verify you are human", text, re.I):
        return {"status": "needs_verification", "records": [], "reason": "页面要求用户完成验证"}
    records, seen = [], set()
    for item in snapshot.get("links", []):
        url = item.get("url", "")
        try:
            validate_url(provider, url)
        except ValueError:
            continue
        parsed = urlsplit(url)
        if not re.fullmatch(PROVIDERS[provider]["path"], parsed.path, re.I):
            continue
        canonical = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        title = (item.get("title") or item.get("anchor") or "").strip().splitlines()
        if not title or not title[0] or canonical in seen:
            continue
        seen.add(canonical)
        records.append({"provider": provider, "url": canonical, "title": title[0][:500],
                        "company": item.get("company", "")[:500], "location": item.get("location", "")[:500],
                        "salary": item.get("salary", "")[:200], "summary": item.get("summary", "")[:1800],
                        "query": query, "discovered_at": now(), "discovery_method": "browser_ui",
                        "access_state": "visible_preview"})
    # The page may have a login link in its navigation while showing real cards.
    if records:
        return {"status": "search_verified", "records": records, "reason": "读取到可见岗位卡片"}
    if re.search(r"登录后查看|登录后浏览|请先登录|扫码登录|手机验证码登录", text):
        return {"status": "needs_login", "records": [], "reason": "页面要求用户登录"}
    if re.search(r"暂无相关职位|没有找到相关职位|暂无搜索结果|未找到相关职位", text):
        return {"status": "no_results", "records": [], "reason": "页面明确显示无结果"}
    return {"status": "browser_error", "records": [], "reason": "页面未加载完成或卡片结构无法识别；不能判断为零结果"}


def collect_pages(page, provider, query="", location="", limit=20, pages=3):
    records, seen, receipts = [], set(), []
    stop = "page_limit"
    for index in range(pages):
        try:
            snapshot = page.evaluate(EXTRACT)
            result = parse_snapshot(provider, snapshot, query, location)
        except Exception:
            snapshot = {"url": page.url}
            result = {"status": "browser_error", "records": [], "reason": "读取页面失败，已保留前面成功读取的岗位"}
        receipts.append({"page": index + 1, "source_url": snapshot["url"], "status": result["status"],
                         "observed_at": now(), "count": len(result["records"]), "reason": result["reason"]})
        if result["status"] != "search_verified":
            stop = result["status"]
            break
        added = 0
        for record in result["records"]:
            if record["url"] not in seen:
                records.append(record)
                seen.add(record["url"])
                added += 1
        if len(records) >= limit:
            stop = "result_limit"
            break
        if not added:
            stop = "repeated_page"
            break
        if index + 1 == pages:
            break
        # Only a normal visible next-page control; never infer private endpoints.
        candidates = page.locator('a[rel="next"],button[aria-label="下一页"],.btn-next,.soupager__btn-next').all()
        candidates += page.get_by_text("下一页", exact=True).all()
        next_button = next((b for b in candidates if b.is_visible() and b.is_enabled()
                            and b.get_attribute("aria-disabled") != "true"
                            and "disabled" not in (b.get_attribute("class") or "")), None)
        if next_button is None:
            stop = "no_visible_next_page"
            break
        try:
            next_button.click(timeout=10000)
            page.wait_for_timeout(2000)
        except Exception:
            stop = "pagination_error"
            break
    status = "search_verified" if records else receipts[-1]["status"]
    return {"provider": provider, "status": status, "executed": True, "records": records[:limit],
            "visible_count": len(records[:limit]), "source_url": receipts[0]["source_url"],
            "observed_at": receipts[-1]["observed_at"], "page_receipts": receipts, "stop_reason": stop,
            "partial": stop in {"needs_login", "needs_verification", "browser_error", "pagination_error"},
            "scope": f"{len(receipts)} pages observed; only visible cards, not complete JDs",
            "filters": {"requested_query": query, "requested_location": location,
                        "applied_by_collector": False,
                        "note": "读取指定搜索标签页；城市、关键词和筛选须在页面中设置并核对，不默认声称已筛选。"},
            "note": "Visible preview leads; use the saved tab for full detail review."}


def collect(provider, url, cdp_url, *, query="", location="", limit=20, pages=3):
    """Attach only to the exact authorized tab, leaving its browser open."""
    validate_url(provider, url)
    if not 1 <= limit <= 100 or not 1 <= pages <= 5:
        raise ValidationError("limit must be 1..100 and pages 1..5")
    endpoint = urlsplit(cdp_url)
    if endpoint.scheme != "http" or endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValidationError("Use the explicitly connected local browser's HTTP CDP endpoint")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"provider": provider, "status": "NOT_CONNECTED", "executed": False,
                "reason": "Install the optional browser dependency: pip install '.[browser]'"}
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(cdp_url, timeout=10000)
        except Exception:
            return {"provider": provider, "status": "NOT_CONNECTED", "executed": False,
                    "reason": "无法连接指定浏览器；需要宿主提供已授权会话。"}
        # Stopping Playwright disconnects; do not browser.close() a user's session.
        page = next((p for c in browser.contexts for p in c.pages if p.url == url), None)
        if page is None:
            return {"provider": provider, "status": "NOT_CONNECTED", "executed": False,
                    "reason": "指定 URL 的标签页未打开；请先在浏览器中搜索并传入地址栏完整 URL。"}
        result = collect_pages(page, provider, query, location, limit, pages)
    raw_records = result.pop("records")
    imported = discovery.import_leads(raw_records, skip_older=True)
    result["import"] = imported
    result["leads"] = [{"id": lid, **item} for lid, item in zip(imported["lead_ids"], raw_records)]
    return result
