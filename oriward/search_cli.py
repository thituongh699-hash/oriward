"""Deterministic, receipt-driven search orchestration packets.

This module schedules work and records stage state; it does not operate a
browser or claim that a planned source was searched.
"""
from __future__ import annotations

from . import discovery, search_runs
from .db import connect, deserialize, serialize, now
from .services import ValidationError


def start(scope, providers=None, output_dir=None):
    registry = discovery.route_registry()
    chosen = providers or [key for key, route in registry.items() if route.get("enabled", True)]
    if any(key not in registry for key in chosen):
        raise ValidationError("Unknown search route")
    enabled = [key for key in chosen if registry.get(key, {}).get("enabled", True)]
    if not enabled:
        raise ValidationError("At least one enabled search route is required")
    run = search_runs.create_run(scope, enabled, output_dir=output_dir)
    plan = {"stage": "coverage", "history": [], "repairs_by_route": {}, "repair_actions": {}, "expansions": [],
            "max_repairs_per_route": 2, "query_history": [], "waiting_for_user": [],
            "catalogue": {"target_companies": 10, "deep_jds_per_company": 5, "max_pages": 5, "max_items": 200},
            "catalogue_pages": [], "companies": [], "company_scans": {}, "company_jds": {}, "directions": []}
    _write_plan(run["id"], plan)
    return {"run_id": run["id"], "stage": "coverage", "planned_channels": enabled,
            "executed": False, "next": next_packet(run["id"])}


