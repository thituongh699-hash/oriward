"""Local channel routing, search leads, text filtering and verified JD intake.

No model call, credential access, browser login or external submission occurs here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

from .db import connect, deserialize, serialize, now, audit
from .services import ValidationError, clean_url, validate_dict
from . import sources
from .legacy import environment


VERIFIED_AT = "2026-10-18"

#: Channels that ship as optional extensions. They are never imported on the
#: default path: the module below is loaded lazily, only when the user opts in
#: through the named environment variable. See `oriward/extras/__init__.py`.
OPTIONAL_EXTENSIONS = {
    "liepin": {
        "module": "oriward.extras.liepin",
        "env": "ORIWARD_ENABLE_LIEPIN",
        "terms": "该渠道调用第三方平台接口，其开放范围与二次使用条件由平台条款决定；"
                 "启用前请自行确认授权范围与合规性，本项目不作任何许可承诺。",
    },
}


def extension_enabled(name):
    """Optional extensions stay off unless the user opts in explicitly."""
    meta = OPTIONAL_EXTENSIONS.get(name)
    return bool(meta) and environment(meta["env"], "").strip() == "1"

CHANNELS = {
    "official": {
        "name": "企业官网直招", "domain": "", "home": "", "mode": "official_site_read",
        "access": "local_read", "supports": ["detail", "apply"], "apply_channel": True,
        "search_entry": "", "verified_at": VERIFIED_AT,
        "note": "唯一能确认雇主真实开放与真实投递入口的渠道；只读单页，schema.org JobPosting 优先",
    },
    "zhiye": {
        "name": "职页", "domain": "zhiye.page", "home": "https://zhiye.page/jobs", "mode": "local_public_search",
        "access": "local", "supports": ["search", "detail"], "apply_channel": False,
        "search_entry": "https://zhiye.page/jobs", "verified_at": VERIFIED_AT,
        "note": "企业官网职位聚合；可本地搜索并取完整 JD，但聚合站验证时间不等于当前开放状态",
    },
    "liepin": {
        "name": "猎聘", "domain": "liepin.com", "home": "https://www.liepin.com/", "mode": "official_api_requires_auth",
        "access": "official_api", "supports": ["search"], "apply_channel": True,
        "search_entry": "https://www.liepin.com/zhaopin/", "verified_at": VERIFIED_AT,
        "note": "可选扩展，默认关闭（需 ORIWARD_ENABLE_LIEPIN=1）；需 90 天 Token；只返回搜索卡片，完整 JD 需人工读取",
    },
    "boss": {
        "name": "BOSS直聘", "domain": "zhipin.com", "home": "https://www.zhipin.com/", "mode": "browser_ui",
        "access": "browser", "supports": ["search", "detail"], "apply_channel": True,
        "search_entry": "https://www.zhipin.com/web/geek/job", "verified_at": VERIFIED_AT,
        "note": "必须走已连接浏览器；本地 HTTP 受 robots 限制。端到端自动搜索尚未验证成功",
    },
    "zhilian": {
        "name": "智联招聘", "domain": "zhaopin.com", "home": "https://www.zhaopin.com/", "mode": "browser_ui",
        "access": "browser", "supports": ["search", "detail"], "apply_channel": True,
        "search_entry": "https://sou.zhaopin.com/", "verified_at": VERIFIED_AT,
        "note": "站内搜索已实测；未登录时详情/薪资受限，完整 JD 需登录后读取",
    },
    "51job": {
        "name": "前程无忧", "domain": "51job.com", "home": "https://www.51job.com/", "mode": "web_index_or_authorized_import",
        "access": "catalog", "supports": ["search"], "apply_channel": True,
        "search_entry": "https://we.51job.com/pc/search", "verified_at": VERIFIED_AT,
        "note": "公开检索线索 + 授权导入；未验证本地直接搜索接口",
    },
    "jobui": {
        "name": "职友集", "domain": "jobui.com", "home": "https://www.jobui.com/", "mode": "web_index_or_authorized_import",
        "access": "catalog", "supports": ["search"], "apply_channel": False,
        "search_entry": "https://www.jobui.com/jobs/", "verified_at": VERIFIED_AT,
        "note": "公司/岗位发现用；开放收录 XML 不是读取 API，不宜作为投递渠道",
    },
    "ncss": {
        "name": "国家大学生就业服务平台", "domain": "ncss.cn", "home": "https://www.ncss.cn/", "mode": "web_index_or_authorized_import",
        "access": "catalog", "supports": ["search"], "apply_channel": True,
        "search_entry": "https://www.ncss.cn/", "verified_at": VERIFIED_AT,
        "note": "应届生/校园招聘补充渠道；未验证本地直接搜索接口",
    },
    "public": {
        "name": "中国公共招聘网", "domain": "job.mohrss.gov.cn", "home": "https://job.mohrss.gov.cn/", "mode": "web_index_or_authorized_import",
        "access": "catalog", "supports": ["search"], "apply_channel": True,
        "search_entry": "https://job.mohrss.gov.cn/", "verified_at": VERIFIED_AT,
        "note": "公共就业信息入口；未验证本地直接搜索接口",
    },
    "careerjet": {
        "name": "Careerjet 中国", "domain": "careerjet.cn", "home": "https://www.careerjet.cn/", "mode": "api_requires_credentials",
        "access": "official_api", "supports": ["search"], "apply_channel": False,
        "search_entry": "https://www.careerjet.cn/", "verified_at": VERIFIED_AT,
        "note": "官方 API 需发布商 key、用户 IP 与 User-Agent；本项目尚未配置或实测",
    },
}

# Where a submission can actually be recorded. The value is a channel ID, never
# an instruction to submit anything automatically.
APPLY_CHANNELS = {key for key, value in CHANNELS.items() if value["apply_channel"]}
APPLY_CHANNELS |= {"email", "referral", "other"}

DEFAULT_PLAN_PROVIDERS = ["official", "zhiye", "liepin", "boss", "zhilian", "51job", "jobui", "ncss", "public", "careerjet", "shixiseng", "nowcoder", "gaodun"]

ROUTE_KEY = "job_search_routes"
EXTRA_ROUTES = {
    "shixiseng": {"name": "实习僧", "domain": "shixiseng.com", "home": "https://www.shixiseng.com/", "mode": "web_index_or_authorized_import", "access": "catalog", "supports": ["search"], "apply_channel": True, "search_entry": "https://www.shixiseng.com/", "verified_at": "", "note": "目录来源；需实际读取并授权导入"},
    "nowcoder": {"name": "牛客招聘", "domain": "nowcoder.com", "home": "https://www.nowcoder.com/", "mode": "web_index_or_authorized_import", "access": "catalog", "supports": ["search"], "apply_channel": True, "search_entry": "https://www.nowcoder.com/jobs/center", "verified_at": "", "note": "目录来源；需实际读取并授权导入"},
    "gaodun": {"name": "高顿招聘", "domain": "gaodun.com", "home": "https://www.gaodun.com/", "mode": "web_index_or_authorized_import", "access": "catalog", "supports": ["search"], "apply_channel": True, "search_entry": "https://www.gaodun.com/", "verified_at": "", "note": "目录来源；需实际读取并授权导入"},
}


def route_registry():
    """Return static routes plus persisted user additions and disabled states."""
    with connect() as db:
        ensure_schema(db)
        row = db.execute("SELECT data FROM career_settings WHERE key=?", (ROUTE_KEY,)).fetchone()
    saved = deserialize(row["data"]) if row else {}
    routes = {key: dict(value, enabled=True, discovered=False) for key, value in CHANNELS.items()}
    for key, value in EXTRA_ROUTES.items():
        routes.setdefault(key, dict(value, enabled=True, discovered=False))
    for key, value in saved.items():
        routes[key] = {**routes.get(key, {}), **value}
    return routes


def set_route(provider, *, enabled=None, url=None, name=None, reason="", resolution=None):
    """Persist enable/disable or a newly discovered source URL; no connector is enabled."""
    if not isinstance(provider, str) or not provider.strip() or len(provider) > 80:
        raise ValidationError("provider must be nonempty text up to 80 characters")
    provider = provider.strip().lower()
    current = route_registry()
    if enabled is None and url is None:
        raise ValidationError("Provide enabled or url")
    if enabled is not None and type(enabled) is not bool:
        raise ValidationError("enabled must be boolean")
    value = dict(current.get(provider, {}))
    if resolution is not None:
        if resolution not in {"resolved", "declined"}:
            raise ValidationError("resolution must be resolved or declined")
        if not value.get("user_assistance_requested"):
            raise ValidationError("User assistance must be requested before resolution")
        value["user_assistance_resolution"] = resolution
    if url is not None:
        value["search_entry"] = clean_url(_text(url, "url", 2048))
        value["home"] = value["search_entry"]
        value["discovered"] = provider not in CHANNELS and provider not in EXTRA_ROUTES
        value.setdefault("name", _text(name or provider, "name", 120))
        value.setdefault("domain", (urlsplit(value["search_entry"]).hostname or ""))
        value.setdefault("mode", "manual_public_search")
        value.setdefault("access", "catalog")
        value.setdefault("supports", ["search"])
        value.setdefault("apply_channel", False)
        value.setdefault("note", "用户发现的来源；需要逐次人工执行并记录回执")
    if enabled is not None:
        if enabled is False:
            failures = 0
            with connect() as db:
                for row in db.execute("SELECT data FROM search_runs"):
                    pipeline = deserialize(row["data"]).get("pipeline", {})
                    failures += sum(1 for attempt in pipeline.get("query_history", [])
                                    if attempt.get("provider") == provider and attempt.get("attempted")
                                    and attempt.get("status") == "failed" and attempt.get("stage") == "repair")
            if failures < 2:
                raise ValidationError("Route disable requires two recorded technical repair failures")
            if not value.get("user_assistance_requested") or value.get("user_assistance_resolution") not in {"resolved", "declined"}:
                raise ValidationError("Route disable requires requested user assistance and resolved/declined state")
        value["enabled"] = enabled
        value["route_note"] = _text(reason, "reason", 500) if reason else ("已启用" if enabled else "已停用")
        if enabled:
            value["user_assistance_requested"] = False
            value.pop("user_assistance_resolution", None)
    with connect() as db:
        ensure_schema(db)
        row = db.execute("SELECT data FROM career_settings WHERE key=?", (ROUTE_KEY,)).fetchone()
        saved = deserialize(row["data"]) if row else {}
        saved[provider] = value
        db.execute("INSERT INTO career_settings(key,data,updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at",
                   (ROUTE_KEY, serialize(saved), now()))
        audit(db, "search.route.updated", "career_settings", ROUTE_KEY, provider)
    return {"id": provider, **value}


def request_route_assistance(provider):
    provider = _text(provider, "provider", 80).lower()
    current = route_registry().get(provider)
    if current is None:
        raise ValidationError("Unknown search route")
    value = dict(current, user_assistance_requested=True, user_assistance_resolution="")
    with connect() as db:
        row = db.execute("SELECT data FROM career_settings WHERE key=?", (ROUTE_KEY,)).fetchone()
        saved = deserialize(row["data"]) if row else {}
        saved[provider] = value
        db.execute("INSERT INTO career_settings(key,data,updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at",
                   (ROUTE_KEY, serialize(saved), now()))
        audit(db, "search.route.assistance_requested", "career_settings", ROUTE_KEY, provider)
    return {"id": provider, **value}


def channels(*, include_dynamic=False):
    registry = route_registry() if include_dynamic else CHANNELS
    return [{"id": key, **value} for key, value in registry.items()]


def channel_route(provider, query="", location=""):
    """Return the executable next step for one channel instead of a bare plan."""
    registry = route_registry()
    if provider not in registry:
        raise ValidationError("Unknown search channel")
    meta = registry[provider]
    query, location = (query or "").strip(), (location or "").strip()
    route = {
        "provider": provider,
        "access": meta["access"],
        "mode": meta["mode"],
        "supports": meta["supports"],
        "executed": False,
        "index_query": f"site:{meta['domain']} {location} {query} 招聘".strip() if meta["domain"] else "",
        "entry_url": meta.get("search_entry") or meta["home"],
    }
    if provider == "official":
        route.update(executed=False, action="search_company_site",
                     steps=["用搜索引擎定位该公司招聘主页（com/careers/jobs 路径优先）",
                            "在官网岗位列表找到目标岗位的单岗页面 URL",
                            "执行 official fetch --url <单岗URL>，由本地解析 JD 与发布时间",
                            "确认后 application prepare --job-id <id>，在官网完成投递"])
    elif meta["access"] == "local":
        route.update(action="run_local_search",
                     next_command=f'jobs search --provider {provider} --query "{query}" --location "{location}"')
    elif meta["access"] == "official_api":
        if provider in OPTIONAL_EXTENSIONS:
            route.update(action="enable_optional_extension",
                         next_command=f"设置环境变量 {OPTIONAL_EXTENSIONS[provider]['env']}=1 后重试",
                         terms=OPTIONAL_EXTENSIONS[provider]["terms"])
        else:
            route.update(action="needs_credential", next_command="配置发布商 API key")
    elif meta["access"] == "browser":
        route.update(action="browser_ui",
                     next_command=f'jobs browser-plan --provider {provider} --query "{query}" --location "{location}"',
                     workflow=".agents/skills/job-search/references/browser-search.md")
    else:
        route.update(action="search_then_import",
                     steps=["在 entry_url 或搜索引擎索引中定位单岗页面",
                            "读取完整 JD 后按 job-import-contract 写入 leads JSON（provider=%s, discovery_method=web_index）" % provider,
                            "leads promote --id <id> 提升为岗位"],
                     next_command="leads import --file <leads.json>")
    return route



def _text(value, name, maximum=500):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValidationError(f"{name} must be nonempty text of at most {maximum} characters")
    return value.strip()


def _date(value, name):
    _text(value, name, 80)
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt > datetime.now(timezone.utc):
            raise ValueError()
    except ValueError as exc:
        raise ValidationError(f"{name} must be a non-future ISO timestamp with timezone") from exc
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def search_plan(query, location="", providers=None):
    query = _text(query, "query", 120)
    if not isinstance(location, str) or len(location) > 80:
        raise ValidationError("location must be text of at most 80 characters")
    registry = route_registry()
    selected = providers or [p for p, meta in registry.items() if meta.get("enabled", True)]
    if not isinstance(selected, list) or any(p not in registry for p in selected):
        raise ValidationError("Unknown search channel")
    ordered = [p for p in dict.fromkeys(selected) if registry[p].get("enabled", True)]
    return {"query": query, "location": location.strip(), "executed": False,
            "channels": [{"provider": p, **registry[p], "enabled": registry[p].get("enabled", True),
                          "executed": False, "search_query": f"site:{registry[p].get('domain','')} {location.strip()} {query} 招聘".strip()}
                         for p in ordered],
            "note": "计划不是搜索结果。local_public_search 本地执行；browser_ui 由浏览器操作执行；"
                    "official_site_read 需要单岗 URL；catalog 渠道只能检索后导入线索。"}



def browser_plan(query, location="", provider="boss", limit=10):
    search_plan(query, location, [provider])
    _limit(limit)
    if provider not in {"boss", "zhilian"}:
        raise ValidationError("Browser workflow currently supports boss and zhilian")
    return {"provider": provider, "query": query.strip(), "location": location.strip(), "limit": limit,
            "executed": False, "status": "BROWSER_ACTION_REQUIRED", "entry_url": CHANNELS[provider]["home"],
            "executor": "Agent connected browser UI", "steps": [
                "复用已连接用户浏览器，读取当前页面；在站内搜索框填关键词并选择城市，核对实际筛选条件。",
                "只读岗位卡片；点击选中岗位核对详情 URL。只提取页面可见职位信息，不读取 cookie/隐藏接口。",
                "登录/验证码/空白错误页记录为待恢复状态并保留标签，不当作没有职位，也不放弃渠道。",
                "用 jobs browser-record 保存实际观察；小批量线索以 browser_ui 导入；完整 JD 阅读后才 promote。"],
            "record_command": "jobs browser-record --file <observation.json>",
            "workflow": ".agents/skills/job-search/references/browser-search.md"}


def record_browser_observation(data):
    validate_dict(data, ["provider", "query", "location", "source_url", "observed_at", "status", "evidence", "visible_count"])
    provider = data["provider"]
    browser_plan(data["query"], data["location"], provider)
    status = data["status"]
    if status not in {"search_verified", "needs_login", "needs_verification", "browser_error", "no_results"}:
        raise ValidationError("Unknown browser observation status")
    count = data["visible_count"]
    if type(count) is not int or not 0 <= count <= 1000:
        raise ValidationError("visible_count must be 0..1000")
    if (status == "search_verified" and count == 0) or (status in {"no_results", "browser_error"} and count != 0):
        raise ValidationError("visible_count contradicts browser observation status")
    url = clean_url(_text(data["source_url"], "source_url", 2048))
    parsed = urlsplit(url)
    domain = CHANNELS[provider]["domain"]
    if parsed.username or parsed.password or not (parsed.hostname == domain or (parsed.hostname or "").endswith("." + domain)):
        raise ValidationError("source_url must belong to the observed provider")
    record = {"provider": provider, "query": data["query"].strip(), "location": data["location"].strip(),
              "source_url": url, "observed_at": _date(data["observed_at"], "observed_at"),
              "status": status, "evidence": _text(data["evidence"], "evidence", 2000), "visible_count": count}
    with connect() as db:
        ensure_schema(db)
        rid = db.execute("INSERT INTO browser_search_runs(data,created_at) VALUES (?,?)", (serialize(record), now())).lastrowid
        audit(db, "browser.observed", "browser_search_runs", rid, status)
    return {"id": rid, **record, "recorded_only": True}


def browser_runs(limit=10):
    _limit(limit)
    with connect() as db:
        ensure_schema(db)
        return [{"id": row["id"], **deserialize(row["data"])}
                for row in db.execute("SELECT * FROM browser_search_runs ORDER BY id DESC LIMIT ?", (limit,))]


def ensure_schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS search_leads (
        id INTEGER PRIMARY KEY, provider TEXT NOT NULL, url TEXT NOT NULL,
        data TEXT NOT NULL, job_id INTEGER REFERENCES jobs(id),
        discovered_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(provider,url))""")
    db.execute("CREATE TABLE IF NOT EXISTS browser_search_runs (id INTEGER PRIMARY KEY, data TEXT NOT NULL, created_at TEXT NOT NULL)")


