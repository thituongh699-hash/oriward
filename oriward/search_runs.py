"""Auditable search attempts and local Markdown reports (standard library only).

The module records observations; it does not search, authenticate, assess fit or
infer employer dates. Every planned run starts with a report, including routes
which were never executed. Only allowlisted summaries enter the report/store.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .db import connect, database_path, deserialize, now, serialize
from .services import ValidationError

STATUSES = {"success", "failed", "auth_required", "not_connected", "not_attempted", "zero_results"}
LABELS = {"success": "成功", "failed": "失败", "auth_required": "需登录/验证",
          "not_connected": "未接入", "not_attempted": "未尝试", "zero_results": "确认零结果"}
COUNT_KEYS = ("leads", "full_jds", "imported", "deduplicated")
SCOPE_KEYS = {"query", "companies", "roles", "location", "cities", "keywords", "filters",
              "time_window", "requested_limit", "board", "source_url", "company", "limit"}
CANDIDATE_KEYS = {"id", "lead_id", "job_id", "provider", "source", "company", "title", "location", "url",
                  "core_tasks", "fit_reason", "uncertainties", "evidence_level", "published_at", "updated_at",
                  "deadline", "start_date", "duration", "application_url", "apply_url", "retrieved_at",
                  "discovered_at", "imported_at", "source_verified_label", "time_sources", "availability",
                  "suggested_apply_date", "priority_reason", "next_action"}


def _text(value, name, limit=1000, *, required=False):
    if not isinstance(value, str) or len(value.strip()) > limit or (required and not value.strip()):
        raise ValidationError(f"{name} must be text of at most {limit} characters")
    return value.strip()


def _object(value, name, max_chars=16000):
    if not isinstance(value, dict) or len(serialize(value)) > max_chars:
        raise ValidationError(f"{name} must be an object of at most {max_chars} serialized characters")
    return value


def _count(value, name):
    if value is not None and (type(value) is not int or value < 0):
        raise ValidationError(f"{name} must be a nonnegative integer or null (unknown)")
    return value


def _load(conn, run_id):
    row = conn.execute("SELECT * FROM search_runs WHERE id=?", (run_id,)).fetchone()
    if row is None:
        raise ValidationError("Search run not found")
    return {"id": row["id"], "report_path": row["report_path"], **deserialize(row["data"])}


def _save(conn, run):
    data = {key: value for key, value in run.items() if key not in {"id", "report_path"}}
    conn.execute("UPDATE search_runs SET data=?,report_path=? WHERE id=?",
                 (serialize(data), run["report_path"], run["id"]))


def _cell(value, fallback="未披露"):
    if value is None or value == "" or value == [] or value == {}:
        return fallback
    if isinstance(value, dict):
        value = serialize(value)
    elif isinstance(value, list):
        value = "；".join(_cell(item) for item in value)
    # Escaping also prevents source content from becoming HTML or Markdown
    # instructions/links; original URLs remain checkable text.
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(
        ">", "&gt;").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _totals(run):
    receipts = list(run["channels"].values())
    values = {}
    for key in COUNT_KEYS:
        counts = [receipt["counts"].get(key) for receipt in receipts]
        # Failed, unexecuted and unreported routes never contribute invented 0s.
        values[key] = sum(counts) if counts and all(v is not None for v in counts) else None
    values.update(run.get("counts", {}))
    return values


def render_report(run):
    """Pure deterministic renderer: unavailable information stays unknown."""
    rows = [f"# 搜岗报告 · 批次 {run['id']}", "", f"开始：{run['created_at']}；结束：{_cell(run.get('finished_at'), '尚未结束')}。",
            "", "## 搜索范围", ""]
    if run["scope"]:
        rows.extend(f"- {_cell(key)}：{_cell(value, '未指定')}" for key, value in run["scope"].items())
    else:
        rows.append("未指定；不能据此宣称覆盖全部市场。")
    actual = [provider for provider, receipt in run["channels"].items() if receipt["attempted"]]
    rows += ["", f"计划渠道：{_cell(run['planned_channels'], '无')}。", f"实际执行渠道：{_cell(actual, '无')}。",
             "", "## 渠道执行", "", "| 渠道 | 状态 | 实际执行 | 原因/证据 | 覆盖范围 | 下一步 |", "|---|---|---|---|---|---|"]
    for provider, receipt in run["channels"].items():
        evidence = "{}；来源：{}；核对：{}".format(receipt.get("reason") or "未披露", receipt.get("source_url") or "未披露", receipt.get("observed_at") or "未核对")
        rows.append("| " + " | ".join(_cell(v) for v in (provider, LABELS[receipt["status"]],
                    "是" if receipt["attempted"] else "否", evidence, receipt.get("coverage"),
                    receipt.get("next_action"))) + " |")
        for round_no, attempt in enumerate(receipt.get("attempts", []), 1):
            rows.append(f"| {_cell(provider)} · 第{round_no}次 | {_cell(LABELS.get(attempt.get('status'), attempt.get('status')))} | {'是' if attempt.get('attempted') else '否'} | {_cell(attempt.get('reason'))}；{_cell(attempt.get('observed_at'))} | {_cell(attempt.get('coverage'))} | {_cell(attempt.get('next_action'))} |")
    rows += ["", "## 数量与覆盖", "", "| 范围 | 发现线索 | 完整JD | 导入岗位 | 去重后 |", "|---|---|---|---|---|"]
    for provider, receipt in run["channels"].items():
        rows.append("| " + " | ".join([_cell(provider)] + [_cell(receipt["counts"].get(key), "未知") for key in COUNT_KEYS]) + " |")
    totals = _totals(run)
    rows.append("| 合计 | " + " | ".join(_cell(totals.get(key), "未知") for key in COUNT_KEYS) + " |")
    rows += ["", "去重后默认只汇总各渠道内部去重数；跨渠道身份未核对。失败或未执行的数量为未知，不是零岗位。",
             _cell(run.get("coverage"), "覆盖完整性未核对；不得宣称全量检索。"), "", "## 候选岗位", ""]
    pipeline = run.get("pipeline")
    if isinstance(pipeline, dict):
        rows += ["## 流程阶段", "", f"当前阶段：{_cell(pipeline.get('stage'))}；扩词轮次：{pipeline.get('expansions', 0)}/2；修复轮次：{pipeline.get('repairs', 0)}/2。",
                 "阶段记录是调度状态；只有带实际执行回执的渠道尝试才代表搜索发生。", ""]
        for event in pipeline.get("history", []):
            rows.append(f"- {_cell(event.get('stage'))} / {_cell(event.get('status'))} / {_cell(event.get('provider'))}：{_cell(event.get('detail'))}")
        rows.append("")
    if not run["candidates"]:
        rows.append("本批次没有已记录候选；请结合渠道状态判断，不能将失败解释为零岗位。")
    for index, item in enumerate(run["candidates"], 1):
        rows += [f"### {index}. {_cell(item.get('company'))} · {_cell(item.get('title'))}", "",
                 f"地点：{_cell(item.get('location'))}；来源：{_cell(item.get('provider') or item.get('source'))}；证据层次：{_cell(item.get('evidence_level'), '待核对')}。",
                 f"原始链接：{_cell(item.get('url'))}",
                 f"核心任务：{_cell(item.get('core_tasks'), '尚未从完整JD提炼')}。",
                 f"与用户的关联：{_cell(item.get('fit_reason'), '尚未评估；关键词命中不等于适配')}。",
                 f"关键待核项：{_cell(item.get('uncertainties'), '需核对完整JD、资格、安排与开放状态')}。", "",
                 "| 时间/入口 | 已披露内容 |", "|---|---|"]
        for label, key in (("发布", "published_at"), ("更新", "updated_at"), ("雇主正式截止", "deadline"),
                           ("到岗", "start_date"), ("持续时长", "duration")):
            rows.append(f"| {label} | {_cell(item.get(key))} |")
        rows += [f"| 投递入口 | {_cell(item.get('application_url') or item.get('apply_url'))} |",
                 f"| 来源及核对时间 | {_cell(item.get('time_sources'), '未核对')} |",
                 f"| 抓取/发现时间（不是发布） | {_cell(item.get('retrieved_at') or item.get('discovered_at'))} |",
                 f"| 本地导入时间（不是发布） | {_cell(item.get('imported_at'))} |",
                 f"| 聚合站验证标签（不是雇主截止） | {_cell(item.get('source_verified_label'))} |",
                 f"| 建议准备/投递日期（个人计划） | {_cell(item.get('suggested_apply_date'), '未安排')} |", "",
                 f"优先原因：{_cell(item.get('priority_reason'), '未排序；需先分析适配与开放状态')}。",
                 f"下一步：{_cell(item.get('next_action'), '核对仍在招及申请入口，再读取相关经历并准备定向简历')}。", ""]
    rows += ["## 建议顺序与下一步", "", _cell(run.get("next_action"), "先处理渠道阻塞，核对完整JD与开放状态，再评估候选优先顺序。"), "",
             "截止未披露就保留未知；滚动招聘仅按来源原文记录。抓取、导入、建议投递日期均不充当雇主截止。", ""]
    return "\n".join(rows)


def _write_report(run):
    path = Path(run["report_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=path.parent, prefix=".search-report-", delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(render_report(run).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _persist(conn, run):
    _save(conn, run)
    _write_report(run)


def create_run(scope, planned_channels, *, output_dir=None):
    scope = _object(scope, "scope")
    if set(scope) - SCOPE_KEYS:
        raise ValidationError("Unknown scope fields; do not include personal experience details")
    if not isinstance(planned_channels, list) or not 1 <= len(planned_channels) <= 30:
        raise ValidationError("planned_channels must contain 1..30 providers")
    providers = list(dict.fromkeys(_text(item, "provider", 80, required=True) for item in planned_channels))
    stamp = now()
    run = {"scope": scope, "planned_channels": providers, "created_at": stamp, "finished_at": "",
           "channels": {p: {"status": "not_attempted", "attempted": False, "attempts": [], "reason": "尚无执行回执",
                             "coverage": "", "counts": {key: None for key in COUNT_KEYS}} for p in providers},
           "candidates": [], "counts": {}, "coverage": "", "next_action": ""}
    root = Path(output_dir).expanduser().resolve() if output_dir else database_path().parent / "search-reports"
    with connect() as conn:
        run_id = conn.execute("INSERT INTO search_runs(data,report_path,created_at) VALUES (?,?,?)",
                              (serialize(run), "", stamp)).lastrowid
        run.update(id=run_id, report_path=str(root / f"search-run-{run_id:06d}.md"))
        _persist(conn, run)
    return run


def show(run_id):
    with connect() as conn:
        return _load(conn, run_id)


def list_runs(limit=20):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValidationError("limit must be 1..100")
    with connect() as conn:
        return [{"id": row["id"], "report_path": row["report_path"], "created_at": row["created_at"]}
                for row in conn.execute("SELECT id,report_path,created_at FROM search_runs ORDER BY id DESC LIMIT ?", (limit,))]


def record_channel(run_id, provider, status, *, attempted=None, reason="", coverage="", counts=None,
                   next_action="", source_url="", observed_at=None):
    if status not in STATUSES:
        raise ValidationError("Unknown search channel status")
    provider = _text(provider, "provider", 80, required=True)
    if attempted is None:
        attempted = status in {"success", "failed", "zero_results"}
    if type(attempted) is not bool or (status in {"success", "zero_results"} and not attempted):
        raise ValidationError("Successful or zero-result observations require actual execution")
    counts = {} if counts is None else _object(counts, "counts", 1000)
    if set(counts) - set(COUNT_KEYS):
        raise ValidationError("Unknown count field")
    counts = {key: _count(counts.get(key), key) for key in COUNT_KEYS}
    if status == "zero_results":
        if not reason.strip():
            raise ValidationError("zero_results requires evidence of a successful empty search")
        if any(value not in (None, 0) for value in counts.values()):
            raise ValidationError("zero_results cannot contain positive counts")
        counts = dict.fromkeys(COUNT_KEYS, 0)
    if not attempted and any(v is not None for v in counts.values()):
        raise ValidationError("Unexecuted channels have unknown counts")
    receipt = {"status": status, "attempted": attempted, "counts": counts,
               "reason": _text(reason, "reason", 2000), "coverage": _text(coverage, "coverage", 2000),
               "next_action": _text(next_action, "next_action"), "source_url": _text(source_url, "source_url", 2000),
               "observed_at": _text(observed_at or now(), "observed_at", 100)}
    with connect() as conn:
        run = _load(conn, run_id)
        if provider not in run["planned_channels"]:
            raise ValidationError("Channel must be included in planned_channels")
        channel = run["channels"][provider]
        # Keep the legacy latest-receipt fields while preserving every round.
        channel.setdefault("attempts", []).append(dict(receipt))
        channel.update(receipt)
        _persist(conn, run)
    return receipt


def append_attempt(run_id, provider, status, **kwargs):
    """Append one round/query/repair receipt, retaining previous observations."""
    return record_channel(run_id, provider, status, **kwargs)


def add_candidates(run_id, candidates):
    if not isinstance(candidates, list) or len(candidates) > 1000:
        raise ValidationError("candidates must be an array of at most 1000 summaries")
    cleaned = []
    for item in candidates:
        _object(item, "candidate")
        item = dict(item)
        original_sources = item.get("time_sources")
        time_sources = dict(original_sources) if isinstance(original_sources, dict) else (
            {"provided": original_sources} if original_sources else {})
        for target, source in (("deadline", "valid_through"), ("published_at", "listed_at")):
            if not item.get(target) and item.get(source):
                item[target] = item[source]
                time_sources[target] = {"field": source, "url": item.get("url"),
                                        "checked_at": item.get("retrieved_at")}
        if time_sources:
            item["time_sources"] = time_sources
        cleaned.append({key: value for key, value in item.items() if key in CANDIDATE_KEYS})
    with connect() as conn:
        run = _load(conn, run_id)
        if len(run["candidates"]) + len(cleaned) > 1000:
            raise ValidationError("A search run supports at most 1000 candidate summaries")
        run["candidates"].extend(cleaned)
        _persist(conn, run)
    return {"run_id": run_id, "recorded": len(cleaned), "candidate_count": len(run["candidates"])}


def finish_run(run_id, *, counts=None, coverage="", next_action="", partial=False, reason=""):
    with connect() as conn:
        run = _load(conn, run_id)
        if "pipeline" in run:
            from .search_cli import next_packet
            complete = next_packet(run_id).get("stage") == "complete"
            if not complete and (partial is not True or not isinstance(reason, str) or not reason.strip()):
                raise ValidationError("Pipeline has pending stages; partial finish requires a reason")
            if partial:
                coverage = ("部分完成：" + reason.strip())
        if counts is not None:
            _object(counts, "counts", 1000)
            if set(counts) - set(COUNT_KEYS):
                raise ValidationError("Unknown count field")
            run["counts"] = {key: _count(value, key) for key, value in counts.items()}
        run.update(finished_at=now(), coverage=_text(coverage, "coverage", 2000),
                   next_action=_text(next_action, "next_action", 2000))
        _persist(conn, run)
    return {"run_id": run_id, "report_path": run["report_path"], "counts": _totals(run),
            "channels": run["channels"]}


def record_result(run_id, provider, result):
    """Normalize known CLI result shapes conservatively, retaining unknowns."""
    if not isinstance(result, dict):
        raise ValidationError("Search operation must return an object")
    status = str(result.get("status", ""))
    lower = status.lower()
    records = result.get("leads", result.get("records"))
    imported = result.get("import", result)
    job_ids = imported.get("job_ids") if isinstance(imported, dict) else None
    single_job_id = result.get("job_id") or (imported.get("job_id") if isinstance(imported, dict) else None)
    if single_job_id and records is None:
        job_ids = [single_job_id]
    if isinstance(job_ids, list) and records is None:
        # Import/sync commands return IDs rather than content. Read only those
        # current summaries; add_candidates removes long descriptions/evidence.
        records = []
        with connect() as conn:
            for job_id in dict.fromkeys(job_ids):
                row = conn.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
                if row:
                    records.append({"job_id": job_id, **deserialize(row["data"]), "evidence_level": "full_jd"})
    browser_verified = lower == "search_verified"
    executed = result.get("executed") is True or browser_verified or lower == "no_results"
    if ("job_ids" in result or "job_id" in result or
            isinstance(result.get("import"), dict) and ("job_ids" in result["import"] or "job_id" in result["import"]) or
            result.get("evidence_level") == "full_jd"):
        executed = True
    if lower in {"auth_required", "needs_login", "needs_verification"}:
        normalized = "auth_required"
    elif lower in {"extension_disabled", "not_connected"}:
        normalized = "not_connected"
    elif lower in {"request_failed", "response_requires_validation", "browser_error", "failed"}:
        normalized = "failed"
    elif executed:
        empty = lower == "no_results" or (job_ids == [] if job_ids is not None else isinstance(records, list) and not records)
        normalized = "zero_results" if empty else "success"
    else:
        normalized = "not_attempted"
    attempted = executed or result.get("request_sent") is True or normalized == "failed"
    counts = dict.fromkeys(COUNT_KEYS)
    if attempted:
        if isinstance(records, list):
            counts["leads"] = len(records)
            counts["full_jds"] = sum(item.get("evidence_level") == "full_jd" for item in records)
            # Search cards do not become imported vacancies merely because the
            # adapter stores them as leads. A lead import is separate accounting.
            if "leads" in result:
                counts["imported"] = 0
                counts["deduplicated"] = len(records)
        if browser_verified and type(result.get("visible_count")) is int:
            counts["leads"] = result["visible_count"]
        if isinstance(imported, dict) and "job_ids" in imported:
            ids = imported["job_ids"]
            counts["imported"] = sum(imported.get(key, 0) for key in ("added", "updated"))
            counts["deduplicated"] = len(set(ids))
            counts["full_jds"] = len(ids)
            executed = True
        elif single_job_id:
            counts.update(leads=1, full_jds=1,
                          imported=sum(imported.get(key, 0) for key in ("added", "updated")) if isinstance(imported, dict) else 0,
                          deduplicated=1)
            executed = True
        if result.get("evidence_level") == "full_jd":
            records = [result]
            counts.update(leads=1, full_jds=1, imported=0, deduplicated=1)
    reason = result.get("reason") or result.get("evidence") or result.get("note") or status
    if not isinstance(reason, str):
        reason = serialize(reason)
    if normalized == "zero_results" and not reason:
        reason = "Adapter returned a validated successful empty result list."
    retrieval = result.get("retrieval", {})
    coverage = result.get("scope")
    if not coverage and isinstance(retrieval, dict) and retrieval:
        coverage = "returned_count={}; available_count={}; requested_limit={}; only returned records covered".format(
            retrieval.get("returned_count", "unknown"), retrieval.get("available_count", "unknown"), retrieval.get("limit", "unknown"))
    record_channel(run_id, provider, normalized, attempted=attempted,
                   reason=reason[:2000], coverage=str(coverage or "覆盖范围未披露")[:2000], counts=counts,
                   source_url=str(result.get("search_url") or result.get("source_url") or result.get("url") or retrieval.get("request_url") or ""),
                   observed_at=result.get("observed_at") or result.get("fetched_at") or result.get("retrieved_at"),
                   next_action=str(result.get("next_command") or "核对渠道回执，必要时使用受支持的公开读取或授权导入")[:1000])
    if isinstance(records, list):
        summaries = []
        for item in records:
            if isinstance(item, dict):
                item = dict(item)
                if "listed_at" in item and "published_at" not in item:
                    item["published_at"] = item["listed_at"]
                item.setdefault("provider", provider)
                item.setdefault("evidence_level", "lead_only")
                summaries.append(item)
        add_candidates(run_id, summaries)


def execute_search(provider, scope, operation, *, output_dir=None, reraise=True):
    """Wrap one existing deterministic command; write a report even on failure.

    Returns the original result plus search_run_id/report_path. On exceptions the
    original exception is re-raised with these same attributes, unless reraise is
    false (which returns a structured failed receipt). No exception is called an
    empty successful search. Providers which only return plans stay unexecuted.
    """
    run = create_run(scope, [provider], output_dir=output_dir)
    try:
        result = operation()
        record_result(run["id"], provider, result)
    except Exception as exc:
        record_channel(run["id"], provider, "failed", reason=f"{type(exc).__name__}: {str(exc)[:1500]}",
                       next_action="检查报错与访问状态；修复后重试或选择其他已支持路线")
        finish_run(run["id"])
        if reraise:
            exc.search_run_id = run["id"]
            exc.report_path = run["report_path"]
            raise
        return {"status": "failed", "error": str(exc), "search_run_id": run["id"], "report_path": run["report_path"]}
    finish_run(run["id"])
    return {**result, "search_run_id": run["id"], "report_path": run["report_path"]}