def _read_plan(run_id):
    with connect() as db:
        row = db.execute("SELECT data,report_path FROM search_runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        raise ValidationError("Search run not found")
    return deserialize(row["data"]).get("pipeline", {"stage": "coverage", "history": [], "repairs_by_route": {}, "expansions": []})


def _write_plan(run_id, plan):
    with connect() as db:
        row = db.execute("SELECT data,report_path FROM search_runs WHERE id=?", (run_id,)).fetchone()
        data = deserialize(row["data"])
        data["pipeline"] = plan
        db.execute("UPDATE search_runs SET data=? WHERE id=?", (serialize(data), run_id))
        search_runs._write_report({"id": run_id, "report_path": row["report_path"], **data})


def _norm_query(value):
    return " ".join(str(value or "").casefold().split())


def _scope_key(scope):
    cities = scope.get("cities", [])
    if not isinstance(cities, list):
        raise ValidationError("cities must be an array")
    return "|".join(sorted({_norm_query(city) for city in [scope.get("location", ""), *cities] if _norm_query(city)}))


def record_stage(run_id, stage, detail, *, status="recorded"):
    plan = _read_plan(run_id)
    if stage in {"repair", "expansion"} and status == "attempted":
        raise ValidationError("Repair and expansion require a real source receipt via record_attempt")
    if stage == "catalogue-page":
        _record_catalogue_page(plan, detail)
    elif stage == "company-scan":
        _record_company_scan(plan, detail)
    elif stage == "company-jd":
        _record_company_jd(plan, detail)
    elif stage == "direction":
        _record_direction(plan, detail, search_runs.show(run_id)["scope"])
    elif stage not in {"company-catalogue", "partial", "complete"}:
        raise ValidationError("Unknown pipeline stage")
    plan.setdefault("history", []).append({"stage": stage, "status": status, "detail": detail, "at": now()})
    _write_plan(run_id, plan)
    return next_packet(run_id)


def record_attempt(run_id, provider, status, *, stage="coverage", query=None, refresh=False, **receipt):
    """Record an actual source observation; all rounds remain in attempt history."""
    run = search_runs.show(run_id)
    plan = _read_plan(run_id)
    query = query if query is not None else run["scope"].get("query", "")
    location = _scope_key(run["scope"])
    key = _norm_query(query) + "|" + location
    if stage not in {"coverage", "repair", "expansion"}:
        raise ValidationError("Attempt stage must be coverage, repair or expansion")
    route_repairs = plan.setdefault("repairs_by_route", {})
    repair_action = ""
    used_actions = plan.setdefault("repair_actions", {}).setdefault(provider, [])
    if stage == "expansion":
        used = {item["query_key"] for item in plan.get("expansions", [])}
        base_key = _norm_query(run["scope"].get("query", "")) + "|" + location
        if not _norm_query(query) or key == base_key or key in used or len(used) >= 2:
            raise ValidationError("Expansion query must be distinct; at most two are allowed")
    if stage == "repair":
        repair_action = receipt.pop("repair_action", "")
        if not repair_action or repair_action in used_actions:
            raise ValidationError("Repair needs a new repair_action for this route")
        if route_repairs.get(provider, 0) >= 2:
            raise ValidationError("At most two repair attempts per route are allowed")
    day = now()[:10]
    reused = [(run_id, entry) for entry in plan.get("query_history", []) if entry["provider"] == provider
              and entry["query_key"] == key and entry["date"] == day]
    with connect() as db:
        for row in db.execute("SELECT id,data FROM search_runs WHERE id<>? ORDER BY id DESC LIMIT 100", (run_id,)):
            old_plan = deserialize(row["data"]).get("pipeline", {})
            reused.extend((row["id"], entry) for entry in old_plan.get("query_history", [])
                          if entry.get("provider") == provider and entry.get("query_key") == key and entry.get("date") == day)
    if reused and not refresh and stage != "repair":
        source_run_id, source = max(reused, key=lambda pair: pair[1].get("at", ""))
        if source.get("attempted") and source.get("status") in {"success", "zero_results"}:
            reuse_receipt = {"status": "not_attempted", "attempted": False,
                "counts": {key: None for key in search_runs.COUNT_KEYS},
                "reason": f"同日复用批次 {source_run_id} 的来源回执；未发起网络请求",
                "coverage": "缓存回执复用", "next_action": "仅在用户要求刷新时重试",
                "source_url": "", "observed_at": now(), "reused_from": source_run_id,
                "reused_status": source["status"]}
            with connect() as db:
                current = search_runs._load(db, run_id)
                current["channels"][provider].setdefault("attempts", []).append(reuse_receipt)
                search_runs._persist(db, current)
            item = {"provider": provider, "query": query, "query_key": key, "date": day,
                    "refresh": False, "status": source["status"], "attempted": True, "stage": stage,
                    "reused": True, "source_run_id": source_run_id, "at": now()}
            plan.setdefault("query_history", []).append(item)
            if stage == "expansion" and not any(exp.get("query_key") == key for exp in plan.setdefault("expansions", [])):
                plan["expansions"].append(item)
            plan.setdefault("history", []).append({"stage": stage, "status": "reused", "provider": provider,
                                                     "query": query, "at": now()})
            _write_plan(run_id, plan)
            return {"reused": True, "executed": False, "source_run_id": source_run_id,
                    "receipt": reuse_receipt, "next": next_packet(run_id)}
    result = search_runs.append_attempt(run_id, provider, status, **receipt)
    if result["attempted"] and stage == "repair":
        used_actions.append(repair_action)
    item = {"provider": provider, "query": query, "query_key": key, "date": day,
            "refresh": bool(refresh), "status": status, "attempted": result["attempted"], "stage": stage, "at": now()}
    plan.setdefault("query_history", []).append(item)
    plan.setdefault("history", []).append({"stage": stage, "status": "attempted" if result["attempted"] else "waiting",
                                            "provider": provider, "query": query, "at": now()})
    if result["attempted"] and stage == "repair":
        route_repairs[provider] = route_repairs.get(provider, 0) + 1
    if result["attempted"] and stage == "expansion":
        plan.setdefault("expansions", []).append(item)
    if result["status"] == "auth_required":
        waiting = plan.setdefault("waiting_for_user", [])
        if provider not in waiting:
            waiting.append(provider)
        discovery.request_route_assistance(provider)
    _write_plan(run_id, plan)
    return {"receipt": result, "next": next_packet(run_id)}


def _record_catalogue_page(plan, detail):
    if not isinstance(detail, dict) or not isinstance(detail.get("companies"), list) or not isinstance(detail.get("items"), list):
        raise ValidationError("catalogue-page requires companies and items arrays")
    company_name = detail.get("company")
    if not company_name:
        raise ValidationError("catalogue-page requires a company name")
    pages = plan.setdefault("catalogue_pages", [])
    prior = [page for page in pages if page["company"] == company_name]
    if len(prior) >= 5 or sum(p["item_count"] for p in prior) + len(detail["items"]) > 200:
        raise ValidationError("Catalogue cap is five pages and 200 total items per company")
    for company in detail["companies"]:
        if not isinstance(company, dict) or not all(company.get(k) for k in ("name", "reason", "reason_url", "local_presence_url")):
            raise ValidationError("Company needs sourced reason and local presence")
        company["reason_url"] = discovery.clean_url(company["reason_url"])
        company["local_presence_url"] = discovery.clean_url(company["local_presence_url"])
    pages.append({"company": company_name, "item_count": len(detail["items"]), "source_url": detail.get("source_url", ""), "at": now()})
    known = {c["name"] for c in plan.setdefault("companies", [])}
    additions = [c for c in detail["companies"] if c["name"] not in known]
    if len(known) + len(additions) > 10:
        raise ValidationError("Company catalogue target is capped at ten entries")
    plan["companies"].extend(additions)


def _record_company_scan(plan, detail):
    if not isinstance(detail, dict) or not detail.get("company") or detail.get("status") not in {"complete", "incomplete"} or not detail.get("reason") or not detail.get("source_url") or detail.get("continuation") not in {"exhausted", "more_available", "blocked", "unknown"}:
        raise ValidationError("Company scan needs status, reason, source URL and continuation state")
    if not any(c["name"] == detail["company"] for c in plan.get("companies", [])):
        raise ValidationError("Company must first be in the sourced catalogue")
    detail["source_url"] = discovery.clean_url(detail["source_url"])
    if not isinstance(detail.get("pages", 0), int) or not 0 <= detail.get("pages", 0) <= 5:
        raise ValidationError("Company scan pages must be 0..5")
    if not isinstance(detail.get("items", 0), int) or not 0 <= detail.get("items", 0) <= 200:
        raise ValidationError("Company scan items must be 0..200")
    if detail["status"] == "complete" and (detail.get("pages", 0) < 1 or detail.get("items", 0) < 1):
        raise ValidationError("A complete company scan needs an observed page and item")
    plan.setdefault("company_scans", {})[detail["company"]] = {**detail, "at": now()}


def _record_direction(plan, detail, scope):
    if not isinstance(detail, dict) or not detail.get("name") or not isinstance(detail.get("job_ids"), list) or not detail["job_ids"] or not isinstance(detail.get("experience_ids"), list) or not detail["experience_ids"]:
        raise ValidationError("Direction needs a name, complete-JD job_ids and experience_ids")
    with connect() as db:
        target_cities = scope.get("cities", [])
        if scope.get("location"):
            target_cities = [*target_cities, scope["location"]]
        for job_id in detail["job_ids"]:
            row = db.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row or not _is_complete_job(deserialize(row["data"])):
                raise ValidationError("Direction validation requires stored complete-JD jobs")
            if target_cities:
                location = str(deserialize(row["data"]).get("location", ""))
                if not any(str(city).casefold() in location.casefold() for city in target_cities):
                    raise ValidationError("Direction JD evidence must match a target city")
    from . import experience_library
    for experience_id in detail["experience_ids"]:
        try:
            experience = experience_library.get(experience_id)
        except ValueError as exc:
            raise ValidationError("Direction requires a current experience that does not need review") from exc
        if experience.get("status") != "current" or experience.get("needs_review"):
            raise ValidationError("Direction requires a current experience that does not need review")
    directions = plan.setdefault("directions", [])
    if any(d["name"] == detail["name"] for d in directions) or len(directions) >= 5:
        raise ValidationError("Direction names must be unique; maximum is five")
    directions.append({**detail, "status": "jd_evidence_checked", "at": now()})


def _record_company_jd(plan, detail):
    if not isinstance(detail, dict) or not detail.get("company") or not detail.get("job_id"):
        raise ValidationError("company-jd needs company and job_id")
    if not any(c["name"] == detail["company"] for c in plan.get("companies", [])):
        raise ValidationError("Company must first be recorded with sourced catalogue evidence")
    with connect() as db:
        row = db.execute("SELECT data FROM jobs WHERE id=?", (detail["job_id"],)).fetchone()
    job = deserialize(row["data"]) if row else {}
    if not row or not _is_complete_job(job):
        raise ValidationError("Company JD must reference an imported complete JD")
    if job.get("company", "").casefold() != detail["company"].casefold():
        raise ValidationError("Company JD must belong to the catalogued company")
    jds = plan.setdefault("company_jds", {})
    values = jds.setdefault(detail["company"], [])
    if detail["job_id"] in values:
        raise ValidationError("Company JD is already recorded")
    if len(values) >= 5:
        raise ValidationError("At most five complete JDs per company")
    values.append(detail["job_id"])


def _is_complete_job(job):
    # Imported job records require a description, employer and source URL. A
    # promoted lead additionally carries the explicit full_jd evidence label.
    return (job.get("evidence_level") == "full_jd" or
            all(isinstance(job.get(key), str) and job[key].strip() for key in ("title", "company", "description", "url")))


def next_packet(run_id):
    run = search_runs.show(run_id)
    plan = _read_plan(run_id)
    for provider in run["planned_channels"]:
        receipt = run["channels"][provider]
        if not receipt.get("attempts") or all(a.get("status") == "not_attempted" and not a.get("reused_from")
                                                for a in receipt.get("attempts", [])):
            return {"stage": "coverage", "provider": provider, "query": run["scope"].get("query", ""),
                    "location": run["scope"].get("location", ""), "executed": False,
                    "instruction": "执行该来源一次并写真实回执；计划不算尝试。"}
    pending = [p for p in run["planned_channels"] if run["channels"][p]["status"] in {"failed", "not_connected"}
               and plan.get("repairs_by_route", {}).get(p, 0) < 2]
    if pending:
        provider = pending[0]
        return {"stage": "repair", "provider": provider,
                "remaining_repair_rounds": 2-plan.get("repairs_by_route", {}).get(provider, 0),
                "executed": False, "instruction": "技术失败可针对本路线修复；每次都需新的真实回执。"}
    if len(plan.get("expansions", [])) < 2:
        idx = len(plan.get("expansions", []))
        return {"stage": "expansion", "round": idx+1,
                "query_family": "alias_or_tasks" if idx == 0 else "industry_scenario_company_tools",
                "query": "根据证据生成不同检索词", "executed": False,
                "cache_policy": {"same_day_query": "reuse_unless_refresh", "candidate_detail_hours": 72,
                                 "resume_candidate_hours": 24, "company_catalogue_days": 7},
                "instruction": "扩词必须实际搜索并用真实渠道回执记录，query 须不同于已有检索词。"}
    companies = plan.get("companies", [])
    if len(companies) < 10:
        return {"stage": "company_catalogue", "recorded_companies": len(companies),
                "pages_recorded": len(plan.get("catalogue_pages", [])), "targets": plan["catalogue"],
                "freshness_days": 7,
                "executed": False, "instruction": "公司理由和本地存在必须附来源；不足10家可标记覆盖不完整。"}
    unscanned = [c["name"] for c in companies if c["name"] not in plan.get("company_scans", {})]
    if unscanned:
        return {"stage": "company_scan", "company": unscanned[0], "scanned": len(plan.get("company_scans", {})),
                "limit": {"max_pages": 5, "max_items": 200, "max_complete_jds": 5}, "executed": False,
                "continuation": "record more_available, exhausted, blocked or unknown from the actual source",
                "instruction": "记录该公司的职位目录是否完整、查询范围和继续加载状态；不完整也需原因。"}
    directions = plan.get("directions", [])
    if len(directions) < 3:
        return {"stage": "directions", "recorded": len(directions), "required": "3..5",
                "candidate_freshness_hours": 24, "detail_freshness_hours": 72,
                "executed": False, "instruction": "方向假设需绑定真实完整JD job_id 与经验ID。"}
    incomplete = [name for name, scan in plan.get("company_scans", {}).items()
                  if scan.get("status") != "complete" or scan.get("continuation") != "exhausted"]
    if incomplete:
        return {"stage": "partial_coverage", "companies": incomplete, "executed": False,
                "instruction": "目录尚有覆盖缺口；继续检索或用 partial=true 和原因收尾，不得称为全部完成。"}
    return {"stage": "complete", "complete": True, "executed": False}


def finish(run_id, *, partial=False, reason=""):
    packet = next_packet(run_id)
    if packet["stage"] != "complete" and (not partial or not reason.strip()):
        raise ValidationError("Pipeline has pending stages; partial finish requires a reason")
    return search_runs.finish_run(run_id, partial=partial, reason=reason,
                                  coverage="全部要求阶段均有本地记录",
                                  next_action="按报告中的阻塞/待办继续" if partial else "复核完整JD与方向证据")


def dispatch(action, **kwargs):
    """Parent CLI integration point: start, next, record-stage, record, finish."""
    if action == "start":
        return start(kwargs["scope"], kwargs.get("providers"), kwargs.get("output_dir"))
    if action == "next":
        return next_packet(kwargs["run_id"])
    if action == "record-stage":
        return record_stage(kwargs["run_id"], kwargs["stage"], kwargs.get("detail", ""), status=kwargs.get("status", "recorded"))
    if action == "record":
        return record_attempt(kwargs["run_id"], kwargs["provider"], kwargs["status"], **kwargs.get("receipt", {}))
    if action == "finish":
        return finish(kwargs["run_id"], partial=kwargs.get("partial", False), reason=kwargs.get("reason", ""))
    raise ValidationError("Unknown search pipeline action")