def import_leads(records, *, skip_older=False):
    if not isinstance(records, list) or len(records) > 1000:
        raise ValidationError("Provide an array of at most 1000 leads")
    checked = []
    for raw in records:
        validate_dict(raw, ["provider", "title", "url", "discovered_at", "discovery_method"])
        provider = raw["provider"]
        registry = route_registry()
        if provider not in registry:
            raise ValidationError("Unknown lead provider")
        url = clean_url(_text(raw["url"], "url", 2048))
        p = urlsplit(url)
        if provider == "official":
            # An employer domain is not known in advance, so the official channel
            # is validated by reachability rules instead of a fixed platform host.
            from .official import require_public_https
            require_public_https(url)
        else:
            domain = registry[provider].get("domain", "")
            if not domain:
                raise ValidationError("Custom lead route needs a declared public domain")
            if p.username or p.password or not (p.hostname == domain or (p.hostname or "").endswith("." + domain)):
                raise ValidationError("Lead URL must belong to the declared platform without credentials")
        method = raw["discovery_method"]
        if method not in {"web_index", "local_public_search", "authorized_import", "browser_ui", "official_api", "official_site"}:
            raise ValidationError("Unknown discovery_method")
        data = {"provider": provider, "url": url, "title": _text(raw["title"], "title"),
                "discovered_at": _date(raw["discovered_at"], "discovered_at"), "discovery_method": method,
                "availability": "unknown", "evidence_level": "lead_only"}
        for key in ("company", "location", "summary", "query", "source_verified_label", "index_crawled_label", "salary", "education", "experience"):
            value = raw.get(key, "")
            if not isinstance(value, str) or len(value) > 2000:
                raise ValidationError(f"{key} must be text of at most 2000 characters")
            data[key] = value.strip()
        if method == "browser_ui":
            state = raw.get("access_state")
            if state not in {"visible_preview", "full_detail"}:
                raise ValidationError("Browser lead requires access_state visible_preview or full_detail")
            data["access_state"] = state
        checked.append(data)
    result = {"added": 0, "updated": 0, "duplicate": 0, "skipped_older": 0, "lead_ids": []}
    with connect() as db:
        ensure_schema(db)
        for data in checked:
            row = db.execute("SELECT * FROM search_leads WHERE provider=? AND url=?", (data["provider"], data["url"])).fetchone()
            if row is None:
                cursor = db.execute("INSERT INTO search_leads(provider,url,data,discovered_at,updated_at) VALUES (?,?,?,?,?)",
                                    (data["provider"], data["url"], serialize(data), data["discovered_at"], now()))
                lid = cursor.lastrowid
                result["added"] += 1
            else:
                lid = row["id"]
                old = deserialize(row["data"])
                if data["discovered_at"] < old["discovered_at"]:
                    if skip_older:
                        result["skipped_older"] += 1
                        result["lead_ids"].append(lid)
                        continue
                    raise ValidationError("Older lead observation cannot overwrite a newer one")
                compare = lambda d: {k: v for k, v in d.items() if k != "discovered_at"}
                result["duplicate" if compare(data) == compare(old) else "updated"] += 1
                db.execute("UPDATE search_leads SET data=?,updated_at=? WHERE id=?", (serialize(data), now(), lid))
            audit(db, "lead.observed", "search_leads", lid, data["provider"])
            result["lead_ids"].append(lid)
    return result


def _limit(limit):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValidationError("limit must be 1..100")


def list_leads(provider=None, limit=20):
    _limit(limit)
    if provider is not None and provider not in CHANNELS:
        raise ValidationError("Unknown provider")
    with connect() as db:
        ensure_schema(db)
        sql = "SELECT * FROM search_leads"
        args = []
        if provider:
            sql += " WHERE provider=?"
            args.append(provider)
        args.append(limit)
        return [{"id": r["id"], "job_id": r["job_id"], **deserialize(r["data"])}
                for r in db.execute(sql + " ORDER BY id DESC LIMIT ?", args)]


def promote_lead(lead_id, data):
    """Accept an explicitly reviewed full JD; indexed snippets remain leads."""
    validate_dict(data, ["title", "company", "description", "url", "read_method", "retrieved_at"])
    if data.get("content_complete") is not True:
        raise ValidationError("Promotion requires the complete JD, not search snippets")
    if data["read_method"] not in {"local_public_page", "authorized_page_read", "user_copy", "browser_ui", "official_site_read"}:
        raise ValidationError("Use a verified page read or user-supplied JD")
    if data["read_method"] == "browser_ui" and data.get("access_state") != "full_detail":
        raise ValidationError("Browser promotion requires full_detail; login-gated previews cannot be full JDs")
    _text(data["description"], "description", 100000)
    _date(data["retrieved_at"], "retrieved_at")
    with connect() as db:
        ensure_schema(db)
        row = db.execute("SELECT * FROM search_leads WHERE id=?", (lead_id,)).fetchone()
        if row is None:
            raise ValidationError("Lead not found")
        lead = deserialize(row["data"])
    url = clean_url(data["url"])
    if url != lead["url"]:
        raise ValidationError("JD URL must match the specific lead; create a detail-page lead first")
    if lead["provider"] == "boss" and "/job_detail/" not in urlsplit(url).path:
        raise ValidationError("BOSS listing pages cannot be promoted as a single vacancy")
    if lead["provider"] == "zhilian" and "/jobdetail/" not in urlsplit(url).path:
        raise ValidationError("Zhilian listing pages cannot be promoted as a single vacancy")
    record = dict(data, source=lead["provider"], source_id=url, url=url,
                  discovery_lead_id=lead_id, evidence_level="full_jd", availability=data.get("availability", "unknown"))
    # Aggregate and indexed pages cannot prove that the original employer is hiring.
    if lead["provider"] in {"zhiye", "careerjet", "jobui"}:
        record["availability"] = "unknown"
    # An employer's own posting page is the authoritative source for this vacancy.
    if lead["provider"] == "official":
        record["availability"] = "listed"
    result = sources.import_records([record])
    job_id = result["job_ids"][0]
    with connect() as db:
        ensure_schema(db)
        db.execute("UPDATE search_leads SET job_id=?,updated_at=? WHERE id=?", (job_id, now(), lead_id))
        audit(db, "lead.promoted", "search_leads", lead_id, f"job={job_id}")
    return {"lead_id": lead_id, "job_id": job_id, "import": result,
            "next_command": f"jobs card --id {job_id}"}


def search_local(query, location="", provider="zhiye", limit=10, refresh=False):
    _limit(limit)
    _text(query, "query", 120)
    registry = route_registry()
    if provider == "liepin":
        if not extension_enabled("liepin"):
            meta = OPTIONAL_EXTENSIONS["liepin"]
            return {"provider": "liepin", "executed": False, "status": "EXTENSION_DISABLED",
                    "reason": "该渠道作为可选扩展发布，默认不加载，也不会发起任何网络请求。",
                    "terms": meta["terms"],
                    "module": meta["module"],
                    "enable_with": f"设置环境变量 {meta['env']}=1 后重试",
                    "readme": "docs/LIEPIN_INTEGRATION.md"}
        from .extras.liepin import search
        result = search(query, location, limit, refresh)
        if result.get("status") != "SEARCH_VERIFIED":
            return result
        imported = import_leads(result.pop("records"), skip_older=True)
        with connect() as db:
            stored = [{"id": lid, **deserialize(db.execute("SELECT data FROM search_leads WHERE id=?", (lid,)).fetchone()["data"])}
                      for lid in imported["lead_ids"]]
        return {**result, "import": imported, "leads": stored, "imported": len(stored), "availability": "unknown"}
    if provider != "zhiye":
        if provider not in registry:
            raise ValidationError("Unknown provider")
        if provider in {"boss", "zhilian"}:
            return browser_plan(query, location, provider, limit)
        if provider == "official":
            return {"provider": "official", "executed": False, "status": "OFFICIAL_URL_REQUIRED",
                    "reason": CHANNELS["official"]["note"],
                    "next_command": 'official fetch --url "<单岗页面URL>" --company "<公司>"',
                    "plan": search_plan(query, location, ["official"])}
        meta = registry[provider]
        return {"provider": provider, "executed": False, "status": meta.get("mode", "manual_public_search"),
                "reason": meta.get("note", "需要人工读取并授权导入"),
                "route": channel_route(provider, query, location) if provider in CHANNELS else {"provider": provider, "access": meta.get("access", "catalog"), "entry_url": meta.get("search_entry", ""), "executed": False},
                "plan": search_plan(query, location, [provider])}

    from .public_search import search_zhiye
    result = search_zhiye(query, location=location, limit=limit, refresh=refresh)
    records = [{**r, "provider": provider, "discovered_at": result["fetched_at"],
                "discovery_method": "local_public_search", "query": query} for r in result["records"]]
    imported = import_leads(records, skip_older=True)
    # An older query cache must not overwrite or display obsolete stored facts.
    with connect() as db:
        stored = [deserialize(db.execute("SELECT data FROM search_leads WHERE id=?", (lid,)).fetchone()["data"])
                  for lid in imported["lead_ids"]]
    return {"provider": provider, "executed": True, "cache_hit": result["cache_hit"],
            "fetched_at": result["fetched_at"], "search_url": result["search_url"], "import": imported,
            "has_more": result.get("has_more", False), "scope": "first_public_result_page",
            "leads": [{"id": lid, "title": r["title"], "company": r.get("company", ""), "location": r.get("location", ""),
                       "url": r["url"], "source_verified_label": r.get("source_verified_label", ""),
                       "discovered_at": r["discovered_at"]}
                      for lid, r in zip(imported["lead_ids"], stored)], "availability": "unknown",
            "next_command": f"leads fetch --id {imported['lead_ids'][0]}" if imported["lead_ids"] else ""}


def fetch_lead(lead_id, refresh=False):
    with connect() as db:
        ensure_schema(db)
        row = db.execute("SELECT * FROM search_leads WHERE id=?", (lead_id,)).fetchone()
        if row is None:
            raise ValidationError("Lead not found")
        lead = deserialize(row["data"])
    if lead["provider"] != "zhiye":
        raise ValidationError("This channel requires an authorized JD import; automatic detail fetch is unavailable")
    from .public_search import fetch_zhiye_detail
    record = fetch_zhiye_detail(lead["url"], refresh=refresh)
    return promote_lead(lead_id, dict(record, content_complete=True, read_method="local_public_page"))


def shortlist(query, location="", exclude="", limit=10):
    """Local lexical shortlist only. It never emits fit grades or probabilities."""
    _limit(limit)
    terms = _text(query, "query", 120).casefold().split()
    excluded = exclude.casefold().split()
    with connect() as db:
        matches = []
        for row in db.execute("SELECT * FROM jobs"):
            job = deserialize(row["data"])
            title = job["title"].casefold()
            corpus = " ".join(str(job.get(k, "")) for k in ("title", "company", "description", "location")).casefold()
            if job.get("availability") == "closed" or (location and location.casefold() not in str(job.get("location", "")).casefold()):
                continue
            if any(term in corpus for term in excluded):
                continue
            hit = [term for term in terms if term in corpus]
            if not hit:
                continue
            score = sum(3 if term in title else 1 for term in hit)
            matches.append({"job_id": row["id"], "title": job["title"], "company": job["company"],
                            "location": job.get("location", ""), "url": job.get("url", ""), "matched_terms": hit,
                            "lexical_score": score, "availability": job.get("availability", "unknown"),
                            "freshness": sources.freshness(job)["status"]})
    matches.sort(key=lambda r: (-r["lexical_score"], -r["job_id"]))
    return {"method": "local_lexical_filter_not_candidate_fit", "matched": len(matches), "results": matches[:limit]}
